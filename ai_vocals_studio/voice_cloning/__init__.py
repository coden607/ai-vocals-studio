# -*- coding: utf-8 -*-
"""Voice cloning package initializer.
Provides a unified `clone_voice` function that dispatches to the selected backend.
"""

from pathlib import Path
from typing import Literal

_BACKEND_MODULES = {
    "coqui": "ai_vocals_studio.voice_cloning.coqui",
    "silero": "ai_vocals_studio.voice_cloning.silero",
    "qwen3": "ai_vocals_studio.voice_cloning.qwen3",
}

BackendType = Literal["coqui", "silero", "qwen3"]

def clone_voice(
    source_wav: str,
    reference_wav: str,
    model: BackendType = "coqui",
    output_path: str | None = None,
) -> str:
    """Clone `source_wav` to sound like `reference_wav` using the chosen backend.

    Parameters
    ----------
    source_wav: Path to the original audio (e.g., a song or spoken phrase).
    reference_wav: Path to a short clean recording of the target voice.
    model: Backend identifier – "coqui", "silero" or "qwen3".
    output_path: Destination file. If omitted, a `<source>_cloned_<model>.wav`
        file will be created beside `source_wav`.

    Returns
    -------
    str
        Absolute path to the generated audio file.
    """
    source_wav = Path(source_wav).expanduser().resolve()
    reference_wav = Path(reference_wav).expanduser().resolve()
    if output_path is None:
        output_path = source_wav.parent / f"{source_wav.stem}_cloned_{model}.wav"
    output_path = Path(output_path).expanduser().resolve()

    mod_path = _BACKEND_MODULES[model]
    module = __import__(mod_path, fromlist=["clone"])
    try:
        return module.clone(str(source_wav), str(reference_wav), str(output_path))
    except Exception as e:
        # Fallback to Silero backend if Coqui fails (e.g., missing config)
        fallback_mod = __import__(_BACKEND_MODULES["silero"], fromlist=["clone"])
        return fallback_mod.clone(str(source_wav), str(reference_wav), str(output_path))
