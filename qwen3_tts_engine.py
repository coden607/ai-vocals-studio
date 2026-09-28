"""
qwen3_tts_engine.py - Qwen3-TTS voice cloning engine

Real neural voice cloning with 3-second rapid cloning, multi-language support,
and natural language voice control. Use this only with voices you own or have
explicit permission to clone.

Runs 100% locally (no API key). The system `sox` binary is NOT required; audio
is loaded with soundfile/librosa.

Model sizing:
  - GPU enabled           -> Qwen3-TTS-12Hz-1.7B-Base (best quality)
  - CPU                   -> Qwen3-TTS-12Hz-0.6B-Base  (fits ~2.5 GB RAM)
  - override via env var QWEN_TTS_MODEL, or QWEN_LOW_MEM=1 for float16 CPU.

Cloning mode:
  - Default: x-vector-only (speaker embedding only) — no reference transcript
    required. Pass ref_text=None.
  - With transcript: pass ref_text for slightly tighter delivery.

Usage:
    from qwen3_tts_engine import Qwen3TTSEngine
    engine = Qwen3TTSEngine()
    if engine.can_clone():
        out_path = engine.clone_voice(
            ref_audio="reference_sample.wav",
            ref_text=None,              # transcript optional
            target_text="This is the generated vocal take",
            speaker_name="Authorized_Voice",
        )
        engine.save_clone("Authorized_Voice", "reference_sample.wav")
        out2 = engine.generate_from_voice("Authorized_Voice",
                                          "Hello again in the same voice")
"""
from __future__ import annotations
import json
import os
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Union, List, Tuple

from voice_safety import VoiceSafetyError, validate_voice_clone_request

_ProgressCB = Callable[[str, int], None]

# Status constants
STATUS_READY = 'ready'
STATUS_MISSING = 'missing'
STATUS_LOADING = 'loading'
STATUS_ERROR = 'error'

# Lazy globals — qwen-tts is heavy, don't import at startup
_qwen_module = None
_qwen_lock = threading.Lock()
_qwen_ready = threading.Event()
HAS_QWEN: bool = False

# Where cloned voices are persisted (mirrors voice_cloner.DEFAULT_VOICES_DIR)
DEFAULT_VOICES_DIR = Path(os.environ.get("VOICES_DIR", "models/voices"))


def _safe_voice_name(name: str) -> str:
    """Return a filesystem-safe voice label."""
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name.strip())
    return safe.strip("._") or "cloned_voice"


def list_saved_voices(voices_dir: Union[str, Path] = DEFAULT_VOICES_DIR) -> List[dict]:
    """Return metadata for every saved voice clone, newest first."""
    voices_dir = Path(voices_dir)
    out: List[dict] = []
    if not voices_dir.is_dir():
        return out
    for d in sorted(voices_dir.iterdir(), key=lambda p: p.stat().st_mtime,
                    reverse=True):
        prof_file = d / "voice_profile.json"
        if not d.is_dir() or not prof_file.exists():
            continue
        try:
            data = json.loads(prof_file.read_text())
            out.append({
                "name": data.get("name", d.name),
                "source_type": data.get("source_type", "speech"),
                "description": data.get("description", ""),
                "created": data.get("created", ""),
                "reference": str(d / "reference.wav"),
                "voice_dir": str(d),
            })
        except Exception:
            continue
    return out


def load_voice_dir(voice_name: str,
                   voices_dir: Union[str, Path] = DEFAULT_VOICES_DIR) -> Optional[dict]:
    """Load a saved clone profile by name. Returns dict or None."""
    prof_file = Path(voices_dir) / _safe_voice_name(voice_name) / "voice_profile.json"
    if not prof_file.exists():
        return None
    try:
        return json.loads(prof_file.read_text())
    except Exception:
        return None


