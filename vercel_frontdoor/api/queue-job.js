import { createJob, uploadObject, storageConfig } from "./_supabase.js";
import { randomUUID } from "node:crypto";

export const config = {
  api: { bodyParser: { sizeLimit: "20mb" } },
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
  const clipping = Number(metrics?.maxClippingFraction || 0);
  const fileCount = Array.isArray(metrics?.files) ? metrics.files.length : 0;
  const reasons = [];
  if (target === "draft") return { ok: true, reasons };
  if (totalDuration < 20) reasons.push("Upload at least 20 seconds of clean single-speaker voice; 60+ seconds is better.");
  if (fit < 60) reasons.push("The uploaded samples are not strong enough for studio-match mode.");
  if (clipping > 0.02) reasons.push("The samples appear clipped/distorted; lower the recording gain and re-upload.");
  if (target === "pro") {
    if (totalDuration < 90) reasons.push("Pro-match mode requires 90+ seconds of clean authorized reference voice.");
    if (fileCount < 3) reasons.push("Pro-match mode requires at least 3 separate reference clips for a more stable voice profile.");
    if (fit < 85) reasons.push("Pro-match mode requires an input fit score of 85% or higher.");
    if (clipping > 0.005) reasons.push("Pro-match mode needs unclipped audio; re-upload lower-gain source files.");
  }
  return {
    ok: reasons.length === 0,
    reasons,
  };
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
    // Studio/Pro song replacement is fail-closed: the worker must separate the
    // real vocal and instrumental stems before voice conversion/remix.
    if (taskMode === "song_replace" && ["studio", "pro"].includes(qualityTarget)) separation = "demucs";
    if (!body.permission) return sendJson(res, 400, { ok: false, error: "Permission confirmation is required." });
    if (!files.length) return sendJson(res, 400, { ok: false, error: "Upload at least one voice sample." });
    if (taskMode === "voiceover" && !text) return sendJson(res, 400, { ok: false, error: "Voice-over text is required." });
    if (!["voiceover", "rvc_train"].includes(taskMode) && !body.targetFile?.data) {
      return sendJson(res, 400, { ok: false, error: "Target song/audio is required for replacement jobs." });
    }

    const totalBytes = files.reduce((sum, file) => sum + Number(file.size || 0), 0) + Number(body.targetFile?.size || 0);
    if (totalBytes > 14 * 1024 * 1024) {
      return sendJson(res, 413, { ok: false, error: "Uploaded audio is too large for Vercel serverless queueing. Use shorter clips or run the local app/worker directly for large songs." });
    }
    const gate = qualityGate(body.referenceMetrics, qualityTarget);
    if (!gate.ok) {
      return sendJson(res, 422, {
        ok: false,
        error: `${qualityTarget === "pro" ? "Pro-match" : "Studio-match"} input rejected: ${gate.reasons.join(" ")}`,
        referenceMetrics: body.referenceMetrics || null,
      });
    }

    const jobPrefix = `queued/${randomUUID()}`;
    const storedFiles = [];
    for (const file of files.slice(0, 6)) {
      if (!file || !file.data) continue;
      const safeName = cleanName(file.name || "voice-sample.wav").replace(/\s+/g, "_");
      const path = `${jobPrefix}/voices/${Date.now()}-${safeName}`;
      const buffer = Buffer.from(String(file.data), "base64");
      const publicUrl = await uploadObject(path, buffer, file.type || "application/octet-stream");
      storedFiles.push({
        name: safeName,
        type: file.type || "application/octet-stream",
        size: Number(file.size || buffer.length),
        path,
        url: publicUrl,
      });
    }
    let storedTarget = null;
    if (!["voiceover", "rvc_train"].includes(taskMode)) {
      const target = body.targetFile;
      const safeName = cleanName(target.name || "target-audio.wav").replace(/\s+/g, "_");
      const path = `${jobPrefix}/target/${Date.now()}-${safeName}`;
      const buffer = Buffer.from(String(target.data), "base64");
      const publicUrl = await uploadObject(path, buffer, target.type || "application/octet-stream");
      storedTarget = {
        name: safeName,
        type: target.type || "application/octet-stream",
        size: Number(target.size || buffer.length),
        path,
        url: publicUrl,
      };
    }
    const workerMode = taskMode === "song_replace" ? "song" : taskMode === "clip_convert" ? "clip" : "bed";

    const job = await createJob({
      status: "queued",
      job_type: taskMode === "voiceover"
        ? "local_worker_voiceover"
        : taskMode === "rvc_train" ? "local_worker_rvc_train" : "local_worker_audio_replace",
      voice_name: cleanName(body.voiceName),
      engine: "local best available",
      permission_confirmed: true,
      input_files: storedFiles,
      text,
      mode: workerMode,
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
        queuedBy: "vercel",
        storageProvider: storage.provider,
        totalSampleMb: Math.round((totalBytes / (1024 * 1024)) * 100) / 100,
        referenceMetrics: body.referenceMetrics || null,
      },
    });

    return sendJson(res, 200, { ok: true, provider: storage.provider, job, files: storedFiles, targetFile: storedTarget });
  } catch (error) {
    return sendJson(res, 500, { ok: false, error: error.message || String(error) });
  }
}
