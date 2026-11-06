"""Exercise the launcher without credentials, audio, models, or a real worker."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.fixture
def launcher(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    target = scripts / "run_supabase_worker.sh"
    shutil.copyfile(Path(__file__).parent / "scripts/run_supabase_worker.sh", target)
    return target


def fake_python(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('#!/bin/sh\nprintf "%s\\n" "$0" "$@"\n')
    path.chmod(0o755)


def launch(launcher, **extra):
    env = {k: v for k, v in os.environ.items()
           if k not in {"SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "LOCAL_STORAGE_DIR", "MAIN_PY"}}
    env.update(extra)
    return subprocess.run(["bash", str(launcher), "--once"], env=env,
                          text=True, capture_output=True, timeout=5)


def test_installer_dotvenv_launches_local_queue(launcher):
    root = launcher.parent.parent
    python = root / ".venv/bin/python"
    fake_python(python)
    result = launch(launcher, LOCAL_STORAGE_DIR=str(root / "local"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [str(python), "supabase_worker.py", "--once"]


def test_legacy_venv_and_explicit_override_remain_supported(launcher):
    root = launcher.parent.parent
    legacy = root / "venv/bin/python"
    fake_python(legacy)
    result = launch(launcher, SUPABASE_URL="https://example.invalid", SUPABASE_SERVICE_ROLE_KEY="test-only")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == str(legacy)
    override = root / "custom python"
    fake_python(override)
    result = launch(launcher, LOCAL_STORAGE_DIR=str(root / "local"), MAIN_PY=str(override))
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == str(override)


def test_missing_runtime_explains_how_to_install(launcher):
    result = launch(launcher, LOCAL_STORAGE_DIR="local")
    assert result.returncode == 2
    assert "install_voice_engines.sh" in result.stderr


def test_missing_storage_is_rejected_before_starting_worker(launcher):
    fake_python(launcher.parent.parent / ".venv/bin/python")
    result = launch(launcher)
    assert result.returncode == 2
    assert "LOCAL_STORAGE_DIR" in result.stderr
