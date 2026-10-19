# ai_vocals_studio/voice_cloning/yourtts.py
"""YourTTS backend wrapper.

Provides a ``clone`` function compatible with ``clone_voice``.
The implementation uses the official ``yourtts`` library.  It expects a pretrained
model checkpoint (e.g., ``v2_3``) to be present under ``external/models/yourtts``.
If the model is missing, a clear ``FileNotFoundError`` is raised – the user can
run ``scripts/download_voice_models.py`` to fetch it.
"""

import os
from pathlib import Path

def _ensure_model_downloaded():
    """Check that a YourTTS checkpoint exists.
    The YourTTS repo ships a ``model.pth`` and a ``configs`` directory.  For the
    purpose of this wrapper we only need the model file.
    """
    model_path = Path("external/models/yourtts/model.pth")
    if not model_path.is_file():
        raise FileNotFoundError(
            f"YourTTS model not found at {model_path}. Run scripts/download_voice_models.py"
        )
    return str(model_path)

def clone(source_wav: str, reference_wav: str, output_path: str) -> str:
    """Run YourTTS voice conversion.

    YourTTS works primarily as a TTS engine, but it also offers a ``voice_transfer``
    method that can convert an input audio to the timbre of a reference voice.
    This wrapper calls that method.
    """
    try:
        from yourtts import Synthesizer, load_config
    except ImportError as exc:
        raise ImportError(
            "YourTTS library is required for the YourTTS backend. Install with "
            "`pip install yourtts` or the extra `voice-clone[yourtts]`."
        ) from exc

    model_path = _ensure_model_downloaded()

    # Load a minimal config – we reuse the default config shipped with the package.
    cfg = load_config()
    synthesizer = Synthesizer(model_path, cfg)

    # Convert the source audio to match the reference timbre.
    # YourTTS expects raw waveform data; we let the library handle loading.
    synthesizer.voice_transfer(
        source_path=source_wav,
        reference_path=reference_wav,
        output_path=output_path,
    )

    return os.path.abspath(output_path)
