import { randomUUID } from "node:crypto";
import { createJob, getJob, storageConfig, supabaseConfig, supabaseRequest, updateJob } from "./_supabase.js";
import { authenticateUploadRequest } from "./_upload-auth.js";

export const config = {
  api: { bodyParser: { sizeLimit: "128kb" } },
  maxDuration: 30,
};

const ALLOWED_TASKS = new Set(["voiceover", "song_replace", "clip_convert", "rvc_train"]);
const AUDIO_EXTENSION = /\.(wav|mp3|m4a|aac|flac|ogg|aiff|aif)$/i;
const DEFAULT_MAX_DIRECT_UPLOAD_BYTES = 512 * 1024 * 1024;
const DEFAULT_MAX_DIRECT_BATCH_BYTES = 1024 * 1024 * 1024;
const MAX_FILES_PER_BATCH = 7;

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

function boundedLimit(value, fallback) {
  const parsed = Number(value || fallback);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function jobType(taskMode) {
  return taskMode === "voiceover"
    ? "local_worker_voiceover"
    : taskMode === "rvc_train"
      ? "local_worker_rvc_train"
      : "local_worker_audio_replace";
}

function workerMode(taskMode) {
  return taskMode === "song_replace" ? "song" : taskMode === "clip_convert" ? "clip" : "bed";
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
        error: "Direct resumable uploads require Supabase Storage. Local storage mode uses the compatibility server upload path.",
      });
    }

    const principal = authenticateUploadRequest(req);
    if (!principal) {
      return sendJson(res, 401, {
        ok: false,
        error: "Direct uploads require an authorized access key. Enter the configured upload/ElevenLabs key and retry.",
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

    const item = body.file || {};
    const role = item?.role === "target" ? "target" : "voice";
    const clientId = String(item?.clientId || `${role}:0`).slice(0, 80);
    const name = cleanName(item?.name);
    const size = Number(item?.size || 0);
    const type = String(item?.type || "application/octet-stream").slice(0, 120);
    if (!AUDIO_EXTENSION.test(name)) return sendJson(res, 400, { ok: false, error: `Unsupported audio file: ${name}` });
    if (!Number.isFinite(size) || size <= 0) return sendJson(res, 400, { ok: false, error: `Invalid audio size for ${name}` });
    if (role === "target" && !["song_replace", "clip_convert"].includes(taskMode)) {
      return sendJson(res, 400, { ok: false, error: "This task does not accept a target song/audio file." });
    }

    const maxObjectBytes = boundedLimit(process.env.MAX_DIRECT_UPLOAD_BYTES, DEFAULT_MAX_DIRECT_UPLOAD_BYTES);
    const maxBatchBytes = boundedLimit(process.env.MAX_DIRECT_UPLOAD_BATCH_BYTES, DEFAULT_MAX_DIRECT_BATCH_BYTES);
    if (size > maxObjectBytes) {
      return sendJson(res, 413, {
        ok: false,
        error: `${name} exceeds the direct-upload object ceiling of ${Math.round(maxObjectBytes / (1024 * 1024))} MB.`,
      });
    }

    let uploadJob = null;
    const uploadSessionId = String(body.uploadSessionId || "");
    if (uploadSessionId) {
      uploadJob = await getJob(uploadSessionId);
      if (!uploadJob || uploadJob.status !== "uploading") {
        return sendJson(res, 409, { ok: false, error: "Upload session is missing, expired, or already finalized." });
      }
      const report = uploadJob.report || {};
      if (report.uploadPrincipal !== principal || report.taskMode !== taskMode) {
        return sendJson(res, 403, { ok: false, error: "Upload session authorization mismatch." });
      }
    } else {
      uploadJob = await createJob({
        status: "uploading",
        job_type: jobType(taskMode),
        voice_name: cleanName(body.voiceName || "Authorized Voice"),
        engine: "awaiting upload",
        permission_confirmed: true,
        input_files: [],
        text: String(body.text || "").trim(),
        mode: workerMode(taskMode),
        settings: {
          taskMode,
          qualityTarget: String(body.qualityTarget || "draft"),
        },
        report: {
          queuedBy: "vercel",
          storageProvider: "supabase",
          uploadMode: "direct_resumable",
          uploadPrincipal: principal,
          taskMode,
          stagedBytes: 0,
          stagedFiles: 0,
          expectedUploads: [],
        },
      });
    }

    const report = uploadJob.report || {};
    const expectedUploads = Array.isArray(report.expectedUploads) ? [...report.expectedUploads] : [];
    let ticketMeta = expectedUploads.find((entry) => entry.clientId === clientId);
    if (ticketMeta) {
      if (ticketMeta.role !== role || ticketMeta.name !== name || Number(ticketMeta.size) !== size) {
        return sendJson(res, 409, { ok: false, error: "This upload slot was already reserved for a different file." });
      }
    } else {
      const stagedFiles = Number(report.stagedFiles || 0);
      const stagedBytes = Number(report.stagedBytes || 0);
      if (stagedFiles >= MAX_FILES_PER_BATCH) {
        return sendJson(res, 429, { ok: false, error: `Upload session is limited to ${MAX_FILES_PER_BATCH} files.` });
      }
      if (stagedBytes + size > maxBatchBytes) {
        return sendJson(res, 413, {
          ok: false,
          error: `Upload session exceeds the ${Math.round(maxBatchBytes / (1024 * 1024))} MB batch quota.`,
        });
      }

      const folder = role === "target" ? "target" : "voices";
      const safeName = name.replace(/\s+/g, "_");
      const objectPath = `queued/${uploadJob.id}/${folder}/${randomUUID()}-${safeName}`;
      ticketMeta = { clientId, role, name, type, size, path: objectPath };
      expectedUploads.push(ticketMeta);
      uploadJob = await updateJob(uploadJob.id, {
        report: {
          ...report,
          stagedFiles: stagedFiles + 1,
          stagedBytes: stagedBytes + size,
          expectedUploads,
        },
      }) || uploadJob;
    }

    // Mint the signed capability only when this specific file is about to start.
    // Repeated calls for the same clientId refresh the token for the same path.
    const token = await createSignedUploadToken(ticketMeta.path);
    const cfg = supabaseConfig();
    return sendJson(res, 200, {
      ok: true,
      provider: "supabase",
      bucket: cfg.bucket,
      endpoint: directStorageEndpoint(cfg.url),
      chunkSize: 6 * 1024 * 1024,
      uploadSessionId: uploadJob.id,
      ticket: { ...ticketMeta, token },
    });
  } catch (error) {
    return sendJson(res, 500, { ok: false, error: error.message || String(error) });
  }
}
