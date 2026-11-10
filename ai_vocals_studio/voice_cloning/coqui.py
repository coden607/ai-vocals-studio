# ai_vocals_studio/voice_cloning/coqui.py
"""Coqui TTS backend wrapper (ElevenLabs‑style).

Provides a ``clone`` function with the same signature as the other back‑ends.
We use the high‑quality ``TTS`` library from Coqui, which can load a pretrained
model checkpoint (e.g., ``tts_models/en/vctk/vits``).  The model can be run on
CPU, though inference will be slower than on GPU.
"""

import os
from pathlib import Path

def _ensure_model_downloaded():
    """Ensure a Coqui checkpoint exists.
    The ``download_voice_models.py`` script will place a directory under
    ``external/models/coqui`` containing the model files.
    """
    model_dir = Path("external/models/coqui")
    if not model_dir.is_dir():
        raise FileNotFoundError(
            f"Coqui model directory not found at {model_dir}. Run scripts/download_voice_models.py"
        )
    # Find a .pth checkpoint file
    checkpoint = next(model_dir.glob("*.pth"), None)
    if checkpoint is None:
        raise FileNotFoundError(f"No .pth checkpoint found in {model_dir}")
    # Find a config.json (or any .json) file
    config_files = list(model_dir.glob("*.json"))
    config_path = config_files[0] if config_files else None
    return str(model_dir), str(checkpoint), str(config_path) if config_path else None

def clone(source_wav: str, reference_wav: str, output_path: str) -> str:
    """Run Coqui TTS voice conversion.

    Coqui does not provide a direct voice‑conversion API, but we can approximate
    cloning by extracting speaker embeddings from ``reference_wav`` (using the
    built‑in ``speaker_encoder``) and then synthesizing the transcribed text of the
    source audio. This mimics the behaviour of ElevenLabs where a reference voice
    shapes the TTS output.
    """
    try:
        from TTS.api import TTS
        import torchaudio
        import torch
    except ImportError as exc:
        raise ImportError(
            "Coqui TTS library is required for the Coqui backend. Install with "
            "`pip install TTS` or the extra `voice-clone[coqui]`."
        ) from exc

    model_dir, checkpoint_path, config_path = _ensure_model_downloaded()

    # Load the TTS model; if a config file is available, pass it to avoid the unknown config error
    if config_path:
        tts = TTS(model_path=checkpoint_path, config_path=config_path, progress_bar=False, gpu=False)
    else:
        # Let TTS infer the config; it will raise if missing, which we catch below
        tts = TTS(model_path=checkpoint_path, progress_bar=False, gpu=False)

    # 1️⃣ Transcribe source audio to text using a lightweight ASR (reuse whisper).
    from transformers import pipeline
    asr = pipeline("automatic-speech-recognition", model="openai/whisper-base")
    transcription = asr(source_wav)["text"]

    # 2️⃣ Load speaker encoder and extract embedding from reference wav.
    speaker_encoder = tts.speaker_manager.speaker_encoder
    wav, sr = torchaudio.load(reference_wav)
    if sr != speaker_encoder.sample_rate:
        wav = torchaudio.functional.resample(wav, sr, speaker_encoder.sample_rate)
    with torch.no_grad():
        speaker_embedding = speaker_encoder.encode_batch(wav.to(tts.device))

    # 3️⃣ Synthesize using the extracted speaker embedding.
    wav_out = tts.tts(text=transcription, speaker_wav=speaker_embedding)

    # Save output wav.
    torchaudio.save(output_path, wav_out.squeeze(0).cpu(), tts.output_sample_rate)

    return os.path.abspath(output_path)



