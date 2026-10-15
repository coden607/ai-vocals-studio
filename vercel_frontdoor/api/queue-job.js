import { createJob, getJob, storageConfig, updateJob, uploadObject } from "./_supabase.js";
import { authenticateUploadRequest } from "./_upload-auth.js";
import { randomUUID } from "node:crypto";

export const config = {
  api: { bodyParser: { sizeLimit: "5mb" } },
  maxDuration: 60,
};

function sendJson(res, status, payload) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(payload));
}

function cleanName(value) {
  return String(value || "Authorized Voice").replace(/[^A-Za-z0-9_. -]+/g, "").trim().slice(0, 80) || "Authorized Voice";
}

function qualityGate(metrics, target = "studio") {
  const totalDuration = Number(metrics?.totalDurationS || 0);
  const fit = Number(metrics?.fitScore || 0);
  const clipping = metrics?.maxClippingFraction == null ? null : Number(metrics.maxClippingFraction);
  const fileCount = Array.isArray(metrics?.files) ? metrics.files.length : 0;
  const reasons = [];
  if (target === "draft") return { ok: true, reasons };
  if (totalDuration < 20) reasons.push("Upload at least 20 seconds of clean single-speaker voice; 60+ seconds is better.");
  if (fit < 60) reasons.push("The uploaded samples are not strong enough for studio-match mode.");
  if (clipping != null && clipping > 0.02) reasons.push("The samples appear clipped/distorted; lower the recording gain and re-upload.");
  if (target === "pro") {
    if (totalDuration < 90) reasons.push("Pro-match mode requires 90+ seconds of clean authorized reference voice.");
    if (fileCount < 3) reasons.push("Pro-match mode requires at least 3 separate reference clips for a more stable voice profile.");
    if (fit < 85) reasons.push("Pro-match mode requires an input fit score of 85% or higher.");
    if (clipping != null && clipping > 0.005) reasons.push("Pro-match mode needs unclipped audio; re-upload lower-gain source files.");
  }
  return { ok: reasons.length === 0, reasons };
}

function validQueuedPath(value, role, uploadSessionId = "") {
  const folder = role === "target" ? "target" : "voices";
  const sessionPattern = uploadSessionId ? String(uploadSessionId).replace(/[^0-9a-f-]/gi, "") : "[0-9a-f-]{36}";
  return new RegExp(`^queued/${sessionPattern}/${folder}/[0-9a-f-]{36}-[^/]+$`, "i").test(String(value || ""));
}

function referencedFile(file, role, uploadSessionId) {
  if (!file?.path || !validQueuedPath(file.path, role, uploadSessionId)) return null;
  return {
    clientId: String(file.clientId || ""),
    name: cleanName(file.name || (role === "target" ? "target-audio.wav" : "voice-sample.wav")).replace(/\s+/g, "_"),
    type: String(file.type || "application/octet-stream"),
    size: Number(file.size || 0),
    path: String(file.path),
    url: null,
  };
}