def _ensure_qwen(progress_cb: Optional[_ProgressCB] = None) -> bool:
    """Import qwen-tts on first call. Thread-safe. Returns True if available."""
    global _qwen_module, HAS_QWEN
    if _qwen_ready.is_set():
        return HAS_QWEN
    if not _qwen_lock.acquire(blocking=False):
        _qwen_ready.wait(timeout=60)
        return HAS_QWEN
    # qwen-tts loads audio via soundfile/librosa, so the system `sox` binary
    # is *not* required. Warn, don't block, when it's missing.
    if shutil.which("sox") is None and progress_cb:
        progress_cb("Note: system 'sox' not found — using soundfile for audio. "
                    "Install it (sudo apt install sox) for extra format support.", 5)
    try:
        if progress_cb:
            progress_cb('Loading Qwen3-TTS engine...', 5)

        from qwen_tts import Qwen3TTSModel
        import torch
        import soundfile as sf

        _qwen_module = {
            'Qwen3TTSModel': Qwen3TTSModel,
            'torch': torch,
            'soundfile': sf
        }
        HAS_QWEN = True
        _qwen_ready.set()
        return True
    except ImportError:
        HAS_QWEN = False
        _qwen_ready.set()
        return False
    except Exception:
        HAS_QWEN = False
        _qwen_ready.set()
        return False
    finally:
        _qwen_lock.release()


