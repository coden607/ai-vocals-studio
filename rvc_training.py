#!/usr/bin/env python3
"""Authorized RVC dataset validation, model import, and training helpers.

This module does not manufacture a neural model from a JSON/DSP profile. It
only registers a real RVC artifact produced by a compatible trainer.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Iterable

import librosa
import numpy as np
import soundfile as sf


SUPPORTED_AUDIO = {".wav", ".flac", ".mp3", ".ogg", ".m4a", ".aiff", ".aac"}
MIN_MODEL_BYTES = 10_000


class RvcTrainingError(ValueError):
    """Raised when an RVC dataset or artifact is not safe to use."""


def _audio_files(source_dir: str | Path) -> list[Path]:
    root = Path(source_dir).expanduser()
    if not root.is_dir():
        raise RvcTrainingError(f"Training directory does not exist: {root}")
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO
    )


def _clip_quality(path: Path) -> tuple[float, float]:
    try:
        y, sr = librosa.load(path, sr=22050, mono=True)
    except Exception as exc:
        raise RvcTrainingError(f"Could not decode {path.name}: {exc}") from exc
    if y.size == 0:
        return 0.0, 0.0
    peak = float(np.max(np.abs(y)))
    clipping = float(np.mean(np.abs(y) >= 0.999))
    rms = float(np.sqrt(np.mean(np.square(y))))
    voiced = float(np.mean(np.abs(y) > max(0.008, rms * 0.25)))
    quality = min(1.0, max(0.0, 0.45 * voiced + 0.35 * min(1.0, rms / 0.08) + 0.20 * (1.0 - min(1.0, clipping * 20.0))))
    return float(len(y) / sr), quality


def validate_training_dataset(
    source_dir: str | Path,
    *,
    min_files: int = 3,
    min_duration_s: float = 90.0,
) -> dict:
    """Validate clean, authorized training material before expensive training."""
    files = _audio_files(source_dir)
    if len(files) < min_files:
        raise RvcTrainingError(
            f"RVC training requires at least {min_files} audio files; found {len(files)}."
        )

    durations: list[float] = []
    qualities: list[float] = []
    for path in files:
        duration, quality = _clip_quality(path)
        durations.append(duration)
        qualities.append(quality)

    total_duration = float(sum(durations))
    quality_score = float(np.mean(qualities)) if qualities else 0.0
    clipping_fraction = float(np.mean([
        _clipping_fraction(path) for path in files
    ]))
    ready = total_duration >= min_duration_s and quality_score >= 0.55 and clipping_fraction <= 0.005
    return {
        "ready": bool(ready),
        "file_count": len(files),
        "files": [str(path) for path in files],
        "duration_s": round(total_duration, 2),
        "quality_score": round(quality_score, 4),
        "clipping_fraction": round(clipping_fraction, 6),
        "minimums": {"files": min_files, "duration_s": min_duration_s, "quality_score": 0.55},
    }


def _clipping_fraction(path: Path) -> float:
    y, _ = librosa.load(path, sr=22050, mono=True)
    return float(np.mean(np.abs(y) >= 0.999)) if y.size else 1.0


def import_rvc_model(
    model_path: str | Path,
    voice_dir: str | Path,
    *,
    index_path: str | Path | None = None,
) -> dict:
    """Register a real RVC model and optional retrieval index for a voice."""
    model = Path(model_path).expanduser()
    if not model.is_file() or model.stat().st_size < MIN_MODEL_BYTES:
        raise RvcTrainingError("RVC model must be a real .pth artifact larger than 10 KB.")
    if model.suffix.lower() != ".pth":
        raise RvcTrainingError("RVC model must use the .pth extension.")

    target_dir = Path(voice_dir).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)
    target_model = target_dir / "rvc_model.pth"
    shutil.copy2(model, target_model)

    target_index = None
    if index_path is not None:
        index = Path(index_path).expanduser()
        if not index.is_file() or index.stat().st_size == 0 or index.suffix.lower() != ".index":
            raise RvcTrainingError("RVC index must be a non-empty .index artifact.")
        target_index = target_dir / "rvc_model.index"
        shutil.copy2(index, target_index)

    profile_path = target_dir / "voice_profile.json"
    profile = {}
    if profile_path.exists():
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RvcTrainingError(f"Invalid voice profile JSON: {profile_path}") from exc
    methods = dict(profile.get("methods") or {})
    methods.update({"dsp": True, "rvc": True})
    profile.update({
        "rvc_available": True,
        "preferred_engine": "RVC",
        "rvc_model": target_model.name,
        "rvc_index": target_index.name if target_index else None,
        "methods": methods,
    })
    profile_path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    return profile


def build_training_command(
    dataset_dir: str | Path,
    output_dir: str | Path,
    *,
    trainer: str = "rvc-train",
    epochs: int = 300,
) -> list[str]:
    """Build a deterministic command for an installed RVC trainer adapter."""
    if epochs < 1:
        raise RvcTrainingError("epochs must be positive")
    return [
        trainer,
        "--dataset",
        str(Path(dataset_dir).expanduser()),
        "--output",
        str(Path(output_dir).expanduser()),
        "--epochs",
        str(int(epochs)),
    ]


def run_training_command(command: Iterable[str], *, cwd: str | Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run an explicitly selected trainer; callers must validate first."""
    return subprocess.run(
        list(command),
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )
