#!/usr/bin/env python3
"""Schema/asset smoke tests for the legacy Pacaveli analysis profile.

This file deliberately does not claim that EQ/pitch effects constitute voice cloning.
Production authorized cloning is exercised through the RVC/Qwen pipelines.
"""
from __future__ import annotations

import json
from pathlib import Path


def test_pacaveli_transformation() -> None:
    profile_path = Path("models/pacaveli/voice_profile.json")
    assert profile_path.is_file(), "Pacaveli analysis profile is missing"

    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert profile.get("speaker") == "Pacaveli"
    assert profile.get("model_name") == "pacaveli"
    assert profile.get("type") == "voice_clone"

    characteristics = profile.get("characteristics")
    assert isinstance(characteristics, dict)
    for key in (
        "voice_type",
        "pitch_mean_hz",
        "pitch_median_hz",
        "pitch_dominant_hz",
        "pitch_conversion_target_hz",
        "spectral_centroid_hz",
    ):
        assert key in characteristics, f"missing characteristic: {key}"

    assert characteristics["pitch_mean_hz"] > 0
    assert characteristics["pitch_median_hz"] > 0
    assert characteristics["spectral_centroid_hz"] > 0

    persona = profile.get("persona")
    assert isinstance(persona, dict)
    assert persona.get("style")
    assert persona.get("delivery")


if __name__ == "__main__":
    test_pacaveli_transformation()
    print("Pacaveli profile smoke test passed")
