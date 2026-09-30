from pathlib import Path
import numpy as np
import soundfile as sf
import pytest
import song_converter as sc


def _tone(path: Path, sr: int, seconds: float, hz: float) -> None:
    t = np.arange(int(sr * seconds), dtype=np.float32) / sr
    y = (0.08 * np.sin(2 * np.pi * hz * t)).astype(np.float32)
    sf.write(path, y, sr)


def test_combine_tracks_resamples_and_preserves_instrumental_length(tmp_path):
    vocals = tmp_path / "vocals.wav"
    inst = tmp_path / "inst.wav"
    out = tmp_path / "mix.wav"
    _tone(vocals, 22050, 0.5, 220)
    _tone(inst, 44100, 1.0, 110)

    sc.combine_tracks(vocals, inst, out)

    mixed, sr = sf.read(out, dtype="float32")
    assert sr == 44100
    assert mixed.shape[0] == 44100
    assert np.max(np.abs(mixed)) <= 1.0


def test_strict_demucs_never_silently_falls_back(monkeypatch, tmp_path):
    source = tmp_path / "song.wav"
    _tone(source, 44100, 0.25, 220)
    monkeypatch.setattr(sc, "_ensure_demucs", lambda *_: False)

    with pytest.raises(RuntimeError, match="Demucs is required"):
        sc.separate_vocals(source, tmp_path / "work", "demucs", allow_fallback=False)
