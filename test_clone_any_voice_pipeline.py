#!/usr/bin/env python3
"""Smoke tests for the unified authorized voice cloning pipeline."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf


ROOT = Path(__file__).resolve().parent
PYTHON = Path(sys.executable)


def _write_tone(path: Path, hz: float, *, seconds: float = 2.0, sr: int = 22050) -> None:
    t = np.linspace(0, seconds, int(sr * seconds), False)
    y = (0.2 * np.sin(2 * np.pi * hz * t) + 0.05 * np.sin(2 * np.pi * hz * 2 * t)).astype("float32")
    sf.write(path, y, sr)


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PYTHON), "clone_any_voice.py", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_clip_conversion_writes_audio_and_report() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        ref = base / "ref.wav"
        target = base / "target.wav"
        out_dir = base / "out"
        _write_tone(ref, 150)
        _write_tone(target, 220)

        result = _run([
            "--voice-source", str(ref),
            "--name", "smoke_voice",
            "--target-audio", str(target),
            "--target-type", "clip",
            "--output-dir", str(out_dir),
            "--i-have-permission",
        ])

        assert result.returncode == 0, result.stdout + result.stderr
        converted = out_dir / "target_in_smoke_voice.wav"
        report = out_dir / "quality_report.json"
        assert converted.exists()
        assert report.exists()
        data = json.loads(report.read_text())
        assert data["estimated_accuracy"]["score"] >= 0
        assert data["estimated_accuracy"]["confidence"] > 0
        assert "identity" in data["estimated_accuracy"]
        precision = data["estimated_accuracy"].get("precision") or {}
        assert precision.get("level") in {"near_precision", "studio", "draft", "not_a_clone"}
        assert precision.get("meets_near_precision") is False


def test_instrumental_clip_requires_voiceover_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        ref = base / "ref.wav"
        beat = base / "beat.wav"
        _write_tone(ref, 150)
        sf.write(beat, np.zeros(22050, dtype="float32"), 22050)

        result = _run([
            "--voice-source", str(ref),
            "--name", "smoke_voice",
            "--target-audio", str(beat),
            "--target-type", "clip",
            "--output-dir", str(base / "out"),
            "--i-have-permission",
        ])

        assert result.returncode == 1
        assert "--target-type bed" in result.stdout


if __name__ == "__main__":
    test_clip_conversion_writes_audio_and_report()
    test_instrumental_clip_requires_voiceover_path()
    print("clone_any_voice pipeline smoke tests passed")
