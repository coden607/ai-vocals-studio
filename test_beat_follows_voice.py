"""
The beat follows the voice, not the other way round.

Before 2026-10-15 `dsp_morph_vocals` pitch-shifted the vocal into the target
voice's register (12*log2(target/source), clamped +/-7 st) while the separated
instrumental stayed in the original key, so the output was key-mismatched; and
`convert_vocals` hardcoded `pitch_shift=0` for RVC, which forced every neural
render into the source singer's key. These tests pin the contract that the
performance and the beat always move by the SAME interval, and that tempo
never changes when the key does.
"""
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

import song_converter as sc


def _tone(path: Path, sr: int, seconds: float, hz: float) -> None:
    t = np.arange(int(sr * seconds), dtype=np.float32) / sr
    y = (0.2 * np.sin(2 * np.pi * hz * t)).astype(np.float32)
    sf.write(path, y, sr)


def _dominant_hz(y: np.ndarray, sr: int) -> float:
    if y.ndim > 1:
        y = y[:, 0]
    window = np.hanning(len(y)).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(y * window))
    return float(np.fft.rfftfreq(len(y), 1.0 / sr)[int(np.argmax(spectrum))])


def test_pitch_shift_hits_the_interval_and_keeps_the_duration():
    sr = 22050
    t = np.arange(int(sr * 2.0), dtype=np.float32) / sr
    y = (0.3 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)

    for semitones in (12.0, -12.0, 7.0, -5.0):
        shifted = sc.pitch_shift_semitones(y, sr, semitones)
        # Tempo must survive a key change: same number of samples.
        assert shifted.size == y.size, f"{semitones} st changed the duration"
        expected = 220.0 * 2.0 ** (semitones / 12.0)
        cents = 1200.0 * np.log2(_dominant_hz(shifted, sr) / expected)
        assert abs(cents) < 15.0, f"{semitones} st was off by {cents:.1f} cents"


def test_an_inaudible_shift_is_not_resynthesised():
    sr = 22050
    y = np.sin(2 * np.pi * 220.0 * np.arange(sr, dtype=np.float32) / sr).astype(np.float32)
    out = sc.pitch_shift_semitones(y, sr, 0.01)
    assert out is y or np.array_equal(out, y)


def test_voice_shift_is_the_interval_between_performance_and_voice(tmp_path):
    vocals = tmp_path / "vocals.wav"
    _tone(vocals, 22050, 1.0, 220.0)

    # A voice a fourth below the performance pulls the whole song down a fourth.
    down = sc.voice_shift_semitones(vocals, sc.profile_for_pitch(165.0))
    assert down == pytest.approx(-4.98, abs=0.6)
    # An octave above is clamped: past MAX_KEY_SHIFT_SEMITONES a transposition
    # stops sounding like a key change.
    up = sc.voice_shift_semitones(vocals, sc.profile_for_pitch(440.0))
    assert up == pytest.approx(sc.MAX_KEY_SHIFT_SEMITONES, abs=0.01)


def test_an_unmeasurable_voice_never_silently_transposes_a_song(tmp_path):
    vocals = tmp_path / "vocals.wav"
    _tone(vocals, 22050, 1.0, 220.0)
    # No profile pitch, a nonsense pitch, and silence all mean "do not move".
    assert sc.voice_shift_semitones(vocals, {"name": "x"}) == 0.0
    assert sc.voice_shift_semitones(vocals, sc.profile_for_pitch(0.0)) == 0.0
    silent = tmp_path / "silent.wav"
    sf.write(silent, np.zeros(22050, dtype=np.float32), 22050)
    assert sc.voice_shift_semitones(silent, sc.profile_for_pitch(110.0)) == 0.0


def test_the_beat_is_transposed_by_the_same_interval_as_the_voice(tmp_path):
    sr = 22050
    inst = tmp_path / "instrumental.wav"
    _tone(inst, sr, 1.0, 110.0)

    out_path, applied = sc.match_instrumental_to_voice(inst, -5.0, tmp_path / "beat.wav")
    assert applied == pytest.approx(-5.0)
    assert Path(out_path) == tmp_path / "beat.wav"

    beat, beat_sr = sf.read(out_path, dtype="float32")
    assert beat_sr == sr
    # The beat moved down a fourth, and its length - so its tempo - did not.
    expected = 110.0 * 2.0 ** (-5.0 / 12.0)
    cents = 1200.0 * np.log2(_dominant_hz(beat, beat_sr) / expected)
    assert abs(cents) < 15.0
    assert beat.shape[0] == sr


