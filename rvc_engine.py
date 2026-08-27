"""
rvc_engine.py — RVC v2 (Retrieval-based Voice Conversion) inference engine

Audio-to-audio voice conversion: input speech/rap → Pacaveli's voice.
This is what deepfake rap tracks use — preserves rap rhythm and flow
while swapping the voice timbre.

Requires:  pip install rvc-python
Model files (trained on Colab):
    models/<name>/rvc_model.pth    — required
    models/<name>/rvc_model.index  — optional but improves quality

Usage:
    engine = RvcEngine()
    if engine.can_infer('Pacaveli'):
        ok, err = engine.convert('Pacaveli', 'input.wav', 'output.wav', pitch_shift=0)
"""
from __future__ import annotations
import threading
from pathlib import Path
from typing import Callable, Optional

_ProgressCB = Callable[[str, int], None]

# Status constants (parallel to svc_engine)
STATUS_READY   = 'ready'
STATUS_MISSING = 'missing'

# Lazy globals — rvc-python is heavy, don't import at startup
_rvc_module = None
_rvc_lock   = threading.Lock()
_rvc_ready  = threading.Event()
HAS_RVC: bool = False


def _ensure_rvc(progress_cb: Optional[_ProgressCB] = None) -> bool:
    """Import rvc-python on first call. Thread-safe. Returns True if available."""
    global _rvc_module, HAS_RVC
    if _rvc_ready.is_set():
        return HAS_RVC
    if not _rvc_lock.acquire(blocking=False):
        _rvc_ready.wait(timeout=60)
        return HAS_RVC
    try:
        if progress_cb:
            progress_cb('Loading RVC v2 engine…', 5)
        from rvc_python.infer import RVCInference as _RVC  # type: ignore
        _rvc_module = _RVC
        HAS_RVC = True
    except ImportError:
        HAS_RVC = False
    except Exception:
        HAS_RVC = False
    finally:
        _rvc_ready.set()
        _rvc_lock.release()
    return HAS_RVC


