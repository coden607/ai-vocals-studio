"""Cloning must preserve the selected backend and report its real failures."""
import sys
from types import SimpleNamespace

import pytest

from ai_vocals_studio.voice_cloning import clone_voice


def test_backend_failure_never_substitutes_generic_tts(monkeypatch, tmp_path):
    def unavailable(*args):
        raise RuntimeError("selected neural backend is unavailable")

    monkeypatch.setitem(sys.modules, "ai_vocals_studio.voice_cloning.coqui",
                        SimpleNamespace(clone=unavailable))
    monkeypatch.setitem(sys.modules, "ai_vocals_studio.voice_cloning.silero",
                        SimpleNamespace(clone=lambda *args: pytest.fail("silently substituted generic TTS")))
    with pytest.raises(RuntimeError, match="selected neural backend is unavailable"):
        clone_voice("source.wav", "reference.wav", output_path=str(tmp_path / "out.wav"))


def test_explicit_silero_is_rejected_as_a_clone(monkeypatch):
    monkeypatch.setitem(sys.modules, "ai_vocals_studio.voice_cloning.silero",
                        SimpleNamespace(clone=lambda *args: pytest.fail("generic TTS cannot clone the reference")))
    with pytest.raises(ValueError, match="Silero.*reference voice"):
        clone_voice("source.wav", "reference.wav", model="silero")


def test_selected_backend_receives_resolved_audio_paths(monkeypatch, tmp_path):
    seen = []
    def convert(*args):
        seen.append(args)
        return args[2]

    monkeypatch.setitem(sys.modules, "ai_vocals_studio.voice_cloning.coqui",
                        SimpleNamespace(clone=convert))
    source, reference, output = [tmp_path / name for name in ("source.wav", "ref.wav", "out.wav")]
    result = clone_voice(str(source), str(reference), output_path=str(output))
    assert result == str(output)
    assert seen == [(str(source), str(reference), str(output))]


def test_unknown_backend_has_actionable_error():
    with pytest.raises(ValueError, match="Unsupported cloning backend"):
        clone_voice("source.wav", "reference.wav", model="missing")
