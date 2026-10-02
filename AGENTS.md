# AGENTS.md — AI Vocals Studio

## Mission
Build a reliable, consent-first AI vocal production studio for authorized voices. Optimize for real audio quality, reproducibility, observability, and graceful failure rather than demos that merely appear to work.

## Non-negotiable workflow
1. Inspect existing architecture and tests before editing.
2. Work on a feature branch; never push experimental changes directly to main.
3. Preserve backward compatibility unless a migration is documented.
4. Never commit secrets, API keys, private training audio, generated voice models, or large binary artifacts.
5. Run fast static/sanity checks first, then focused tests, then the broader suite.
6. Do not claim an engine/model is active unless runtime validation proves it.
7. Do not silently fall back from a requested high-fidelity engine to DSP/persona simulation. Return a clear actionable error.
8. Merge only after required checks pass.

## Voice authorization
Voice cloning/training requires explicit speaker permission or a valid license. Route cloning/training entry points through `voice_safety.validate_voice_clone_request`. Store only a minimal authorization assertion/metadata; do not commit identity documents or private consent recordings.

Pacaveli is an authorized project voice per the project owner. Training audio still stays outside Git; model artifacts should live in configured object/model storage.

## Engine strategy
- **RVC**: primary path for singing/rap voice conversion when a trained authorized model is available.
- **Qwen3-TTS**: rapid reference cloning / speech generation where supported.
- **XTTS v2**: local TTS/reference-cloning sidecar option.
- **ElevenLabs**: optional hosted cloning/TTS provider; never make local operation depend on it.
- **Demucs**: stem/vocal separation before conversion when input is a mix.
- **WORLD/DSP/persona transforms**: explicit preview/fallback only; never label them as a trained clone.

Engine selection should be capability-based and deterministic. Report selected engine, model/profile, elapsed time, input/output duration, and failure/fallback reason without logging secrets or raw private audio.

## Production pipeline
Preferred song workflow:
`ingest -> validate -> separate vocals if needed -> normalize/clean -> select authorized voice -> RVC conversion -> preserve timing/prosody -> loudness/peak guard -> remix -> QA -> export`.

Reference/TTS workflow:
`authorized reference -> validate -> Qwen3-TTS/XTTS/hosted provider -> QA -> export`.

## Precision claims
Do not label WORLD/DSP, gTTS+DSP, or persona transforms as near-precision clones.
Near-precision requires an authorized speaker, a neural engine that actually ran,
a stored speaker embedding, identity cosine ≥ 0.82, and ≥15 seconds of clean
reference audio with quality ≥ 0.55. `speaker_identity.precision_verdict` is
the source of truth for that label.

## Quality gates
At minimum:
- Python compile/import sanity for changed modules.
- Focused unit tests for changed behavior.
- Existing voice safety, RVC training, conversion, worker, and upstream-error tests.
- No zero-byte placeholder model accepted as a real model.
- Dataset validation before expensive training.
- Deterministic error messages for missing engines/models.
- Audio output must be non-empty, finite, and decodable.
- Where fixtures permit, verify duration drift, clipping/peak, loudness, and basic pitch/prosody preservation.
- Benchmark expensive paths separately; do not turn GPU/network benchmarks into mandatory unit tests.

## Training
Use `rvc_training_cli.py` for real RVC preparation/import. Require `--i-have-permission`. Validate the dataset before launching expensive training. Prefer GPU workers (local CUDA or configured Kaggle worker) over CPU training. Training must produce a real non-trivial `.pth`; use an `.index` when available.

Never create empty `.pth` placeholders and call them trained models.

## Git discipline
Keep commits scoped and reviewable. Update README/docs whenever behavior or setup changes. Prefer a PR into `main`; do not merge while checks are failing. Generated audio, datasets, caches, virtualenvs, credentials, and model binaries belong in ignored/local/object storage.

## Definition of done
A feature is done only when the implementation, tests, documentation, runtime configuration, and failure paths agree. “Production ready” means verified by the applicable automated checks and a real end-to-end smoke test on the target runtime—not merely that code was written.
