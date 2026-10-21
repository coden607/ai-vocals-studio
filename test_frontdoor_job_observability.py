from pathlib import Path

SOURCE = (Path(__file__).parent / "vercel_frontdoor/index.html").read_text(encoding="utf-8")


def test_job_observability_features_are_present():
    for marker in (
        'id="refreshJobs"',
        'id="autoRefreshJobs"',
        'id="jobFilter"',
        'id="jobMeta"',
        'function escapeHtml(value)',
        'function jobStatus(job)',
        'function copyText(value, label)',
        'class="status-badge"',
        'copy-job-id',
        'copy-output-url',
        'document.visibilityState === "visible"',
        'setInterval(() =>',
    ):
        assert marker in SOURCE


def test_job_rendering_escapes_dynamic_values():
    start = SOURCE.index("const allJobs = payload.jobs || [];")
    end = SOURCE.index("} catch (err)", start)
    block = SOURCE[start:end]
    for value in ("job.voice_name", "job.engine", "stage", "statusText"):
        assert "escapeHtml" in block
    assert 'href="${escapeHtml(outputUrl)}"' in block
