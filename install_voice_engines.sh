#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

MAIN_PY="${MAIN_PY:-venv/bin/python}"

if [ ! -x "$MAIN_PY" ]; then
  python3 -m venv venv
  MAIN_PY="venv/bin/python"
fi

echo "Installing Python 3.12-compatible voice engines into main venv..."
"$MAIN_PY" -m pip install --upgrade pip
"$MAIN_PY" -m pip install -r requirements_minimal.txt elevenlabs pyworld demucs resemblyzer

if command -v sox >/dev/null 2>&1; then
  echo "SoX found: $(command -v sox)"
else
  echo "SoX not found. Optional: sudo apt-get install sox libsox-fmt-all ffmpeg"
fi

if command -v uv >/dev/null 2>&1; then
  echo "Installing Python 3.11 with uv for sidecar engines..."
  uv python install 3.11

  echo "Creating XTTS sidecar..."
  uv venv --python 3.11 venv_xtts_engines
  uv pip install --python venv_xtts_engines/bin/python --upgrade pip setuptools wheel
  uv pip install --python venv_xtts_engines/bin/python -r requirements_voice_engines_py310.txt
  printf '%s\n' "venv_xtts_engines/bin/python" > .xtts_engine_sidecar

  echo "Installing Python 3.10 with uv for RVC sidecar..."
  uv python install 3.10
  echo "Creating RVC sidecar..."
  uv venv --python 3.10 venv_rvc_engines
  uv pip install --python venv_rvc_engines/bin/python --upgrade pip "setuptools<81" wheel
  uv pip install --python venv_rvc_engines/bin/python -r requirements_rvc_sidecar.txt
  printf '%s\n' "venv_rvc_engines/bin/python" > .rvc_engine_sidecar
elif command -v python3.11 >/dev/null 2>&1 || command -v python3.10 >/dev/null 2>&1; then
  SIDECAR_PY="$(command -v python3.11 || command -v python3.10)"

  echo "Creating XTTS sidecar with $SIDECAR_PY..."
  "$SIDECAR_PY" -m venv venv_xtts_engines
  venv_xtts_engines/bin/python -m pip install --upgrade pip setuptools wheel
  venv_xtts_engines/bin/python -m pip install -r requirements_voice_engines_py310.txt
  printf '%s\n' "venv_xtts_engines/bin/python" > .xtts_engine_sidecar

  echo "Creating RVC sidecar with $SIDECAR_PY..."
  "$SIDECAR_PY" -m venv venv_rvc_engines
  venv_rvc_engines/bin/python -m pip install --upgrade pip "setuptools<81" wheel
  venv_rvc_engines/bin/python -m pip install -r requirements_rvc_sidecar.txt
  printf '%s\n' "venv_rvc_engines/bin/python" > .rvc_engine_sidecar
else
  cat <<'EOF'

XTTS/RVC sidecars not installed: Python 3.10/3.11 and uv were not found.
Install uv or Python 3.11, then rerun:
  ./install_voice_engines.sh

The app still has Qwen3-TTS, ElevenLabs when configured, WORLD/DSP conversion,
and Demucs separation.
EOF
fi

echo "Voice engine install complete."
