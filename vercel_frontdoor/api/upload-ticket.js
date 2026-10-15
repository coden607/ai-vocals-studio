import { randomUUID } from "node:crypto";
import { storageConfig, supabaseConfig, supabaseRequest } from "./_supabase.js";

export const config = {
  api: { bodyParser: { sizeLimit: "128kb" } },
  maxDuration: 30,
};

const ALLOWED_TASKS = new Set(["voiceover", "song_replace", "clip_convert", "rvc_train"]);
const AUDIO_EXTENSION = /\.(wav|mp3|m4a|aac|flac|ogg|aiff|aif)$/i;
const DEFAULT_MAX_DIRECT_UPLOAD_BYTES = 1024 * 1024 * 1024;

function sendJson(res, status, payload) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Cache-Control", "no-store");
  res.end(JSON.stringify(payload));
}

function cleanName(value) {
  return String(value || "audio.wav")
    .replace(/[^A-Za-z0-9_. -]+/g, "")
    .trim()
    .slice(0, 120) || "audio.wav";
}

function encodeObjectPath(value) {
  return String(value || "")
    .split("/")
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

function directStorageEndpoint(supabaseUrl) {
  const parsed = new URL(supabaseUrl);
  if (parsed.hostname.endsWith(".supabase.co")) {
    const projectRef = parsed.hostname.slice(0, -".supabase.co".length);
    if (projectRef) {
      return `${parsed.protocol}//${projectRef}.storage.supabase.co/storage/v1/upload/resumable`;
    }
  }
  return `${supabaseUrl.replace(/\/+$/, "")}/storage/v1/upload/resumable`;
}

async function createSignedUploadToken(objectPath) {
  const cfg = supabaseConfig();
  const response = await supabaseRequest(
    `/storage/v1/object/upload/sign/${encodeURIComponent(cfg.bucket)}/${encodeObjectPath(objectPath)}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-upsert": "false",
      },
      body: "{}",
    },
  );
  const payload = await response.json();
  const token = new URL(String(payload?.url || ""), "https://storage.local").searchParams.get("token");
  if (!token) throw new Error("Supabase did not return a signed upload token.");
  return token;
}

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return sendJson(res, 405, { ok: false, error: "Method not allowed" });
  }

  try {
    const storage = storageConfig();
    if (storage.provider !== "supabase") {
      return sendJson(res, 409, {
        ok: false,
        error: "Direct resumable uploads require Supabase Storage. Local storage mode uses the legacy server upload path.",
      });
    }

    const body = typeof req.body === "string" ? JSON.parse(req.body) : (req.body || {});
    const taskMode = String(body.taskMode || "voiceover");
    if (!ALLOWED_TASKS.has(taskMode)) {
      return sendJson(res, 400, { ok: false, error: "Unsupported upload task mode." });
    }
    if (!body.permission) {
      return sendJson(res, 400, { ok: false, error: "Permission confirmation is required before uploading voice material." });
    }

    const requested = Array.isArray(body.files) ? body.files : [];
    if (!requested.length || requested.length > 7) {
      return sendJson(res, 400, { ok: false, error: "Upload between 1 and 7 audio files per job." });
    }

    const configuredLimit = Number(process.env.MAX_DIRECT_UPLOAD_BYTES || DEFAULT_MAX_DIRECT_UPLOAD_BYTES);
    const maxBytes = Number.isFinite(configuredLimit) && configuredLimit > 0
      ? configuredLimit
      : DEFAULT_MAX_DIRECT_UPLOAD_BYTES;

    const normalized = requested.map((item, index) => {
      const role = item?.role === "target" ? "target" : "voice";
      const clientId = String(item?.clientId || `${role}:${index}`).slice(0, 80);
      const name = cleanName(item?.name);
      const size = Number(item?.size || 0);
      const type = String(item?.type || "application/octet-stream").slice(0, 120);
      if (!AUDIO_EXTENSION.test(name)) throw new Error(`Unsupported audio file: ${name}`);
      if (!Number.isFinite(size) || size <= 0) throw new Error(`Invalid audio size for ${name}`);
      if (size > maxBytes) {
        throw new Error(`${name} exceeds the configured direct-upload ceiling of ${Math.round(maxBytes / (1024 * 1024))} MB.`);
      }
      return { role, clientId, name, size, type };
    });

    const voiceFiles = normalized.filter((item) => item.role === "voice");
    const targetFiles = normalized.filter((item) => item.role === "target");
    if (!voiceFiles.length || voiceFiles.length > 6) {
      return sendJson(res, 400, { ok: false, error: "Upload 1 to 6 voice reference files." });
    }
    const requiresTarget = taskMode === "song_replace" || taskMode === "clip_convert";
    if (requiresTarget && targetFiles.length !== 1) {
      return sendJson(res, 400, { ok: false, error: "Exactly one target song/audio file is required." });
    }
    if (!requiresTarget && targetFiles.length) {
      return sendJson(res, 400, { ok: false, error: "This task does not accept a target song/audio file." });
    }

    const batchId = randomUUID();
    const cfg = supabaseConfig();
    const tickets = [];
    for (const item of normalized) {
      const folder = item.role === "target" ? "target" : "voices";
      const safeName = item.name.replace(/\s+/g, "_");
      const objectPath = `queued/${batchId}/${folder}/${randomUUID()}-${safeName}`;
      const token = await createSignedUploadToken(objectPath);
      tickets.push({
        clientId: item.clientId,
        role: item.role,
        name: item.name,
        type: item.type,
        size: item.size,
        path: objectPath,
        token,
      });
    }

    return sendJson(res, 200, {
      ok: true,
      provider: "supabase",
      bucket: cfg.bucket,
      endpoint: directStorageEndpoint(cfg.url),
      chunkSize: 6 * 1024 * 1024,
      batchId,
      tickets,
    });
  } catch (error) {
    return sendJson(res, 500, { ok: false, error: error.message || String(error) });
  }
}
