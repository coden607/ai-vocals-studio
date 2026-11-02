#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

if [ -x .venv/bin/python ]; then
  PYTHON=.venv/bin/python
elif [ -x venv/bin/python ]; then
  PYTHON=venv/bin/python
else
  echo "AI Vocals Studio is not installed. Run ./install.sh first." >&2
  exit 1
fi

if ! "$PYTHON" -c 'import soundfile, librosa, demucs' >/dev/null 2>&1; then
  echo "The audio runtime is incomplete or uses an unsupported Python. Run ./install_voice_engines.sh." >&2
  exit 1
fi

exec "$PYTHON" app_studio.py
