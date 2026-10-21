from pathlib import Path

SOURCE = (Path(__file__).parent / "supabase_worker.py").read_text(encoding="utf-8")


def test_worker_heartbeat_is_wired_for_long_jobs():
    for marker in (
        "import threading",
        "def _heartbeat_job(",
        'client.update_job(job_id, {"status": "running"})',
        "threading.Event()",
        "threading.Thread(",
        "heartbeat_thread.start()",
        "heartbeat_stop.set()",
        "heartbeat_thread.join(timeout=2.0)",
    ):
        assert marker in SOURCE


def test_heartbeat_is_bounded_and_failure_tolerant():
    start = SOURCE.index("def _heartbeat_job(")
    end = SOURCE.index("def _content_type", start)
    block = SOURCE[start:end]
    assert "max(5.0" in block
    assert "stop_event.wait(interval)" in block
    assert "except Exception as exc" in block
