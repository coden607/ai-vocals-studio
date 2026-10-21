from pathlib import Path

SOURCE = (Path(__file__).parent / "vercel_frontdoor/index.html").read_text(encoding="utf-8")


def test_job_observability_controls_and_safety_are_present():
    for marker in (
        'id="refreshJobs"',
        'id="autoRefreshJobs"',
        'id="jobFilter"',
        'id="jobMeta"',
        'function escapeHtml(value)',
        'function jobStatus(job)',
        'function jobIsStale(job)',
        'function copyText(value, label)',
        'copy-job-id',
        'copy-output-url',
        'document.visibilityState === "visible"',
        'navigator.onLine',
        'job.error',
        'stale running',
    ):
        assert marker in SOURCE


def test_dynamic_job_values_are_escaped():
    start = SOURCE.index("const allJobs = payload.jobs || [];")
    end = SOURCE.index("} catch (err)", start)
    block = SOURCE[start:end]
    for dynamic in ("job.voice_name", "job.engine", "job.error", "outputUrl", "model"):
        assert dynamic in block
    assert block.count("escapeHtml(") >= 8


def test_stale_running_threshold_is_bounded():
    start = SOURCE.index("function jobIsStale(job)")
    end = SOURCE.index("async function copyText", start)
    block = SOURCE[start:end]
    assert 'jobStatus(job) !== "running"' in block
    assert "15 * 60 * 1000" in block
