"""
song_converter.py — Turn ANY song into the voice of a cloned vocal profile.

Pipeline for "change any song with a cloned voice":
    1. separate  -> extract clean vocals + instrumental from any song
                     ("center" = instant stereo center-channel karaoke trick;
                      "demucs" = neural separation, ~700 MB model download)
    2. convert   -> morph the song's vocals toward the cloned voice profile.
                     Keeps rhythm/flow/melody but moves pitch, formants and
                     timbre toward the target voice. Backends:
                       - RVC (real neural conversion, when a trained model
                         exists for the voice)
                       - DSP (pure librosa/scipy - no download, works anywhere)
    3. combine   -> mix converted vocals back over the instrumental.

Only use this with voices you own or have permission to clone.
"""
from __future__ import annotations

import os
import json
import shutil
import sys
import threading
import subprocess
from pathlib import Path
from typing import Callable, Optional

import numpy as np

try:
    import soundfile as sf
    HAS_SF = True
except ImportError:                                   # pragma: no cover
    HAS_SF = False

try:
    import librosa
    HAS_LIBROSA = True
except ImportError:                                   # pragma: no cover
    HAS_LIBROSA = False

try:
    from scipy import signal as _signal
    HAS_SCIPY = True
except ImportError:                                   # pragma: no cover
    HAS_SCIPY = False

_ProgressCB = Callable[[str, int], None]


def _noop(msg: str, pct: int) -> None:
    pass


# lazy demucs flag (heavy import, do on demand)
_demucs_ready = threading.Event()
_HAS_DEMUCS = False


def _ensure_demucs(progress_cb: Optional[_ProgressCB] = None) -> bool:
    """Import demucs on demand (only needed for neural separation)."""
    global _HAS_DEMUCS
    if _demucs_ready.is_set():
        return _HAS_DEMUCS
    try:
        if progress_cb:
            progress_cb("Loading demucs (neural separation)...", 5)
        import demucs  # noqa: F401
        _HAS_DEMUCS = True
    except Exception:
        _HAS_DEMUCS = False
    finally:
        _demucs_ready.set()
    return _HAS_DEMUCS

