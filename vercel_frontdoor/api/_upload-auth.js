import { createHash, timingSafeEqual } from "node:crypto";

export function configuredUploadSecret() {
  return String(process.env.UPLOAD_ACCESS_TOKEN || process.env.ELEVENLABS_API_KEY || "");
}

export function bearerToken(req) {
  const header = String(req.headers?.authorization || "");
  const match = header.match(/^Bearer\s+(.+)$/i);
  return match ? match[1].trim() : "";
}

export function authenticateUploadRequest(req) {
  const expected = configuredUploadSecret();
  const provided = bearerToken(req);
  if (!expected || !provided) return null;
  const a = Buffer.from(expected);
  const b = Buffer.from(provided);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return null;
  return createHash("sha256").update(provided).digest("hex").slice(0, 24);
}
