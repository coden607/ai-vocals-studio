from pathlib import Path

ROOT = Path(__file__).parent
QUEUE = (ROOT / "vercel_frontdoor/api/queue-job.js").read_text(encoding="utf-8")
SUPABASE = (ROOT / "vercel_frontdoor/api/_supabase.js").read_text(encoding="utf-8")


def test_queue_verifies_resumable_objects_before_finalizing():
    assert "objectMetadata" in QUEUE
    assert "async function verifyReferencedObject(file)" in QUEUE
    assert QUEUE.count("await verifyReferencedObject(") >= 2
    assert "Uploaded object size mismatch" in QUEUE
    assert "Storage did not report the uploaded object size" in QUEUE


def test_storage_metadata_uses_authenticated_head_and_exact_size():
    assert "export async function objectMetadata(objectPath)" in SUPABASE
    assert "/storage/v1/object/authenticated/" in SUPABASE
    assert 'method: "HEAD"' in SUPABASE
    assert 'response.headers.get("content-length")' in SUPABASE
    assert "Number(stat.size || 0)" in SUPABASE
