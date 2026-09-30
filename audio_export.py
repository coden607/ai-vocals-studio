"""Final audio export helpers.

The processing master remains WAV/float audio. Delivery encoding can mirror the
source container/bitrate when that is technically meaningful; lossless sources
stay lossless. Requires ffmpeg/ffprobe for compressed delivery formats.
"""
from __future__ import annotations
import json
import shutil
import subprocess
from pathlib import Path


def probe_audio(path: str | Path) -> dict:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise RuntimeError("ffprobe is required for source-matched export")
    p = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_name,bit_rate,sample_rate,channels",
         "-show_entries", "format=format_name,bit_rate",
         "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    data = json.loads(p.stdout)
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    return {
        "codec": stream.get("codec_name"),
        "bit_rate": int(stream.get("bit_rate") or fmt.get("bit_rate") or 0),
        "sample_rate": int(stream.get("sample_rate") or 0),
        "channels": int(stream.get("channels") or 0),
        "format": fmt.get("format_name", ""),
    }


def export_like_source(master_wav: str | Path, source: str | Path,
                       out_dir: str | Path) -> str:
    """Encode a delivery copy resembling source codec/bitrate.

    WAV/FLAC sources remain lossless. MP3/AAC/Opus use the source bitrate when
    reported, clamped to sensible codec ranges. This never re-encodes the
    processing master until final delivery.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for source-matched export")
    meta = probe_audio(source)
    codec = meta["codec"]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(master_wav).stem
    if codec in {"flac"}:
        ext, args = ".flac", ["-c:a", "flac"]
    elif codec in {"pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le"}:
        ext, args = ".wav", ["-c:a", codec]
    elif codec == "mp3":
        br = min(max(meta["bit_rate"] or 192000, 64000), 320000)
        ext, args = ".mp3", ["-c:a", "libmp3lame", "-b:a", str(br)]
    elif codec in {"aac"}:
        br = min(max(meta["bit_rate"] or 192000, 64000), 320000)
        ext, args = ".m4a", ["-c:a", "aac", "-b:a", str(br)]
    elif codec in {"opus"}:
        br = min(max(meta["bit_rate"] or 160000, 48000), 256000)
        ext, args = ".opus", ["-c:a", "libopus", "-b:a", str(br)]
    else:
        ext, args = ".flac", ["-c:a", "flac"]
    out = out_dir / f"{stem}_source_matched{ext}"
    subprocess.run([ffmpeg, "-y", "-i", str(master_wav), *args, str(out)],
                   check=True, capture_output=True, text=True)
    return str(out)
