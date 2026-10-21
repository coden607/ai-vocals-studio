import { randomUUID } from "node:crypto";
import fs from "node:fs/promises";
import pathModule from "node:path";

const DEFAULT_BUCKET = "voiceovers";

function localRoot() {
  return pathModule.resolve(process.env.LOCAL_STORAGE_DIR || pathModule.join(process.cwd(), ".local_voiceover_storage"));
}

export function supabaseConfig() {
  const url = String(process.env.SUPABASE_URL || "").replace(/\/+$/, "");
  const key = String(process.env.SUPABASE_SERVICE_ROLE_KEY || "");
  let host = "";
  try {
    host = url ? new URL(url).host : "";
  } catch {
    host = "invalid-url";
  }
  return {
    enabled: Boolean(url && key),
    url,
    host,
    key,
    bucket: String(process.env.SUPABASE_STORAGE_BUCKET || DEFAULT_BUCKET),
  };
}

export function storageConfig() {
  const supabase = supabaseConfig();
  return {
    enabled: true,
    provider: supabase.enabled ? "supabase" : "local",
    localRoot: localRoot(),
    supabase,
  };
}

async function ensureLocalRoot() {
  const root = localRoot();
  await fs.mkdir(pathModule.join(root, "objects"), { recursive: true });
  return root;
}

async function readLocalJobs() {
  const root = await ensureLocalRoot();
  const jobsPath = pathModule.join(root, "jobs.json");
  try {
    return JSON.parse(await fs.readFile(jobsPath, "utf8"));
  } catch (error) {
    if (error?.code === "ENOENT") return [];
    throw error;
  }
}

async function writeLocalJobs(jobs) {
  const root = await ensureLocalRoot();
  const jobsPath = pathModule.join(root, "jobs.json");
  const tmpPath = `${jobsPath}.${process.pid}.tmp`;
  await fs.writeFile(tmpPath, JSON.stringify(jobs, null, 2));
  await fs.rename(tmpPath, jobsPath);
}

function localPublicUrl(objectPath) {
  return `/api/local-object?path=${encodeURIComponent(objectPath)}`;
}

export async function supabaseRequest(path, options = {}) {
  const cfg = supabaseConfig();
  if (!cfg.enabled) throw new Error("Supabase is not configured");
  let response;
  try {
    response = await fetch(`${cfg.url}${path}`, {
      ...options,
      headers: {
        apikey: cfg.key,
        Authorization: `Bearer ${cfg.key}`,
        ...(options.headers || {}),
      },
    });
  } catch (error) {
    throw new Error(`Supabase network error for ${cfg.host || "unknown host"}: ${error.message || String(error)}`);
  }
  if (response.ok) return response;
  const text = await response.text();
  throw new Error(`Supabase ${response.status}: ${text || response.statusText}`);
}

export async function createJob(payload) {
  if (!supabaseConfig().enabled) {
    const now = new Date().toISOString();
    const job = {
      id: randomUUID(),
      created_at: now,
      updated_at: now,
      error: null,
      output_path: null,
      output_url: null,
      ...payload,
      report: {
        ...(payload.report || {}),
        storageProvider: "local",
      },
    };
    const jobs = await readLocalJobs();
    jobs.unshift(job);
    await writeLocalJobs(jobs);
    return job;
  }
  const response = await supabaseRequest("/rest/v1/voiceover_jobs", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Prefer: "return=representation",
    },
    body: JSON.stringify(payload),
  });
  const rows = await response.json();
  return rows?.[0] || null;
}

export async function getJob(id) {
  if (!id) return null;
  if (!supabaseConfig().enabled) {
    const jobs = await readLocalJobs();
    return jobs.find((job) => String(job.id) === String(id)) || null;
  }
  const response = await supabaseRequest(
    `/rest/v1/voiceover_jobs?id=eq.${encodeURIComponent(id)}&select=*&limit=1`,
  );
  const rows = await response.json();
  return rows?.[0] || null;
}

