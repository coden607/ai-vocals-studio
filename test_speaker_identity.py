import numpy as np
import soundfile as sf

from speaker_identity import PrecisionCloneError, enforce_quality_target, extract_embedding, precision_verdict, score_identity


def test_same_clip_identity_is_high(tmp_path):
    sr = 16000
    t = np.linspace(0, 1.5, int(sr * 1.5), endpoint=False)
    y = (0.2 * np.sin(2 * np.pi * 140 * t)).astype(np.float32)
    path = tmp_path / "same.wav"
    sf.write(path, y, sr)
    emb = extract_embedding(path)
    score = score_identity(reference_embedding=emb, output_audio=path)
    assert score["identity"] > 0.95


def test_dsp_cannot_claim_studio():
    verdict = precision_verdict(identity=0.91, engine="gTTS + DSP", reference_duration_s=30, reference_quality=0.8, quality_target="studio")
    assert verdict["level"] != "studio"
    assert verdict["meets_quality_target"] is False
    try:
        enforce_quality_target(verdict, "studio")
    except PrecisionCloneError:
        return
    raise AssertionError("studio DSP result should fail closed")


def test_neural_can_meet_studio():
    verdict = precision_verdict(identity=0.75, engine="XTTS v2", reference_duration_s=20, reference_quality=0.7, quality_target="studio")
    assert verdict["meets_quality_target"] is True
    assert verdict["meets_near_precision"] is False
