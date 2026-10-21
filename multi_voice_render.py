"""Route detected vocal speakers to independent authorized voice profiles.

The module preserves the original song timeline. Each anonymous speaker stem from
verse_voices.distinguish_verse_voices is converted independently, then the
converted stems are summed sample-for-sample. If the recombined cloned vocal
would clip, the operation fails instead of normalizing or otherwise changing
the cloned vocal. The protected vocal-led mixer then adapts only the beat.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import soundfile as sf

from song_converter import combine_tracks, convert_vocals, separate_vocals
from verse_voices import distinguish_verse_voices


def parse_profile_map(values: list[str]) -> dict[str, Path]:
    """Parse repeated voice_01=/path/profile.json assignments."""
    result: dict[str, Path] = {}
    for raw in values:
        key, sep, value = str(raw).partition("=")
        key = key.strip()
        value = value.strip()
        if not sep or not key or not value:
            raise ValueError(
                f"Invalid profile mapping {raw!r}; expected voice_XX=/path/profile.json"
            )
        if key in result:
            raise ValueError(f"Duplicate profile mapping for {key}.")
        result[key] = Path(value)
    return result


def load_profile_map(values: list[str]) -> dict[str, dict[str, Any]]:
    paths = parse_profile_map(values)
    profiles: dict[str, dict[str, Any]] = {}
    for voice_id, path in paths.items():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Profile for {voice_id} must be a JSON object.")
        profiles[voice_id] = payload
    return profiles


def recombine_converted_stems(
    converted: Mapping[str, str | Path],
    out_path: str | Path,
    *,
    expected_frames: int | None = None,
) -> str:
    """Sum converted speaker stems without modifying their individual samples."""
    if not converted:
        raise ValueError("At least one converted speaker stem is required.")

    arrays: list[np.ndarray] = []
    sample_rate: int | None = None
    max_frames = int(expected_frames or 0)

    for voice_id, path in converted.items():
        data, sr = sf.read(str(path), dtype="float32", always_2d=True)
        if data.shape[0] == 0 or not np.isfinite(data).all():
            raise ValueError(f"Converted stem {voice_id} is empty or non-finite.")
        if sample_rate is None:
            sample_rate = int(sr)
        elif int(sr) != sample_rate:
            raise ValueError("Converted speaker stems must share one sample rate.")
        arrays.append(data)
        max_frames = max(max_frames, int(data.shape[0]))

    channels = max(data.shape[1] for data in arrays)
    mix = np.zeros((max_frames, channels), dtype=np.float64)
    for data in arrays:
        if data.shape[1] == 1 and channels == 2:
            data = np.repeat(data, 2, axis=1)
        elif data.shape[1] != channels:
            raise ValueError("Converted speaker stems must be mono/stereo compatible.")
        frames = min(max_frames, data.shape[0])
        mix[:frames] += data[:frames].astype(np.float64)

    if not np.isfinite(mix).all():
        raise RuntimeError("Recombined cloned vocal contains non-finite audio.")
    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    if peak >= 0.999:
        raise RuntimeError(
            "Recombined cloned vocal would clip; speaker conversions must be "
            "re-rendered with safe headroom instead of normalizing the clone."
        )

    output = Path(out_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(output), mix.astype(np.float32), sample_rate, subtype="FLOAT")
    return str(output)


def render_multi_speaker_song(
    song_path: str | Path,
    profiles: Mapping[str, dict[str, Any]],
    out_dir: str | Path,
    *,
    separation: str = "demucs",
    require_neural: bool = False,
    progress_cb=None,
) -> dict[str, Any]:
    """Separate, diarize, route speakers, recombine cloned vocal, and remix."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    vocals, beat, method = separate_vocals(
        song_path,
        out,
        separation,
        progress_cb,
        allow_fallback=not require_neural,
    )
    if not vocals or not beat:
        raise RuntimeError("Song separation failed.")
    if require_neural and method != "demucs":
        raise RuntimeError("Demucs neural separation was required but unavailable.")

    diarized = distinguish_verse_voices(vocals, out)
    detected = [str(item["voice"]) for item in diarized.get("voices", [])]
    missing = [voice_id for voice_id in detected if voice_id not in profiles]
    unknown = [voice_id for voice_id in profiles if voice_id not in detected]
    if missing:
        raise ValueError(
            "Missing authorized profile mapping for detected speaker(s): "
            + ", ".join(sorted(missing))
        )
    if unknown:
        raise ValueError(
            "Profile mapping references speaker(s) not detected in this song: "
            + ", ".join(sorted(unknown))
        )

    converted_dir = out / "converted_speakers"
    converted_dir.mkdir(exist_ok=True)
    converted: dict[str, str] = {}
    engines: dict[str, str] = {}
    voice_rows = {str(item["voice"]): item for item in diarized.get("voices", [])}

    for index, voice_id in enumerate(detected, start=1):
        source_stem = voice_rows[voice_id]["stem"]
        target = converted_dir / f"{voice_id}.wav"
        if progress_cb:
            progress_cb(
                f"Converting detected speaker {voice_id} ({index}/{len(detected)})...",
                35 + int(35 * index / max(1, len(detected))),
            )
        ok, engine = convert_vocals(
            source_stem,
            profiles[voice_id],
            target,
            out,
            progress_cb,
            require_neural=require_neural,
        )
        if not ok:
            raise RuntimeError(f"Conversion failed for {voice_id}: {engine}")
        converted[voice_id] = str(target)
        engines[voice_id] = engine

    source_info = sf.info(str(vocals))
    cloned_vocal = recombine_converted_stems(
        converted,
        out / "cloned_vocal_multi.wav",
        expected_frames=source_info.frames,
    )
    final = out / f"{Path(song_path).stem.replace(' ', '_')}_multi_voice.wav"
    combine_tracks(cloned_vocal, beat, final, progress_cb=progress_cb)

    report = {
        "song": str(song_path),
        "separation": method,
        "detected_speakers": detected,
        "speaker_routes": {
            voice_id: {
                "profile_name": str(profiles[voice_id].get("name") or voice_id),
                "source_stem": voice_rows[voice_id]["stem"],
                "converted_stem": converted[voice_id],
                "engine": engines[voice_id],
            }
            for voice_id in detected
        },
        "diarization_backend": diarized.get("backend"),
        "turns": diarized.get("turns", []),
        "verses": diarized.get("verses", []),
        "cloned_vocal": cloned_vocal,
        "beat": beat,
        "output": str(final),
        "mix_report": str(final.with_suffix(".mix.json")),
        "vocal_policy": "speaker stems recombined sample-for-sample; beat adapted around clone",
    }
    report_path = out / "multi_speaker_render.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report
