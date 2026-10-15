from pathlib import Path


ROOT = Path(__file__).parent
SOURCE = (ROOT / "vercel_frontdoor/index.html").read_text(encoding="utf-8")
QUEUE_SOURCE = (ROOT / "vercel_frontdoor/api/queue-job.js").read_text(encoding="utf-8")
TICKET_SOURCE = (ROOT / "vercel_frontdoor/api/upload-ticket.js").read_text(encoding="utf-8")


def test_frontend_handles_platform_text_errors_and_large_uploads():
    assert "readJsonResponse" in SOURCE
    assert "response.text()" in SOURCE
    assert "Request returned a non-JSON response" not in SOURCE

    # Instant hosted cloning still has to cross the Vercel request boundary.
    assert "3 * 1024 * 1024" in SOURCE
    assert "Instant hosted cloning is limited to about 3 MB" in SOURCE

    # Worker jobs must bypass Vercel request bodies and stream to Supabase via TUS.
    assert 'fetch("/api/upload-ticket"' in SOURCE
    assert '"Tus-Resumable": TUS_VERSION' in SOURCE
    assert '"Upload-Offset": String(offset)' in SOURCE
    assert '"Content-Type": "application/offset+octet-stream"' in SOURCE
    assert "6 * 1024 * 1024" in SOURCE
    assert "workerUploads?.files || encoded" in SOURCE

    # Upload tickets are signed server-side; the service-role key never reaches the browser.
    assert "createSignedUploadToken" in TICKET_SOURCE
    assert "SUPABASE_SERVICE_ROLE_KEY" not in SOURCE
    assert "x-signature" in SOURCE
    assert "storage/v1/upload/resumable" in TICKET_SOURCE

    # Queueing accepts object references for large jobs but keeps the legacy inline path.
    assert "validQueuedPath" in QUEUE_SOURCE
    assert 'uploadMode: containsInlineAudio ? "server_inline" : "direct_resumable"' in QUEUE_SOURCE
    assert "containsInlineAudio && totalBytes > 14 * 1024 * 1024" in QUEUE_SOURCE


if __name__ == "__main__":
    test_frontend_handles_platform_text_errors_and_large_uploads()
    print("Frontend API error handling and resumable upload checks passed")
