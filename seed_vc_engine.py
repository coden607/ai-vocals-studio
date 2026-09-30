"""Seed-VC zero-shot voice-conversion adapter.

Seed-VC is an optional external GPL-3.0 runtime. We intentionally do not vendor
its source or model weights into this repository. Configure SEED_VC_DIR to a
checked-out Seed-VC tree. The adapter supports CPU inference and singing/rap
conversion with F0 conditioning.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

ProgressCB = Callable[[str, int], None]


def seed_vc_available() -> bool:
    root = Path(os.environ.get("SEED_VC_DIR", "")).expanduser()
    return bool(str(root) and (root / "inference.py").is_file())


def convert_seed_vc(
    source_audio: str | Path,
    reference_audio: str | Path,
    output_audio: str | Path,
    *,
    singing: bool = True,
    diffusion_steps: int = 30,
    progress_cb: Optional[ProgressCB] = None,
) -> str:
    """Run zero-shot Seed-VC and normalize its generated WAV to output_audio."""
    root_raw = os.environ.get("SEED_VC_DIR", "").strip()
    if not root_raw:
        raise RuntimeError("SEED_VC_DIR is not configured")
    root = Path(root_raw).expanduser().resolve()
    inference = root / "inference.py"
    if not inference.is_file():
        raise RuntimeError(f"Seed-VC inference.py not found under {root}")

    source = Path(source_audio).resolve()
    reference = Path(reference_audio).resolve()
    if not source.is_file() or not reference.is_file():
        raise RuntimeError("Seed-VC requires existing source and reference audio")

    out = Path(output_audio).resolve()
    run_dir = out.parent / ".seed_vc"
    run_dir.mkdir(parents=True, exist_ok=True)
    before = {p.resolve() for p in run_dir.glob("*.wav")}

    cb = progress_cb or (lambda _m, _p: None)
    cb("Running Seed-VC zero-shot voice conversion on CPU/GPU auto-device...", 25)
    python = os.environ.get("SEED_VC_PYTHON", sys.executable)
    cmd = [
        python, str(inference),
        "--source", str(source),
        "--target", str(reference),
        "--output", str(run_dir),
        "--diffusion-steps", str(max(1, int(diffusion_steps))),
        "--length-adjust", "1.0",
        "--inference-cfg-rate", "0.7",
        "--f0-condition", "True" if singing else "False",
        "--auto-f0-adjust", "False",
        "--semi-tone-shift", "0",
        "--fp16", "False",
    ]
    proc = subprocess.run(
        cmd, cwd=str(root), capture_output=True, text=True,
        timeout=int(os.environ.get("SEED_VC_TIMEOUT", "7200")),
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "unknown Seed-VC error")[-1200:]
        raise RuntimeError(f"Seed-VC failed: {detail.strip()}")

    candidates = [
        p.resolve() for p in run_dir.glob("*.wav")
        if p.resolve() not in before and p.stat().st_size > 1024
    ]
    if not candidates:
        candidates = [p.resolve() for p in run_dir.glob("*.wav") if p.stat().st_size > 1024]
    if not candidates:
        raise RuntimeError("Seed-VC completed but produced no WAV output")
    generated = max(candidates, key=lambda p: p.stat().st_mtime_ns)
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(generated, out)
    cb("Seed-VC conversion complete", 100)
    return str(out)
