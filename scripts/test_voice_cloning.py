# scripts/test_voice_cloning.py
"""Sanity‑check test for the voice‑cloning package.

The script:
1. Downloads a tiny public‑domain audio clip (a few seconds of speech).
2. Downloads a short reference voice clip (also public domain).
3. For each enabled backend (RVC, YourTTS, Qwen3, Coqui) it calls
   ``ai_vocals_studio.voice_cloning.clone_voice`` and verifies that the output
   file exists and its size is > 0 bytes.
4. Prints a concise success/failure report.

The test is deliberately lightweight so it can run on the CI CPU runner.
"""

import os
import urllib.request
from pathlib import Path

from ai_vocals_studio.voice_cloning import clone_voice

# ----------------------------------------------------------------------------
# Helper to download a small WAV file (≈3 s of spoken English).
# We'll use a public‑domain sample from the "VoxForge" dataset.
# URL chosen for reliable small size.
SOURCE_URL = "https://cdn.jsdelivr.net/gh/karpathy/char-rnn@master/data/tinyshakespeare.txt"
# Actually we need an audio file; use a short speech sample from
# https://github.com/common-voice/common-voice/raw/main/validated/en/1709830.wav
SOURCE_WAV_URL = "https://github.com/common-voice/common-voice/raw/main/validated/en/1709830.wav"
REFERENCE_WAV_URL = "https://github.com/common-voice/common-voice/raw/main/validated/en/1724479.wav"

def download_file(url: str, dest: Path):
    if dest.is_file():
        return dest
    print(f"Downloading {url} …")
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, str(dest))
    return dest

def main():
    data_dir = Path(".tmp_voice_test")
    source_wav = download_file(SOURCE_WAV_URL, data_dir / "source.wav")
    reference_wav = download_file(REFERENCE_WAV_URL, data_dir / "reference.wav")

    # Determine which backends have available models
    backends = []
    # Qwen3 model is always downloaded by the script
    backends.append("qwen3")
    # Coqui model is always downloaded by the script
    backends.append("coqui")
    # YourTTS may be missing if authentication failed; include only if model directory exists
    if Path("external/models/yourtts").exists() and any(Path("external/models/yourtts").rglob("*.pth")):
        backends.append("yourtts")
    # RVC requires user-provided checkpoint; skip automatically
    # backends.append("rvc")
    success = []
    failures = []
    for backend in backends:
        out_path = data_dir / f"out_{backend}.wav"
        try:
            print(f"\n--- Testing backend: {backend} ---")
            result_path = clone_voice(
                source_wav=str(source_wav),
                reference_wav=str(reference_wav),
                model=backend,
                output_path=str(out_path),
            )
            if Path(result_path).exists() and os.path.getsize(result_path) > 0:
                print(f"✅ {backend} produced {result_path} (size {os.path.getsize(result_path)} bytes)")
                success.append(backend)
            else:
                print(f"❌ {backend} output missing or empty.")
                failures.append(backend)
        except Exception as exc:
            print(f"❌ {backend} raised an exception: {exc}")
            failures.append(backend)
    print("\n=== Test Summary ===")
    print(f"Successful backends: {', '.join(success) if success else 'none'}")
    print(f"Failed backends: {', '.join(failures) if failures else 'none'}")
    if failures:
        raise SystemExit(1)
    else:
        print("All backends passed the sanity check.")

if __name__ == "__main__":
    main()
