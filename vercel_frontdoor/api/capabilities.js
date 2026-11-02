import { storageConfig } from "./_supabase.js";

function sendJson(res, status, payload) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.end(JSON.stringify(payload));
}

export default async function handler(req, res) {
  if (req.method !== "GET") {
    res.setHeader("Allow", "GET");
    return sendJson(res, 405, { ok: false, error: "Method not allowed" });
  }
  const storage = storageConfig();
  return sendJson(res, 200, {
    ok: true,
    hosted: [
      {
        name: "ElevenLabs IVC + TTS",
        available: Boolean(process.env.ELEVENLABS_API_KEY),
        mode: "instant voice-over",
        note: process.env.ELEVENLABS_API_KEY ? "API key configured" : "set ELEVENLABS_API_KEY for instant generation",
      },
    ],
    worker: [
      { name: "Qwen3-TTS", mode: "local neural TTS" },
      { name: "XTTS v2", mode: "local neural TTS sidecar" },
      { name: "Demucs", mode: "neural vocal separation" },
      { name: "Seed-VC", mode: "zero-shot speech, rap, and singing conversion" },
      { name: "RVC + Applio", mode: "GPU fine-tuning and vocal conversion" },
      { name: "WORLD/DSP", mode: "local fallback conversion" },
    ],
    queue: {
      configured: storage.provider === "supabase",
      provider: storage.provider,
      training: "RVC training requires a GPU worker; use cloud/kaggle_rvc_worker.ipynb",
    },
  });
}