def test_a_negligible_beat_shift_leaves_the_original_file_alone(tmp_path):
    inst = tmp_path / "instrumental.wav"
    _tone(inst, 22050, 0.5, 110.0)
    out_path, applied = sc.match_instrumental_to_voice(inst, 0.0, tmp_path / "beat.wav")
    assert applied == 0.0
    assert Path(out_path) == inst, "an unshifted beat must not be resynthesised"
    assert not (tmp_path / "beat.wav").exists()


def _stub_pipeline(monkeypatch, tmp_path, sr=22050):
    """Separation and conversion are stubbed; only the pitch contract is under test."""
    vocals = tmp_path / "isolated_vocals.wav"
    inst = tmp_path / "instrumental.wav"
    _tone(vocals, sr, 1.0, 220.0)
    _tone(inst, sr, 1.0, 110.0)
    seen = {}

    def fake_separate(song_path, work_dir, method, progress_cb=None, allow_fallback=True):
        return str(vocals), str(inst), "demucs"

    def fake_convert(vocals_path, profile, out_path, work_dir, progress_cb=None,
                     require_neural=False, pitch_steps=None):
        seen["convert_input"] = Path(vocals_path).name
        seen["pitch_steps"] = pitch_steps
        # Echo the input so the register move stays observable downstream.
        audio, audio_sr = sf.read(str(vocals_path), dtype="float32")
        sf.write(Path(out_path), audio, audio_sr)
        return True, "stub conversion"

    def fake_combine(vocals_path, instrumental_path, out_path, vocals_gain_db=0.0, progress_cb=None):
        seen["remix_instrumental"] = Path(instrumental_path).name
        audio, audio_sr = sf.read(str(instrumental_path), dtype="float32")
        sf.write(Path(out_path), audio, audio_sr)
        return str(out_path)

    monkeypatch.setattr(sc, "separate_vocals", fake_separate)
    monkeypatch.setattr(sc, "convert_vocals", fake_convert)
    monkeypatch.setattr(sc, "combine_tracks", fake_combine)
    return seen


def test_change_song_moves_voice_and_beat_by_one_interval(tmp_path, monkeypatch):
    source = tmp_path / "song.wav"
    _tone(source, 22050, 1.0, 220.0)
    seen = _stub_pipeline(monkeypatch, tmp_path)

    out, steps = sc.change_song(
        source,
        sc.profile_for_pitch(165.0),  # a voice a fourth below the performance
        tmp_path / "out",
        separation="demucs",
        source_matched_export=False,
    )

    assert steps["beat_follows_voice"] == "yes"
    voice_shift = float(steps["voice_shift_semitones"])
    assert voice_shift == pytest.approx(-4.98, abs=0.6)
    # The single most important invariant: one interval for both stems.
    assert float(steps["beat_key_shift"]) == pytest.approx(voice_shift, abs=0.01)
    assert float(steps["vocal_register_shift"]) == pytest.approx(voice_shift, abs=0.01)

    # The performance was moved before conversion, and no engine was asked to
    # apply a second shift the beat would not know about.
    assert seen["convert_input"] == "vocals_in_voice_register.wav"
    assert seen["pitch_steps"] == 0.0
    assert seen["remix_instrumental"] == "instrumental_in_voice_key.wav"
    assert Path(out).exists()


def test_change_song_can_keep_the_original_key_on_request(tmp_path, monkeypatch):
    source = tmp_path / "song.wav"
    _tone(source, 22050, 1.0, 220.0)
    seen = _stub_pipeline(monkeypatch, tmp_path)

    _, steps = sc.change_song(
        source,
        sc.profile_for_pitch(110.0),
        tmp_path / "out",
        separation="demucs",
        source_matched_export=False,
        match_beat_to_voice=False,
    )

    assert steps["beat_follows_voice"] == "no (original key kept)"
    assert "beat_key_shift" not in steps
    # Opting out restores the old behaviour: untouched stems either side.
    assert seen["convert_input"] == "isolated_vocals.wav"
    assert seen["remix_instrumental"] == "instrumental.wav"


