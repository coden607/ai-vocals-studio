from pathlib import Path
import shutil
import subprocess
import numpy as np
import pytest
import soundfile as sf
from audio_export import probe_audio, export_like_source


pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="ffmpeg/ffprobe unavailable",
)


def test_mp3_export_matches_source_bitrate_class(tmp_path: Path):
    wav = tmp_path / "master.wav"
    t = np.arange(44100, dtype=np.float32) / 44100
    sf.write(wav, 0.1 * np.sin(2 * np.pi * 220 * t), 44100)
    source = tmp_path / "source.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(wav), "-c:a", "libmp3lame", "-b:a", "192k",
        str(source)
    ], check=True, capture_output=True)
    out = export_like_source(wav, source, tmp_path / "out")
    meta = probe_audio(out)
    assert Path(out).suffix == ".mp3"
    assert meta["codec"] == "mp3"
    assert 180000 <= meta["bit_rate"] <= 205000
