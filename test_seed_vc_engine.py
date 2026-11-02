from pathlib import Path
import seed_vc_engine as svc


def test_seed_vc_project_root_is_repository_root():
    assert svc.PROJECT_ROOT == Path(svc.__file__).resolve().parent


def test_seed_vc_availability_requires_inference(monkeypatch, tmp_path):
    monkeypatch.setenv("SEED_VC_DIR", str(tmp_path))
    assert not svc.seed_vc_available()
    (tmp_path / "inference.py").write_text("# fixture")
    assert svc.seed_vc_available()


def test_seed_vc_cpu_command(monkeypatch, tmp_path):
    root = tmp_path / "seed-vc"
    root.mkdir()
    (root / "inference.py").write_text("# fixture")
    source = tmp_path / "source.wav"
    ref = tmp_path / "ref.wav"
    source.write_bytes(b"source")
    ref.write_bytes(b"reference")
    out = tmp_path / "out.wav"
    monkeypatch.setenv("SEED_VC_DIR", str(root))

    seen = {}
    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        run_dir = Path(cmd[cmd.index("--output") + 1])
        (run_dir / "generated.wav").write_bytes(b"x" * 2048)
        return Result()

    monkeypatch.setattr(svc.subprocess, "run", fake_run)
    result = svc.convert_seed_vc(source, ref, out, singing=True, diffusion_steps=8)
    assert result == str(out.resolve())
    assert out.stat().st_size == 2048
    assert "--f0-condition" in seen["cmd"]
    assert seen["cmd"][seen["cmd"].index("--f0-condition") + 1] == "True"
    assert seen["cmd"][seen["cmd"].index("--fp16") + 1] == "False"


def test_seed_vc_discovers_bundled_install(monkeypatch, tmp_path):
    root = tmp_path / ".engines" / "seed-vc"
    root.mkdir(parents=True)
    (root / "inference.py").write_text("# fixture")
    monkeypatch.delenv("SEED_VC_DIR", raising=False)
    monkeypatch.setattr(svc, "PROJECT_ROOT", tmp_path)

    assert svc.seed_vc_available()


def test_seed_vc_is_preferred_for_zero_shot_conversion(monkeypatch, tmp_path):
    from engine_planner import choose_best_plan

    (tmp_path / "inference.py").write_text("# fixture")
    reference = tmp_path / "reference.wav"
    reference.write_bytes(b"reference")
    monkeypatch.setenv("SEED_VC_DIR", str(tmp_path))

    plan = choose_best_plan(
        profile={"name": "authorized", "reference": str(reference)},
        mode="song",
        target_has_voice=True,
    )

    assert plan["engine"] == "Seed-VC"
    assert plan["fallback"] is False


def test_seed_vc_is_a_neural_engine_for_quality_gates():
    from speaker_identity import precision_verdict

    verdict = precision_verdict(
        identity=0.75,
        engine="Seed-VC zero-shot neural voice conversion",
        reference_duration_s=20,
        reference_quality=0.7,
        quality_target="studio",
        identity_backend="neural",
    )

    assert verdict["neural_engine"] is True
    assert verdict["meets_quality_target"] is True


def test_seed_vc_never_reuses_output_from_an_earlier_run(monkeypatch, tmp_path):
    import pytest
    root = tmp_path / 'runtime'
    root.mkdir()
    (root / 'inference.py').write_text('# fixture')
    source = tmp_path / 'source.wav'
    source.write_bytes(b'audio')
    cache = tmp_path / '.seed_vc'
    cache.mkdir()
    (cache / 'old.wav').write_bytes(b'x' * 2048)
    monkeypatch.setenv('SEED_VC_DIR', str(root))
    class Result:
        returncode = 0
        stdout = stderr = ''
    monkeypatch.setattr(svc.subprocess, 'run', lambda *a, **kw: Result())
    with pytest.raises(RuntimeError, match='no WAV'):
        svc.convert_seed_vc(source, source, tmp_path / 'out.wav')
