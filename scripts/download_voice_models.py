# scripts/download_voice_models.py
"""Utility to download pretrained checkpoints for the voice‑cloning back‑ends.

The script creates ``external/models/<backend>`` directories (git‑ignored) and
fetches the required files.  It can be invoked manually or from the CI workflow.

Supported back‑ends and their sources:

* **RVC** – a generic ``model.pth`` placed by the user.  This script will not
  download a model automatically because the choice of checkpoint is highly
  domain‑specific.  Instead, it prints a helpful message.
* **YourTTS** – downloads the ``v2_3`` checkpoint from the official repo.
* **Qwen3‑Audio** – uses ``huggingface_hub`` to cache the ``Qwen/Qwen3-Audio``
  model under ``external/models/qwen3``.
* **Coqui** – downloads a pretrained VCTK‑based VITS model (en_us) via the
  Coqui ``tts`` CLI.

Running the script without arguments downloads *all* optional models.
"""

import argparse
import os
from pathlib import Path

def _ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

def download_yourtts():
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import RepositoryNotFoundError
    repo_id = "nii-yamagishilab/YourTTS"
    cache_dir = Path("external/models/yourtts")
    _ensure_dir(cache_dir)
    print(f"Downloading YourTTS checkpoint to {cache_dir} …")
    try:
        snapshot_download(repo_id=repo_id, local_dir=cache_dir, allow_patterns=["*.pth", "*.json"])
        print("YourTTS model downloaded.")
    except RepositoryNotFoundError:
        print("⚠️ YourTTS repository requires authentication or is private. Skipping download.")
    except Exception as exc:
        print(f"⚠️ Unexpected error while downloading YourTTS: {exc}")

def download_qwen3():
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import RepositoryNotFoundError
    repo_id = "Qwen/Qwen3-Audio"
    cache_dir = Path("external/models/qwen3")
    _ensure_dir(cache_dir)
    print(f"Downloading Qwen3‑Audio model to {cache_dir} …")
    try:
        snapshot_download(repo_id=repo_id, local_dir=cache_dir, ignore_patterns=["*.ckpt"])
        print("Qwen3 model cached.")
    except RepositoryNotFoundError:
        print("⚠️ Qwen3 repository requires authentication or is private. Skipping download.")
    except Exception as exc:
        print(f"⚠️ Unexpected error while downloading Qwen3: {exc}")

def download_coqui():
    # Use Coqui's ModelManager to download the model and copy it locally.
    from TTS.utils.manage import ModelManager
    import shutil
    model_dir = Path("external/models/coqui")
    _ensure_dir(model_dir)
    model_name = "tts_models/en/vctk/vits"
    print(f"Downloading Coqui TTS model '{model_name}' …")
    manager = ModelManager()
    # download_model returns a tuple (model_path, config_path, model_item).
    model_path, _, _ = manager.download_model(model_name)
    src_path = Path(model_path)
    if src_path.is_dir():
        shutil.copytree(src_path, model_dir, dirs_exist_ok=True)
    else:
        shutil.copy2(src_path, model_dir / src_path.name)
    print("Coqui model downloaded to external/models/coqui.")

def main():
    parser = argparse.ArgumentParser(description="Download pretrained voice‑cloning models.")
    parser.add_argument("--backends", nargs="*", choices=["yourtts", "qwen3", "coqui"], default=["yourtts", "qwen3", "coqui"], help="Which back‑ends to download.")
    args = parser.parse_args()
    if "yourtts" in args.backends:
        download_yourtts()
    if "qwen3" in args.backends:
        download_qwen3()
    if "coqui" in args.backends:
        download_coqui()
    if "rvc" in args.backends:
        print("RVC requires a user‑provided checkpoint placed at external/models/rvc/model.pth.")

if __name__ == "__main__":
    main()
