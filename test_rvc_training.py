#!/usr/bin/env python3
"""Tests for the authorized RVC model lifecycle."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from rvc_training import (
    RvcTrainingError,
    import_rvc_model,
    validate_training_dataset,
)


def _write(path: Path, seconds: float, amplitude: float = 0.15) -> None:
    sr = 22050
    t = np.linspace(0, seconds, int(sr * seconds), endpoint=False)
    sf.write(path, (amplitude * np.sin(2 * np.pi * 180 * t)).astype("float32"), sr)


def test_dataset_validation_requires_real_training_material(tmp_path: Path) -> None:
    _write(tmp_path / "one.wav", 2.0)

    try:
        validate_training_dataset(tmp_path, min_files=2, min_duration_s=3.0)
    except RvcTrainingError as exc:
        assert "at least 2" in str(exc)
    else:
        raise AssertionError("a one-file dataset must not pass RVC readiness checks")


def test_dataset_validation_reports_duration_and_quality(tmp_path: Path) -> None:
    _write(tmp_path / "one.wav", 2.0)
    _write(tmp_path / "two.wav", 2.0)

    report = validate_training_dataset(tmp_path, min_files=2, min_duration_s=3.0)

    assert report["file_count"] == 2
    assert report["duration_s"] >= 3.9
    assert 0.0 <= report["quality_score"] <= 1.0
    assert report["ready"] is True


def test_import_rvc_model_registers_profile_and_optional_index(tmp_path: Path) -> None:
    model = tmp_path / "trained.pth"
    index = tmp_path / "trained.index"
    model.write_bytes(b"RVC" + b"x" * 20_000)
    index.write_bytes(b"index" * 100)
    voice_dir = tmp_path / "voices" / "authorized_voice"
    voice_dir.mkdir(parents=True)
    profile_path = voice_dir / "voice_profile.json"
    profile_path.write_text(json.dumps({"name": "authorized_voice", "methods": {"dsp": True}}))

    profile = import_rvc_model(model, voice_dir, index_path=index)

    assert (voice_dir / "rvc_model.pth").exists()
    assert (voice_dir / "rvc_model.index").exists()
    assert profile["rvc_available"] is True
    assert profile["preferred_engine"] == "RVC"
    assert profile["methods"]["rvc"] is True
    saved = json.loads(profile_path.read_text())
    assert saved["rvc_model"] == "rvc_model.pth"


def test_import_rvc_model_rejects_tiny_or_missing_models(tmp_path: Path) -> None:
    voice_dir = tmp_path / "voice"
    voice_dir.mkdir()
    tiny = tmp_path / "tiny.pth"
    tiny.write_bytes(b"not a model")

    try:
        import_rvc_model(tiny, voice_dir)
    except RvcTrainingError as exc:
        assert "10 KB" in str(exc)
    else:
        raise AssertionError("invalid RVC artifacts must be rejected")


if __name__ == "__main__":
    import tempfile

    tests = [
        test_dataset_validation_requires_real_training_material,
        test_dataset_validation_reports_duration_and_quality,
        test_import_rvc_model_registers_profile_and_optional_index,
        test_import_rvc_model_rejects_tiny_or_missing_models,
    ]
    for test in tests:
        with tempfile.TemporaryDirectory() as directory:
            test(Path(directory))
    print("RVC training lifecycle tests passed")
