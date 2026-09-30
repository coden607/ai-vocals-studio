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


def test_change_song_always_separates_before_conversion_and_remix(monkeypatch, tmp_path):
    source = tmp_path / "song.wav"
    _tone(source, 44100, 0.25, 220)
    calls = []

    vocals = tmp_path / "isolated_vocals.wav"
    inst = tmp_path / "instrumental.wav"
    _tone(vocals, 44100, 0.25, 220)
    _tone(inst, 44100, 0.25, 110)

    def fake_separate(song_path, work_dir, method, progress_cb, allow_fallback=True):
        calls.append(("separate", Path(song_path).name, method, allow_fallback))
        return str(vocals), str(inst), "demucs"

    def fake_convert(vocals_path, profile, out_path, work_dir, progress_cb=None, require_neural=False):
        calls.append(("convert", Path(vocals_path).name, require_neural))
        _tone(Path(out_path), 44100, 0.25, 220)
        return True, "Seed-VC zero-shot neural voice conversion"

    def fake_combine(vocals_path, instrumental_path, out_path, vocals_gain_db=0.0, progress_cb=None):
        calls.append(("remix", Path(vocals_path).name, Path(instrumental_path).name))
        _tone(Path(out_path), 44100, 0.25, 110)
        return str(out_path)

    monkeypatch.setattr(sc, "separate_vocals", fake_separate)
    monkeypatch.setattr(sc, "convert_vocals", fake_convert)
    monkeypatch.setattr(sc, "combine_tracks", fake_combine)

    out, steps = sc.change_song(
        source,
        {"name": "AuthorizedVoice"},
        tmp_path / "out",
        separation="demucs",
        require_neural=True,
        source_matched_export=False,
    )

    assert [item[0] for item in calls] == ["separate", "convert", "remix"]
    assert calls[1][1] == "isolated_vocals.wav"
    assert calls[2][2] == "instrumental.wav"
    assert steps["separation"] == "demucs"
    assert steps["conversion"].startswith("Seed-VC")
    assert Path(out).exists()
