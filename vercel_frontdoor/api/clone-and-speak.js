import { createJob, updateJob, uploadAudio, storageConfig } from "./_supabase.js";
import { randomUUID } from "node:crypto";

const ELEVEN_API = "https://api.elevenlabs.io/v1";

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
  if (target === "draft") return { ok: true, reasons, totalDuration, fit, clipping };
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
    totalDuration,
    fit,
    clipping,
  };
}

async function elevenFetch(path, options) {
  const response = await fetch(`${ELEVEN_API}${path}`, options);
  if (response.ok) return response;
  const body = await response.text();
  let detail = body;
  try {
    detail = body ? JSON.stringify(JSON.parse(body)) : "";
  } catch {
    // Upstream gateways sometimes return plain text instead of JSON.
  }
  throw new Error(`ElevenLabs ${response.status}: ${detail || response.statusText}`);
}

async function readJsonResponse(response, label) {
  const body = await response.text();
  try {
    return body ? JSON.parse(body) : {};
  } catch {
    throw new Error(`${label} returned non-JSON data: ${body.replace(/\s+/g, " ").trim().slice(0, 180) || "empty response"}`);
  }
}

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return sendJson(res, 405, { ok: false, error: "Method not allowed" });
  }
  let job = null;
  try {
    const storage = storageConfig();
    const body = typeof req.body === "string" ? JSON.parse(req.body) : (req.body || {});
    const apiKey = String(body.apiKey || process.env.ELEVENLABS_API_KEY || "").trim();
    const files = Array.isArray(body.files) ? body.files : [];
    const text = String(body.text || "").trim();
    const qualityTarget = String(body.qualityTarget || (body.studioQuality === false ? "draft" : "pro"));
    const allowedQualityTargets = new Set(["draft", "studio", "pro"]);
    if (!allowedQualityTargets.has(qualityTarget)) return sendJson(res, 400, { ok: false, error: "Unsupported quality target." });
    if (!apiKey) return sendJson(res, 400, { ok: false, error: "Set ELEVENLABS_API_KEY on Vercel or enter an API key in the form." });
    if (!body.permission) return sendJson(res, 400, { ok: false, error: "Permission confirmation is required." });
    if (!files.length) return sendJson(res, 400, { ok: false, error: "Upload at least one voice sample." });
    if (!text) return sendJson(res, 400, { ok: false, error: "Voice-over text is required." });
    const totalBytes = files.reduce((sum, file) => sum + Number(file.size || 0), 0);
    if (totalBytes > 14 * 1024 * 1024) {
      return sendJson(res, 413, { ok: false, error: "Uploaded samples are too large for Vercel serverless. Use shorter clips or the Docker/local app." });
    }
    const gate = qualityGate(body.referenceMetrics, qualityTarget);
    if (!gate.ok) {
      return sendJson(res, 422, {
        ok: false,
        error: `${qualityTarget === "pro" ? "Pro-match" : "Studio-match"} input rejected: ${gate.reasons.join(" ")}`,
        referenceMetrics: gate,
      });
    }
    job = await createJob({
      status: "running",
      job_type: "instant_voiceover",
      voice_name: cleanName(body.voiceName),
      engine: "ElevenLabs IVC",
      permission_confirmed: true,
      text,
      mode: "bed",
      settings: {
        stability: Number.isFinite(Number(body.stability)) ? Number(body.stability) : 0.62,
        similarity: Number.isFinite(Number(body.similarity)) ? Number(body.similarity) : 0.97,
        studioQuality: body.studioQuality !== false,
        qualityTarget,
      },
      input_files: files.map((file) => ({
        name: cleanName(file.name || "voice-sample"),
        type: file.type || "application/octet-stream",
        size: Number(file.size || 0),
      })),
      report: {
        totalSampleMb: Math.round((totalBytes / (1024 * 1024)) * 100) / 100,
        storageProvider: storage.provider,
        qualityTarget,
        referenceMetrics: body.referenceMetrics || null,
      },
    });

    const voiceForm = new FormData();
    voiceForm.append("name", cleanName(body.voiceName));
    voiceForm.append("description", "Authorized instant voice clone generated from AI Vocals Studio Vercel app.");
    voiceForm.append("remove_background_noise", "true");
    for (const file of files.slice(0, 4)) {
      if (!file || !file.data) continue;
      const blob = new Blob([Buffer.from(String(file.data), "base64")], { type: file.type || "application/octet-stream" });
      voiceForm.append("files", blob, cleanName(file.name || "voice-sample.wav"));
    }

    const voiceResponse = await elevenFetch("/voices/add", {
      method: "POST",
      headers: { "xi-api-key": apiKey },
      body: voiceForm,
    });
    const voice = await readJsonResponse(voiceResponse, "ElevenLabs voice creation");
    const voiceId = voice.voice_id;
    if (!voiceId) throw new Error("ElevenLabs did not return a voice_id.");

    const ttsResponse = await elevenFetch(`/text-to-speech/${encodeURIComponent(voiceId)}?output_format=mp3_44100_128`, {
      method: "POST",
      headers: { "xi-api-key": apiKey, "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        model_id: "eleven_multilingual_v2",
        voice_settings: {
          stability: Number.isFinite(Number(body.stability)) ? Number(body.stability) : 0.62,
          similarity_boost: Number.isFinite(Number(body.similarity)) ? Number(body.similarity) : 0.97,
          style: 0.15,
          use_speaker_boost: true,
        },
      }),
    });

    const audioBuffer = Buffer.from(await ttsResponse.arrayBuffer());
    const outputPath = `${job?.id || randomUUID()}/voiceover.mp3`;
    const outputUrl = await uploadAudio(outputPath, audioBuffer, "audio/mpeg");
    let deleted = false;
    if (body.deleteVoice) {
      try {
        await elevenFetch(`/voices/${encodeURIComponent(voiceId)}`, { method: "DELETE", headers: { "xi-api-key": apiKey } });
        deleted = true;
      } catch {
        deleted = false;
      }
    }
    await updateJob(job?.id, {
      status: "complete",
      output_path: outputUrl ? outputPath : null,
      output_url: outputUrl,
      report: {
        voiceId,
        deleted,
        requiresVerification: Boolean(voice.requires_verification),
        sampleCount: files.length,
        totalSampleMb: Math.round((totalBytes / (1024 * 1024)) * 100) / 100,
        storage: outputUrl ? storage.provider : "inline",
        qualityTarget,
        referenceMetrics: body.referenceMetrics || null,
      },
    });

    return sendJson(res, 200, {
      ok: true,
      jobId: job?.id || null,
      engine: "ElevenLabs IVC",
      voiceId,
      requiresVerification: Boolean(voice.requires_verification),
      deleted,
      mediaType: "audio/mpeg",
      audioBase64: audioBuffer.toString("base64"),
      outputUrl,
      storageProvider: storage.provider,
      report: {
        sampleCount: files.length,
        totalSampleMb: Math.round((totalBytes / (1024 * 1024)) * 100) / 100,
        referenceMetrics: body.referenceMetrics || null,
        notes: [
          "Hosted Vercel path uses ElevenLabs Instant Voice Cloning and text-to-speech.",
          "For local Qwen/XTTS/RVC/Demucs workflows, run the Docker/local app.",
        ],
      },
    });
  } catch (error) {
    try {
      if (job?.id) {
        await updateJob(job.id, { status: "failed", error: error.message || String(error) });
      }
    } catch {}
    return sendJson(res, 500, { ok: false, error: error.message || String(error) });
  }
}
