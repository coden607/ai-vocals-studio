# Quick Start

## Install once

```bash
./install.sh
```

The installer uses Python 3.12 for the app and isolated compatible runtimes for [Demucs](https://github.com/facebookresearch/demucs), [Seed-VC](https://github.com/Plachtaa/seed-vc), XTTS, and RVC. It also installs neural speaker verification. The first neural conversion downloads model weights; later runs reuse the local cache.

Check what this machine can actually run:

```bash
.venv/bin/python scripts/doctor.py
```

## Desktop: clone and replace a song

1. Launch with `./run.sh`.
2. Create a saved voice profile from at least 15–20 seconds of clean, authorized speech or vocals. Confirm that you own the voice or have explicit permission/a valid license.
3. Open **Generate**, select that voice, and choose the source song in **Audio Input**.
4. Click **Replace Song Vocals**.

With Seed-VC installed, no per-voice training is needed. The app runs Demucs separation, neural conversion of only the isolated vocal, and a protected remix that leaves the cloned vocal samples unchanged. If no neural converter is available, it stops rather than presenting DSP as a clone.

## CLI: one command from reference to finished song

```bash
.venv/bin/python clone_any_voice.py \
  --voice-source /path/to/authorized-reference.wav \
  --voice-source-type speech \
  --name my_voice \
  --target-audio /path/to/song.wav \
  --target-type song \
  --quality-target studio \
  --output-dir output/my_voice_song \
  --i-have-permission
```

Use `--voice-source-type song` when the reference itself needs Demucs vocal isolation. Studio requires neural conversion and a passing neural speaker-identity score; lower-quality DSP output is never substituted silently.

## Separate stems only

```bash
.venv/bin/python song_pipeline_cli.py separate /path/to/song.wav \
  --output-dir output/stems --method demucs --require-neural
```

This writes `vocals.wav` and `instrumental.wav`.

## Optional trained RVC path

For a voice-specific RVC checkpoint, prepare or import it with `rvc_training_cli.py --i-have-permission`. Training requires clean authorized audio and a configured local/Kaggle GPU trainer; a reference-only profile is not represented as a trained checkpoint.
