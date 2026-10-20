from pathlib import Path

SOURCE = (Path(__file__).parent / "vercel_frontdoor/index.html").read_text(encoding="utf-8")


def test_input_ergonomics_features_are_present():
    for marker in (
        'id="voiceDropzone"',
        'id="targetDropzone"',
        'id="clearVoiceFiles"',
        'id="clearTargetFile"',
        'id="clearBedFile"',
        'id="voicePreview"',
        'id="targetPreview"',
        'id="scriptCount"',
        'function bindDropzone(',
        'function assignFiles(',
        'function isAudioFile(',
        'function setPreview(',
        'function updateScriptCount()',
        'function markDraftDirty()',
        'files.slice(0, 6)',
    ):
        assert marker in SOURCE
