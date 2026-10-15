from pathlib import Path


ROOT = Path(__file__).parent
SOURCE = (ROOT / "vercel_frontdoor/index.html").read_text(encoding="utf-8")
QUEUE_SOURCE = (ROOT / "vercel_frontdoor/api/queue-job.js").read_text(encoding="utf-8")
TICKET_SOURCE = (ROOT / "vercel_frontdoor/api/upload-ticket.js").read_text(encoding="utf-8")
ABORT_SOURCE = (ROOT / "vercel_frontdoor/api/upload-abort.js").read_text(encoding="utf-8")
AUTH_SOURCE = (ROOT / "vercel_frontdoor/api/_upload-auth.js").read_text(encoding="utf-8")
WORKER_SOURCE = (ROOT / "supabase_worker.py").read_text(encoding="utf-8")


def test_frontend_handles_platform_text_errors_and_large_uploads():
    assert "readJsonResponse" in SOURCE
    assert "response.text()" in SOURCE
    assert "Request returned a non-JSON response" not in SOURCE

    # Instant/compatibility requests remain below the Vercel body boundary.
    assert "3 * 1024 * 1024" in SOURCE
    assert "Instant hosted cloning is limited to about 3 MB" in SOURCE
    assert "uploadSize > 3 * 1024 * 1024" in SOURCE
    assert "totalBytes > 3 * 1024 * 1024" in QUEUE_SOURCE
    assert "14 * 1024 * 1024" not in SOURCE
    assert "14 * 1024 * 1024" not in QUEUE_SOURCE

    # Worker jobs bypass Vercel bodies and stream directly to Supabase via TUS.
    assert 'fetch("/api/upload-ticket"' in SOURCE
    assert '"Tus-Resumable": TUS_VERSION' in SOURCE
    assert '"Upload-Offset": String(chunkStart)' in SOURCE
    assert '"Content-Type": "application/offset+octet-stream"' in SOURCE
    assert "recoveredOffset !== chunkStart" in SOURCE
    assert "const chunkStart = offset" in SOURCE
    assert "file.slice(chunkStart" in SOURCE
    assert "6 * 1024 * 1024" in SOURCE

    # Tickets are authenticated, quota-limited, and minted just-in-time per file.
    assert "authenticateUploadRequest" in TICKET_SOURCE
    assert "UPLOAD_ACCESS_TOKEN" in AUTH_SOURCE
    assert "MAX_FILES_PER_BATCH = 7" in TICKET_SOURCE
    assert "MAX_DIRECT_UPLOAD_BATCH_BYTES" in TICKET_SOURCE
    assert "Mint the signed capability only when this specific file is about to start" in TICKET_SOURCE
    assert "requestUploadTicket(" in SOURCE
    assert "for (const item of requested)" in SOURCE
    assert "uploadSessionId" in SOURCE

    # Failed partial batches get an authenticated cleanup path.
    assert 'fetch("/api/upload-abort"' in SOURCE
    assert "deleteObjects(paths)" in ABORT_SOURCE
    assert "status: \"failed\"" in ABORT_SOURCE

    # Large references do not get fully decoded in browser memory.
    assert "MAX_BROWSER_DECODE_BYTES = 8 * 1024 * 1024" in SOURCE
    assert "probeAudioDuration(file)" in SOURCE
    assert 'analysisMode: usedMetadataOnly ? "bounded_metadata" : "decoded"' in SOURCE

    # Queueing finalizes only paths reserved inside the authenticated upload session.
    assert "expectedPathSet" in QUEUE_SOURCE
    assert "Authorized upload access key required to finalize this job" in QUEUE_SOURCE
    assert 'uploadMode: uploadSessionId ? "direct_resumable" : "server_inline"' in QUEUE_SOURCE

    # Full-song replacement is always separated with Demucs; clean refs bypass it.
    assert 'if (taskMode === "song_replace") separation = "demucs"' in QUEUE_SOURCE
    assert "Every full-song replacement starts with real vocal/instrumental separation" in QUEUE_SOURCE

    # Worker storage transfers are streamed rather than buffered as response.content/read_bytes.
    assert "stream=True" in WORKER_SOURCE
    assert "iter_content(chunk_size=1024 * 1024)" in WORKER_SOURCE
    assert "target.write_bytes(response.content)" not in WORKER_SOURCE
    assert "data=source.read_bytes()" not in WORKER_SOURCE

    # Service-role credentials never reach the browser.
    assert "createSignedUploadToken" in TICKET_SOURCE
    assert "SUPABASE_SERVICE_ROLE_KEY" not in SOURCE
    assert "x-signature" in SOURCE
    assert "storage/v1/upload/resumable" in TICKET_SOURCE


if __name__ == "__main__":
    test_frontend_handles_platform_text_errors_and_large_uploads()
    print("Frontend API error handling and hardened resumable upload checks passed")
