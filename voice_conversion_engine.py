#!/usr/bin/env python3
"""
Real DSP Voice Conversion Engine built on the WORLD vocoder.

This module performs speech/voice conversion *for real* (no placeholders):

  1. It learns a reference voice model from any speaker's acapella clips by
     extracting pitch statistics + an average spectral envelope (timbre).
  2. It then converts *any* input audio into that speaker's voice using the
     WORLD vocoder: F0 is mapped onto the target's pitch distribution while
     the spectral envelope (formant/timbre) is morphed toward the target's
     average envelope, and the audio is resynthesized with pyworld.

This engine powers the precision voice cloning pipeline. It replaces the old
placeholder path that compared validation audio against itself and wrote
random noise instead of generated vocals.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

import warnings

import numpy as np
import librosa
import soundfile as sf

# pyworld still imports deprecated pkg_resources at import time.
warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API",
    category=DeprecationWarning,
)

try:
    import pyworld as pw
    WORLD_OK = True
except Exception:  # pragma: no cover - fallback when pyworld missing
    pw = None
    WORLD_OK = False

warnings.filterwarnings('ignore')

try:
    from gtts import gTTS
    GTTS_OK = True
except Exception:  # pragma: no cover
    GTTS_OK = False


class VoiceConversionEngine:
    """
    WORLD-vocoder based voice conversion engine.

    A "model" is a JSON payload containing:
      * pitch profile   (median/mean F0, std, percentiles)
      * spectral profile (average spectral envelope / timbre template)
      * formant estimates
      * prosody snapshot (tempo, average loudness)

    ``convert_audio`` performs the conversion in 5 steps:
        1. WORLD analysis of the source (f0, spectral envelope, aperiodicity)
        2. pitch mapping  -> target vocal range (log-frequency ratio)
        3. spectral envelope relocation + morphing toward the reference
           timbre template (strength controlled)
        4. WORLD resynthesis
        5. loudness normalization to the reference average loudness
    """

    def __init__(self, target_sr: int = 22050, frame_period: float = 5.0,
                 max_seconds: Optional[float] = 90.0):
        self.target_sr = target_sr
        self.frame_period = frame_period   # 5 ms frame period (WORLD)
        self.max_seconds = max_seconds
        if not WORLD_OK:
            raise RuntimeError(
                "pyworld is required for the voice-conversion engine. "
                "Install it with `pip install pyworld`."
            )
# ------------------------------------------------------------------ #
    # 1. MODEL BUILDING ("training" on the speaker's acapellas)
    # ------------------------------------------------------------------ #
    def extract_reference_profile(self, audio_paths: List[str],
                                  progress_cb=None) -> Dict:
        """
        Train a reference voice model from a list of speaker clips.

        For every voiced WORLD frame across all clips we collect:
          * F0 samples           -> pitch distribution
          * log-spectral frames  -> average timbre envelope
        Loudness + tempo are also snapshotted for prosody matching.
        """
        if not audio_paths:
            raise ValueError("No reference audio clips given")

        voiced_list: List[float] = []
        sp_sum = None
        n_voiced = 0
        rms_accum: List[float] = []
        tempo_list: List[float] = []

        n_files = len(audio_paths)

        for idx, path in enumerate(audio_paths):
            if progress_cb:
                progress_cb(f"Analyzing {Path(path).name} ({idx + 1}/{n_files})",
                            15 + 65 * idx // n_files)
            try:
                y, sr = librosa.load(path, sr=self.target_sr, mono=True)
            except Exception as e:
                print(f"  ! could not load {path}: {e}")
                continue
            if len(y) == 0:
                continue

            # Cap the analysis so long acapellas stay fast.
            if self.max_seconds is not None:
                max_n = int(self.max_seconds * sr)
                if len(y) > max_n:
                    y = y[:max_n]

            max_amp = np.max(np.abs(y))
            if max_amp > 0:
                y = y / max_amp * 0.95

            # chunk long clips to keep memory bounded
            for chunk in self._chunk(y, sr, chunk_sec=25.0):
                f0, t = pw.dio(chunk.astype(np.float64), sr,
                               frame_period=self.frame_period)
                sp = pw.cheaptrick(chunk.astype(np.float64), f0, t, sr)
                voiced = f0 > 0
                if not np.any(voiced):
                    continue
                voiced_list.extend(f0[voiced].tolist())
                vsp = sp[voiced]
                voiced_count = len(vsp)
                log_env = np.mean(np.log10(vsp + 1e-7), axis=0)
                linear_env = np.power(10.0, log_env)
                if n_voiced == 0:
                    sp_sum = (linear_env * voiced_count).astype(np.float64)
                else:
                    sp_sum += linear_env.astype(np.float64) * voiced_count
                n_voiced += voiced_count
                rms_accum.append(float(np.sqrt(np.mean(chunk ** 2))))
                try:
                    tempo, _ = librosa.beat.beat_track(y=chunk, sr=sr)
                    tempo_list.append(float(np.ravel(tempo)[0]))
                except Exception:
                    pass

        if n_voiced == 0:
            raise ValueError("No voiced frames found in reference clips")

        sp_mean = sp_sum / n_voiced
        spect_env = sp_mean / (np.max(sp_mean) + 1e-9)

        n_bins = int(spect_env.shape[0])
        freqs = np.linspace(0.0, self.target_sr / 2.0, n_bins)
        voiced_arr = np.asarray(voiced_list, dtype=np.float64)

        # --- dominant vocal band -----------------------------------------
        # Male/female speech F0 clusters well inside 70..350 Hz.  2Pac & rap
        # male voices concentrate around 100..220 Hz.  Using the raw overall
        # mean can be polluted by backing vocals / ad-libs, so we also expose
        # a "dominant" pitch (histogram peak) and a male-band median.
        hist, bin_edges = np.histogram(voiced_arr, bins=60,
                                       range=(50.0, 500.0))
        dominant_hz = float(bin_edges[np.argmax(hist)])
        male_band = voiced_arr[(voiced_arr >= 70.0) & (voiced_arr <= 260.0)]
        male_band_median = float(np.median(male_band)) if len(male_band) else float(np.median(voiced_arr))

        formants = self._estimate_formants(spect_env, freqs)

        profile = {
            "engine": "world_vocoder",
            "version": 2,
            "sample_rate": self.target_sr,
            "num_reference_files": len(audio_paths),
            "num_voiced_frames": int(n_voiced),
            "pitch": {
                "mean_hz": float(np.mean(voiced_arr)),
                "median_hz": float(np.median(voiced_arr)),
                "std_hz": float(np.std(voiced_arr)),
                "min_hz": float(np.percentile(voiced_arr, 2)),
                "max_hz": float(np.percentile(voiced_arr, 98)),
                "dominant_hz": dominant_hz,
                "male_band_median_hz": male_band_median,
            },
            "pitch_target": male_band_median,  # sane default for conversion
            "spectral": {
                "mean_centroid_hz": float(np.average(freqs, weights=spect_env + 1e-9)),
                "envelope_mean": spect_env.tolist(),
                "freq_axis": freqs.tolist(),
                "num_bins": int(n_bins),
            },
            "formants": formants,
            "prosody": {
                "mean_rms": float(np.mean(rms_accum)) if rms_accum else 0.05,
                "tempo_bpm": float(np.mean(tempo_list)) if tempo_list else 90.0,
            },
            "extracted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        return profile
# ------------------------------------------------------------------ #
    # 2. MODEL LOADING
    # ------------------------------------------------------------------ #
    def load_profile(self, model_path: str) -> Dict:
        """Load a saved model JSON (the ``model.pth`` payload)."""
        with open(model_path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def save_profile(profile: Dict, model_path: str) -> str:
        """Persist a trained profile to disk."""
        os.makedirs(os.path.dirname(os.path.abspath(model_path)), exist_ok=True)
        with open(model_path, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2)
        return model_path

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _chunk(y: np.ndarray, sr: int, chunk_sec: float = 25.0):
        """Split a long signal into overlapping-ish contiguous chunks."""
        n = int(chunk_sec * sr)
        if len(y) <= n:
            yield y
            return
        for start in range(0, len(y), n):
            yield y[start:start + n]

    @staticmethod
    def _estimate_formants(env: np.ndarray, freqs: np.ndarray) -> Dict:
        """
        Peak-pick formant-like landmarks from the average spectral envelope.
        Returns up to 4 prominence-ranked resonant frequencies below 5 kHz.
        """
        if env.ndim != 1 or len(freqs) != len(env):
            return {}
        peaks = []
        n = len(env)
        # local maxima above a relative floor; only look below 5 kHz
        search = int(np.sum(freqs <= 5000.0))
        span = max(2, n // 200)
        floor = np.max(env[:search]) * 0.15 if search else 1e-6
        for i in range(1, search - 1):
            if env[i] > env[i - 1] and env[i] > env[i + 1] and env[i] > floor:
                # simple prominence filter
                peaks.append((freqs[i], env[i]))
        # merge close peaks (within 150 Hz) keeping strongest
        peaks.sort(key=lambda x: -x[1])  # descending by amplitude
        merged = []
        for freq, amp in peaks:
            if not merged or abs(freq - merged[-1][0]) > 150:
                merged.append((freq, amp))
            else:
                # keep the stronger of the two (already sorted strongest-first)
                pass
        merged = merged[:4]
        merged.sort(key=lambda x: x[0])
        return {"F1": merged[0][0] if len(merged) > 0 else None,
                "F2": merged[1][0] if len(merged) > 1 else None,
                "F3": merged[2][0] if len(merged) > 2 else None,
                "F4": merged[3][0] if len(merged) > 3 else None,
                "count": len(merged)}

    # ------------------------------------------------------------------ #
    # 3. VOICE CONVERSION (the actual "cloning" transform)
    # ------------------------------------------------------------------ #
    def convert_audio(self, input_audio: str, profile: Dict,
                      output_audio: Optional[str] = None,
                      strength: float = 0.9,
                      pitch_target: Optional[float] = None,
                      progress_cb=None) -> Optional[str]:
        """
        Convert ``input_audio`` to the reference voice in ``profile``.

        Parameters
        ----------
        strength : float
            How aggressively the input timbre is pushed toward the
            reference envelope (0 = none / pure pitch-map, 1 = full morph,
            >1 = exaggerate).
        pitch_target : float, optional
            Target F0 for the conversion.  Defaults to the profile's
            ``pitch_target`` (male-band median) or its mean pitch.
        """
        strength = float(np.clip(strength, 0.0, 1.0))
        if progress_cb:
            progress_cb("Loading source audio", 5)
        y, sr = librosa.load(input_audio, sr=self.target_sr, mono=True)
        prof_sr = int(profile.get("sample_rate", self.target_sr))
        if sr != prof_sr:
            y = librosa.resample(y, orig_sr=sr, target_sr=prof_sr)
            sr = prof_sr

        if np.max(np.abs(y)) > 0:
            y = y / np.max(np.abs(y)) * 0.5

        # ---------- WORLD analysis -----------------------------------
        if progress_cb:
            progress_cb("Extracting F0 / spectral envelope (WORLD)", 30)
        f0, t = pw.dio(y.astype(np.float64), sr,
                       frame_period=self.frame_period)
        sp = pw.cheaptrick(y.astype(np.float64), f0, t, sr)
        ap = pw.d4c(y.astype(np.float64), f0, t, sr)

        # ---------- pitch mapping ------------------------------------
        voiced_mask = f0 > 0
        if not np.any(voiced_mask):
            raise ValueError("Source audio has no detectable voiced frames")

        src_mean = np.mean(f0[voiced_mask])
        if pitch_target is None:
            pitch_target = float(profile.get(
                "pitch_target",
                profile["pitch"].get("male_band_median_hz",
                                     profile["pitch"]["mean_hz"],
                                  ))
            )
        # Use a bounded log-frequency shift so source prosody is retained.
        target_hz = float(pitch_target) if pitch_target and pitch_target > 0 else src_mean
        ratio = 2.0 ** (np.log2(target_hz) - np.log2(src_mean))
        ratio = float(np.clip(ratio, 0.75, 1.35))
        f0_conv = np.where(voiced_mask, f0 * float(ratio), 0.0)

        # ---------- spectral envelope transfer ------------------------
        ref_env = np.asarray(profile["spectral"]["envelope_mean"])
        if ref_env.ndim != 1:
            ref_env = ref_env.flatten()
        if len(ref_env) != sp.shape[1]:
            ref_env = np.interp(
                np.linspace(0, 1, sp.shape[1]),
                np.linspace(0, 1, len(ref_env)),
                ref_env,
            )
        freqs = np.linspace(0.0, sr / 2.0, sp.shape[1])
        ref_env = np.maximum(ref_env, 1e-8)

        sp_conv = sp.copy()
        n_bins = sp.shape[1]
        voiced_idx = np.where(voiced_mask)[0]
        sv = np.maximum(sp[voiced_idx], 1e-8)          # (n_voiced, n_bins)

        if abs(ratio - 1.0) > 0.01:
            # relocate harmonics: new spectrum @ f comes from f/ratio
            # (bilinear interpolation on the linear WORLD frequency grid)
            desired = freqs / ratio
            bin_pos = np.clip(desired / freqs[-1] * (n_bins - 1), 0.0, n_bins - 1)
            x0 = np.floor(bin_pos).astype(np.intp)
            x1 = np.minimum(x0 + 1, n_bins - 1)
            frac = bin_pos - x0
            shifted = (sv[:, x0] * (1.0 - frac) + sv[:, x1] * frac)
            shifted[:, desired > freqs[-1]] = 0.0
        else:
            shifted = sv

        # Blend normalized spectral shapes so articulation and per-frame
        # energy remain audible while the reference timbre is transferred.
        source_log_shape = np.log(np.maximum(shifted, 1e-8))
        source_log_shape -= np.mean(source_log_shape, axis=1, keepdims=True)
        reference_log_shape = np.log(ref_env)
        reference_log_shape -= np.mean(reference_log_shape)
        blended_shape = ((1.0 - strength) * source_log_shape
                 + strength * reference_log_shape)
        source_energy = np.sqrt(np.mean(sv ** 2, axis=1, keepdims=True))
        sp_conv[voiced_idx] = np.exp(blended_shape) * source_energy

        # keep overall loudness of the source clip
        energy_in = np.sum(sp ** 2)
        energy_out = np.sum(sp_conv ** 2) + 1e-8
        sp_conv *= np.sqrt(energy_in / energy_out)

        # ---------- resynthesis ---------------------------------------
        if progress_cb:
            progress_cb("Resynthesizing with WORLD vocoder", 72)
        y_out = pw.synthesize(f0_conv, sp_conv, ap, sr,
                              frame_period=self.frame_period)

        # ---------- loudness matching -------------------------------
        ref_rms = float(profile["prosody"]["mean_rms"])
        if ref_rms > 0:
            cur_rms = np.sqrt(np.mean(y_out ** 2)) + 1e-8
            y_out = y_out * (ref_rms / cur_rms)
        # Preserve transients while avoiding hard clipping after gain matching.
        peak = np.max(np.abs(y_out))
        if peak > 0.98:
            y_out = np.tanh(y_out / peak) * 0.98

        if output_audio:
            os.makedirs(os.path.dirname(os.path.abspath(output_audio)),
                        exist_ok=True)
            sf.write(output_audio, y_out, sr)
            if progress_cb:
                progress_cb("Saved converted audio", 100)
            return output_audio
        return None
# ------------------------------------------------------------------ #
    # 4. TEXT-TO-SPEECH + CONVERSION ("generate vocals from text")
    # ------------------------------------------------------------------ #
    def text_to_speech_with_voice(self, text: str, profile: Dict,
                                  output_audio: str,
                                  strength: float = 0.9,
                                  pitch_target: Optional[float] = None,
                                  progress_cb=None) -> Optional[str]:
        """
        Synthesize ``text`` with a neutral TTS then convert it into the
        reference voice stored in ``profile``. Falls back to a DSP tone
        when gTTS is offline/unavailable.
        """
        if progress_cb:
            progress_cb("Generating neutral speech from text", 10)
        tts_path = self._tts_to_wav(text, output_audio)

        try:
            return self.convert_audio(tts_path, profile, output_audio,
                                      strength=strength,
                                      pitch_target=pitch_target,
                                      progress_cb=progress_cb)
        finally:
            for tmp in (output_audio + ".tts.mp3",
                        output_audio + ".tts.wav",
                        output_audio + ".fb.wav"):
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass

    def _tts_to_wav(self, text: str, base_path: str) -> str:
        if GTTS_OK:
            try:
                mp3 = base_path + ".tts.mp3"
                gTTS(text=text, lang="en", slow=False).save(mp3)
                y, sr = librosa.load(mp3, sr=self.target_sr, mono=True)
                wav = base_path + ".tts.wav"
                sf.write(wav, y, sr)
                return wav
            except Exception as e:
                print(f"  ! gTTS failed ({e}); using tone fallback")
        fb = base_path + ".fb.wav"
        self._fallback_tts_audio(text, fb)
        return fb

    @staticmethod
    def _fallback_tts_audio(text: str, path: str) -> str:
        """Melodic placeholder voice when gTTS is unavailable/offline."""
        import hashlib
        sr = 22050
        seed = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        n_words = max(1, len(text.split()))
        total_n = int(sr * 0.55 * n_words * 1.2)
        t = np.arange(total_n) / sr
        amp = 0.5 + 0.5 * np.sin(2 * np.pi * 1.6 * t)
        y = 0.4 * np.sin(2 * np.pi * 150 * t) * amp
        y += 0.15 * np.sin(2 * np.pi * 300 * t) * amp
        y += 0.05 * rng.standard_normal(total_n) * amp
        max_amp = np.max(np.abs(y))
        if max_amp > 0:
            y = y / max_amp * 0.6
        sf.write(path, y, sr)
        return path


def main():
    """CLI quick test."""
    import glob
    import sys

    engine = VoiceConversionEngine()
    clips = sorted(glob.glob("dataset/Pacaveli_processed/*.wav"))
    if not clips:
        print("No Pacaveli clips found; nothing to do.")
        sys.exit(0)
    print(f"Building reference voice from {len(clips)} clips ...")
    profile = engine.extract_reference_profile(clips)
    out_pth = "models/pacaveli/model.pth"
    engine.save_profile(profile, out_pth)
    print(f"Saved model -> {out_pth}")
    print(f"  mean pitch   : {profile['pitch']['mean_hz']:.1f} Hz")
    print(f"  median pitch : {profile['pitch']['median_hz']:.1f} Hz")
    print(f"  centroid     : {profile['spectral']['mean_centroid_hz']:.0f} Hz")
    print(f"  formants     : {profile.get('formants', {})}")


if __name__ == "__main__":
    main()