class RvcEngine:
    """
    Manages RVC v2 model loading and audio-to-audio inference.

    Parameters
    ----------
    models_dir : path to models/ directory
    """

    def __init__(self, models_dir: str | Path = 'models'):
        self.MODELS = Path(models_dir)
        self._rvc = None          # loaded RVCInference instance
        self._loaded_name: Optional[str] = None
        self._lock = threading.Lock()

    # ── Model discovery ──────────────────────────────────────────

    def _model_dir(self, model_name: str) -> Optional[Path]:
        """Return the model directory for flat or saved voice profiles."""
        candidates = [self.MODELS / model_name,
                      self.MODELS / 'voices' / model_name]
        return next((path for path in candidates if path.is_dir()), None)

    def _find_pth(self, model_name: str) -> Optional[Path]:
        """Find the RVC .pth file for a model. Prefers rvc_model.pth."""
        model_dir = self._model_dir(model_name)
        if model_dir is None:
            return None
        # Prefer explicit rvc_model.pth
        rvc_pth = model_dir / 'rvc_model.pth'
        if rvc_pth.exists() and rvc_pth.stat().st_size > 10_000:
            return rvc_pth
        # Any .pth that isn't the SO-VITS base model
        candidates = [
            p for p in model_dir.glob('*.pth')
            if p.stat().st_size > 10_000
            and p.name not in ('G_0.pth', 'model.pth')
            and not p.stem.startswith('G_')   # skip SO-VITS G_NNNN.pth
        ]
        return candidates[0] if candidates else None

    def _find_index(self, model_name: str) -> Optional[Path]:
        """Find the .index file for retrieval (optional, improves quality)."""
        model_dir = self._model_dir(model_name)
        if model_dir is None:
            return None
        indices = [
            p for p in model_dir.glob('*.index')
            if p.stat().st_size > 0
        ]
        return indices[0] if indices else None

    def model_status(self, model_name: str) -> str:
        return STATUS_READY if self._find_pth(model_name) else STATUS_MISSING

    def can_infer(self, model_name: str) -> bool:
        return self.model_status(model_name) == STATUS_READY

    # ── Load ─────────────────────────────────────────────────────

    def load(
        self,
        model_name: str,
        device: Optional[str] = None,
        progress_cb: Optional[_ProgressCB] = None,
    ) -> tuple[bool, str]:
        """
        Load RVC model into memory. Returns (success, message).
        Reuses cached instance if same model already loaded.
        """
        if self._loaded_name == model_name and self._rvc is not None:
            return True, f'Already loaded ({model_name})'

        if not _ensure_rvc(progress_cb):
            return False, (
                'rvc-python not installed.\n'
                'Run:  pip install rvc-python'
            )

        pth = self._find_pth(model_name)
        if not pth:
            return False, f'No RVC model found for "{model_name}"'

        if device is None:
            try:
                import torch  # type: ignore
                device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
            except ImportError:
                device = 'cpu'

        index = self._find_index(model_name)

        try:
            with self._lock:
                rvc_instance = _rvc_module(device=device)
                rvc_instance.load_model(str(pth))
                if index:
                    # Set index for retrieval-based feature matching
                    try:
                        rvc_instance.set_params(
                            index_path=str(index),
                            index_rate=0.75,
                        )
                    except Exception:
                        pass  # index support varies by version
                self._rvc = rvc_instance
                self._loaded_name = model_name
            idx_note = f' + index' if index else ''
            return True, f'Loaded {pth.name}{idx_note} on {device}'
        except Exception as e:
            self._rvc = None
            self._loaded_name = None
            return False, str(e)

    def unload(self):
        with self._lock:
            self._rvc = None
            self._loaded_name = None

    # ── Inference ─────────────────────────────────────────────────

    def convert(
        self,
        model_name: str,
        input_wav: str | Path,
        output_wav: str | Path,
        pitch_shift: int = 0,
        f0_method: str = 'rmvpe',   # rmvpe = best quality, harvest = fast
        index_rate: float = 0.75,
        protect: float = 0.33,
        progress_cb: Optional[_ProgressCB] = None,
    ) -> tuple[bool, str]:
        """
        Convert input audio to target voice using RVC v2.

        Parameters
        ----------
        pitch_shift : semitones to shift pitch (0 = no change)
        f0_method   : 'rmvpe' (best), 'harvest' (fast), 'crepe' (accurate)
        index_rate  : how much to use the .index file (0=none, 1=full)
        protect     : protect voiceless consonants (0=none, 0.5=max)

        Returns (success, error_or_empty).
        """
        cb = progress_cb or _noop

        cb('Loading RVC v2 model…', 10)
        ok, msg = self.load(model_name, progress_cb=cb)
        if not ok:
            return False, msg

        cb('Running RVC v2 voice conversion…', 35)

        # Apply generation params
        try:
            with self._lock:
                try:
                    self._rvc.set_params(
                        f0up_key=int(pitch_shift),
                        f0method=f0_method,
                        index_rate=index_rate,
                        filter_radius=3,
                        resample_sr=44100,
                        rms_mix_rate=0.25,
                        protect=protect,
                    )
                except Exception:
                    pass  # older rvc-python versions may not have set_params

                cb('Converting voice…', 60)
                self._rvc.infer_file(
                    str(input_wav),
                    str(output_wav),
                )
        except Exception as e:
            return False, f'RVC inference error: {e}'

        out = Path(output_wav)
        if not out.exists() or out.stat().st_size < 500:
            return False, 'RVC output file empty or missing'

        cb('Done!', 100)
        return True, ''


# ── Utilities ─────────────────────────────────────────────────────

def _noop(msg: str, pct: int): pass


def rvc_status_label(model_name: str, models_dir: str | Path = 'models') -> str:
    engine = RvcEngine(models_dir)
    status = engine.model_status(model_name)
    return '🟣 RVC READY' if status == STATUS_READY else '⚫ RVC NOT TRAINED'
