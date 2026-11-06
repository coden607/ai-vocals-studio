# -*- coding: utf-8 -*-
"""Voice cloning package initializer.
Provides a unified `clone_voice` function that dispatches to the selected backend.
"""

from pathlib import Path
from typing import Literal

_BACKEND_MODULES = {
    "coqui": "ai_vocals_studio.voice_cloning.coqui",
    "qwen3": "ai_vocals_studio.voice_cloning.qwen3",
}

BackendType = Literal["coqui", "qwen3"]

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
    model: Backend identifier – "coqui" or "qwen3". Backend failures propagate;
        generic TTS cannot substitute for the selected reference voice.
    output_path: Destination file. If omitted, a `<source>_cloned_<model>.wav`
        file will be created beside `source_wav`.

    Returns
    -------
    str
        Absolute path to the generated audio file.
    """
    if model == "silero":
        raise ValueError("Silero cannot clone a reference voice or preserve a song performance; use the neural song pipeline.")
    if model not in _BACKEND_MODULES:
        raise ValueError(f"Unsupported cloning backend: {model!r}. Choose coqui or qwen3.")

    source_wav = Path(source_wav).expanduser().resolve()
    reference_wav = Path(reference_wav).expanduser().resolve()
    if output_path is None:
        output_path = source_wav.parent / f"{source_wav.stem}_cloned_{model}.wav"
    output_path = Path(output_path).expanduser().resolve()

    mod_path = _BACKEND_MODULES[model]
    module = __import__(mod_path, fromlist=["clone"])
    return module.clone(str(source_wav), str(reference_wav), str(output_path))
