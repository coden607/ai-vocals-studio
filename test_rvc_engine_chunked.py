#!/usr/bin/env python3
"""Chunked RVC inference must preserve duration and stay decodable."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import soundfile as sf

from rvc_engine import RvcEngine


class _FakeRvc:
    """Stand-in for rvc_python.infer.RVCInference: halves amplitude."""

    def __init__(self) -> None:
        self.calls = 0

    def infer_file(self, input_path: str, output_path: str) -> None:
        audio, sr = sf.read(input_path, dtype="float32")
        self.calls += 1
        sf.write(output_path, (audio * 0.5).astype("float32"), sr)


def _engine() -> RvcEngine:
    engine = RvcEngine.__new__(RvcEngine)
    engine._rvc = _FakeRvc()
    return engine


def test_short_audio_converts_in_one_pass(tmp_path: Path) -> None:
    sr = 16000
    t = np.arange(sr * 3) / sr
    src = tmp_path / "in.wav"
    out = tmp_path / "out.wav"
    sf.write(src, (0.2 * np.sin(2 * np.pi * 220 * t)).astype("float32"), sr)

    engine = _engine()
    engine._infer_file(src, out)

    assert engine._rvc.calls == 1
    audio, out_sr = sf.read(out)
    assert out_sr == sr
    assert abs(len(audio) / out_sr - 3.0) < 0.05
    assert 0.05 < np.sqrt(np.mean(audio ** 2)) < 0.2


def test_long_audio_is_chunked_and_duration_preserved(tmp_path: Path,
                                                      monkeypatch) -> None:
    monkeypatch.setenv("RVC_CHUNK_SECONDS", "4")
    sr = 16000
    seconds = 11.0
    t = np.arange(int(sr * seconds)) / sr
    src = tmp_path / "in.wav"
    out = tmp_path / "out.wav"
    sf.write(src, (0.2 * np.sin(2 * np.pi * 220 * t)).astype("float32"), sr)

    engine = _engine()
    engine._infer_file(src, out)

    assert engine._rvc.calls >= 3, "11s with 4s chunks must split"
    audio, out_sr = sf.read(out)
    assert out_sr == sr
    drift = abs(len(audio) / out_sr - seconds)
    assert drift < 0.1, f"duration drift {drift:.3f}s"
    assert np.isfinite(audio).all()
    assert np.sqrt(np.mean(audio ** 2)) > 0.05


if __name__ == "__main__":
    import tempfile

    class _MonkeyPatch:
        def setenv(self, key: str, value: str) -> None:
            os.environ[key] = value

    with tempfile.TemporaryDirectory() as d:
        test_short_audio_converts_in_one_pass(Path(d))
    with tempfile.TemporaryDirectory() as d:
        test_long_audio_is_chunked_and_duration_preserved(Path(d), _MonkeyPatch())
    print("chunked RVC inference tests passed")
