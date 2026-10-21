from pathlib import Path

import numpy as np
import soundfile as sf
import pytest

import multi_voice_render as multi


def test_parse_profile_map_rejects_duplicates_and_bad_values():
    parsed = multi.parse_profile_map(["voice_01=a.json", "voice_02=b.json"])
    assert parsed["voice_01"] == Path("a.json")
    with pytest.raises(ValueError):
        multi.parse_profile_map(["voice_01=a.json", "voice_01=b.json"])
    with pytest.raises(ValueError):
        multi.parse_profile_map(["voice_01"])


def test_recombine_preserves_timeline_and_fails_closed_on_clipping(tmp_path):
    sr = 16000
    a = np.zeros(sr, dtype=np.float32)
    b = np.zeros(sr, dtype=np.float32)
    a[: sr // 2] = 0.4
    b[sr // 2 :] = 0.3
    pa = tmp_path / "a.wav"
    pb = tmp_path / "b.wav"
    sf.write(pa, a, sr, subtype="FLOAT")
    sf.write(pb, b, sr, subtype="FLOAT")

    out = tmp_path / "combined.wav"
    multi.recombine_converted_stems({"voice_01": pa, "voice_02": pb}, out, expected_frames=sr)
    y, out_sr = sf.read(out, dtype="float32")
    assert out_sr == sr
    assert len(y) == sr
    assert np.allclose(y[: sr // 2], 0.4, atol=1e-5)
    assert np.allclose(y[sr // 2 :], 0.3, atol=1e-5)

    sf.write(pb, np.full(sr, 0.7, dtype=np.float32), sr, subtype="FLOAT")
    sf.write(pa, np.full(sr, 0.7, dtype=np.float32), sr, subtype="FLOAT")
    with pytest.raises(RuntimeError, match="would clip"):
        multi.recombine_converted_stems({"voice_01": pa, "voice_02": pb}, out)


def test_render_multi_requires_exact_detected_speaker_mapping(tmp_path, monkeypatch):
    vocals = tmp_path / "vocals.wav"
    beat = tmp_path / "beat.wav"
    sf.write(vocals, np.zeros(16000, dtype=np.float32), 16000)
    sf.write(beat, np.zeros(16000, dtype=np.float32), 16000)

    monkeypatch.setattr(
        multi,
        "separate_vocals",
        lambda *_args, **_kwargs: (str(vocals), str(beat), "demucs"),
    )
    monkeypatch.setattr(
        multi,
        "distinguish_verse_voices",
        lambda *_args, **_kwargs: {
            "backend": "neural-verse-diarization",
            "voices": [
                {"voice": "voice_01", "stem": str(vocals)},
                {"voice": "voice_02", "stem": str(vocals)},
            ],
            "turns": [],
            "verses": [],
        },
    )

    with pytest.raises(ValueError, match="Missing authorized profile mapping"):
        multi.render_multi_speaker_song(
            "song.wav",
            {"voice_01": {"name": "A"}},
            tmp_path / "out",
        )
