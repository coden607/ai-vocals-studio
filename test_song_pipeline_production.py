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


def test_strict_demucs_rejects_missing_instrumental_stem(monkeypatch, tmp_path):
    source = tmp_path / "song.wav"
    _tone(source, 44100, 0.25, 220)
    monkeypatch.setattr(sc, "_ensure_demucs", lambda *_: True)

    def fake_run(cmd, **kwargs):
        demucs_root = tmp_path / "work" / "demucs" / "htdemucs" / "song"
        demucs_root.mkdir(parents=True, exist_ok=True)
        _tone(demucs_root / "vocals.wav", 44100, 0.25, 220)
        class Result:
            returncode = 0
            stderr = ""
        return Result()

    monkeypatch.setattr(sc.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="no instrumental stem"):
        sc.separate_vocals(source, tmp_path / "work", "demucs", allow_fallback=False)


def test_strict_demucs_rejects_empty_instrumental_stem(monkeypatch, tmp_path):
    source = tmp_path / "song.wav"
    _tone(source, 44100, 0.25, 220)
    monkeypatch.setattr(sc, "_ensure_demucs", lambda *_: True)

    def fake_run(cmd, **kwargs):
        demucs_root = tmp_path / "work" / "demucs" / "htdemucs" / "song"
        demucs_root.mkdir(parents=True, exist_ok=True)
        _tone(demucs_root / "vocals.wav", 44100, 0.25, 220)
        (demucs_root / "no_vocals.wav").write_bytes(b"")
        class Result:
            returncode = 0
            stderr = ""
        return Result()

    monkeypatch.setattr(sc.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="empty/corrupt stem"):
        sc.separate_vocals(source, tmp_path / "work", "demucs", allow_fallback=False)


def test_polish_converted_vocals_preserves_length_and_peak(tmp_path):
    source = tmp_path / "source_vocals.wav"
    converted = tmp_path / "converted.wav"
    polished = tmp_path / "polished.wav"
    sr = 44100
    t = np.arange(sr, dtype=np.float32) / sr
    # Source has a clear two-part performance envelope.
    src = np.concatenate([
        0.03 * np.sin(2 * np.pi * 220 * t[: sr // 2]),
        0.12 * np.sin(2 * np.pi * 220 * t[sr // 2 :]),
    ]).astype(np.float32)
    conv = (0.08 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    sf.write(source, src, sr)
    sf.write(converted, conv, sr)

    sc.polish_converted_vocals(converted, source, polished)

    y, out_sr = sf.read(polished, dtype="float32")
    assert out_sr == sr
    assert y.shape[0] == sr
    assert np.max(np.abs(y)) <= 0.981
    first = float(np.sqrt(np.mean(y[: sr // 2] ** 2)))
    second = float(np.sqrt(np.mean(y[sr // 2 :] ** 2)))
    assert second > first * 2.0


def test_change_song_remixes_polished_vocal_not_raw_conversion(monkeypatch, tmp_path):
    source = tmp_path / "song.wav"
    vocals = tmp_path / "isolated_vocals.wav"
    inst = tmp_path / "instrumental.wav"
    _tone(source, 44100, 0.25, 220)
    _tone(vocals, 44100, 0.25, 220)
    _tone(inst, 44100, 0.25, 110)
    seen = {}

    monkeypatch.setattr(
        sc, "separate_vocals",
        lambda *args, **kwargs: (str(vocals), str(inst), "demucs"),
    )

    def fake_convert(vocals_path, profile, out_path, work_dir, progress_cb=None, require_neural=False):
        _tone(Path(out_path), 44100, 0.25, 220)
        return True, "Seed-VC zero-shot neural voice conversion"

    def fake_combine(vocals_path, instrumental_path, out_path, vocals_gain_db=0.0, progress_cb=None):
        seen["vocals"] = Path(vocals_path).name
        seen["instrumental"] = Path(instrumental_path).name
        _tone(Path(out_path), 44100, 0.25, 110)
        return str(out_path)

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

    assert Path(out).exists()
    assert seen["vocals"] == "polished_vocals.wav"
    assert seen["instrumental"] == "instrumental.wav"
    assert "vocal_polish" in steps
