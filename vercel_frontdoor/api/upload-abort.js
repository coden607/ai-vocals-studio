import { deleteObjects, getJob, updateJob } from "./_supabase.js";
import { authenticateUploadRequest } from "./_upload-auth.js";

export const config = {
  api: { bodyParser: { sizeLimit: "64kb" } },
  maxDuration: 30,
};

function sendJson(res, status, payload) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Cache-Control", "no-store");
  res.end(JSON.stringify(payload));
}

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return sendJson(res, 405, { ok: false, error: "Method not allowed" });
  }

  try {
    const principal = authenticateUploadRequest(req);
    if (!principal) return sendJson(res, 401, { ok: false, error: "Unauthorized upload cleanup request." });

    const body = typeof req.body === "string" ? JSON.parse(req.body) : (req.body || {});
    const uploadSessionId = String(body.uploadSessionId || "");
    const job = await getJob(uploadSessionId);
    if (!job) return sendJson(res, 404, { ok: false, error: "Upload session not found." });

    const report = job.report || {};
    if (report.uploadPrincipal !== principal) {
      return sendJson(res, 403, { ok: false, error: "Upload session authorization mismatch." });
    }
    if (job.status !== "uploading") {
      return sendJson(res, 200, { ok: true, cleaned: false, status: job.status });
    }

    const expectedUploads = Array.isArray(report.expectedUploads) ? report.expectedUploads : [];
    const paths = expectedUploads.map((entry) => entry?.path).filter(Boolean);
    await deleteObjects(paths);
    await updateJob(job.id, {
      status: "failed",
      error: String(body.reason || "Upload aborted before queueing.").slice(0, 500),
      report: {
        ...report,
        cleanupAt: new Date().toISOString(),
        cleanedPaths: paths.length,
      },
    });

    return sendJson(res, 200, { ok: true, cleaned: true, removed: paths.length });
  } catch (error) {
    return sendJson(res, 500, { ok: false, error: error.message || String(error) });
  }
}