function expectedPathSet(job) {
  const expected = Array.isArray(job?.report?.expectedUploads) ? job.report.expectedUploads : [];
  return new Set(expected.map((item) => String(item?.path || "")).filter(Boolean));
}

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return sendJson(res, 405, { ok: false, error: "Method not allowed" });
  }

  try {
    const storage = storageConfig();
    const body = typeof req.body === "string" ? JSON.parse(req.body) : (req.body || {});
    const files = Array.isArray(body.files) ? body.files : [];
    const text = String(body.text || "").trim();
    const taskMode = String(body.taskMode || "voiceover");
    const supportedTasks = new Set(["voiceover", "song_replace", "clip_convert", "rvc_train"]);
    if (!supportedTasks.has(taskMode)) return sendJson(res, 400, { ok: false, error: "Unsupported worker task mode." });

    const qualityTarget = String(body.qualityTarget || (body.studioQuality === false ? "draft" : "pro"));
    const allowedQualityTargets = new Set(["draft", "studio", "pro"]);
    if (!allowedQualityTargets.has(qualityTarget)) return sendJson(res, 400, { ok: false, error: "Unsupported quality target." });

    let separation = String(body.separation || "demucs");
    const allowedSeparation = new Set(["auto", "demucs", "center"]);
    if (!allowedSeparation.has(separation)) return sendJson(res, 400, { ok: false, error: "Unsupported separation mode." });
    // Every full-song replacement starts with real vocal/instrumental separation.
    // Clean voice references, isolated vocals, and instrumental-only beds bypass Demucs.
    if (taskMode === "song_replace") separation = "demucs";

    if (!body.permission) return sendJson(res, 400, { ok: false, error: "Permission confirmation is required." });
    if (!files.length) return sendJson(res, 400, { ok: false, error: "Upload at least one voice sample." });
    if (taskMode === "voiceover" && !text) return sendJson(res, 400, { ok: false, error: "Voice-over text is required." });
    if (!["voiceover", "rvc_train"].includes(taskMode) && !body.targetFile?.path && !body.targetFile?.data) {
      return sendJson(res, 400, { ok: false, error: "Target song/audio is required for replacement jobs." });
    }

    const uploadSessionId = String(body.uploadSessionId || "");
    const containsReferencedAudio = files.some((file) => Boolean(file?.path)) || Boolean(body.targetFile?.path);
    const containsInlineAudio = files.some((file) => Boolean(file?.data)) || Boolean(body.targetFile?.data);
    if (containsReferencedAudio && !uploadSessionId) {
      return sendJson(res, 400, { ok: false, error: "Referenced uploads require an upload session ID." });
    }
    if (containsReferencedAudio && containsInlineAudio) {
      return sendJson(res, 400, { ok: false, error: "Do not mix resumable references with inline audio in one job." });
    }

    const totalBytes = files.reduce((sum, file) => sum + Number(file.size || 0), 0) + Number(body.targetFile?.size || 0);
    if (containsInlineAudio && totalBytes > 3 * 1024 * 1024) {
      return sendJson(res, 413, {
        ok: false,
        error: "Inline audio is too large for Vercel serverless queueing. Retry the authenticated resumable Supabase upload.",
      });
    }

    const gate = qualityGate(body.referenceMetrics, qualityTarget);
    if (!gate.ok) {
      return sendJson(res, 422, {
        ok: false,
        error: `${qualityTarget === "pro" ? "Pro-match" : "Studio-match"} input rejected: ${gate.reasons.join(" ")}`,
        referenceMetrics: body.referenceMetrics || null,
      });
    }

    let stagedJob = null;
    let expectedPaths = null;
    if (uploadSessionId) {
      const principal = authenticateUploadRequest(req);
      if (!principal) return sendJson(res, 401, { ok: false, error: "Authorized upload access key required to finalize this job." });
      stagedJob = await getJob(uploadSessionId);
      if (!stagedJob || stagedJob.status !== "uploading") {
        return sendJson(res, 409, { ok: false, error: "Upload session is missing, expired, or already finalized." });
      }
      const report = stagedJob.report || {};
      if (report.uploadPrincipal !== principal || report.taskMode !== taskMode) {
        return sendJson(res, 403, { ok: false, error: "Upload session authorization mismatch." });
      }
      expectedPaths = expectedPathSet(stagedJob);
    }

    const jobPrefix = `queued/${randomUUID()}`;
    const storedFiles = [];
    for (const file of files.slice(0, 6)) {
      if (!file) continue;
      if (file.path) {
        if (storage.provider !== "supabase") return sendJson(res, 400, { ok: false, error: "Referenced uploads require Supabase Storage." });
        const referenced = referencedFile(file, "voice", uploadSessionId);
        if (!referenced || !expectedPaths?.has(referenced.path)) {
          return sendJson(res, 400, { ok: false, error: "Invalid or unreserved queued voice object path." });
        }
        storedFiles.push(referenced);
        continue;
      }
      if (!file.data) continue;
      const safeName = cleanName(file.name || "voice-sample.wav").replace(/\s+/g, "_");
      const path = `${jobPrefix}/voices/${Date.now()}-${safeName}`;
      const buffer = Buffer.from(String(file.data), "base64");
      const publicUrl = await uploadObject(path, buffer, file.type || "application/octet-stream");
      storedFiles.push({ name: safeName, type: file.type || "application/octet-stream", size: Number(file.size || buffer.length), path, url: publicUrl });
    }
    if (!storedFiles.length) return sendJson(res, 400, { ok: false, error: "No usable voice uploads were supplied." });

    let storedTarget = null;
    if (!["voiceover", "rvc_train"].includes(taskMode)) {
      const target = body.targetFile;
      if (target?.path) {
        if (storage.provider !== "supabase") return sendJson(res, 400, { ok: false, error: "Referenced target uploads require Supabase Storage." });
        storedTarget = referencedFile(target, "target", uploadSessionId);
        if (!storedTarget || !expectedPaths?.has(storedTarget.path)) {
          return sendJson(res, 400, { ok: false, error: "Invalid or unreserved queued target object path." });
        }
      } else {
        const safeName = cleanName(target.name || "target-audio.wav").replace(/\s+/g, "_");
        const path = `${jobPrefix}/target/${Date.now()}-${safeName}`;
        const buffer = Buffer.from(String(target.data), "base64");
        const publicUrl = await uploadObject(path, buffer, target.type || "application/octet-stream");
        storedTarget = { name: safeName, type: target.type || "application/octet-stream", size: Number(target.size || buffer.length), path, url: publicUrl };
      }
    }

    const mode = taskMode === "song_replace" ? "song" : taskMode === "clip_convert" ? "clip" : "bed";
    const patch = {
      status: "queued",
      job_type: taskMode === "voiceover"
        ? "local_worker_voiceover"
        : taskMode === "rvc_train" ? "local_worker_rvc_train" : "local_worker_audio_replace",
      voice_name: cleanName(body.voiceName),
      engine: "local best available",
      permission_confirmed: true,
      input_files: storedFiles,
      text,
      mode,
      settings: {
        mood: body.mood || "default",
        stability: Number(body.stability || 0.62),
        similarity: Number(body.similarity || 0.97),
        studioQuality: body.studioQuality !== false,
        qualityTarget,
        taskMode,
        separation,
        targetFile: storedTarget,
        trainer: body.trainer || undefined,
        epochs: Number(body.epochs || 300),
        voicesDir: "models/voices",
      },
      report: {
        ...(stagedJob?.report || {}),
        queuedBy: "vercel",
        storageProvider: storage.provider,
        uploadMode: uploadSessionId ? "direct_resumable" : "server_inline",
        totalSampleMb: Math.round((totalBytes / (1024 * 1024)) * 100) / 100,
        referenceMetrics: body.referenceMetrics || null,
        finalizedAt: new Date().toISOString(),
      },
      error: null,
    };

    const job = stagedJob ? await updateJob(stagedJob.id, patch) : await createJob(patch);
    return sendJson(res, 200, { ok: true, provider: storage.provider, job, files: storedFiles, targetFile: storedTarget });
  } catch (error) {
    return sendJson(res, 500, { ok: false, error: error.message || String(error) });
  }
}
