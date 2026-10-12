#!/usr/bin/env python3
"""doctor.py — honest runtime probes for AI Vocals Studio.

Answers "what can this box actually do right now?" without downloading
models or making network calls. Run it with the studio venv:

    python3 scripts/doctor.py

Exits 0 always — a missing engine is a *finding*, not a crash. The
capability table is the point.
"""
from __future__ import annotations

import importlib.util
import json
import os
import platform
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS = ROOT / "models"


# ---------------------------------------------------------------- helpers
def _findable(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except Exception:
        return False


def _py_ver() -> str:
    v = sys.version_info
    return f"{v.major}.{v.minor}.{v.micro}"


def _machine() -> dict:
    ncpu = os.cpu_count() or 0
    ram_gb = 0.0
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        ram_gb = round(pages * page_size / (1024 ** 3), 1)
    except (ValueError, OSError, AttributeError):
        pass
    return {"cpu_cores": ncpu, "ram_gb": ram_gb, "arch": platform.machine()}


def _gpu() -> bool:
    if shutil.which("nvidia-smi"):
        return True
    try:
        if _findable("torch"):
            import torch  # type: ignore

            return bool(torch.cuda.is_available())
    except Exception:
        pass
    return False


# ---------------------------------------------------------------- probes
def probe_environment() -> list[tuple[str, str, str]]:
    rows = []
    machine = _machine()
    ffmpeg = shutil.which("ffmpeg")
    rows.append(("ffmpeg", "present: " + ffmpeg if ffmpeg else "MISSING (apt-get install ffmpeg)", "ok" if ffmpeg else "fail"))
    rows.append(("python", f"{_py_ver()} ({sys.executable})", "ok"))
    rows.append(("cpu", f"{machine['cpu_cores']} cores, {machine['arch']}", "ok"))
    rows.append(("ram", f"{machine['ram_gb']} GB total", "ok" if machine["ram_gb"] >= 4 else "warn"))
    rows.append(("gpu", "available" if _gpu() else "none (CPU-only inference)", "ok" if _gpu() else "warn"))
    return rows


def probe_engines() -> list[tuple[str, str, str]]:
    """Importability of each engine stack in THIS interpreter."""
    engines = [
        ("resemblyzer", "resemblyzer", "the identity scorer (contract enforcer)"),
        ("librosa", "librosa", "audio features / decode"),
        ("torch", "torch", "neural inference base"),
        ("demucs", "demucs", "song vocal separation"),
        ("elevenlabs (API client)", "elevenlabs", "cloud premium clone engine"),
        ("qwen-tts", "qwen_tts", "local zero-shot TTS (Apache-2.0)"),
        ("gTTS", "gtts", "parametric fallback (never a clone)"),
        ("pyworld", "pyworld", "WORLD/DSP vocoder fallback"),
        ("TTS (Coqui/XTTS)", "TTS", "XTTS v2 — normally sidecar-only on py3.12"),
        ("rvc_python", "rvc_python", "RVC — normally sidecar-only"),
    ]
    rows = []
    for label, module, note in engines:
        ok = _findable(module)
        rows.append((label, f"importable ({note})" if ok else f"not installed ({note})", "ok" if ok else "warn"))
    return rows


def probe_models() -> list[tuple[str, str, str]]:
    rows = []
    placeholder = MODELS / "model.pth"
    if not placeholder.exists():
        rows.append(("models/model.pth", "absent", "warn"))
    else:
        size = placeholder.stat().st_size
        rows.append((
            "models/model.pth",
            f"PLACEHOLDER ({size} B — no weights in repo, by design)" if size < 1024 else f"present ({size} B)",
            "warn" if size < 1024 else "ok",
        ))
    ckpts = sorted(MODELS.glob("**/*.pth")) + sorted(MODELS.glob("**/*.ckpt")) + sorted(MODELS.glob("**/*.pt"))
    ckpts = [c for c in ckpts if c != placeholder]
    if ckpts:
        rows.append(("imported checkpoints", ", ".join(str(c.relative_to(ROOT)) for c in ckpts[:5]), "ok"))
    else:
        rows.append(("imported checkpoints", "none — train in cloud (Kaggle/Colab) and import, or use zero-shot engines", "warn"))
    return rows


def probe_keys() -> list[tuple[str, str, str]]:
    rows = []
    key = bool(os.environ.get("ELEVENLABS_API_KEY", "").strip())
    cfg = ROOT / ".cloud_config"
    if not key and cfg.exists():
        try:
            key = any("ELEVENLABS" in line.upper() for line in cfg.read_text(errors="ignore").splitlines())
        except Exception:
            key = False
    rows.append(("ELEVENLABS_API_KEY", "configured" if key else "not set (ElevenLabs engine inert until supplied)", "ok" if key else "warn"))
    rows.append((".cloud_config", "present" if cfg.exists() else "absent (see install_voice_engines.sh / cloud notes)", "ok" if cfg.exists() else "warn"))
    return rows


# ---------------------------------------------------------------- report
def main() -> int:
    sections = [
        ("Environment", probe_environment()),
        ("Engines (this interpreter)", probe_engines()),
        ("Models / weights", probe_models()),
        ("Keys / config (boolean only)", probe_keys()),
    ]

    width = max(len(name) for _, rows in sections for name, _, _ in rows)
    print("=" * (width + 34))
    print("AI VOCALS STUDIO — doctor (honest capability probe)")
    print("repo:", ROOT)
    print("=" * (width + 34))
    for title, rows in sections:
        print(f"\n## {title}")
        for name, value, status in rows:
            mark = {"ok": "[ OK ]", "warn": "[WARN]", "fail": "[FAIL]"}[status]
            print(f"  {mark} {name:<{width}}  {value}")

    print("\n## Notes")
    print("  - The studio CONTRACT only counts resemblyzer speaker identity as accuracy;")
    print("    WORLD/DSP/gTTS can never pass the studio gate (speaker_identity.py).")
    print("  - XTTS/RVC install into py3.10/3.11 sidecar venvs (install_voice_engines.sh);")
    print("    this table only reports THIS interpreter. Sidecar health is checked by")
    print("    engine_planner._sidecar_importable() at plan time.")
    print("  - No weights are shipped in git (DMCA + size). Real checkpoints are")
    print("    user-provided or cloud-trained (Kaggle/Colab) and imported locally.")

    # Machine-readable copy for CI/reporting
    summary = {
        "python": _py_ver(),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "gpu": _gpu(),
        "engines": {label: _findable(mod) for label, mod in [
            ("resemblyzer", "resemblyzer"), ("demucs", "demucs"), ("torch", "torch"),
            ("elevenlabs", "elevenlabs"), ("qwen_tts", "qwen_tts"), ("TTS", "TTS"),
            ("rvc_python", "rvc_python"),
        ]},
        "elevenlabs_key": bool(os.environ.get("ELEVENLABS_API_KEY", "").strip()),
    }
    print("\n## JSON")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
