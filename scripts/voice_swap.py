#!/usr/bin/env python3
"""
Voice‑Swap Utility
==================

Take a *source* song and replace its vocals with a cloned voice
derived from a *reference* song.  The workflow is:

1️⃣ Separate the source into vocals + instrumental (Demucs or center‑channel).
2️⃣ Clone the reference voice onto the source’s vocal track (via `clone_voice`).
3️⃣ Mix the cloned vocals back onto the instrumental.

All steps use the existing library code; no external binaries are required
beyond the already‑installed `demucs`, `julius`, and `torch`.

Run it as:

```bash
python scripts/voice_swap.py \
  --source /path/to/source_song.mp3 \
  --reference /path/to/reference_voice.wav \
  --output /path/to/final_mix.wav
```

The script creates a temporary work directory under `/tmp/voice_swap_<uuid>/`
that is automatically cleaned up.
"""

import argparse
import sys
import shutil
import uuid
from pathlib import Path

# Ensure repository root is in sys.path for internal imports
repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from song_converter import separate_vocals
from ai_vocals_studio.voice_cloning import clone_voice
import numpy as np
import soundfile as sf
import soundfile as sf

def _mix_tracks(vocals: np.ndarray, instrumental: np.ndarray) -> np.ndarray:
    """Mix two audio arrays, padding the shorter one and normalising."""
    # Pad to same length
    max_len = max(vocals.shape[0], instrumental.shape[0])
    if vocals.shape[0] < max_len:
        pad = [(0, max_len - vocals.shape[0])]
        if vocals.ndim == 2:
            pad.append((0, 0))
        vocals = np.pad(vocals, pad, mode="constant")
    if instrumental.shape[0] < max_len:
        pad = [(0, max_len - instrumental.shape[0])]
        if instrumental.ndim == 2:
            pad.append((0, 0))
        instrumental = np.pad(instrumental, pad, mode="constant")

    mixed = vocals + instrumental
    peak = np.max(np.abs(mixed))
    if peak > 1.0:
        mixed = mixed / peak
    return mixed


def voice_swap(
    source_path: Path,
    reference_path: Path,
    output_path: Path,
    work_dir: Path | None = None,
    backend: str = "coqui",
) -> None:
    """Perform the full voice‑swap pipeline."""
    tmp_dir = work_dir or Path("/tmp") / f"voice_swap_{uuid.uuid4().hex}"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    vocals_path, instrumental_path, _ = separate_vocals(
        song_path=source_path,
        work_dir=tmp_dir,
        method="auto",
        progress_cb=lambda msg, pct: print(f"[sep] {msg} ({pct}%)"),
        allow_fallback=True,
    )
    if not vocals_path or not instrumental_path:
        raise RuntimeError("Failed to separate source audio.")

    cloned_vocals = tmp_dir / f"cloned_{source_path.stem}_{backend}.wav"
    clone_voice(
        source_wav=vocals_path,
        reference_wav=reference_path,
        model=backend,
        output_path=cloned_vocals,
    )

    cloned_arr, sr = sf.read(str(cloned_vocals), dtype="float32")
    inst_arr, sr2 = sf.read(str(instrumental_path), dtype="float32")
    if sr != sr2:
        raise RuntimeError("Sample‑rate mismatch between tracks.")

    final_mix = _mix_tracks(cloned_arr, inst_arr)
    sf.write(str(output_path), final_mix, sr)
    print(f"[done] Final track written to {output_path}")

    if work_dir is None:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replace vocals with a cloned voice.")
    parser.add_argument("--source", type=Path, required=True, help="Path to source song.")
    parser.add_argument(
        "--reference", type=Path, required=True, help="Path to reference voice clip."
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Path for the final mixed audio."
    )
    parser.add_argument(
        "--backend",
        default="coqui",
        choices=["coqui", "silero", "qwen3"],
        help="Voice‑cloning backend (default: coqui).",
    )
    args = parser.parse_args()
    voice_swap(
        source_path=args.source,
        reference_path=args.reference,
        output_path=args.output,
        backend=args.backend,
    )
