#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

if [ -z "${MAIN_PY:-}" ]; then
  if [ ! -x .venv/bin/python ]; then
    if command -v uv >/dev/null 2>&1; then
      uv python install 3.12
      uv venv --python 3.12 .venv
    elif command -v python3.12 >/dev/null 2>&1; then
      python3.12 -m venv .venv
    else
      echo "Python 3.12 is required. Install it or install uv, then rerun this script." >&2
      exit 1
    fi
  fi
  MAIN_PY=".venv/bin/python"
fi

if ! "$MAIN_PY" -c 'import sys; raise SystemExit(sys.version_info[:2] != (3, 12))'; then
  echo "$MAIN_PY must use Python 3.12; the existing venv was left untouched." >&2
  exit 1
fi

ensure_pip() {
  if ! "$1" -m pip --version >/dev/null 2>&1; then
    "$1" -m ensurepip --upgrade
  fi
}

HAS_NVIDIA=0
if command -v nvidia-smi >/dev/null 2>&1; then
  HAS_NVIDIA=1
else
  export UV_TORCH_BACKEND=cpu
fi

echo "Installing Demucs, Qwen3-TTS, speaker verification, and app dependencies..."
ensure_pip "$MAIN_PY"
"$MAIN_PY" -m pip install --upgrade pip
if [ "$HAS_NVIDIA" = "0" ]; then
  "$MAIN_PY" -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
fi
"$MAIN_PY" -m pip install -r requirements_minimal.txt resemblyzer

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg is required for compressed audio formats. Install it with your system package manager." >&2
  exit 1
fi

if [ "${INSTALL_SEED_VC:-1}" != "0" ]; then
  if ! command -v git >/dev/null 2>&1; then
    echo "git is required to install Seed-VC." >&2
    exit 1
  fi
  mkdir -p .engines
  if [ ! -f .engines/seed-vc/inference.py ]; then
    git clone --depth 1 https://github.com/Plachtaa/seed-vc.git .engines/seed-vc
  fi
  SEED_VC_REF="${SEED_VC_REF:-51383efd921027683c89e5348211d93ff12ac2a8}"
  git -C .engines/seed-vc fetch --depth 1 origin "$SEED_VC_REF"
  git -C .engines/seed-vc checkout --detach "$SEED_VC_REF"
  if command -v uv >/dev/null 2>&1; then
    uv python install 3.10
    [ -x venv_seed_vc/bin/python ] || uv venv --python 3.10 venv_seed_vc
  elif command -v python3.10 >/dev/null 2>&1; then
    [ -x venv_seed_vc/bin/python ] || python3.10 -m venv venv_seed_vc
  else
    echo "Seed-VC requires Python 3.10. Install it or uv, then rerun this script." >&2
    exit 1
  fi
  echo "Installing Seed-VC zero-shot speech/singing conversion..."
  ensure_pip venv_seed_vc/bin/python
  venv_seed_vc/bin/python -m pip install --upgrade pip
  if [ "$HAS_NVIDIA" = "0" ]; then
    venv_seed_vc/bin/python -m pip install torch==2.4.0 torchvision==0.19.0 torchaudio==2.4.0 --index-url https://download.pytorch.org/whl/cpu
  fi
  venv_seed_vc/bin/python -m pip install -r .engines/seed-vc/requirements.txt
fi

if [ "${INSTALL_TRAINING_SIDECARS:-1}" != "0" ]; then
  if ! command -v uv >/dev/null 2>&1 && ! command -v python3.11 >/dev/null 2>&1 && ! command -v python3.10 >/dev/null 2>&1; then
    echo "Skipping XTTS/RVC sidecars: install uv or Python 3.10/3.11 to enable them." >&2
  else
    if command -v uv >/dev/null 2>&1; then
      uv python install 3.11
      [ -x venv_xtts_engines/bin/python ] || uv venv --python 3.11 venv_xtts_engines
      uv pip install --python venv_xtts_engines/bin/python --upgrade pip setuptools wheel
      uv pip install --python venv_xtts_engines/bin/python -r requirements_voice_engines_py310.txt
      printf '%s\n' "venv_xtts_engines/bin/python" > .xtts_engine_sidecar

      uv python install 3.10
      [ -x venv_rvc_engines/bin/python ] || uv venv --python 3.10 venv_rvc_engines
      uv pip install --python venv_rvc_engines/bin/python --upgrade pip "setuptools<81" wheel
      uv pip install --python venv_rvc_engines/bin/python -r requirements_rvc_sidecar.txt
      printf '%s\n' "venv_rvc_engines/bin/python" > .rvc_engine_sidecar
    else
      SIDECAR_PY="$(command -v python3.11 || command -v python3.10)"
      [ -x venv_xtts_engines/bin/python ] || "$SIDECAR_PY" -m venv venv_xtts_engines
      venv_xtts_engines/bin/python -m pip install --upgrade pip setuptools wheel
      venv_xtts_engines/bin/python -m pip install -r requirements_voice_engines_py310.txt
      printf '%s\n' "venv_xtts_engines/bin/python" > .xtts_engine_sidecar

      [ -x venv_rvc_engines/bin/python ] || "$SIDECAR_PY" -m venv venv_rvc_engines
      venv_rvc_engines/bin/python -m pip install --upgrade pip "setuptools<81" wheel
      venv_rvc_engines/bin/python -m pip install -r requirements_rvc_sidecar.txt
      printf '%s\n' "venv_rvc_engines/bin/python" > .rvc_engine_sidecar
    fi
  fi
fi

echo "Voice engine install complete. Check capabilities with: $MAIN_PY scripts/doctor.py"