# ─────────────────────────────────────────────────────────────────
#  Step 1 — Vocal / instrumental separation
# ─────────────────────────────────────────────────────────────────
def separate_vocals(
    song_path: str | Path,
    work_dir: str | Path,
    method: str = "auto",
    progress_cb: Optional[_ProgressCB] = None,
) -> tuple[Optional[str], Optional[str], str]:
    """
    Split `song_path` into vocals and instrumental tracks.

    method:
      "auto"   -> demucs if available, else center-channel
      "demucs" -> neural separation (best quality; downloads model once)
      "center" -> instant stereo center-channel (vocals ~= center). Requires a
                  stereo recording (works great on most studio songs).

    Returns (vocals_wav, instrumental_wav, method_used).
    On failure returns (None, None, method_used).
    """
    cb = progress_cb or _noop
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    if method == "auto":
        method = "demucs" if _ensure_demucs() else "center"

    # ---- center-channel (karaoke trick) ----
    if method == "center":
        cb("Reading song...", 10)
        data, sr = sf.read(str(song_path), dtype="float32")
        if data.ndim == 1:
            # mono input: nothing to subtract, fall back to full track
            cb("Mono source - using full track as vocals", 30)
            vocals = data
            inst = np.zeros_like(data)
        else:
            cb("Extracting center-channel vocals...", 35)
            left = data[:, 0].astype(np.float32)
            right = data[:, 1].astype(np.float32)
            vocals = ((left + right) / 2.0).astype(np.float32)
            inst = ((left - right) / 2.0).astype(np.float32)

        vocals_w = work_dir / "vocals.wav"
        inst_w = work_dir / "instrumental.wav"
        sf.write(str(vocals_w), vocals, sr)
        sf.write(str(inst_w), inst, sr)
        cb("Separation done", 100)
        return str(vocals_w), str(inst_w), "center"

    # ---- neural demucs ----
    if method == "demucs":
        if not _ensure_demucs(cb):
            cb("demucs unavailable - using center-channel", 0)
            return separate_vocals(song_path, work_dir, "center", cb)
        try:
            cb("Separating with demucs (first run downloads model)...", 20)
            cmd = [
                sys.executable, "-m", "demucs", "--two-stems", "vocals",
                "-o", str(work_dir / "demucs"), str(song_path),
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if r.returncode != 0:
                cb(f"demucs failed ({r.stderr[-200:].strip()}) - using center", 0)
                return separate_vocals(song_path, work_dir, "center", cb)
            demucs_out = list((work_dir / "demucs").rglob("vocals.wav"))
            if not demucs_out:
                cb("demucs produced no output - using center", 0)
                return separate_vocals(song_path, work_dir, "center", cb)
            vocals_src = demucs_out[0]
            inst_src = vocals_src.with_name("no_vocals.wav")
            vocals_w = work_dir / "vocals.wav"
            inst_w = work_dir / "instrumental.wav"
            shutil.copy2(vocals_src, vocals_w)
            if inst_src.exists():
                shutil.copy2(inst_src, inst_w)
            else:
                sf.write(str(inst_w), np.zeros((1,)), 44100)
            cb("Separation done", 100)
            return str(vocals_w), str(inst_w), "demucs"
        except Exception as e:  # pragma: no cover
            cb(f"demucs error ({e}) - using center", 0)
            return separate_vocals(song_path, work_dir, "center", cb)

    cb("Unknown method - using center", 0)
    return separate_vocals(song_path, work_dir, "center", cb)


def _load_mono(path: str | Path, sr: int = 22050) -> np.ndarray:
    """Load any audio file as mono float32 at `sr`."""
    if HAS_LIBROSA:
        return librosa.load(str(path), sr=sr, mono=True)[0].astype(np.float32)
    y, _ = sf.read(str(path), dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    return y


def _to_stereo(mono: np.ndarray) -> np.ndarray:
    return np.stack([mono, mono], axis=-1)
# ─────────────────────────────────────────────────────────────────
#  Vocal analysis helpers (used for profiling AND conversion)
# ─────────────────────────────────────────────────────────────────
def estimate_pitch(y: np.ndarray, sr: int = 22050) -> tuple[float, float]:
    """
    Estimate median fundamental frequency (Hz) and std over voiced frames.
    Uses librosa.yin (fast, robust). Returns (median_f0, std_f0) or (0, 0).
    """
    if not HAS_LIBROSA:
        return 0.0, 0.0
    try:
        f0 = librosa.yin(y, fmin=librosa.note_to_hz("C2"),
                         fmax=librosa.note_to_hz("C6"), sr=sr)
        voiced = f0[(f0 > 0) & np.isfinite(f0)]
        if voiced.size == 0:
            return 0.0, 0.0
        return float(np.median(voiced)), float(np.std(voiced))
    except Exception:
        return 0.0, 0.0


def voiced_fraction(y: np.ndarray, sr: int = 22050) -> float:
    """Return the fraction of frames with detectable voice-like pitch."""
    if not HAS_LIBROSA or y.size == 0:
        return 0.0
    if float(np.sqrt(np.mean(y ** 2))) < 1e-4:
        return 0.0
    try:
        f0 = librosa.yin(y, fmin=librosa.note_to_hz("C2"),
                         fmax=librosa.note_to_hz("C6"), sr=sr)
        rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
        if rms.size != f0.size:
            rms = np.interp(
                np.linspace(0, 1, f0.size),
                np.linspace(0, 1, rms.size),
                rms,
            )
        threshold = max(1e-4, float(np.percentile(rms, 65)) * 0.25)
        voiced = (f0 > 0) & np.isfinite(f0) & (rms > threshold)
        return float(np.mean(voiced)) if f0.size else 0.0
    except Exception:
        return 0.0


def band_energy_profile(y: np.ndarray, sr: int = 22050,
                        n_bands: int = 16) -> list[float]:
    """Long-term average per-band RMS dB profile of `y` (log-mel-like)."""
    if not HAS_LIBROSA:
        return [0.0] * n_bands
    mels = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=n_bands,
                                          fmax=sr / 2)
    band_db = librosa.power_to_db(mels, ref=np.max)
    avg = np.mean(band_db, axis=1)
    avg = avg - np.max(avg)
    return [float(v) for v in avg]


def _limit(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ─────────────────────────────────────────────────────────────────
#  DSP voice morph engine (no model download needed)
# ─────────────────────────────────────────────────────────────────
def dsp_morph_vocals(
    vocals_path: str | Path,
    profile: dict,
    out_path: str | Path,
    sr: int = 22050,
    progress_cb: Optional[_ProgressCB] = None,
    pitch_steps: Optional[float] = None,
) -> str:
    """
    Morph `vocals_path` toward `profile` using pure DSP:

      1. pitch shift so the song's median pitch matches the cloned voice
      2. spectral-envelope shaping so broadband timbre moves toward the voice
      3. gentle dynamics (RMS) matching
    """
    cb = progress_cb or _noop
    if not HAS_LIBROSA:
        raise RuntimeError("librosa is required for DSP voice morphing")
    if not HAS_SCIPY:
        raise RuntimeError("scipy is required for DSP voice morphing")

    cb("Loading vocals...", 10)
    y = _load_mono(vocals_path, sr).copy()
    if np.max(np.abs(y)) > 0:
        y = y / np.max(np.abs(y)) * 0.98

    audio_profile = profile.get("audio_profile", {})
    target_f0 = float(audio_profile.get("median_f0_hz", 0.0) or 0.0)

    # ---- 1) pitch map ----
    source_f0, _ = estimate_pitch(y, sr)
    if pitch_steps is None:
        pitch_steps = 0.0
        if source_f0 > 40 and target_f0 > 40:
            pitch_steps = float(12.0 * np.log2(target_f0 / source_f0))
        pitch_steps = _limit(pitch_steps, -7.0, 7.0)
    if abs(pitch_steps) > 0.01:
        cb(f"Pitch-mapping to target voice ({pitch_steps:+.1f} st)...", 35)
        y = librosa.effects.pitch_shift(y, sr=sr, n_steps=pitch_steps)

    # ---- 2) spectral-envelope (timbre) shaping ----
    target_env = audio_profile.get("spectral_envelope")
    if target_env:
        cb("Shaping timbre toward cloned voice...", 55)
        y = _apply_envelope_shaping(y, sr, list(target_env), n_bands=16)

    # ---- 3) loudness matching ----
    target_rms = float(audio_profile.get("rms", 0.0) or 0.0)
    if target_rms > 1e-6:
        cur = float(np.sqrt(np.mean(y ** 2)))
        if cur > 1e-9:
            y = y * float(target_rms / cur)
    if np.max(np.abs(y)) > 1.0:
        y = y / np.max(np.abs(y)) * 0.98

    cb("Saving converted vocals...", 85)
    sf.write(str(out_path), y, sr)
    cb("Done", 100)
    return str(out_path)


def _apply_envelope_shaping(y: np.ndarray, sr: int, target_db: list[float],
                            n_bands: int) -> np.ndarray:
    """Shape long-term spectrum of `y` toward `target_db` band profile."""
    src_db = band_energy_profile(y, sr, n_bands)
    diff = np.clip(np.array(target_db) - np.array(src_db), -9.0, 9.0)
    freqs = np.linspace(0.0, sr / 2.0, n_bands)
    gain = 10.0 ** (diff / 20.0)
    n_taps = 255
    fir = _signal.firwin2(n_taps, freqs, gain, fs=sr)
    shaped = _signal.filtfilt(fir, 1.0, y)
    return shaped.astype(np.float32)
# ─────────────────────────────────────────────────────────────────
#  Step 2 — convert vocals (RVC if available, else DSP)
# ─────────────────────────────────────────────────────────────────
def convert_vocals(
    vocals_path: str | Path,
    profile: dict,
    out_path: str | Path,
    work_dir: str | Path,
    progress_cb: Optional[_ProgressCB] = None,
    require_neural: bool = False,
) -> tuple[bool, str]:
    """
    Run the song's vocals through the selected voice's converter.

    Uses RVC when a trained RVC model exists for the cloned voice
    (models/voices/<name>/rvc_model.pth or .index), otherwise falls back to
    the pure-DSP morph. Returns (success, message).
    """
    cb = progress_cb or _noop
    name = profile.get("name", "voice")
    configured_voice_dir = Path(profile.get("voice_dir", Path("models") / "voices" / name))
    voice_dir = configured_voice_dir if configured_voice_dir.name == name else configured_voice_dir / name
    rvc_model = None
    for cand in (voice_dir / f"{name}.pth", voice_dir / "rvc_model.pth",
                 voice_dir / "model.pth"):
        if cand.exists() and cand.stat().st_size > 10_000:
            rvc_model = cand

    if rvc_model is not None:
        try:
            from rvc_engine import RvcEngine
            engine = RvcEngine(str(voice_dir.parent))
            ok, msg = engine.convert(
                name, vocals_path, out_path,
                pitch_shift=0, progress_cb=cb,
            )
            if ok:
                return True, "RVC neural voice conversion"
            cb(f"RVC fell back to DSP: {msg}", 0)
        except Exception:
            pass

        try:
            from clone_any_voice import _run_sidecar

            cb("Running RVC sidecar voice conversion...", 20)
            _run_sidecar([
                "rvc",
                "--voice-name", str(name),
                "--input", str(vocals_path),
                "--output", str(out_path),
                "--models-dir", str(voice_dir.parent),
            ])
            cb("RVC sidecar conversion complete", 100)
            return True, "RVC neural voice conversion (sidecar)"
        except Exception as exc:
            cb(f"RVC sidecar fell back to DSP: {exc}", 0)

    if require_neural:
        raise RuntimeError(
            "A trained RVC model and working RVC backend are required for "
            "indistinguishable song replacement; DSP fallback is disabled."
        )
    dsp_morph_vocals(vocals_path, profile, out_path, progress_cb=cb)
    return True, "DSP timbre mapping (RVC optional - train a model to upgrade)"


def write_conversion_report(
    report_path: str | Path,
    *,
    profile: dict,
    source_audio: str | Path,
    output_audio: str | Path,
    engine: str,
    score: dict,
    plan: dict | None = None,
) -> str:
    """Persist a machine-readable conversion quality report."""
    report = {
        "voice": profile.get("name", "voice"),
        "reference": profile.get("reference"),
        "source_audio": str(source_audio),
        "output_audio": str(output_audio),
        "engine": engine,
        "plan": plan or {},
        "estimated_accuracy": score,
        "reference_quality": profile.get("audio_profile", {}).get("reference_quality", {}),
        "average_source_quality": profile.get("audio_profile", {}).get("average_source_quality"),
        "score_notes": [
            "Score compares pitch, broad timbre envelope, and loudness to the cloned profile.",
            "It is an engineering estimate, not proof of human-perceived identity.",
            "RVC or neural TTS backends generally outperform DSP fallback on real voices.",
            "Reference quality measures voiced content, noise floor, clipping, and usable duration.",
        ],
    }
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return str(report_path)


# ─────────────────────────────────────────────────────────────────
#  Step 3 — combine converted vocals + instrumental
# ─────────────────────────────────────────────────────────────────
def combine_tracks(
    vocals_path: str | Path,
    instrumental_path: str | Path,
    out_path: str | Path,
    vocals_gain_db: float = 0.0,
    progress_cb: Optional[_ProgressCB] = None,
) -> str:
    """Mix converted vocals back over the instrumental, same length."""
    cb = progress_cb or _noop
    cb("Mixing converted vocals over instrumental...", 80)
    v, vsr = sf.read(str(vocals_path), dtype="float32")
    i_, isr = sf.read(str(instrumental_path), dtype="float32")
    if v.ndim == 1:
        v = _to_stereo(v)
    if i_.ndim == 1:
        i_ = _to_stereo(i_)

    n = min(v.shape[0], i_.shape[0])
    if n <= 0:
        raise RuntimeError("Empty tracks - nothing to mix")
    v = v[:n]
    i_ = i_[:n]

    gain = 10.0 ** (vocals_gain_db / 20.0)
    mixed = (v * gain + i_).astype(np.float32)
    peak = np.max(np.abs(mixed)) or 1.0
    if peak > 1.0:
        mixed = mixed / peak * 0.98

    sr = isr if isr == vsr else min(isr, vsr)
    sf.write(str(out_path), mixed, sr)
    cb("Done", 100)
    return str(out_path)


# ─────────────────────────────────────────────────────────────────
#  High-level: convert an entire song with a cloned voice
# ─────────────────────────────────────────────────────────────────
def change_song(
    song_path: str | Path,
    profile: dict,
    out_dir: str | Path,
    progress_cb: Optional[_ProgressCB] = None,
    separation: str = "auto",
    vocals_gain_db: float = 0.0,
    require_neural: bool = False,
) -> tuple[Optional[str], dict]:
    """
    One-call: separate -> convert -> recombine any song with a cloned voice.

    Returns (output_song_path, steps_done) where steps_done describes the
    produced artifacts and which techniques were used.
    """
    cb = progress_cb or _noop
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    steps: dict[str, str] = {}

    cb("Separating vocals from instrumental...", 10)
    vocals, inst, method = separate_vocals(song_path, out_dir,
                                           separation or "auto", cb)
    if not vocals:
        raise RuntimeError("Could not separate vocals from the song")
    if require_neural and method != "demucs":
        raise RuntimeError(
            "Neural Demucs separation is required for indistinguishable "
            "song replacement; center-channel fallback is disabled."
        )
    steps["separation"] = method

    cb("Converting vocals to the cloned voice...", 45)
    conv_vocals = out_dir / "converted_vocals.wav"
    ok, msg = convert_vocals(vocals, profile, conv_vocals, out_dir, cb,
                             require_neural=require_neural)
    steps["conversion"] = msg

    cb("Recombining with the instrumental...", 75)
    stem = Path(song_path).stem.replace(" ", "_")
    new_name = f"{stem}_in_{profile.get('name', 'voice')}.wav"
    out_path = out_dir / new_name
    combine_tracks(conv_vocals, inst, out_path,
                   vocals_gain_db=vocals_gain_db, progress_cb=cb)
    steps["output"] = str(out_path)
    cb("Song conversion complete!", 100)
    return str(out_path), steps


def profile_for_pitch(pitch_hz: float) -> dict:
    """Build a minimal voice profile from just a target pitch (for tests)."""
    return {
        "name": "custom",
        "audio_profile": {
            "median_f0_hz": float(pitch_hz),
            "rms": 0.15,
            "spectral_envelope": [0.0, -2, -5, -9, -13, -18, -24, -32,
                                  -40, -50, -60, -70, -80, -90, -100, -110],
        },
    }
