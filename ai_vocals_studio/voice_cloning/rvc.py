# ai_vocals_studio/voice_cloning/rvc.py
"""RVC backend wrapper.

Expose a ``clone`` function matching the signature expected by ``clone_voice``:

    clone(source_wav: str, reference_wav: str, output_path: str) -> str

The implementation uses the community ``infer_rvc_python`` package, which works on CPU.
If the package is not installed, the wrapper will raise a clear ``ImportError``.
"""

import os
from pathlib import Path

def _ensure_model_downloaded():
    """Ensure an RVC model checkpoint is present.
    For simplicity we expect the user to have placed a ``.pth`` file under
    ``external/models/rvc/model.pth``.  If it does not exist we raise an error.
    """
    model_path = Path("external/models/rvc/model.pth")
    if not model_path.is_file():
        raise FileNotFoundError(
            f"RVC model not found at {model_path}. Please run ``scripts/download_voice_models.py``"
        )
    return str(model_path)

def clone(source_wav: str, reference_wav: str, output_path: str) -> str:
    """Run RVC voice conversion.

    Parameters
    ----------
    source_wav: Path to the audio you want to convert.
    reference_wav: Path to a short (5‑30 s) clean recording of the target voice.
    output_path: Destination file (must end with ``.wav``).
    """
    try:
        from infer_rvc_python import BaseLoader
    except ImportError as exc:
        raise ImportError(
            "The 'infer_rvc_python' package is required for the RVC backend. "
            "Install it with `pip install infer_rvc_python` or add the extra "
            "`voice-clone[rvc]` to your requirements."
        ) from exc

    model_path = _ensure_model_downloaded()

    # Initialise the converter – ``only_cpu=True`` forces CPU usage.
    converter = BaseLoader(only_cpu=True)
    # Apply a minimal configuration – most settings can stay at defaults.
    converter.apply_conf(
        tag="default",
        file_model=model_path,
        pitch_algo="rmvpe+",
        pitch_lvl=0,
        file_index="",
        index_influence=0.0,
        respiration_median_filtering=3,
        envelope_ratio=0.25,
        consonant_breath_protection=0.33,
    )
    # The ``generate_audio`` method expects input and output paths.
    converter.generate_audio(speaker="default", input_path=source_wav, output_path=output_path)

    # The wrapper returns the absolute output path for consistency.
    return os.path.abspath(output_path)
