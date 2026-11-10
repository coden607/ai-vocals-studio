"""Silero TTS backend wrapper (lightweight, CPU‑friendly).

The original Silero TTS models are small (~70 MB) and run well on a
CPU‑only VPS. This wrapper provides a ``clone`` function compatible with the
package's public API:

```python
clone(source_wav: str, reference_wav: str, output_path: str) -> str
```

The Silero model does **not** perform true voice cloning – it synthesises the
text of ``source_wav`` with a generic voice. For a lightweight approximation we
simply:

1. Transcribe ``source_wav`` to text using Whisper‑base (already a small
   dependency in the repo).
2. Run the Silero TTS model on that text.
3. Save the generated audio to ``output_path``.

If a GPU is available ``torch.cuda.is_available()`` the model is moved to the
GPU automatically.
"""

import os
from pathlib import Path
import torch
import torchaudio
from transformers import pipeline

# Load Whisper base for transcription (already used elsewhere).
_ASR_PIPELINE = None

def _get_asr_pipeline():
    global _ASR_PIPELINE
    if _ASR_PIPELINE is None:
        _ASR_PIPELINE = pipeline("automatic-speech-recognition", model="openai/whisper-base")
    return _ASR_PIPELINE

def _load_silero_tts():
    """Load the Silero TTS model (CPU by default, GPU if available)."""
    # Silero TTS is distributed via torch.hub
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = torch.hub.load("snakers4/silero-models", "silero_tts", language="en", speaker="en_1")
    model.to(device)
    return model, device

def clone(source_wav: str, reference_wav: str, output_path: str) -> str:
    """Generate speech from ``source_wav`` using Silero TTS.

    The function ignores ``reference_wav`` because Silero does not support speaker
    conditioning. This limitation is documented for users who need true voice
    cloning.
    """
    # 1️⃣ Transcribe source audio
    asr = _get_asr_pipeline()
    transcription = asr(source_wav)["text"]

    # 2️⃣ Synthesize with Silero TTS
    tts_model, device = _load_silero_tts()
    # Silero expects a list of strings
    wav = tts_model.apply_tts(text=transcription, speaker=1, sample_rate=48000)
    wav = torch.tensor(wav).unsqueeze(0)  # shape (1, samples)

    # 3️⃣ Save to file (convert to 16kHz for consistency)
    wav_resampled = torchaudio.transforms.Resample(orig_freq=48000, new_freq=16000)(wav)
    torchaudio.save(output_path, wav_resampled.cpu(), 16000)
    return os.path.abspath(output_path)
