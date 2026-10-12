#!/usr/bin/env python3
"""CLI for source separation and authorized cloned-voice song replacement."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from song_converter import change_song, combine_tracks, convert_vocals, separate_vocals
from verse_voices import distinguish_verse_voices


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

    render = sub.add_parser("render", help="Separate, label verse voices, clone the vocal, write alone and over-beat")
    render.add_argument("song")
    render.add_argument("--profile", required=True)
    render.add_argument("--output-dir", default="output/rendered")
    render.add_argument("--separation", choices=["auto", "demucs", "center"], default="auto")
    render.add_argument("--vocals-gain-db", type=float, default=0.0)
    render.add_argument("--i-have-permission", action="store_true", required=True)

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

    if not args.i_have_permission:
        raise SystemExit("permission confirmation is required")
    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))

    if args.command == "render":
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        vocals, instrumental, method = separate_vocals(args.song, out, args.separation, _progress)
        if not vocals or not instrumental:
            raise SystemExit("separation failed")
        verses = distinguish_verse_voices(vocals, out)
        cloned = out / "cloned_vocal_alone.wav"
        ok, msg = convert_vocals(vocals, profile, cloned, out, _progress)
        if not ok:
            raise SystemExit(msg)
        over = out / "cloned_vocal_over_beat.wav"
        combine_tracks(cloned, instrumental, over, vocals_gain_db=args.vocals_gain_db, progress_cb=_progress)
        print(json.dumps({
            "separation": method,
            "acapella": vocals,
            "beat": instrumental,
            "verse_voices": verses["voices"],
            "turns": verses["turns"],
            "cloned_vocal_alone": str(cloned),
            "cloned_vocal_over_beat": str(over),
            "conversion": msg,
        }, indent=2))
        return 0

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
