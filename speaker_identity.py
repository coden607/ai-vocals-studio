"""Speaker-identity embeddings and clone-precision scoring.

The previous pipeline scored clones with median F0, a 16-band energy envelope,
and RMS. Those metrics can look high after a pitch/timbre DSP map without the
output actually matching the speaker.

This module adds a speaker embedding (neural if installed, otherwise a stable
acoustic fingerprint) and an honest precision verdict. DSP fallbacks are never
labeled near-precision.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

try:
    import librosa

    HAS_LIBROSA = True
except ImportError:  # pragma: no cover
    HAS_LIBROSA = False


SAMPLE_RATE = 16000
NEAR_PRECISION_IDENTITY = 0.82
STUDIO_IDENTITY = 0.68
MIN_REFERENCE_SECONDS_NEAR = 15.0
MIN_REFERENCE_QUALITY_NEAR = 0.55
NEURAL_ENGINES = {
    "RVC",
    "ElevenLabs",
    "Qwen3-TTS",
    "XTTS v2",
    "XTTS v2 sidecar",
}


class PrecisionCloneError(RuntimeError):
    """Raised when a requested precision target cannot be met honestly."""


def _load_mono(path: str | Path, sr: int = SAMPLE_RATE) -> np.ndarray:
    if HAS_LIBROSA:
        y, _ = librosa.load(str(path), sr=sr, mono=True)
        return np.asarray(y, dtype=np.float32)
    import soundfile as sf

    y, file_sr = sf.read(str(path), dtype="float32", always_2d=False)
    if getattr(y, "ndim", 1) > 1:
        y = np.mean(y, axis=1)
    if file_sr != sr and y.size:
        duration = len(y) / float(file_sr)
        target = max(1, int(round(duration * sr)))
        x_old = np.linspace(0.0, 1.0, num=len(y), endpoint=False)
        x_new = np.linspace(0.0, 1.0, num=target, endpoint=False)
        y = np.interp(x_new, x_old, y).astype(np.float32)
    return np.asarray(y, dtype=np.float32)


def _l2_normalize(vec: np.ndarray) -> np.ndarray:
    vec = np.asarray(vec, dtype=np.float64).reshape(-1)
    norm = float(np.linalg.norm(vec))
    if norm < 1e-9:
        return vec
    return vec / norm


def _pitch_histogram(y: np.ndarray, sr: int, bins: int = 24) -> np.ndarray:
    if not HAS_LIBROSA or y.size < sr // 4:
        return np.zeros(bins, dtype=np.float64)
    try:
        f0 = librosa.yin(y, fmin=50.0, fmax=500.0, sr=sr, frame_length=2048)
    except Exception:
        return np.zeros(bins, dtype=np.float64)
    voiced = f0[np.isfinite(f0) & (f0 > 50.0)]
    if voiced.size == 0:
        return np.zeros(bins, dtype=np.float64)
    log_f0 = np.log2(voiced)
    hist, _ = np.histogram(log_f0, bins=bins, range=(np.log2(50.0), np.log2(500.0)), density=True)
    return hist.astype(np.float64)


def acoustic_embedding(y: np.ndarray, sr: int = SAMPLE_RATE) -> np.ndarray:
    """Content-robust speaker fingerprint from MFCCs, contrast, chroma, pitch."""
    if y.size == 0:
        return np.zeros(140, dtype=np.float64)
    y = np.asarray(y, dtype=np.float32)
    peak = float(np.max(np.abs(y)) or 1.0)
    y = y / peak * 0.95
    if not HAS_LIBROSA:
        spec = np.abs(np.fft.rfft(y[: min(len(y), sr * 4)]))
        bands = np.array_split(spec, 32)
        stats = [float(np.mean(y)), float(np.std(y)), float(np.sqrt(np.mean(y ** 2)))]
        return _l2_normalize(np.concatenate([np.array(stats), np.array([float(np.mean(b)) for b in bands])]))

    n_fft = 1024
    hop = 256
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20, n_fft=n_fft, hop_length=hop)
    delta = librosa.feature.delta(mfcc)
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr, n_fft=n_fft, hop_length=hop)
    chroma = librosa.feature.chroma_stft(y=y, sr=sr, n_fft=n_fft, hop_length=hop)
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, n_fft=n_fft, hop_length=hop)
    rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, n_fft=n_fft, hop_length=hop)
    zcr = librosa.feature.zero_crossing_rate(y, hop_length=hop)
    rms = librosa.feature.rms(y=y, hop_length=hop)

    parts = [
        mfcc.mean(axis=1),
        mfcc.std(axis=1),
        delta.mean(axis=1),
        delta.std(axis=1),
        contrast.mean(axis=1),
        contrast.std(axis=1),
        chroma.mean(axis=1),
        _pitch_histogram(y, sr),
        np.array(
            [
                float(np.mean(centroid)),
                float(np.std(centroid)),
                float(np.mean(rolloff)),
                float(np.std(rolloff)),
                float(np.mean(zcr)),
                float(np.mean(rms)),
                float(np.std(rms)),
            ],
            dtype=np.float64,
        ),
    ]
    return _l2_normalize(np.concatenate([np.asarray(p, dtype=np.float64).reshape(-1) for p in parts]))


def _neural_embedding(path: str | Path) -> Optional[np.ndarray]:
    """Optional stronger backends. Never required; absence is not a failure."""
    try:
        from resemblyzer import VoiceEncoder, preprocess_wav  # type: ignore

        encoder = VoiceEncoder()
        wav = preprocess_wav(str(path))
        return _l2_normalize(np.asarray(encoder.embed_utterance(wav), dtype=np.float64))
    except Exception:
        pass
    try:
        from speechbrain.inference.speaker import EncoderClassifier  # type: ignore

        classifier = EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb")
        signal = _load_mono(path, 16000)
        tensor = classifier.encode_batch(
            __import__("torch").tensor(signal).unsqueeze(0)
        )
        return _l2_normalize(tensor.squeeze().detach().cpu().numpy().astype(np.float64))
    except Exception:
        return None


def extract_embedding(audio: str | Path | np.ndarray, sr: int = SAMPLE_RATE) -> dict[str, Any]:
    """Return embedding + backend used."""
    neural = None
    path: Optional[Path] = None
    if isinstance(audio, (str, Path)):
        path = Path(audio)
        neural = _neural_embedding(path)
        y = _load_mono(path, sr)
    else:
        y = np.asarray(audio, dtype=np.float32)
        if HAS_LIBROSA and sr != SAMPLE_RATE:
            y = librosa.resample(y, orig_sr=sr, target_sr=SAMPLE_RATE)
            sr = SAMPLE_RATE
    if neural is not None:
        return {
            "backend": "neural",
            "vector": [round(float(v), 6) for v in neural.tolist()],
            "dim": int(neural.size),
        }
    vec = acoustic_embedding(y, SAMPLE_RATE if path is not None else sr)
    return {
        "backend": "acoustic",
        "vector": [round(float(v), 6) for v in vec.tolist()],
        "dim": int(vec.size),
    }


def average_embeddings(embeddings: Iterable[dict[str, Any]]) -> Optional[dict[str, Any]]:
    items = [e for e in embeddings if e and e.get("vector")]
    if not items:
        return None
    backend = items[0].get("backend", "acoustic")
    dim = min(len(e["vector"]) for e in items)
    stacked = np.stack([np.asarray(e["vector"][:dim], dtype=np.float64) for e in items], axis=0)
    vec = _l2_normalize(stacked.mean(axis=0))
    return {
        "backend": backend,
        "vector": [round(float(v), 6) for v in vec.tolist()],
        "dim": int(vec.size),
        "source_count": len(items),
    }


def cosine_similarity(a: Iterable[float], b: Iterable[float]) -> float:
    va = np.asarray(list(a), dtype=np.float64).reshape(-1)
    vb = np.asarray(list(b), dtype=np.float64).reshape(-1)
    n = min(va.size, vb.size)
    if n == 0:
        return 0.0
    va = _l2_normalize(va[:n])
    vb = _l2_normalize(vb[:n])
    return float(np.clip(np.dot(va, vb), -1.0, 1.0))


def _engine_family(engine: str | None) -> str:
    text = str(engine or "")
    if "RVC" in text:
        return "RVC"
    if "ElevenLabs" in text:
        return "ElevenLabs"
    if "Qwen" in text:
        return "Qwen3-TTS"
    if "XTTS" in text:
        return "XTTS v2"
    if "DSP" in text or "WORLD" in text or "gTTS" in text:
        return "WORLD/DSP"
    return text or "unknown"


def is_neural_engine(engine: str | None) -> bool:
    family = _engine_family(engine)
    if family in NEURAL_ENGINES:
        return True
    text = str(engine or "")
    return any(name in text for name in ("RVC", "ElevenLabs", "Qwen3-TTS", "XTTS"))


def score_identity(
    *,
    reference_embedding: dict[str, Any] | None,
    output_audio: str | Path,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare an output clip to a stored speaker embedding (or profile reference)."""
    ref = reference_embedding
    if (not ref or not ref.get("vector")) and profile:
        ref = (profile.get("audio_profile") or {}).get("speaker_embedding")
        if (not ref or not ref.get("vector")) and profile.get("reference"):
            ref = extract_embedding(profile["reference"])
    if not ref or not ref.get("vector"):
        return {
            "identity": 0.0,
            "backend": "none",
            "notes": ["No speaker embedding available on the voice profile."],
        }
    out = extract_embedding(output_audio)
    identity = cosine_similarity(ref["vector"], out["vector"])
    identity_pct = round(((identity + 1.0) / 2.0) * 100.0, 1)
    return {
        "identity": round(float(identity), 4),
        "identity_pct": identity_pct,
        "backend": f"{ref.get('backend', 'acoustic')}+{out.get('backend', 'acoustic')}",
        "reference_backend": ref.get("backend"),
        "output_backend": out.get("backend"),
        "output_embedding": out,
    }


