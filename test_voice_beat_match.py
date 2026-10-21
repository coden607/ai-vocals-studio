import voice_beat_match as match


def _voice(name, tempo, rms, f0, spectral):
    return {
        "name": name,
        "audio_profile": {
            "rms": rms,
            "median_f0_hz": f0,
            "spectral_envelope": spectral,
        },
        "_tempo": tempo,
    }


def test_rank_matrix_selects_best_voice_and_best_beat(monkeypatch):
    voices = [
        _voice("low-pocket", 90.0, 0.10, 110.0, [-12.0] * 8 + [0.0] * 8),
        _voice("bright-fast", 140.0, 0.05, 230.0, [0.0] * 8 + [-12.0] * 8),
    ]

    def fake_voice_features(profile):
        return {
            "name": profile["name"],
            "reference": None,
            "tempo_bpm": profile["_tempo"],
            "onset_rate_hz": 2.0,
            "rms": profile["audio_profile"]["rms"],
            "centroid_hz": 1500.0,
            "median_f0_hz": profile["audio_profile"]["median_f0_hz"],
            "spectral_profile": profile["audio_profile"]["spectral_envelope"],
        }

    beats = {
        "slow.wav": {
            "path": "slow.wav", "sample_rate": 22050, "duration_s": 30.0,
            "tempo_bpm": 90.0, "onset_rate_hz": 2.0, "rms": 0.20,
            "centroid_hz": 1200.0, "median_f0_hz": 0.0, "f0_std_hz": 0.0,
            "spectral_profile": [0.0] * 8 + [-12.0] * 8,
        },
        "fast.wav": {
            "path": "fast.wav", "sample_rate": 22050, "duration_s": 30.0,
            "tempo_bpm": 140.0, "onset_rate_hz": 3.0, "rms": 0.10,
            "centroid_hz": 2600.0, "median_f0_hz": 0.0, "f0_std_hz": 0.0,
            "spectral_profile": [-12.0] * 8 + [0.0] * 8,
        },
    }

    monkeypatch.setattr(match, "voice_features", fake_voice_features)
    monkeypatch.setattr(match, "analyze_audio", lambda path: beats[str(path)])

    report = match.rank_matrix(voices, ["slow.wav", "fast.wav"])

    best_by_beat = {row["beat"]: row["voice"] for row in report["best_voice_for_each_beat"]}
    assert best_by_beat["slow.wav"] == "low-pocket"
    assert best_by_beat["fast.wav"] == "bright-fast"

    best_by_voice = {row["voice"]: row["beat"] for row in report["best_beat_for_each_voice"]}
    assert best_by_voice["low-pocket"] == "slow.wav"
    assert best_by_voice["bright-fast"] == "fast.wav"


def test_score_is_explainable_and_not_clone_accuracy(monkeypatch):
    profile = _voice("test", 100.0, 0.08, 150.0, [-6.0] * 16)
    monkeypatch.setattr(match, "voice_features", lambda _profile: {
        "name": "test", "reference": None, "tempo_bpm": 100.0,
        "onset_rate_hz": 2.0, "rms": 0.08, "centroid_hz": 1600.0,
        "median_f0_hz": 150.0, "spectral_profile": [-6.0] * 16,
    })
    monkeypatch.setattr(match, "analyze_audio", lambda _path: {
        "path": "beat.wav", "sample_rate": 22050, "duration_s": 20.0,
        "tempo_bpm": 100.0, "onset_rate_hz": 2.0, "rms": 0.16,
        "centroid_hz": 1800.0, "median_f0_hz": 0.0, "f0_std_hz": 0.0,
        "spectral_profile": [-12.0] * 16,
    })

    result = match.score_voice_beat(profile, "beat.wav")
    assert 0.0 <= result["fit_score"] <= 100.0
    assert set(result["factors"]) == {
        "rhythm_pocket", "energy_balance", "spectral_space", "pitch_room"
    }
    assert result["score_type"] == "arrangement_compatibility_heuristic"
    assert "not speaker identity" in result["note"]


def test_half_time_and_double_time_count_as_rhythm_matches():
    assert match._tempo_compatibility(70.0, 140.0) > 0.95
    assert match._tempo_compatibility(140.0, 70.0) > 0.95
