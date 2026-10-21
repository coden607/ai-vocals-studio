from pathlib import Path

import numpy as np
import soundfile as sf

import verse_voices


def test_merge_adjacent_same_voice_turns():
    turns = [
        {"turn": 1, "voice": "voice_01", "start_s": 0.0, "end_s": 2.0, "confidence": 0.9},
        {"turn": 2, "voice": "voice_01", "start_s": 2.4, "end_s": 4.0, "confidence": 0.8},
        {"turn": 3, "voice": "voice_02", "start_s": 5.0, "end_s": 7.0, "confidence": 0.85},
    ]
    verses = verse_voices._merge_adjacent_turns(turns)
    assert len(verses) == 2
    assert verses[0]["turns"] == [1, 2]
    assert verses[0]["voice"] == "voice_01"
    assert verses[1]["voice"] == "voice_02"


def test_distinguish_verse_voices_reports_backend_and_verses(tmp_path, monkeypatch):
    sr = 16000
    y = np.concatenate([
        np.full(sr * 2, 0.08, dtype=np.float32),
        np.zeros(sr, dtype=np.float32),
        np.full(sr * 2, 0.12, dtype=np.float32),
    ])
    source = tmp_path / "vocals.wav"
    sf.write(source, y, sr)

    calls = {"n": 0}

    def fake_embed(_clip, _sr, _temp_dir):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"backend": "neural", "vector": [1.0, 0.0]}
        return {"backend": "neural", "vector": [0.0, 1.0]}

    monkeypatch.setattr(verse_voices, "_embed_clip", fake_embed)
    report = verse_voices.distinguish_verse_voices(source, tmp_path / "out", window_s=10.0)

    assert report["backend"] == "neural-verse-diarization"
    assert report["identity_scope"] == "anonymous speaker clusters only"
    assert len(report["voices"]) == 2
    assert len(report["verses"]) == 2
    assert {turn["embedding_backend"] for turn in report["turns"]} == {"neural"}


def test_acoustic_threshold_is_stricter_than_neural(tmp_path, monkeypatch):
    sr = 16000
    y = np.concatenate([
        np.full(sr, 0.08, dtype=np.float32),
        np.zeros(sr, dtype=np.float32),
        np.full(sr, 0.08, dtype=np.float32),
    ])
    source = tmp_path / "vocals.wav"
    sf.write(source, y, sr)

    vectors = iter([
        {"backend": "acoustic", "vector": [1.0, 0.0]},
        {"backend": "acoustic", "vector": [0.76, 0.65]},
    ])
    monkeypatch.setattr(verse_voices, "_embed_clip", lambda *_: next(vectors))
    report = verse_voices.distinguish_verse_voices(source, tmp_path / "out", window_s=10.0)

    assert report["backend"] == "acoustic-verse-diarization"
    assert len(report["voices"]) == 2
