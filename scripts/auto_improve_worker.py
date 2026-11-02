"""Auto‑improve worker for ai‑vocals‑studio.

Runs in a loop (default every 6 h) and performs lightweight maintenance:

1. Run the project validation suite via `piv-validate` (tests, lint, type‑check).
2. If validation fails, attempt to auto‑fix simple issues using `piv-fix-review-findings`.
3. If the repo is clean, run `ruff` formatting and commit any style changes.
4. Push a new branch `auto‑improve/<timestamp>` and open a PR via `piv-create-pr`.

The script is deliberately defensive – it never rewrites history, never
removes existing commits, and only creates new PRs.
"""

import subprocess
import shutil
import datetime
import os
import sys
import time

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def run(cmd, check=True):
    # Ensure the virtual environment's bin directory is in PATH for subprocess commands
    env = os.environ.copy()
    venv_bin = os.path.join(REPO_ROOT, "venv", "bin")
    env["PATH"] = f"{venv_bin}:{env.get('PATH','')}"
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=REPO_ROOT, capture_output=True, text=True, env=env)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd)
    return result
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=True, cwd=REPO_ROOT, capture_output=True, text=True)
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd)
    return result

def command_exists(cmd):
    return shutil.which(cmd) is not None

def validate():
    if command_exists('piv-validate'):
        try:
            run("piv-validate")
            return True
        except subprocess.CalledProcessError:
            return False
    else:
        # Fallback: run pytest to ensure tests pass
        try:
            run("pytest -q")
            return True
        except subprocess.CalledProcessError:
            return False
    try:
        run("piv-validate")
        return True
    except subprocess.CalledProcessError:
        return False

def auto_fix():
    if command_exists('piv-fix-review-findings'):
        run('piv-fix-review-findings')
    else:
        # Fallback: attempt to run pytest with --maxfail=1 to surface failures
        try:
            run('pytest -q --maxfail=1')
        except subprocess.CalledProcessError:
            print('[auto-improve] No fix command available and tests still failing.', file=sys.stderr)
    # Attempt to fix simple review findings.
    run("piv-fix-review-findings")

def format_and_commit():
    # Run ruff formatting only (no lint).
    run("ruff format .")
    # Check if there are changes.
    diff = subprocess.run("git diff --quiet", shell=True, cwd=REPO_ROOT)
    if diff.returncode != 0:
        branch = f"auto-improve/{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        run(f"git checkout -b {branch}")
        run("git add .")
        run(f"git commit -m 'auto‑improve: format/code‑health updates'")
        run("git push -u origin HEAD")
        run("piv-create-pr")

def main():
    interval_seconds = int(os.getenv("AUTO_IMPROVE_INTERVAL", "21600"))  # 6 h
    while True:
        print("[auto‑improve] Starting cycle…")
        if not validate():
            print("[auto‑improve] Validation failed – attempting auto‑fix.")
            auto_fix()
        else:
            print("[auto‑improve] Repository clean – formatting.")
            format_and_commit()
        print(f"[auto‑improve] Sleeping for {interval_seconds} seconds…")
        time.sleep(interval_seconds)

if __name__ == "__main__":
    main()
