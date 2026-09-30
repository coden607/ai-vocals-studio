from pathlib import Path
import seed_vc_engine as svc


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
        run_dir = out.parent / ".seed_vc"
        (run_dir / "generated.wav").write_bytes(b"x" * 2048)
        return Result()

    monkeypatch.setattr(svc.subprocess, "run", fake_run)
    result = svc.convert_seed_vc(source, ref, out, singing=True, diffusion_steps=8)
    assert result == str(out.resolve())
    assert out.stat().st_size == 2048
    assert "--f0-condition" in seen["cmd"]
    assert seen["cmd"][seen["cmd"].index("--f0-condition") + 1] == "True"
    assert seen["cmd"][seen["cmd"].index("--fp16") + 1] == "False"
