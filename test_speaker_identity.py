#!/usr/bin/env python3
"""Speaker-identity and precision-gate tests. No celebrity fixtures."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from speaker_identity import (
    attach_embedding_to_profile,
    cosine_similarity,
    extract_embedding,
    is_neural_engine,
    precision_verdict,
    score_identity,
)


def _tone(path: Path, hz: float, seconds: float = 2.0, sr: int = 16000) -> None:
    t = np.linspace(0, seconds, int(sr * seconds), False)
    y = (0.22 * np.sin(2 * np.pi * hz * t) + 0.05 * np.sin(2 * np.pi * hz * 2 * t)).astype("float32")
    sf.write(path, y, sr)


def test_same_clip_has_high_identity(tmp_path: Path) -> None:
    wav = tmp_path / "same.wav"
    _tone(wav, 160)
    emb = extract_embedding(wav)
    assert emb["dim"] > 8
    ident = score_identity(reference_embedding=emb, output_audio=wav)
    assert ident["identity"] > 0.97


def test_different_spectra_are_less_similar(tmp_path: Path) -> None:
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    _tone(a, 110)
    _tone(b, 340)
    ea = extract_embedding(a)
    eb = extract_embedding(b)
    same = cosine_similarity(ea["vector"], ea["vector"])
    diff = cosine_similarity(ea["vector"], eb["vector"])
    assert same > diff
    assert same > 0.99


def test_dsp_cannot_claim_near_precision() -> None:
    verdict = precision_verdict(
        identity=0.99,
        engine="gTTS + DSP",
        reference_duration_s=40.0,
        reference_quality=0.9,
        quality_target="pro",
    )
    assert verdict["level"] != "near_precision"
    assert verdict["neural_engine"] is False
    assert verdict["meets_near_precision"] is False


def test_neural_long_reference_can_claim_near_precision() -> None:
    verdict = precision_verdict(
        identity=0.90,
        engine="RVC",
        reference_duration_s=22.0,
        reference_quality=0.8,
        quality_target="pro",
    )
    assert verdict["meets_near_precision"] is True
    assert is_neural_engine("RVC + polish") is True


def test_profile_stores_embedding(tmp_path: Path) -> None:
    wav = tmp_path / "ref.wav"
    _tone(wav, 180)
    profile = {"name": "unit_voice", "reference": str(wav), "audio_profile": {}}
    attach_embedding_to_profile(profile, wav)
    stored = profile["audio_profile"]["speaker_embedding"]
    assert stored["vector"]
    out = tmp_path / "profile.json"
    out.write_text(json.dumps(profile))
    loaded = json.loads(out.read_text())
    assert loaded["audio_profile"]["speaker_embedding"]["dim"] == stored["dim"]


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        test_same_clip_has_high_identity(base)
        test_different_spectra_are_less_similar(base)
        test_dsp_cannot_claim_near_precision()
        test_neural_long_reference_can_claim_near_precision()
        test_profile_stores_embedding(base)
    print("speaker identity tests passed")