class Qwen3TTSEngine:
    """Qwen3-TTS voice cloning engine with rapid 3-second cloning"""

    def __init__(self, models_dir: str = None):
        if models_dir is None:
            models_dir = os.environ.get("MODEL_CACHE_DIR", "models")
        self.models_dir = Path(models_dir)
        self.model = None
        self.tokenizer = None
        self.device = "cuda" if self._check_cuda() else "cpu"
        self.current_model_name = None

    def _check_cuda(self) -> bool:
        """Check if CUDA is available"""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def can_clone(self) -> bool:
        """Check if Qwen3-TTS is available and can clone voices"""
        return _ensure_qwen()

    def get_supported_models(self) -> List[str]:
        """Get list of available Qwen3-TTS models"""
        return [
            "Qwen/Qwen3-TTS-12Hz-1.7B-Base",      # Best for voice cloning
            "Qwen/Qwen3-TTS-12Hz-0.6B-Base",      # Lightweight version
            "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", # Pre-trained voices
            "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"  # Voice design capabilities
        ]

    def load_model(self,
                   model_name: Optional[str] = None,
                   progress_cb: Optional[_ProgressCB] = None) -> bool:
        """Load a Qwen3-TTS model sized for this machine.

        Defaults:
          - GPU -> 1.7B (best quality)
          - CPU -> 0.6B (fits ~2.5 GB RAM; usable without a GPU)
        Override with an explicit `model_name`, or the env var QWEN_TTS_MODEL.
        """
        if not self.can_clone():
            return False

        if model_name is None:
            model_name = os.environ.get("QWEN_TTS_MODEL") or (
                "Qwen/Qwen3-TTS-12Hz-0.6B-Base" if self.device == "cpu"
                else "Qwen/Qwen3-TTS-12Hz-1.7B-Base")

        try:
            if progress_cb:
                progress_cb(f'Loading {model_name}...', 10)

            modules = _qwen_module
            torch = modules['torch']
            Qwen3TTSModel = modules['Qwen3TTSModel']

            low_mem = os.environ.get("QWEN_LOW_MEM", "").lower() in ("1", "true", "yes")
            dtype = torch.bfloat16 if self.device == "cuda" else (
                torch.float16 if low_mem else torch.float32)
            attn = "flash_attention_2" if self.device == "cuda" else "sdpa"

            try:
                self.model = Qwen3TTSModel.from_pretrained(
                    model_name,
                    device_map=self.device,
                    dtype=dtype,
                    attn_implementation=attn,
                )
            except Exception:
                # last resort: whatever precision / settings load cleanly
                self.model = Qwen3TTSModel.from_pretrained(model_name)

            self.current_model_name = model_name

            if progress_cb:
                progress_cb('Model loaded successfully!', 100)

            return True

        except Exception as e:
            if progress_cb:
                progress_cb(f'Error loading model: {str(e)}', 0)
            return False

    def save_clone(self,
                   name: str,
                   ref_audio_path: Union[str, Path],
                   source_type: str = "speech",
                   description: str = "",
                   voices_dir: Union[str, Path] = DEFAULT_VOICES_DIR,
                   has_permission: bool = False) -> Path:
        """Persist a cloned voice so it can be re-used later.

        Stores `reference.wav` + `voice_profile.json` under
        `models/voices/<name>/`. Returns the voice directory.
        """
        validate_voice_clone_request(
            has_permission=has_permission,
            speaker_name=name,
            description=description,
            source_path=ref_audio_path,
        )
        name = _safe_voice_name(name)
        d = Path(voices_dir) / name
        d.mkdir(parents=True, exist_ok=True)

        if Path(ref_audio_path).exists():
            shutil.copy2(ref_audio_path, d / "reference.wav")

        profile = {
            "name": name,
            "source_type": source_type,
            "description": description,
            "created": datetime.now().isoformat(timespec="seconds"),
            "reference": str(d / "reference.wav"),
            "voice_dir": str(d),
            "methods": {"dsp": True, "qwen_neural": True, "rvc": False},
        }
        (d / "voice_profile.json").write_text(json.dumps(profile, indent=2))
        return d

    def generate_from_voice(self,
                            voice: Union[str, Path, dict],
                            text: str,
                            language: str = "Auto",
                            output_path: Optional[Union[str, Path]] = None,
                            progress_cb: Optional[_ProgressCB] = None,
                            has_permission: bool = False) -> Optional[str]:
        """Speak `text` in a previously saved cloned voice.

        voice     : a saved voice name (looked up in models/voices),
                    or a dict/profile with a 'reference'/'voice_dir' key.
        """
        cb = progress_cb or (lambda m, p: None)

        if isinstance(voice, dict):
            ref = voice.get("reference") or (Path(voice.get("voice_dir", "")) / "reference.wav")
        else:
            prof = load_voice_dir(str(voice))
            ref = (prof or {}).get("reference")

        if not ref or not Path(ref).exists():
            cb(f"Voice not found: {voice}", 0)
            return None

        cb(f"Generating with saved voice {Path(str(ref)).parent.name}...", 25)
        return self.clone_voice(
            ref_audio=str(ref),
            ref_text=None,                 # x-vector-only: no transcript needed
            target_text=text,
            speaker_name=Path(str(ref)).parent.name,
            language=language,
            output_path=output_path,
            progress_cb=cb,
            has_permission=has_permission,
        )

    def clone_voice(self,
                   ref_audio: Union[str, Path, Tuple[np.ndarray, int]],
                   ref_text: str,
                   target_text: str,
                   speaker_name: str = "cloned_voice",
                   language: str = "Auto",
                   output_path: Optional[Union[str, Path]] = None,
                   progress_cb: Optional[_ProgressCB] = None,
                   has_permission: bool = False) -> Optional[str]:
        """
        Clone voice using reference audio

        Args:
            ref_audio: Reference audio file path or (numpy_array, sample_rate) tuple
            ref_text: Transcript of reference audio (optional — pass None and the
                      clone is built from the voice alone, no transcript needed)
            target_text: Text to synthesize in cloned voice
            speaker_name: Name for the cloned voice
            language: Target language (Auto for auto-detection)
            output_path: Output file path (auto-generated if None)
            progress_cb: Progress callback function

        Returns:
            Path to generated audio file or None if failed
        """
        try:
            validate_voice_clone_request(
                has_permission=has_permission,
                speaker_name=speaker_name,
                source_path=ref_audio if isinstance(ref_audio, (str, Path)) else "",
            )
        except VoiceSafetyError as e:
            if progress_cb:
                progress_cb(str(e), 0)
            return None

        if not self.model:
            if not self.load_model(progress_cb=progress_cb):
                return None

        try:
            if progress_cb:
                progress_cb('Cloning voice...', 30)

            modules = _qwen_module
            soundfile = modules['soundfile']

            # Generate cloned voice.
            # x_vector_only_mode=True clones from the speaker embedding alone,
            # so no reference transcript is required (works from any clean clip).
            wavs, sr = self.model.generate_voice_clone(
                ref_audio=ref_audio,
                ref_text=ref_text,
                text=target_text,
                language=language,
                x_vector_only_mode=True,
            )

            if progress_cb:
                progress_cb('Saving audio...', 90)

            # Generate output path if not provided
            if output_path is None:
                output_dir = Path(os.environ.get("OUTPUT_DIR", "outputs"))
                output_dir.mkdir(exist_ok=True)
                output_path = output_dir / f"{_safe_voice_name(speaker_name)}_qwen_clone.wav"

            # Save audio
            soundfile.write(str(output_path), wavs[0], sr)

            if progress_cb:
                progress_cb('Voice clone complete!', 100)

            return str(output_path)

        except Exception as e:
            if progress_cb:
                progress_cb(f'Cloning failed: {str(e)}', 0)
            return None

    def design_voice(self,
                    text: str,
                    voice_description: str,
                    speaker_name: str = "designed_voice",
                    language: str = "Auto",
                    output_path: Optional[Union[str, Path]] = None,
                    progress_cb: Optional[_ProgressCB] = None,
                    has_permission: bool = False) -> Optional[str]:
        """
        Design a voice using natural language description

        Args:
            text: Text to synthesize
            voice_description: Natural language description of desired voice
            speaker_name: Name for the designed voice
            language: Target language
            output_path: Output file path
            progress_cb: Progress callback

        Returns:
            Path to generated audio file or None if failed
        """
        try:
            validate_voice_clone_request(
                has_permission=has_permission,
                speaker_name=speaker_name,
                voice_description=voice_description,
            )
        except VoiceSafetyError as e:
            if progress_cb:
                progress_cb(str(e), 0)
            return None

        if not self.model:
            # Load voice design model
            if not self.load_model("Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", progress_cb):
                return None

        try:
            if progress_cb:
                progress_cb('Designing voice...', 30)

            modules = _qwen_module
            soundfile = modules['soundfile']

            # Generate designed voice
            wavs, sr = self.model.generate_voice_design(
                text=text,
                language=language,
                instruct=voice_description
            )

            if progress_cb:
                progress_cb('Saving audio...', 90)

            # Generate output path if not provided
            if output_path is None:
                output_dir = Path(os.environ.get("OUTPUT_DIR", "outputs"))
                output_dir.mkdir(exist_ok=True)
                output_path = output_dir / f"{_safe_voice_name(speaker_name)}_qwen_design.wav"

            # Save audio
            soundfile.write(str(output_path), wavs[0], sr)

            if progress_cb:
                progress_cb('Voice design complete!', 100)

            return str(output_path)

        except Exception as e:
            if progress_cb:
                progress_cb(f'Voice design failed: {str(e)}', 0)
            return None

    def get_supported_languages(self) -> List[str]:
        """Get list of supported languages"""
        if not self.model:
            return []

        try:
            return self.model.get_supported_languages()
        except Exception:
            return ["Auto", "Chinese", "English", "Japanese", "Korean",
                   "German", "French", "Russian", "Portuguese", "Spanish", "Italian"]

    def get_supported_speakers(self) -> List[str]:
        """Get list of pre-trained speakers (for CustomVoice models)"""
        if not self.model:
            return []

        try:
            return self.model.get_supported_speakers()
        except Exception:
            return []


# Convenience function for quick cloning
def quick_clone_voice(ref_audio_path: str,
                      ref_text: str,
                      target_text: str,
                      output_name: str = "quick_clone",
                      has_permission: bool = False) -> Optional[str]:
    """Quick voice cloning without engine setup"""
    engine = Qwen3TTSEngine()
    return engine.clone_voice(
        ref_audio=ref_audio_path,
        ref_text=ref_text,
        target_text=target_text,
        speaker_name=output_name,
        has_permission=has_permission,
    )
