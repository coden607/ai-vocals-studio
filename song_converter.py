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

# Pitch search range shared by the librosa path (C2..C6) and the fallback.
_FMIN_HZ = 65.41   # C2
_FMAX_HZ = 1046.5  # C6


def _resample_sinc(y: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Windowed-sinc resampler (numpy only) for hosts without librosa/scipy.

    Bandlimits with an FFT brickwall when downsampling, then interpolates
    with a 32-tap Blackman-windowed sinc. Deterministic and dependency-free.
    """
    y = np.asarray(y, dtype=np.float64)
    if y.size == 0 or orig_sr == target_sr:
        return y.astype(np.float32)
    ratio = target_sr / float(orig_sr)
    n_out = int(round(y.size * ratio))
    if n_out <= 0:
        return np.zeros(0, dtype=np.float32)

    # Anti-alias: brickwall lowpass at the new Nyquist before decimation.
    if target_sr < orig_sr:
        n_fft = 1 << int(np.ceil(np.log2(y.size)))
        spec = np.fft.rfft(y, n=n_fft)
        freqs = np.fft.rfftfreq(n_fft, d=1.0 / orig_sr)
        spec[freqs > target_sr / 2.0] = 0.0
        y = np.fft.irfft(spec, n=n_fft)[: y.size]

    half = 16
    offs = np.arange(-half, half)               # int tap offsets
    t = np.arange(n_out, dtype=np.float64) / ratio
    i0 = np.floor(t).astype(np.int64)
    frac = (t - i0)[:, None]                  # (n_out, 1)
    k = i0[:, None] + offs[None, :]           # (n_out, 32) int64
    delta = frac - offs.astype(np.float64)[None, :]  # tap distance from sample time
    np.clip(k, 0, y.size - 1, out=k)
    # Blackman-windowed sinc; delta == 0 contributes exactly 1.
    win = np.blackman(2 * half)
    sinc = np.sinc(delta) * win[None, :]
    out = np.sum(y[k] * sinc, axis=1)
    return out.astype(np.float32)


def _resample(y: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Resample to target_sr — librosa when present, sinc fallback otherwise."""
    if orig_sr == target_sr:
        return np.asarray(y, dtype=np.float32)
    if HAS_LIBROSA:
        return librosa.resample(np.asarray(y, dtype=np.float32),
                                orig_sr=orig_sr, target_sr=target_sr)
    return _resample_sinc(y, orig_sr, target_sr)


def _scan_pitch_fallback(y: np.ndarray, sr: int,
                         frame_length: int = 2048, hop_length: int = 512):
    """Autocorrelation pitch scan (numpy only). Returns (f0, rms) per frame."""
    n = y.size
    if n < frame_length:
        frame_length = max(64, 1 << int(np.floor(np.log2(n))))
    n_frames = 1 + max(0, (n - frame_length) // hop_length)
    f0 = np.zeros(n_frames, dtype=np.float64)
    rms = np.zeros(n_frames, dtype=np.float64)
    win = np.hanning(frame_length)
    lo = max(2, int(sr / _FMAX_HZ))
    hi = min(frame_length - 2, int(sr / _FMIN_HZ))
    for i in range(n_frames):
        frame = y[i * hop_length: i * hop_length + frame_length] * win
        frame = frame - frame.mean()
        rms[i] = float(np.sqrt(np.mean(frame ** 2)))
        if rms[i] < 1e-5 or hi <= lo:
            continue
        acf = np.correlate(frame, frame, mode="full")[frame_length - 1:]
        if acf[0] <= 0:
            continue
        seg = acf[lo: hi + 1]
        pk = lo + int(np.argmax(seg))
        if acf[pk] / acf[0] < 0.3:   # low periodicity → unvoiced/noise
            continue
        # Parabolic refinement of the ACF peak lag
        denom = acf[pk - 1] - 2.0 * acf[pk] + acf[pk + 1]
        lag = float(pk) if abs(denom) < 1e-12 else pk + 0.5 * (acf[pk - 1] - acf[pk + 1]) / denom
        if lag > 0:
            f0[i] = sr / lag
    return f0, rms


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
    allow_fallback: bool = True,
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
            if not allow_fallback:
                raise RuntimeError("Demucs is required for neural separation but is unavailable")
            return separate_vocals(song_path, work_dir, "center", cb, allow_fallback=True)
        try:
            cb("Separating with demucs (first run downloads model)...", 20)
            cmd = [
                sys.executable, "-m", "demucs", "--two-stems", "vocals",
                "-o", str(work_dir / "demucs"), str(song_path),
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if r.returncode != 0:
                cb(f"demucs failed ({r.stderr[-200:].strip()}) - using center", 0)
                if not allow_fallback:
                    raise RuntimeError(f"Demucs is required and separation failed: {r.stderr[-500:].strip()}")
                return separate_vocals(song_path, work_dir, "center", cb, allow_fallback=True)
            demucs_out = list((work_dir / "demucs").rglob("vocals.wav"))
            if not demucs_out:
                cb("demucs produced no output - using center", 0)
                if not allow_fallback:
                    raise RuntimeError("Demucs is required but produced no vocal stem")
                return separate_vocals(song_path, work_dir, "center", cb, allow_fallback=True)
            vocals_src = demucs_out[0]
            inst_src = vocals_src.with_name("no_vocals.wav")
            if not inst_src.exists():
                cb("demucs produced no instrumental stem", 0)
                if not allow_fallback:
                    raise RuntimeError("Demucs is required but produced no instrumental stem")
                return separate_vocals(song_path, work_dir, "center", cb, allow_fallback=True)

            # Validate BOTH neural stems before conversion. Never manufacture a
            # silent beat: production replacement must use the instrumental
            # separated from this exact source song.
            def _valid_stem(path: Path) -> bool:
                try:
                    info = sf.info(str(path))
                    return info.frames > 0 and info.samplerate > 0 and info.duration > 0.05
                except Exception:
                    return False

            if not _valid_stem(vocals_src) or not _valid_stem(inst_src):
                cb("demucs produced an empty/corrupt stem", 0)
                if not allow_fallback:
                    raise RuntimeError("Demucs is required but produced an empty/corrupt stem")
                return separate_vocals(song_path, work_dir, "center", cb, allow_fallback=True)

            vocals_w = work_dir / "vocals.wav"
            inst_w = work_dir / "instrumental.wav"
            shutil.copy2(vocals_src, vocals_w)
            shutil.copy2(inst_src, inst_w)
            cb("Separation done", 100)
            return str(vocals_w), str(inst_w), "demucs"
        except Exception as e:  # pragma: no cover
            cb(f"demucs error ({e}) - using center", 0)
            if not allow_fallback:
                raise RuntimeError(f"Demucs is required and separation errored: {e}") from e
            return separate_vocals(song_path, work_dir, "center", cb, allow_fallback=True)

    if not allow_fallback:
        raise RuntimeError(f"Unknown separation method: {method}")
    cb("Unknown method - using center", 0)
    return separate_vocals(song_path, work_dir, "center", cb, allow_fallback=True)


# ─────────────────────────────────────────────────────────────────
#  Key matching: the beat follows the voice, never the other way round
# ─────────────────────────────────────────────────────────────────
#
#  A cloned voice has its own natural register. Forcing it up or down to the
#  source singer's key is what makes a conversion sound like an impression
#  rather than the person. So the performance is moved into the target voice's
#  register and the INSTRUMENTAL is transposed by the same interval, which
#  keeps voice and beat in one key and transposes the whole track instead.
#
#  Tempo is deliberately untouched: the phase vocoder shifts pitch without
#  changing duration, so the groove, bar lines and timing of the original beat
#  survive. The instrumental remains the timing clock; only its key follows.

#  Transposing further than this stops sounding like a key change and starts
#  sounding broken (chipmunk / sludge), so a shift is clamped.
MAX_KEY_SHIFT_SEMITONES = 7.0

#  Below this the shift is inaudible and not worth a resynthesis pass.
MIN_AUDIBLE_SEMITONES = 0.1


def _phase_vocoder_stretch(y: np.ndarray, rate: float,
                           n_fft: int = 2048, hop: int = 512) -> np.ndarray:
    """
    Time-stretch without changing pitch. `rate` < 1 lengthens, > 1 shortens.
    numpy-only so the key-matching path survives without librosa.
    """
    y = np.asarray(y, dtype=np.float32)
    if y.size < n_fft or abs(rate - 1.0) < 1e-6:
        return y

    window = np.hanning(n_fft).astype(np.float32)
    n_frames = 1 + (y.size - n_fft) // hop
    spectra = np.empty((n_frames, n_fft // 2 + 1), dtype=np.complex128)
    for i in range(n_frames):
        spectra[i] = np.fft.rfft(y[i * hop:i * hop + n_fft] * window)

    magnitude = np.abs(spectra)
    phase = np.angle(spectra)
    # Expected per-hop phase advance of each bin, removed so only the
    # deviation is scaled - that is what keeps transients from smearing.
    expected = 2.0 * np.pi * hop * np.arange(n_fft // 2 + 1) / n_fft

    positions = np.arange(0, n_frames - 1, rate)
    out = np.zeros(int(len(positions) * hop) + n_fft, dtype=np.float32)
    weight = np.zeros_like(out)
    accumulated = phase[0].copy()

    for index, position in enumerate(positions):
        left = int(np.floor(position))
        frac = float(position - left)
        mag = (1.0 - frac) * magnitude[left] + frac * magnitude[left + 1]

        frame = np.fft.irfft(mag * np.exp(1j * accumulated), n=n_fft).astype(np.float32)
        start = index * hop
        out[start:start + n_fft] += frame * window
        weight[start:start + n_fft] += window ** 2

        delta = phase[left + 1] - phase[left] - expected
        delta = np.mod(delta + np.pi, 2.0 * np.pi) - np.pi
        accumulated = accumulated + expected + delta

    nonzero = weight > 1e-8
    out[nonzero] /= weight[nonzero]
    return out[:int(len(positions) * hop)].astype(np.float32)


def pitch_shift_semitones(y: np.ndarray, sr: int, semitones: float) -> np.ndarray:
    """
    Shift pitch by `semitones` while preserving duration (and so tempo).
    Uses librosa when installed, otherwise the numpy phase vocoder above.
    """
    y = np.asarray(y, dtype=np.float32)
    if abs(semitones) < MIN_AUDIBLE_SEMITONES or y.size == 0:
        return y
    if HAS_LIBROSA:
        try:
            return librosa.effects.pitch_shift(y, sr=sr, n_steps=float(semitones))
        except Exception:
            pass
    # Stretch then resample by the inverse ratio: duration returns to the
    # original while every frequency is scaled.
    rate = 2.0 ** (-float(semitones) / 12.0)
    stretched = _phase_vocoder_stretch(y, rate)
    if stretched.size == 0:
        return y
    shifted = _resample(stretched, int(round(sr / rate)), sr)
    if shifted.size >= y.size:
        return shifted[:y.size].astype(np.float32)
    return np.pad(shifted, (0, y.size - shifted.size)).astype(np.float32)


def voice_shift_semitones(vocals_path: str | Path, profile: dict,
                          sr: int = 22050) -> float:
    """
    How far the source performance must move to sit in the target voice's
    natural register. Positive means up. Returns 0.0 when either pitch is
    unknown, so an unmeasurable voice never silently transposes a song.
    """
    audio_profile = profile.get("audio_profile", {}) or {}
    target_f0 = float(audio_profile.get("median_f0_hz", 0.0) or 0.0)
    if target_f0 <= 40:
        return 0.0
    source_f0, _ = estimate_pitch(_load_mono(vocals_path, sr), sr)
    if source_f0 <= 40:
        return 0.0
    return _limit(float(12.0 * np.log2(target_f0 / source_f0)),
                  -MAX_KEY_SHIFT_SEMITONES, MAX_KEY_SHIFT_SEMITONES)


def transpose_audio_file(
    src_path: str | Path,
    semitones: float,
    out_path: str | Path,
    progress_cb: Optional[_ProgressCB] = None,
    label: str = "audio",
    percent: int = 70,
) -> tuple[str, float]:
    """
    Transpose a file by `semitones`, preserving its duration and tempo.
    Returns (path_used, semitones_applied); a negligible shift returns the
    original path untouched rather than paying for a resynthesis.
    """
    cb = progress_cb or _noop
    if abs(semitones) < MIN_AUDIBLE_SEMITONES:
        return str(src_path), 0.0

    cb(f"Transposing {label} ({semitones:+.1f} st)...", percent)
    audio, sr = sf.read(str(src_path), dtype="float32", always_2d=True)
    shifted = np.stack(
        [pitch_shift_semitones(audio[:, ch], sr, semitones) for ch in range(audio.shape[1])],
        axis=-1,
    )
    peak = float(np.max(np.abs(shifted))) or 1.0
    if peak > 1.0:
        shifted = shifted / peak * 0.98
    sf.write(str(out_path), shifted.astype(np.float32), sr)
    return str(out_path), float(semitones)


def match_instrumental_to_voice(
    instrumental_path: str | Path,
    semitones: float,
    out_path: str | Path,
    progress_cb: Optional[_ProgressCB] = None,
) -> tuple[str, float]:
    """The beat follows the voice: transpose the separated instrumental."""
    return transpose_audio_file(
        instrumental_path, semitones, out_path, progress_cb,
        label="the beat to the voice", percent=70,
    )


def move_vocal_into_voice_register(
    vocals_path: str | Path,
    semitones: float,
    out_path: str | Path,
    progress_cb: Optional[_ProgressCB] = None,
) -> tuple[str, float]:
    """
    Put the isolated performance in the target voice's register BEFORE
    conversion, so every engine - Seed-VC, RVC or DSP - converts audio that is
    already in the right range. Doing it here, once, is what keeps the beat
    shift and the vocal shift equal and the output in a single key.
    """
    return transpose_audio_file(
        vocals_path, semitones, out_path, progress_cb,
        label="the performance into the voice's register", percent=35,
    )


def _load_mono(path: str | Path, sr: int = 22050) -> np.ndarray:
    """Load any audio file as mono float32 at `sr`."""
    if HAS_LIBROSA:
        return librosa.load(str(path), sr=sr, mono=True)[0].astype(np.float32)
    y, orig_sr = sf.read(str(path), dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    return _resample(y, orig_sr, sr)


def _to_stereo(mono: np.ndarray) -> np.ndarray:
    return np.stack([mono, mono], axis=-1)
# ─────────────────────────────────────────────────────────────────
#  Vocal analysis helpers (used for profiling AND conversion)
# ─────────────────────────────────────────────────────────────────
def estimate_pitch(y: np.ndarray, sr: int = 22050) -> tuple[float, float]:
    """
    Estimate median fundamental frequency (Hz) and std over voiced frames.
    Uses librosa.yin when available, else an autocorrelation scan.
    Returns (median_f0, std_f0) or (0, 0).
    """
    if y.size == 0:
        return 0.0, 0.0
    if not HAS_LIBROSA:
        f0, rms = _scan_pitch_fallback(y, sr)
        if rms.size == 0:
            return 0.0, 0.0
        threshold = max(1e-4, float(np.percentile(rms, 65)) * 0.25)
        voiced = f0[(f0 > 0) & (rms > threshold)]
        if voiced.size == 0:
            return 0.0, 0.0
        return float(np.median(voiced)), float(np.std(voiced))
    try:
        frame_length, hop_length = 2048, 512
        f0 = librosa.yin(y, fmin=librosa.note_to_hz("C2"),
                         fmax=librosa.note_to_hz("C6"), sr=sr,
                         frame_length=frame_length, hop_length=hop_length)
        # librosa.yin reports a pitch for every frame, including silence and
        # noise - it has no voicing decision. Without the same energy gate the
        # numpy fallback applies, a silent or unpitched stem returns a
        # confident nonsense median, which is enough to transpose a whole song.
        rms = librosa.feature.rms(y=y, frame_length=frame_length,
                                  hop_length=hop_length)[0]
        count = min(f0.size, rms.size)
        if count == 0:
            return 0.0, 0.0
        f0, rms = f0[:count], rms[:count]
        threshold = max(1e-4, float(np.percentile(rms, 65)) * 0.25)
        voiced = f0[(f0 > 0) & np.isfinite(f0) & (rms > threshold)]
        if voiced.size == 0:
            return 0.0, 0.0
        return float(np.median(voiced)), float(np.std(voiced))
    except Exception:
        return 0.0, 0.0


def voiced_fraction(y: np.ndarray, sr: int = 22050) -> float:
    """Return the fraction of frames with detectable voice-like pitch.

    Falls back to an autocorrelation scan when librosa is unavailable, so
    the clip gate still works on constrained hosts (never silently 0)."""
    if y.size == 0:
        return 0.0
    if float(np.sqrt(np.mean(y ** 2))) < 1e-4:
        return 0.0
    if not HAS_LIBROSA:
        f0, rms = _scan_pitch_fallback(y, sr)
        if rms.size == 0:
            return 0.0
        threshold = max(1e-4, float(np.percentile(rms, 65)) * 0.25)
        voiced = (f0 > 0) & (rms > threshold)
        return float(np.mean(voiced))
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
    """Long-term average per-band RMS dB profile of `y` (log-mel-like).

    Without librosa: rFFT into log-spaced bands (same output contract)."""
    if y.size == 0:
        return [0.0] * n_bands
    if not HAS_LIBROSA:
        win = np.hanning(y.size)
        spec = np.abs(np.fft.rfft(y * win))
        power = spec ** 2
        freqs = np.fft.rfftfreq(y.size, d=1.0 / sr)
        edges = np.geomspace(max(20.0, freqs[1] if freqs.size > 1 else 20.0),
                             sr / 2.0, n_bands + 1)
        bands = np.zeros(n_bands)
        for b in range(n_bands):
            mask = (freqs >= edges[b]) & (freqs < edges[b + 1])
            bands[b] = float(np.sum(power[mask])) if np.any(mask) else 0.0
        with np.errstate(divide="ignore"):
            db = 10.0 * np.log10(bands + 1e-12)
        db = db - float(np.max(db))
        return [float(v) for v in db]
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
    pitch_steps: Optional[float] = None,
) -> tuple[bool, str]:
    """
    Run the song's vocals through the selected voice's converter.

    `pitch_steps` is the pitch decision made by the caller. change_song moves
    the performance into the voice's register before calling this and then
    passes 0.0, so no engine applies a second, different shift - that mismatch
    is what previously left the vocal and the beat in different keys.

    Prefers Seed-VC zero-shot conversion when SEED_VC_DIR is configured and a
    reference recording is available, then RVC when a trained model exists,
    otherwise falls back to DSP. Returns (success, message).
    """
    cb = progress_cb or _noop
    name = profile.get("name", "voice")
    configured_voice_dir = Path(profile.get("voice_dir", Path("models") / "voices" / name))
    voice_dir = configured_voice_dir if configured_voice_dir.name == name else configured_voice_dir / name
    # Seed-VC needs no per-speaker training: an authorized reference recording
    # is enough. This is the preferred zero-shot path for rap/singing.
    reference = profile.get("reference") or profile.get("reference_audio")
    if reference:
        reference_path = Path(reference)
        if not reference_path.is_absolute():
            candidate = voice_dir / reference_path
            if candidate.exists():
                reference_path = candidate
        try:
            from seed_vc_engine import seed_vc_available, convert_seed_vc
            if seed_vc_available() and reference_path.exists():
                convert_seed_vc(
                    vocals_path, reference_path, out_path,
                    singing=True, diffusion_steps=30, progress_cb=cb,
                )
                return True, "Seed-VC zero-shot neural voice conversion"
        except Exception as exc:
            cb(f"Seed-VC unavailable/failed: {exc}", 0)

    rvc_model = None
    for cand in (voice_dir / f"{name}.pth", voice_dir / "rvc_model.pth",
                 voice_dir / "model.pth"):
        if cand.exists() and cand.stat().st_size > 10_000:
            rvc_model = cand

    if rvc_model is not None:
        try:
            from rvc_engine import RvcEngine
            engine = RvcEngine(str(voice_dir.parent))
            # Was hardcoded to 0, which forced every RVC render into the
            # source singer's key regardless of the target voice.
            ok, msg = engine.convert(
                name, vocals_path, out_path,
                pitch_shift=int(round(pitch_steps or 0.0)), progress_cb=cb,
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
            "A working Seed-VC reference conversion or trained RVC backend is "
            "required for neural song replacement; DSP fallback is disabled."
        )
    dsp_morph_vocals(vocals_path, profile, out_path, progress_cb=cb,
                     pitch_steps=pitch_steps)
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
        "speaker_identity": score.get("identity"),
        "precision": score.get("precision"),
        "legacy_heuristic": score.get("legacy_heuristic"),
        "reference_quality": profile.get("audio_profile", {}).get("reference_quality", {}),
        "average_source_quality": profile.get("audio_profile", {}).get("average_source_quality"),
        "score_notes": [
            "Headline score is speaker-identity cosine similarity, not pitch or loudness.",
            "legacy_heuristic is the old pitch/timbre/RMS number and is not a clone score.",
            "WORLD/DSP and gTTS cannot meet studio or pro.",
            "Near-precision requires a neural engine, identity >= 0.82, and at least 15s of clean reference.",
        ],
    }
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return str(report_path)


def polish_converted_vocals(
    converted_path: str | Path,
    source_vocals_path: str | Path,
    out_path: str | Path,
    progress_cb: Optional[_ProgressCB] = None,
) -> str:
    """Match converted vocals to the source performance envelope without
    changing timing or pitch.

    The isolated source vocal is the reference for phrasing/dynamics. We apply
    only conservative cleanup: DC removal, optional low-cut, smoothed
    short-term RMS-envelope matching (gain clamped to +/-6 dB), and peak
    protection. This avoids flattening breaths, consonants, vibrato, or
    expressive dynamics while making neural VC output sit more naturally in
    the original mix.
    """
    cb = progress_cb or _noop
    cb("Polishing converted vocal dynamics...", 68)
    converted, csr = sf.read(str(converted_path), dtype="float32", always_2d=True)
    source, ssr = sf.read(str(source_vocals_path), dtype="float32", always_2d=True)
    if converted.shape[0] == 0 or source.shape[0] == 0:
        raise RuntimeError("Cannot polish an empty vocal stem")

    # Use mono source envelope as the performance reference, but preserve the
    # channel layout produced by the neural converter.
    source_mono = source.mean(axis=1)
    if ssr != csr:
        if not HAS_LIBROSA:
            raise RuntimeError("librosa is required to align vocal polish references")
        source_mono = librosa.resample(source_mono, orig_sr=ssr, target_sr=csr).astype(np.float32)

    n = converted.shape[0]
    if source_mono.shape[0] < n:
        source_mono = np.pad(source_mono, (0, n - source_mono.shape[0]))
    else:
        source_mono = source_mono[:n]

    x = converted.astype(np.float32)
    x -= np.mean(x, axis=0, keepdims=True)

    # Conservative high-pass removes VC rumble/DC while leaving vocal body.
    if HAS_SCIPY and csr >= 8000:
        try:
            sos = _signal.butter(2, 60.0, btype="highpass", fs=csr, output="sos")
            x = _signal.sosfiltfilt(sos, x, axis=0).astype(np.float32)
        except Exception:
            pass

    # Follow the source performance envelope instead of applying generic
    # compression. 80 ms windows retain syllabic dynamics without pumping.
    win = max(32, int(csr * 0.080))
    kernel = np.ones(win, dtype=np.float32) / float(win)
    src_pow = np.convolve(source_mono * source_mono, kernel, mode="same")
    conv_mono = x.mean(axis=1)
    conv_pow = np.convolve(conv_mono * conv_mono, kernel, mode="same")
    eps = 1e-8
    gain = np.sqrt((src_pow + eps) / (conv_pow + eps))
    gain = np.clip(gain, 10 ** (-6 / 20), 10 ** (6 / 20))

    # Smooth the gain curve to avoid zipper noise and preserve transients.
    smooth = max(16, int(csr * 0.120))
    smooth_kernel = np.ones(smooth, dtype=np.float32) / float(smooth)
    gain = np.convolve(gain.astype(np.float32), smooth_kernel, mode="same")
    x *= gain[:, None]

    # Keep silence silent: do not boost converter noise in source-silent zones.
    silence_floor = max(1e-6, float(np.percentile(np.sqrt(src_pow + eps), 20)) * 0.5)
    quiet = np.sqrt(src_pow + eps) < silence_floor
    x[quiet] *= 0.25

    peak = float(np.max(np.abs(x))) if x.size else 0.0
    if peak > 0.98:
        x *= np.float32(0.98 / peak)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), x, csr)
    cb("Vocal polish complete", 72)
    return str(out_path)


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

    # The instrumental is the timing/master clock. Resample converted vocals
    # to it, then pad/trim without changing playback speed.
    if vsr != isr:
        v = np.stack([
            _resample(v[:, ch], vsr, isr)
            for ch in range(v.shape[1])
        ], axis=-1).astype(np.float32)
        vsr = isr

    n = i_.shape[0]
    if n <= 0:
        raise RuntimeError("Empty instrumental - nothing to mix")
    if v.shape[0] < n:
        v = np.pad(v, ((0, n - v.shape[0]), (0, 0)))
    else:
        v = v[:n]
    i_ = i_[:n]

    gain = 10.0 ** (vocals_gain_db / 20.0)
    mixed = (v * gain + i_).astype(np.float32)
    peak = np.max(np.abs(mixed)) or 1.0
    if peak > 1.0:
        mixed = mixed / peak * 0.98

    sf.write(str(out_path), mixed, isr)
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
    separation: str = "demucs",
    vocals_gain_db: float = 0.0,
    require_neural: bool = False,
    source_matched_export: bool = True,
    match_beat_to_voice: bool = True,
) -> tuple[Optional[str], dict]:
    """
    One-call production contract: neural-separate the song first, move the
    isolated performance into the target voice's natural register, convert it,
    then transpose the separated instrumental by the SAME interval and remix.

    The beat follows the voice, not the other way round. Tempo and timing are
    untouched; only the key moves, so the whole track is transposed into a
    range the cloned voice actually has. Pass match_beat_to_voice=False to
    keep the original key and let the voice bend to the song instead.

    Returns (output_song_path, steps_done) where steps_done describes the
    produced artifacts and which techniques were used.
    """
    cb = progress_cb or _noop
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    steps: dict[str, str] = {}

    cb("Separating vocals from instrumental...", 10)
    requested_separation = "demucs" if require_neural and (separation or "auto") == "auto" else (separation or "auto")
    vocals, inst, method = separate_vocals(
        song_path, out_dir, requested_separation, cb,
        allow_fallback=not require_neural,
    )
    if not vocals:
        raise RuntimeError("Could not separate vocals from the song")
    if require_neural and method != "demucs":
        raise RuntimeError(
            "Neural Demucs separation is required for indistinguishable "
            "song replacement; center-channel fallback is disabled."
        )
    steps["separation"] = method

    # The key decision is made once, from the separated vocal and the voice
    # profile, and then applied to BOTH the performance and the beat.
    shift = voice_shift_semitones(vocals, profile) if match_beat_to_voice else 0.0
    steps["voice_shift_semitones"] = f"{shift:+.2f}"
    # A clamped shift means the voice could not fully reach its own register,
    # so the result is a compromise. Say so rather than hiding it.
    if abs(shift) >= MAX_KEY_SHIFT_SEMITONES - 1e-6:
        steps["key_shift_clamped"] = (
            f"limited to {MAX_KEY_SHIFT_SEMITONES:.0f} semitones; the voice is "
            f"further from the performance than a usable transposition allows"
        )

    convert_input = vocals
    if match_beat_to_voice:
        in_register, applied = move_vocal_into_voice_register(
            vocals, shift, out_dir / "vocals_in_voice_register.wav", cb)
        convert_input = in_register
        steps["vocal_register_shift"] = f"{applied:+.2f}"

    cb("Converting vocals to the cloned voice...", 45)
    conv_vocals = out_dir / "converted_vocals.wav"
    # pitch_steps=0.0: the register move above already placed the performance,
    # so no engine may apply a second shift the beat would not know about.
    ok, msg = convert_vocals(convert_input, profile, conv_vocals, out_dir, cb,
                             require_neural=require_neural,
                             pitch_steps=0.0 if match_beat_to_voice else None)
    steps["conversion"] = msg

    # Source-aware polish: match the converted vocal's dynamics envelope to
    # the isolated source performance so the replacement sits naturally in
    # the original mix. The polished stem becomes the remix input; the raw
    # converted stem stays on disk for inspection.
    remix_vocals = conv_vocals
    try:
        polished = out_dir / "polished_vocals.wav"
        # Dynamics are matched against the performance actually converted, so
        # the envelope reference shares its register with the output.
        polish_converted_vocals(conv_vocals, convert_input, polished, cb)
        remix_vocals = polished
        steps["vocal_polish"] = str(polished)
    except Exception as exc:
        steps["polish_warning"] = str(exc)

    # The beat follows the voice: transpose the separated instrumental by the
    # same interval so vocal and beat land in one key.
    remix_inst = inst
    if match_beat_to_voice:
        remix_inst, beat_applied = match_instrumental_to_voice(
            inst, shift, out_dir / "instrumental_in_voice_key.wav", cb)
        steps["beat_key_shift"] = f"{beat_applied:+.2f}"
        steps["beat_follows_voice"] = "yes"
    else:
        steps["beat_follows_voice"] = "no (original key kept)"

    cb("Recombining with the instrumental...", 75)
    stem = Path(song_path).stem.replace(" ", "_")
    new_name = f"{stem}_in_{profile.get('name', 'voice')}.wav"
    out_path = out_dir / new_name
    combine_tracks(remix_vocals, remix_inst, out_path,
                   vocals_gain_db=vocals_gain_db, progress_cb=cb)
    steps["output"] = str(out_path)

    # Keep WAV as the processing master; optionally make an iPhone-friendly
    # delivery copy matching the source codec/bitrate class.
    delivery_path = str(out_path)
    if source_matched_export:
        try:
            from audio_export import export_like_source
            delivery_path = export_like_source(out_path, song_path, out_dir / "delivery")
            steps["master"] = str(out_path)
            steps["delivery"] = delivery_path
        except Exception as exc:
            steps["delivery_warning"] = str(exc)

    cb("Song conversion complete!", 100)
    return delivery_path, steps


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
