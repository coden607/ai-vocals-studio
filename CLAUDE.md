Shared agent rules and skills live in [AGENTS.md](AGENTS.md). Read that before editing.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

```bash
# One-click launch (creates venv, installs deps, runs app_minimal.py)
./run.sh

# Run directly (requires venv activated and deps installed)
source venv/bin/activate
python app_minimal.py      # Minimal version (current default, lighter deps)
python app_modern.py       # Full-featured version (requires heavier ML deps)
```

## Installation

```bash
# First-time setup
./install.sh

# Manual dependency install inside venv
pip install gtts demucs so-vits-svc-fork librosa numpy soundfile pydub
```

## Architecture Overview

There are multiple app entry points at different complexity levels:

- **`app_minimal.py`** — The current production default (what `run.sh` launches). Uses gTTS + pydub for TTS and audio transformation. No heavy ML model required. Voice "cloning" is simulated via `voice_personas` dict (pitch shift, speed, reverb, EQ).
- **`app_modern.py`** — Full-featured Tkinter UI with model management, downloads, and richer UI. Requires heavier dependencies (`so-vits-svc-fork`, `demucs`).
- **`app.py`** — Legacy/original version.

### Key Modules

- **`voice_trainer.py`** — `VoiceTrainer` class: processes raw audio files (normalize, trim silence, resample to 22.05kHz) and creates SO-VITS-SVC training configs. Invoked for actual ML-based model training.
- **`enhanced_voice_cloner.py`** — `EnhancedVoiceCloner` class: analyzes voice characteristics (pitch, energy, tempo, speech rate via librosa) from audio files in `dataset/<speaker>/` and saves a JSON voice profile to `models/<speaker>/`.
- **`create_voice_model.py`** — Simpler model creation script.
- **`train_model.py`** — Standalone training script.

### Data Flow

```
dataset/<speaker>/        # Raw training audio (WAV/MP3/FLAC/OGG/M4A)
    ↓ VoiceTrainer / EnhancedVoiceCloner
models/<speaker>/         # model.pth + voice profile JSON
    ↓ app loads model
output/                   # Generated WAV files
```

### UI Structure (Tkinter Notebook tabs)

Both `app_minimal.py` and `app_modern.py` use a 3-tab layout:
1. **Generate** — Text-to-speech or audio-to-audio conversion
2. **Models** — Scan/manage `.pth` model files in `models/`
3. **Training** — Import audio clips into `dataset/`

All long-running operations run in daemon threads via `threading.Thread` to keep the UI responsive. Progress is reported through `update_operation_progress()` which updates a footer `ttk.Progressbar`.

### Model Discovery

`refresh_models()` in both apps scans `models/` for:
- `.pth` files directly in `models/`
- `model.pth` inside subdirectories (e.g., `models/Pacaveli/model.pth`)

The model name shown in the UI is the directory name or file stem.

### Voice Persona System (app_minimal.py)

`app_minimal.py` uses a `voice_personas` dict (not actual ML models) to simulate voice transformation via pydub:
- Pitch shift (frame rate manipulation)
- Speed change (`speedup()`)
- Simple reverb (echo overlay)
- EQ gain simulation

Model names are matched against persona keys (`"2pac"`, `"male"`, `"female"`, `"robot"`, `"default"`).

## Shared agent skills

Read and follow `AGENTS.md` before planning, editing, testing or committing. Use the complete canonical https://github.com/coden607/skills library under its shared-skills policy.
