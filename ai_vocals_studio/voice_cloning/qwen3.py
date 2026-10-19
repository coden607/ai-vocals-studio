# ai_vocals_studio/voice_cloning/qwen3.py
"""Qwen 3‑Audio backend wrapper.

Uses the HuggingFace ``transformers`` pipeline for the ``Qwen/Qwen3-Audio`` model.
The model is large but can run on CPU (slow).  The wrapper expects a model
checkpoint to be cached under ``external/models/qwen3`` – the ``download_voice_models``
script takes care of pulling it from HuggingFace.
"""

import os
from pathlib import Path

def _ensure_model_downloaded():
    """Make sure the Qwen 3 model files exist.
    The HuggingFace `transformers` pipeline will automatically download the
    weights on first use, but for reproducibility we cache them under
    ``external/models/qwen3`` and set ``TRANSFORMERS_CACHE``.
    """
    cache_dir = Path("external/models/qwen3")
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["TRANSFORMERS_CACHE"] = str(cache_dir)
    # No explicit file check – the pipeline will download if missing.
    return str(cache_dir)

def clone(source_wav: str, reference_wav: str, output_path: str) -> str:
    """Run Qwen 3‑Audio TTS/voice‑conversion.

    Qwen 3‑Audio works as a text‑to‑speech model; to emulate voice cloning we
    perform a simple two‑step process:
    1. Transcribe ``source_wav`` to text using a lightweight ASR (we reuse the
       same pipeline in ``transformers`` for convenience).
    2. Synthesize that text with the reference voice characteristics using the
       Qwen 3 model, which accepts a ``speaker_embedding`` extracted from
       ``reference_wav``.
    This is a pragmatic approximation that works on CPU without GPU.
    """
    try:
        from transformers import pipeline
        import torchaudio
    except ImportError as exc:
        raise ImportError(
            "Transformers and torchaudio are required for the Qwen3 backend."
            " Install with `pip install transformers[torch] torchaudio` or the extra "
            "`voice-clone[qwen3]`."
        ) from exc

    _ensure_model_downloaded()

    # 1️⃣ ASR – transcribe source audio to text (fast, cpu‑friendly)
    asr = pipeline("automatic-speech-recognition", model="openai/whisper-base")
    transcription = asr(source_wav)["text"]

    # 2️⃣ Load Qwen3 TTS pipeline – it supports a ``speaker_embeddings`` argument.
    tts = pipeline("text-to-speech", model="Qwen/Qwen3-Audio", torch_dtype="float32")

    # Extract a speaker embedding from the reference wav using the same pipeline.
    # The pipeline provides a ``speech_encoder`` we can reuse.
    speech_encoder = tts.model.get_encoder()
    waveform, sr = torchaudio.load(reference_wav)
    # Resample to 16kHz if needed (most models expect 16k).
    if sr != 16000:
        waveform = torchaudio.functional.resample(waveform, sr, 16000)
    with torch.no_grad():
        speaker_emb = speech_encoder(waveform.to(tts.device))

    # Generate audio conditioned on the speaker embedding.
    generated = tts(text=transcription, speaker_embeddings=speaker_emb)
    # ``generated`` is a dict with ``audio`` tensor.
    audio_tensor = generated["audio"]
    # Save to wav using torchaudio.
    torchaudio.save(output_path, audio_tensor.cpu(), 16000)

    return os.path.abspath(output_path)