def test_separation_still_happens_before_any_pitch_decision(tmp_path, monkeypatch):
    """Demucs first is the standing contract; key matching must not reorder it."""
    source = tmp_path / "song.wav"
    _tone(source, 22050, 0.5, 220.0)
    order = []

    vocals = tmp_path / "isolated_vocals.wav"
    inst = tmp_path / "instrumental.wav"
    _tone(vocals, 22050, 0.5, 220.0)
    _tone(inst, 22050, 0.5, 110.0)

    def fake_separate(song_path, work_dir, method, progress_cb=None, allow_fallback=True):
        order.append("separate")
        return str(vocals), str(inst), "demucs"

    real_shift = sc.voice_shift_semitones

    def spy_shift(vocals_path, profile, sr=22050):
        order.append("decide_pitch")
        return real_shift(vocals_path, profile, sr)

    def fake_convert(vocals_path, profile, out_path, work_dir, progress_cb=None,
                     require_neural=False, pitch_steps=None):
        order.append("convert")
        audio, audio_sr = sf.read(str(vocals_path), dtype="float32")
        sf.write(Path(out_path), audio, audio_sr)
        return True, "stub"

    def fake_combine(vocals_path, instrumental_path, out_path, vocals_gain_db=0.0, progress_cb=None):
        order.append("remix")
        sf.write(Path(out_path), np.zeros(1000, dtype=np.float32), 22050)
        return str(out_path)

    monkeypatch.setattr(sc, "separate_vocals", fake_separate)
    monkeypatch.setattr(sc, "voice_shift_semitones", spy_shift)
    monkeypatch.setattr(sc, "convert_vocals", fake_convert)
    monkeypatch.setattr(sc, "combine_tracks", fake_combine)

    sc.change_song(source, sc.profile_for_pitch(130.0), tmp_path / "out",
                   separation="demucs", source_matched_export=False)

    assert order == ["separate", "decide_pitch", "convert", "remix"]


def test_rvc_receives_the_pitch_decision_instead_of_a_hardcoded_zero(tmp_path, monkeypatch):
    vocals = tmp_path / "vocals.wav"
    _tone(vocals, 22050, 0.5, 220.0)
    voice_dir = tmp_path / "voices" / "Someone"
    voice_dir.mkdir(parents=True)
    (voice_dir / "Someone.pth").write_bytes(b"x" * 20_000)
    captured = {}

    class FakeEngine:
        def __init__(self, models_dir):
            captured["models_dir"] = models_dir

        def convert(self, name, src, dst, pitch_shift=0, progress_cb=None):
            captured["pitch_shift"] = pitch_shift
            sf.write(Path(dst), np.zeros(1000, dtype=np.float32), 22050)
            return True, "RVC"

    import sys
    import types
    module = types.ModuleType("rvc_engine")
    module.RvcEngine = FakeEngine
    monkeypatch.setitem(sys.modules, "rvc_engine", module)

    ok, msg = sc.convert_vocals(
        vocals,
        {"name": "Someone", "voice_dir": str(voice_dir)},
        tmp_path / "out.wav",
        tmp_path,
        pitch_steps=-4.4,
    )

    assert ok and "RVC" in msg
    # Rounded to whole semitones for RVC, but no longer pinned to zero.
    assert captured["pitch_shift"] == -4


def test_a_clamped_transposition_is_reported_not_hidden(tmp_path, monkeypatch):
    source = tmp_path / "song.wav"
    _tone(source, 22050, 1.0, 220.0)
    _stub_pipeline(monkeypatch, tmp_path)

    # An octave down is further than MAX_KEY_SHIFT_SEMITONES allows, so the
    # voice cannot fully reach its register and the caller must be told.
    _, steps = sc.change_song(
        source,
        sc.profile_for_pitch(110.0),
        tmp_path / "out",
        separation="demucs",
        source_matched_export=False,
    )

    assert float(steps["voice_shift_semitones"]) == pytest.approx(-sc.MAX_KEY_SHIFT_SEMITONES)
    assert "key_shift_clamped" in steps, "a clamped shift must be disclosed"
    assert "7" in steps["key_shift_clamped"]
