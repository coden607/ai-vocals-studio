#!/usr/bin/env python3
"""Focused tests for the librosa-free numpy fallbacks in song_converter.

These monkeypatch HAS_LIBROSA off so the fallback code paths are exercised
even on hosts where librosa is installed — proving the studio still loads,
gates, mixes, and profiles audio on constrained machines.
"""
from __future__ import annotations

import numpy as np
import pytest
import soundfile as sf

import song_converter as sc

SR = 22050


def _tone(hz: float, seconds: float = 0.5, sr: int = SR) -> np.ndarray:
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    return (0.3 * np.sin(2 * np.pi * hz * t)
            + 0.05 * np.sin(2 * np.pi * hz * 2 * t)).astype(np.float32)


def _peak_hz(y: np.ndarray, sr: int) -> float:
    spec = np.abs(np.fft.rfft(y * np.hanning(y.size)))
    return float(np.fft.rfftfreq(y.size, 1.0 / sr)[int(np.argmax(spec))])


@pytest.fixture
def no_librosa(monkeypatch):
    monkeypatch.setattr(sc, "HAS_LIBROSA", False)
    return monkeypatch


# ── resampler ────────────────────────────────────────────────────
def test_sinc_resample_preserves_length_ratio(no_librosa):
    y = _tone(220.0, seconds=1.0, sr=22050)
    up = sc._resample_sinc(y, 22050, 44100)
    assert up.size == pytest.approx(y.size * 2, abs=1)
    down = sc._resample_sinc(y, 22050, 11025)
    assert down.size == pytest.approx(y.size // 2, abs=1)


def test_sinc_resample_preserves_tone_frequency(no_librosa):
    y = _tone(220.0, seconds=1.0, sr=22050)
    up = sc._resample_sinc(y, 22050, 44100)
    assert _peak_hz(up, 44100) == pytest.approx(220.0, abs=8.0)
    down = sc._resample_sinc(y, 22050, 11025)  # exercises anti-alias branch
    assert _peak_hz(down, 11025) == pytest.approx(220.0, abs=8.0)


def test_sinc_resample_identity_and_empty(no_librosa):
    y = _tone(220.0)
    assert np.array_equal(sc._resample_sinc(y, SR, SR), y)
    assert sc._resample_sinc(np.zeros(0, dtype=np.float32), SR, 44100).size == 0


def test_load_mono_honors_target_rate_without_librosa(no_librosa, tmp_path):
    wav = tmp_path / "tone44k.wav"
    sf.write(wav, _tone(330.0, sr=44100), 44100)
    y = sc._load_mono(wav, 22050)
    assert y.dtype == np.float32
    assert abs(y.size - int(0.5 * 22050)) <= 2


# ── pitch / voiced gate ──────────────────────────────────────────
def test_voiced_fraction_tone_is_voiced_without_librosa(no_librosa):
    assert sc.voiced_fraction(_tone(220.0), SR) >= 0.8


def test_voiced_fraction_silence_is_zero_without_librosa(no_librosa):
    assert sc.voiced_fraction(np.zeros(SR // 2, dtype=np.float32), SR) == 0.0


def test_voiced_fraction_noise_is_low_without_librosa(no_librosa):
    rng = np.random.default_rng(7)
    noise = (0.2 * rng.standard_normal(SR // 2)).astype(np.float32)
    assert sc.voiced_fraction(noise, SR) < 0.2


def test_estimate_pitch_fallback_finds_tone(no_librosa):
    median_f0, std_f0 = sc.estimate_pitch(_tone(220.0), SR)
    assert median_f0 == pytest.approx(220.0, rel=0.05)
    assert std_f0 < 30.0


# ── band profile ─────────────────────────────────────────────────
def test_band_energy_profile_fallback_matches_contract(no_librosa):
    bands = sc.band_energy_profile(_tone(220.0), SR, n_bands=16)
    assert len(bands) == 16
    assert all(np.isfinite(b) for b in bands)
    assert max(bands) == pytest.approx(0.0, abs=1e-6)  # peak band normalized to 0 dB
    assert any(b < -3.0 for b in bands)               # tonal → energy concentrated


# ── combine ──────────────────────────────────────────────────────
def test_combine_tracks_resamples_mismatched_rates(no_librosa, tmp_path):
    v = tmp_path / "vocals.wav"
    i = tmp_path / "inst.wav"
    out = tmp_path / "mix.wav"
    sf.write(v, _tone(220.0, sr=SR), SR)
    sf.write(i, _tone(110.0, sr=44100), 44100)
    sc.combine_tracks(v, i, out)
    mixed, out_sr = sf.read(out, dtype="float32")
    assert out_sr == SR
    assert mixed.shape[0] == int(0.5 * SR)
    assert np.max(np.abs(mixed)) <= 1.0
