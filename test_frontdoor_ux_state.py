from pathlib import Path

SOURCE = (Path(__file__).parent / "vercel_frontdoor/index.html").read_text(encoding="utf-8")


def test_frontdoor_ux_state_features_are_wired():
    for marker in (
        'id="taskHint"',
        'id="fileSummary"',
        'id="networkStatus"',
        'id="saveDraft"',
        'id="restoreDraft"',
        'id="clearDraft"',
        'function formatBytes(bytes)',
        'function updateFileSummary()',
        'function saveDraft()',
        'function restoreDraft()',
        'function updateNetworkStatus()',
        'function resetOutput()',
        'localStorage.setItem(DRAFT_KEY',
        'localStorage.removeItem(DRAFT_KEY)',
        'form.requestSubmit()',
    ):
        assert marker in SOURCE


def test_draft_does_not_persist_credentials_or_permission():
    start = SOURCE.index("function draftPayload()")
    end = SOURCE.index("function saveDraft()", start)
    block = SOURCE[start:end]
    assert "apiKey" not in block
    assert "permission" not in block
