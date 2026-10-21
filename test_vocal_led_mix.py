import hashlib
import json
import subprocess
import sys

import numpy as np
import pytest
import soundfile as sf

import song_converter as sc


def tone(path, seconds=1.0, sr=16000, hz=220, level=0.2, stereo=False):
    t = np.arange(round(seconds * sr)) / sr
    y = level * np.sin(2 * np.pi * hz * t)
    if stereo:
        y = np.stack([y, y * 0.6], axis=1)
    sf.write(path, y, sr, subtype="FLOAT")


@pytest.mark.parametrize("vstereo,bstereo", [(False, False), (True, False), (False, True), (True, True)])
def test_mix_preserves_vocal_samples_and_source_files(tmp_path, vstereo, bstereo):
    vocal, beat, output = [tmp_path / p for p in ("v.wav", "b.wav", "mix.wav")]
    tone(vocal, stereo=vstereo)
    tone(beat, sr=22050, hz=110, level=0.9, stereo=bstereo)
    original = [p.read_bytes() for p in (vocal, beat)]
    sc.combine_tracks(vocal, beat, output)
    mixed, sr = sf.read(output, dtype="float32", always_2d=True)
    adapted, _ = sf.read(tmp_path / "mix_adapted_beat.wav", dtype="float32", always_2d=True)
    expected, _ = sf.read(vocal, dtype="float32", always_2d=True)
    if expected.shape[1] != mixed.shape[1]:
        expected = np.repeat(expected, mixed.shape[1], axis=1)
    assert sr == 16000 and mixed.shape == expected.shape
    np.testing.assert_allclose(mixed - adapted, expected, atol=8e-8, rtol=0)
    assert np.max(np.abs(mixed)) < 1
    assert [p.read_bytes() for p in (vocal, beat)] == original
    report = json.loads(output.with_suffix(".mix.json").read_text())
    assert report["vocal_sha256"] == hashlib.sha256(original[0]).hexdigest()
    assert report["vocal_modified"] is False


@pytest.mark.parametrize("seconds", [0.85, 1.15])
def test_only_beat_is_stretched_and_pitch_is_preserved(tmp_path, seconds):
    vocal, beat, out = [tmp_path / p for p in ("v.wav", "b.wav", "mix.wav")]
    tone(vocal)
    tone(beat, seconds=seconds, hz=440, stereo=True)
    sc.combine_tracks(vocal, beat, out)
    adapted, sr = sf.read(tmp_path / "mix_adapted_beat.wav", always_2d=True)
    assert len(adapted) == sr
    spectrum = np.abs(np.fft.rfft(adapted[:, 0]))
    assert np.fft.rfftfreq(len(adapted), 1 / sr)[spectrum.argmax()] == pytest.approx(440, abs=2)
    mixed, _ = sf.read(out, always_2d=True)
    expected, _ = sf.read(vocal, always_2d=True)
    np.testing.assert_allclose(mixed - adapted, np.repeat(expected, 2, axis=1), atol=8e-8)


@pytest.mark.parametrize("invalid", ["silent", "nan", "clipped", "empty"])
def test_invalid_clone_fails_without_output(tmp_path, invalid):
    vocal, beat, out = [tmp_path / p for p in ("v.wav", "b.wav", "mix.wav")]
    data = {"silent": np.zeros(100), "nan": np.full(100, np.nan),
            "clipped": np.ones(100), "empty": np.zeros(0)}[invalid]
    sf.write(vocal, data, 16000, subtype="FLOAT")
    tone(beat)
    with pytest.raises(ValueError):
        sc.combine_tracks(vocal, beat, out)
    assert not out.exists()


def test_extreme_mismatch_and_missing_stretcher_fail_closed(tmp_path, monkeypatch):
    vocal, beat, out = [tmp_path / p for p in ("v.wav", "b.wav", "mix.wav")]
    tone(vocal)
    tone(beat, seconds=0.4)
    with pytest.raises(ValueError, match="duration"):
        sc.combine_tracks(vocal, beat, out)
    tone(beat, seconds=0.9)
    monkeypatch.setattr(sc, "HAS_LIBROSA", False)
    with pytest.raises(RuntimeError, match="librosa"):
        sc.combine_tracks(vocal, beat, out)
    assert not out.exists()


def test_source_overwrite_and_vocal_gain_are_rejected(tmp_path):
    vocal, beat = tmp_path / "v.wav", tmp_path / "b.wav"
    tone(vocal)
    tone(beat)
    before = vocal.read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        sc.combine_tracks(vocal, beat, vocal)
    with pytest.raises(ValueError, match="vocals_gain_db"):
        sc.combine_tracks(vocal, beat, tmp_path / "mix.wav", vocals_gain_db=3)
    assert vocal.read_bytes() == before


def test_failed_conversion_never_mixes(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "separate_vocals", lambda *a, **k: ("v.wav", "b.wav", "demucs"))
    monkeypatch.setattr(sc, "convert_vocals", lambda *a, **k: (False, "engine failed"))
    monkeypatch.setattr(sc, "combine_tracks", lambda *a, **k: pytest.fail("mixed a failed clone"))
    with pytest.raises(RuntimeError, match="engine failed"):
        sc.change_song("source.wav", {"name": "test"}, tmp_path)


def test_mix_cli(tmp_path):
    vocal, beat, out = [tmp_path / p for p in ("v.wav", "b.wav", "mix.wav")]
    tone(vocal)
    tone(beat, hz=110)
    result = subprocess.run([sys.executable, "song_pipeline_cli.py", "mix", "--vocals", str(vocal),
                             "--beat", str(beat), "--output", str(out)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["output"] == str(out)


def test_production_song_preserves_clone_and_uses_lossless_delivery(tmp_path, monkeypatch):
    vocal, beat = tmp_path / "v.wav", tmp_path / "b.wav"
    tone(vocal)
    tone(beat, seconds=0.9, hz=110)
    monkeypatch.setattr(sc, "separate_vocals", lambda *a, **k: (str(vocal), str(beat), "demucs"))

    def convert(_source, _profile, output, *args, **kwargs):
        output.write_bytes(vocal.read_bytes())
        return True, "synthetic conversion fixture"

    monkeypatch.setattr(sc, "convert_vocals", convert)
    monkeypatch.setattr(sc, "polish_converted_vocals", lambda *a: pytest.fail("modified the clone"))
    output, steps = sc.change_song("original.mp3", {"name": "test"}, tmp_path / "out",
                                   source_matched_export=True)
    assert output.endswith(".wav")
    assert "delivery" not in steps
    assert (tmp_path / "out" / "converted_vocals.wav").read_bytes() == vocal.read_bytes()
    mixed, sr = sf.read(output, always_2d=True)
    adapted, _ = sf.read(steps["adapted_beat"], always_2d=True)
    original, _ = sf.read(vocal, always_2d=True)
    assert sr == 16000
    np.testing.assert_allclose(mixed - adapted, original, atol=8e-8)
