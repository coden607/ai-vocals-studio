#!/usr/bin/env python3
"""Out-of-venv voice-engine dispatcher (the "sidecar" entrypoint).

``clone_any_voice.py::_run_sidecar()`` invokes this file with the
*sidecar* interpreter — a Python 3.10/3.11 venv that holds the heavy
engines XTTS/RVC (see ``install_voice_engines.sh`` and
``requirements_voice_engines_py310.txt``):

    <sidecar-python> voice_engine_sidecar.py <engine> [engine args...]

The sidecar exists because ``TTS`` (XTTS) does not build on the main
Python 3.12 venv; the heavy wheels live in their own interpreter, and
this script is the stable RPC surface between the main CLI and that
interpreter.

Protocol (kept in sync with ``_run_sidecar``):
  * human progress / diagnostics -> stderr
  * machine result -> exactly ONE JSON object on stdout:
        success: {"ok": true,  "engine": ..., "output": ...}
        failure: {"ok": false, "error": ...}   (non-zero exit code)
    ``_run_sidecar`` scans stdout from the LAST line backwards for the
    first JSON object, so stdout must stay JSON-clean.

Subcommands
-----------
xtts  --text T --voice-name N --reference R --mood M --output O
    Zero-shot XTTS v2 synthesis inside the sidecar venv. Requires the
    ``TTS`` package in the running interpreter; XTTS v2 weights
    (~1.8 GB) download on first use. (Caller: clone_any_voice.py.)

rvc   --voice-name N --input IN.wav --output OUT.wav --models-dir DIR
    RVC v2 audio-to-audio conversion using a trained checkpoint under
    DIR/<name>/ (rvc_model.pth / <name>.pth / model.pth). Requires the
    ``rvc-python`` package in the running interpreter. (Caller:
    song_converter.convert_vocals, as the fallback when the in-process
    RvcEngine is unavailable.)

so-vits-svc has NO sidecar entrypoint: its only callers run in-process
or via the cloud training notebooks. This dispatcher does not invent
RPCs nobody calls.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import traceback
from pathlib import Path


def _emit(payload: dict) -> None:
    """The single stdout line _run_sidecar() parses."""
    print(json.dumps(payload), flush=True)


def _progress(msg: str, pct: int) -> None:
    print(f"[{pct:3d}%] {msg}", file=sys.stderr, flush=True)


def cmd_rvc(ns: argparse.Namespace) -> dict:
    try:
        from rvc_engine import RvcEngine  # repo module; cwd is on sys.path
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError(f"rvc_engine module not importable: {exc}") from exc

    engine = RvcEngine(ns.models_dir)
    ok, msg = engine.convert(
        ns.voice_name,
        ns.input,
        ns.output,
        pitch_shift=0,
        progress_cb=_progress,
    )
    if not ok:
        raise RuntimeError(f"RVC conversion failed: {msg}")
    output = Path(ns.output).expanduser().resolve()
    if not output.exists():
        raise RuntimeError(f"RVC conversion reported success but {output} is missing")
    return {"engine": "rvc", "output": str(output)}


def cmd_xtts(ns: argparse.Namespace) -> dict:
    try:
        from xtts_engine import XttsEngine  # repo module; cwd is on sys.path
    except Exception as exc:  # pragma: no cover - import guard
        raise RuntimeError(f"xtts_engine module not importable: {exc}") from exc

    engine = XttsEngine(Path.cwd())
    if not engine.can_synthesize():
        raise RuntimeError(
            "TTS library is not installed in this interpreter. "
            "Create the sidecar venv with install_voice_engines.sh."
        )

    out = engine.synthesize(
        text=ns.text,
        model_name=ns.voice_name,
        mood=ns.mood or "default",
        custom_ref=ns.reference or None,
        progress_cb=_progress,
    )

    output = Path(ns.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(out, output)
    return {"engine": "xtts", "output": str(output)}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="voice_engine_sidecar.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="engine", required=True)

    px = sub.add_parser("xtts", help="XTTS v2 zero-shot synthesis (requires TTS in this venv)")
    px.add_argument("--text", required=True, help="text to synthesize")
    px.add_argument("--voice-name", required=True, help="voice model name (dataset/<name>/ refs)")
    px.add_argument("--reference", default=None, help="explicit reference WAV (overrides mood picks)")
    px.add_argument("--mood", default=None, help="default | aggressive | storytelling | emotional")
    pr = sub.add_parser("rvc", help="RVC v2 conversion (requires rvc-python + a trained .pth in this venv)")
    pr.add_argument("--voice-name", required=True, help="voice model name (checkpoint under --models-dir)")
    pr.add_argument("--input", required=True, help="source WAV to convert")
    pr.add_argument("--output", required=True, help="destination WAV path")
    pr.add_argument("--models-dir", default="models", help="models root (default: models)")
    return parser


def main(argv: list[str]) -> int:
    ns = _build_parser().parse_args(argv)

    handlers = {"xtts": cmd_xtts, "rvc": cmd_rvc}
    handler = handlers.get(str(ns.engine))
    if handler is None:
        _emit({
            "ok": False,
            "error": (
                f"engine '{ns.engine}' has no sidecar entrypoint. "
                "Supported: xtts, rvc. so-vits runs in-process or via cloud training."
            ),
        })
        return 2

    try:
        payload = handler(ns)
        _emit({"ok": True, **payload})
        return 0
    except SystemExit:
        raise
    except Exception as exc:
        traceback.print_exc(file=sys.stderr)
        _emit({"ok": False, "error": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
