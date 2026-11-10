#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")/.."

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
if [[ -f .env.supabase.local ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env.supabase.local
  set +a
fi

if [[ ( -z "${SUPABASE_URL:-}" || -z "${SUPABASE_SERVICE_ROLE_KEY:-}" ) && -z "${LOCAL_STORAGE_DIR:-}" ]]; then
  cat >&2 <<'EOF'
Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY, or LOCAL_STORAGE_DIR for a local queue.

Example:
  export SUPABASE_URL=https://PROJECT_REF.supabase.co
  export SUPABASE_SERVICE_ROLE_KEY=...
  scripts/run_supabase_worker.sh
EOF
  exit 2
fi

if [[ -n "${MAIN_PY:-}" ]]; then
  WORKER_PY="$MAIN_PY"
elif [[ -x .venv/bin/python ]]; then
  WORKER_PY="$PWD/.venv/bin/python"
elif [[ -x venv/bin/python ]]; then
  WORKER_PY="$PWD/venv/bin/python"
else
  echo "No worker Python found. Run ./install_voice_engines.sh or set MAIN_PY to an installed runtime." >&2
  exit 2
fi

if ! command -v "$WORKER_PY" >/dev/null 2>&1; then
  echo "Worker Python is not executable. Set MAIN_PY to an installed runtime or run ./install_voice_engines.sh." >&2
  exit 2
fi

echo "Starting queue worker..." >&2
exec "$WORKER_PY" supabase_worker.py "$@"
