#!/usr/bin/env python3
"""CLI for source separation and authorized cloned-voice song replacement."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from song_converter import change_song, separate_vocals


def _progress(message: str, percent: int) -> None:
    print(f"[{percent:3d}%] {message}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create acapella/instrumental stems or replace a song vocal with an authorized cloned voice."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sep = sub.add_parser("separate", help="Create vocals.wav and instrumental.wav")
    sep.add_argument("song")
    sep.add_argument("--output-dir", default="output/separated")
    sep.add_argument("--method", choices=["auto", "demucs", "center"], default="demucs")
    sep.add_argument("--require-neural", action="store_true",
                     help="fail instead of falling back when Demucs is unavailable")

    rep = sub.add_parser("replace", help="Separate, convert the vocal, and remix over the original beat")
    rep.add_argument("song")
    rep.add_argument("--profile", required=True, help="authorized voice profile JSON")
    rep.add_argument("--output-dir", default="output/replaced")
    rep.add_argument("--separation", choices=["auto", "demucs", "center"], default="demucs")
    rep.add_argument("--vocals-gain-db", type=float, default=0.0)
    rep.add_argument("--require-neural", action="store_true",
                     help="require Demucs + a trained RVC model; disable DSP/center fallbacks")
    rep.add_argument("--i-have-permission", action="store_true", required=True,
                     help="confirm permission to use the target voice")

    args = parser.parse_args()

    if args.command == "separate":
        out = Path(args.output_dir)
        vocals, instrumental, method = separate_vocals(args.song, out, args.method, _progress)
        if not vocals or not instrumental:
            raise SystemExit("separation failed")
        if args.require_neural and method != "demucs":
            raise SystemExit("Demucs neural separation was required but unavailable")
        print(json.dumps({
            "method": method,
            "acapella": vocals,
            "instrumental": instrumental,
        }, indent=2))
        return 0

    profile_path = Path(args.profile)
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    if not args.i_have_permission:
        raise SystemExit("permission confirmation is required")

    output, steps = change_song(
        args.song,
        profile,
        args.output_dir,
        progress_cb=_progress,
        separation=args.separation,
        vocals_gain_db=args.vocals_gain_db,
        require_neural=args.require_neural,
    )
    print(json.dumps({"output": output, "steps": steps}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