export async function updateJob(id, patch) {
  if (!id) return null;
  if (!supabaseConfig().enabled) {
    const jobs = await readLocalJobs();
    const index = jobs.findIndex((job) => String(job.id) === String(id));
    if (index < 0) return null;
    jobs[index] = {
      ...jobs[index],
      ...patch,
      updated_at: new Date().toISOString(),
    };
    await writeLocalJobs(jobs);
    return jobs[index];
  }
  const response = await supabaseRequest(`/rest/v1/voiceover_jobs?id=eq.${encodeURIComponent(id)}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      Prefer: "return=representation",
    },
    body: JSON.stringify(patch),
  });
  const rows = await response.json();
  return rows?.[0] || null;
}

export async function uploadObject(objectPath, buffer, contentType = "application/octet-stream") {
  const cfg = supabaseConfig();
  if (!cfg.enabled) {
    const root = await ensureLocalRoot();
    const normalized = String(objectPath).replace(/^\/+/, "");
    const target = pathModuleSafe(pathModule.join(root, "objects"), normalized);
    await fs.mkdir(pathModule.dirname(target), { recursive: true });
    await fs.writeFile(target, Buffer.from(buffer));
    return localPublicUrl(normalized);
  }
  const uploadPath = `/storage/v1/object/${encodeURIComponent(cfg.bucket)}/${objectPath}`;
  await supabaseRequest(uploadPath, {
    method: "POST",
    headers: {
      "Content-Type": contentType,
      "x-upsert": "true",
    },
    body: buffer,
  });
  return `${cfg.url}/storage/v1/object/public/${encodeURIComponent(cfg.bucket)}/${objectPath}`;
}

export async function objectMetadata(objectPath) {
  const normalized = String(objectPath || "").replace(/^\/+/, "");
  if (!normalized) throw new Error("Object path is required.");
  const cfg = supabaseConfig();
  if (!cfg.enabled) {
    const root = await ensureLocalRoot();
    const target = pathModuleSafe(pathModule.join(root, "objects"), normalized);
    const stat = await fs.stat(target);
    return { exists: stat.isFile(), size: Number(stat.size || 0) };
  }
  const objectUrl = `/storage/v1/object/authenticated/${encodeURIComponent(cfg.bucket)}/${normalized}`;
  const response = await supabaseRequest(objectUrl, { method: "HEAD" });
  const rawLength = response.headers.get("content-length");
  const size = rawLength != null && /^\d+$/.test(rawLength) ? Number(rawLength) : null;
  return { exists: true, size };
}

export async function deleteObjects(objectPaths) {
  const paths = [...new Set((objectPaths || []).map((value) => String(value || "").replace(/^\/+/, "")).filter(Boolean))];
  if (!paths.length) return;
  const cfg = supabaseConfig();
  if (!cfg.enabled) {
    const root = await ensureLocalRoot();
    for (const objectPath of paths) {
      const target = pathModuleSafe(pathModule.join(root, "objects"), objectPath);
      try {
        await fs.unlink(target);
      } catch (error) {
        if (error?.code !== "ENOENT") throw error;
      }
    }
    return;
  }
  await supabaseRequest(`/storage/v1/object/${encodeURIComponent(cfg.bucket)}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prefixes: paths }),
  });
}

export async function uploadAudio(path, buffer, contentType = "audio/mpeg") {
  return uploadObject(path, buffer, contentType);
}

export async function listJobs(limit = 12) {
  if (!supabaseConfig().enabled) {
    const jobs = await readLocalJobs();
    return jobs.slice(0, Number(limit) || 12);
  }
  const response = await supabaseRequest(
    `/rest/v1/voiceover_jobs?select=id,created_at,status,voice_name,engine,output_url,report,error&order=created_at.desc&limit=${Number(limit) || 12}`,
  );
  return response.json();
}

export async function storageHealth() {
  const cfg = storageConfig();
  if (cfg.provider === "local") {
    await ensureLocalRoot();
    return {
      ok: true,
      provider: "local",
      configured: true,
      localRoot: cfg.localRoot,
    };
  }
  try {
    await supabaseRequest("/rest/v1/voiceover_jobs?select=id&limit=1");
    return {
      ok: true,
      provider: "supabase",
      configured: true,
      host: cfg.supabase.host,
      bucket: cfg.supabase.bucket,
    };
  } catch (error) {
    return {
      ok: false,
      provider: "supabase",
      configured: true,
      host: cfg.supabase.host,
      bucket: cfg.supabase.bucket,
      error: error.message || String(error),
    };
  }
}

export function localObjectPath(objectPath) {
  return pathModuleSafe(pathModule.join(localRoot(), "objects"), String(objectPath || "").replace(/^\/+/, ""));
}

function pathModuleSafe(root, ...segments) {
  const target = pathModule.resolve(root, ...segments);
  const base = pathModule.resolve(root);
  if (target !== base && !target.startsWith(`${base}${pathModule.sep}`)) {
    throw new Error("Invalid local storage path.");
  }
  return target;
}