def precision_verdict(
    *,
    identity: float,
    engine: str | None,
    reference_duration_s: float = 0.0,
    reference_quality: float = 0.0,
    quality_target: str = "studio",
) -> dict[str, Any]:
    """Honest label for how close this output is to a usable clone."""
    neural = is_neural_engine(engine)
    reasons: list[str] = []
    if not neural:
        reasons.append("Output used WORLD/DSP or another non-neural map; that cannot be near-precision.")
    if identity < NEAR_PRECISION_IDENTITY:
        reasons.append(
            f"Speaker identity {identity:.3f} is below near-precision threshold {NEAR_PRECISION_IDENTITY:.2f}."
        )
    if reference_duration_s < MIN_REFERENCE_SECONDS_NEAR:
        reasons.append(
            f"Reference is {reference_duration_s:.1f}s; near-precision needs ≥{MIN_REFERENCE_SECONDS_NEAR:.0f}s of clean speech."
        )
    if reference_quality and reference_quality < MIN_REFERENCE_QUALITY_NEAR:
        reasons.append(
            f"Reference quality {reference_quality:.2f} is below {MIN_REFERENCE_QUALITY_NEAR:.2f}."
        )

    if neural and identity >= NEAR_PRECISION_IDENTITY and reference_duration_s >= MIN_REFERENCE_SECONDS_NEAR and (
        not reference_quality or reference_quality >= MIN_REFERENCE_QUALITY_NEAR
    ):
        level = "near_precision"
    elif identity >= STUDIO_IDENTITY and (neural or quality_target != "pro"):
        level = "studio"
    elif identity >= 0.50:
        level = "draft"
    else:
        level = "not_a_clone"

    pass_pro = level == "near_precision"

    return {
        "level": level,
        "neural_engine": neural,
        "meets_near_precision": level == "near_precision",
        "meets_quality_target": (
            level == "near_precision"
            if quality_target == "pro"
            else level in {"near_precision", "studio"}
            if quality_target == "studio"
            else level != "not_a_clone"
        ),
        "pro_ready": pass_pro,
        "reasons": reasons if level != "near_precision" else ["Neural engine, identity, duration, and reference quality all cleared."],
        "thresholds": {
            "near_precision_identity": NEAR_PRECISION_IDENTITY,
            "studio_identity": STUDIO_IDENTITY,
            "min_reference_seconds": MIN_REFERENCE_SECONDS_NEAR,
            "min_reference_quality": MIN_REFERENCE_QUALITY_NEAR,
        },
    }


def attach_embedding_to_profile(profile: dict[str, Any], audio_path: str | Path | None = None) -> dict[str, Any]:
    """Compute and store a speaker embedding on a voice profile."""
    path = audio_path or profile.get("reference")
    if not path:
        return profile
    embedding = extract_embedding(path)
    profile.setdefault("audio_profile", {})
    profile["audio_profile"]["speaker_embedding"] = embedding
    profile["audio_profile"]["speaker_embedding_backend"] = embedding.get("backend")
    return profile


def enforce_quality_target(verdict: dict[str, Any], quality_target: str) -> None:
    if quality_target != "pro":
        return
    if verdict.get("meets_near_precision"):
        return
    reasons = "; ".join(verdict.get("reasons") or ["near-precision gates failed"])
    raise PrecisionCloneError(
        "Pro-match / near-precision target was not met. " + reasons
    )
