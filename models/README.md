# models/

Real checkpoints are **user-provided or cloud-trained** — never committed to git.

This directory starts empty of weights on purpose:

- **Trained engines (RVC v2, so-vits-svc)** need a training run on cloud GPU.
  Use the repo's own notebooks — `cloud/kaggle_rvc_worker.ipynb` (free Kaggle
  P100) or `colab/` (Colab T4) — against an *authorized* dataset (see
  `dataset/README.md`), then import the produced `.pth` / `.index` locally:
  - `python3 rvc_training_cli.py --model <name> --weights <path>.pth --i-have-permission`
- **Zero-shot engines (Qwen3-TTS, XTTS v2, ElevenLabs)** download their base
  weights at first run or use an API key — nothing to commit.
- The 0-byte `models/model.pth` placeholder is a template, not a model.
  `scripts/doctor.py` reports it as a placeholder, as it should.

**Never commit weights** (`.pth` / `.pt` / `.ckpt`): they are large, and
voice-model weights derived from a person's voice are personal data plus a
license surface. `.gitignore` enforces this — keep it that way.
