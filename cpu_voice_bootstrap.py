#!/usr/bin/env python3
"""Build an authorized reusable voice profile on CPU only.

This is the no-GPU bootstrap path. It analyzes one or more clean clips (or
full songs with source separation), writes models/voices/<name>/voice_profile.json
and reference.wav, and makes the voice immediately usable by the DSP song
replacement path and by zero-shot TTS backends that consume reference.wav.

It does NOT pretend to create an RVC neural checkpoint. RVC training remains a
separate optional upgrade when suitable compute is available.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from voice_cloner import build_voice_profile_from_sources, collect_audio_sources


def _progress(message: str, percent: int) -> None:
    print(f"[{percent:3d}%] {message}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="CPU-only authorized voice bootstrap")
    ap.add_argument("sources", nargs="+", help="audio files and/or folders")
    ap.add_argument("--name", default="Pacaveli")
    ap.add_argument("--source-type", choices=["speech", "song"], default="speech")
    ap.add_argument("--voices-dir", default="models/voices")
    ap.add_argument("--i-have-permission", action="store_true")
    args = ap.parse_args()

    if not args.i_have_permission:
        print("[error] permission confirmation is required")
        return 2

    sources = collect_audio_sources(args.sources)
    if not sources:
        print("[error] no supported audio files found")
        return 2

    profile = build_voice_profile_from_sources(
        args.name,
        sources,
        source_type=args.source_type,
        description="Authorized CPU-only voice profile",
        voices_dir=args.voices_dir,
        progress_cb=_progress,
        has_permission=True,
    )
    if not profile:
        print("[error] profile creation failed")
        return 1

    voice_dir = Path(profile["voice_dir"])
    print(json.dumps({
        "ok": True,
        "name": profile["name"],
        "voice_dir": str(voice_dir),
        "profile": str(voice_dir / "voice_profile.json"),
        "reference": profile["reference"],
        "rvc_available": profile.get("rvc_available", False),
        "cpu_ready": True,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
