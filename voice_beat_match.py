"""Explainable voice <-> beat compatibility scoring.

This is a production-selection heuristic, not speaker identity or clone accuracy.
It compares rhythm pocket, loudness/energy, spectral competition, and vocal
fundamental-frequency room. It can rank voices for one beat or beats for one
voice without modifying either source.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from song_converter import _load_mono, band_energy_profile, estimate_pitch

try:
    import librosa

    HAS_LIBROSA = True
except ImportError:  # pragma: no cover
    HAS_LIBROSA = False


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _rms(y: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(y)))) if y.size else 0.0


def _tempo_bpm(y: np.ndarray, sr: int) -> float:
    if not HAS_LIBROSA or y.size < sr:
        return 0.0
    try:
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        value = float(np.asarray(tempo).reshape(-1)[0])
        return value if math.isfinite(value) else 0.0
    except Exception:
        return 0.0


def _spectral_centroid(y: np.ndarray, sr: int) -> float:
    if y.size == 0:
        return 0.0
    if HAS_LIBROSA:
        try:
            centroid = librosa.feature.spectral_centroid(y=y, sr=sr)
            return float(np.mean(centroid))
        except Exception:
            pass
    spec = np.abs(np.fft.rfft(y))
    freqs = np.fft.rfftfreq(y.size, 1.0 / sr)
    total = float(np.sum(spec))
    return float(np.sum(spec * freqs) / total) if total > 1e-12 else 0.0


def _onset_rate(y: np.ndarray, sr: int) -> float:
    if not HAS_LIBROSA or y.size < sr // 2:
        return 0.0
    try:
        onsets = librosa.onset.onset_detect(y=y, sr=sr, units="time")
        duration = max(len(y) / float(sr), 1e-6)
        return float(len(onsets) / duration)
    except Exception:
        return 0.0


def analyze_audio(path: str | Path, sr: int = 22050) -> dict[str, Any]:
    y = _load_mono(path, sr)
    median_f0, f0_std = estimate_pitch(y, sr)
    return {
        "path": str(path),
        "sample_rate": sr,
        "duration_s": round(len(y) / float(sr), 3) if sr else 0.0,
        "tempo_bpm": round(_tempo_bpm(y, sr), 3),
        "onset_rate_hz": round(_onset_rate(y, sr), 4),
        "rms": round(_rms(y), 6),
        "centroid_hz": round(_spectral_centroid(y, sr), 3),
        "median_f0_hz": round(float(median_f0), 3),
        "f0_std_hz": round(float(f0_std), 3),
        "spectral_profile": [round(float(v), 5) for v in band_energy_profile(y, sr, 16)],
    }


def _profile_reference(profile: dict[str, Any]) -> str | None:
    reference = profile.get("reference") or profile.get("reference_audio")
    if not reference:
        return None
    path = Path(str(reference))
    if path.exists():
        return str(path)
    voice_dir = profile.get("voice_dir")
    if voice_dir:
        candidate = Path(str(voice_dir)) / path
        if candidate.exists():
            return str(candidate)
    return None


def voice_features(profile: dict[str, Any]) -> dict[str, Any]:
    audio_profile = profile.get("audio_profile") or {}
    reference = _profile_reference(profile)
    derived = analyze_audio(reference) if reference else {}

    spectral = audio_profile.get("spectral_envelope") or derived.get("spectral_profile") or [0.0] * 16
    if len(spectral) != 16:
        spectral = (list(spectral) + [0.0] * 16)[:16]

    return {
        "name": str(profile.get("name") or "voice"),
        "reference": reference,
        "tempo_bpm": float(derived.get("tempo_bpm") or 0.0),
        "onset_rate_hz": float(derived.get("onset_rate_hz") or 0.0),
        "rms": float(audio_profile.get("rms") or derived.get("rms") or 0.0),
        "centroid_hz": float(derived.get("centroid_hz") or 0.0),
        "median_f0_hz": float(audio_profile.get("median_f0_hz") or derived.get("median_f0_hz") or 0.0),
        "spectral_profile": [float(v) for v in spectral],
    }


def _tempo_compatibility(voice_bpm: float, beat_bpm: float) -> float:
    if voice_bpm <= 0 or beat_bpm <= 0:
        return 0.65
    candidates = [beat_bpm, beat_bpm / 2.0, beat_bpm * 2.0]
    diff = min(abs(voice_bpm - value) for value in candidates if value > 0)
    return _clamp01(math.exp(-((diff / 22.0) ** 2)))


def _energy_compatibility(voice_rms: float, beat_rms: float) -> float:
    if voice_rms <= 0 or beat_rms <= 0:
        return 0.65
    voice_db = 20.0 * math.log10(max(voice_rms, 1e-8))
    beat_db = 20.0 * math.log10(max(beat_rms, 1e-8))
    # A voice usually sits naturally when the unmastered bed is somewhat louder,
    # but extreme level mismatch predicts more gain riding in the final mix.
    desired = 7.0
    diff = abs((beat_db - voice_db) - desired)
    return _clamp01(math.exp(-((diff / 12.0) ** 2)))


def _spectral_space(voice_profile: Iterable[float], beat_profile: Iterable[float]) -> float:
    voice = np.asarray(list(voice_profile), dtype=np.float64)
    beat = np.asarray(list(beat_profile), dtype=np.float64)
    n = min(voice.size, beat.size)
    if n == 0:
        return 0.65
    # Profiles are relative dB (0 = strongest band). Convert to positive energy
    # weights. Lower overlap means more spectral room for the vocal.
    vw = np.power(10.0, voice[:n] / 20.0)
    bw = np.power(10.0, beat[:n] / 20.0)
    if np.linalg.norm(vw) < 1e-9 or np.linalg.norm(bw) < 1e-9:
        return 0.65
    overlap = float(np.dot(vw / np.linalg.norm(vw), bw / np.linalg.norm(bw)))
    return _clamp01(1.15 - overlap)


def _pitch_room(median_f0_hz: float, beat_profile: Iterable[float], sr: int = 22050) -> float:
    bands = np.asarray(list(beat_profile), dtype=np.float64)
    if median_f0_hz <= 0 or bands.size == 0:
        return 0.65
    # Approximate the 16 log-spaced bands used by band_energy_profile and inspect
    # the fundamental plus first two harmonics. Less beat energy there = more room.
    lo = 20.0
    hi = sr / 2.0
    edges = np.geomspace(lo, hi, bands.size + 1)
    weights = []
    for harmonic in (1.0, 2.0, 3.0):
        hz = median_f0_hz * harmonic
        idx = int(np.searchsorted(edges, hz, side="right") - 1)
        if 0 <= idx < bands.size:
            weights.append(float(np.power(10.0, bands[idx] / 20.0)))
    if not weights:
        return 0.65
    energy = float(np.mean(weights))
    return _clamp01(1.0 - 0.65 * energy)


def score_voice_beat(profile: dict[str, Any], beat_path: str | Path) -> dict[str, Any]:
    voice = voice_features(profile)
    beat = analyze_audio(beat_path)

    factors = {
        "rhythm_pocket": _tempo_compatibility(voice["tempo_bpm"], beat["tempo_bpm"]),
        "energy_balance": _energy_compatibility(voice["rms"], beat["rms"]),
        "spectral_space": _spectral_space(voice["spectral_profile"], beat["spectral_profile"]),
        "pitch_room": _pitch_room(voice["median_f0_hz"], beat["spectral_profile"]),
    }
    weights = {
        "rhythm_pocket": 0.30,
        "energy_balance": 0.20,
        "spectral_space": 0.30,
        "pitch_room": 0.20,
    }
    score = 100.0 * sum(factors[key] * weights[key] for key in weights)
    reasons = [
        f"rhythm pocket {factors['rhythm_pocket'] * 100:.0f}%",
        f"spectral room {factors['spectral_space'] * 100:.0f}%",
        f"energy balance {factors['energy_balance'] * 100:.0f}%",
        f"pitch room {factors['pitch_room'] * 100:.0f}%",
    ]
    return {
        "voice": voice["name"],
        "beat": str(beat_path),
        "fit_score": round(score, 1),
        "factors": {key: round(value * 100.0, 1) for key, value in factors.items()},
        "reason": " · ".join(reasons),
        "voice_features": voice,
        "beat_features": beat,
        "score_type": "arrangement_compatibility_heuristic",
        "note": "This predicts mix/arrangement fit; it is not speaker identity, clone accuracy, or artistic quality.",
    }


def rank_matrix(
    profiles: Iterable[dict[str, Any]],
    beat_paths: Iterable[str | Path],
) -> dict[str, Any]:
    profile_list = list(profiles)
    beats = [str(path) for path in beat_paths]
    rows = [score_voice_beat(profile, beat) for profile in profile_list for beat in beats]

    best_voice_for_each_beat = []
    for beat in beats:
        matches = [row for row in rows if row["beat"] == beat]
        if matches:
            best_voice_for_each_beat.append(max(matches, key=lambda row: row["fit_score"]))

    best_beat_for_each_voice = []
    for profile in profile_list:
        name = str(profile.get("name") or "voice")
        matches = [row for row in rows if row["voice"] == name]
        if matches:
            best_beat_for_each_voice.append(max(matches, key=lambda row: row["fit_score"]))

    return {
        "matches": sorted(rows, key=lambda row: row["fit_score"], reverse=True),
        "best_voice_for_each_beat": best_voice_for_each_beat,
        "best_beat_for_each_voice": best_beat_for_each_voice,
    }


def write_match_report(report: dict[str, Any], output: str | Path) -> str:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return str(path)
