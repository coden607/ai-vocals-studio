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

Pacaveli is an authorized project voice per the project owner. Training audio still stays outside Git; model artifacts should live in configured object/model storage. Do not train Pacaveli on the 2Pac acapellas in `dataset/`.

## Engine strategy
- **RVC**: primary path for singing/rap voice conversion when a trained authorized model is available.
- **Qwen3-TTS**: rapid reference cloning / speech generation where supported.
- **XTTS v2**: local TTS/reference-cloning sidecar option.
- **ElevenLabs**: optional hosted cloning/TTS provider; never make local operation depend on it.
- **Demucs**: stem/vocal separation before conversion when input is a mix.
- **WORLD/DSP/persona transforms**: explicit preview/fallback only; never label them as a trained clone.

Engine selection should be capability-based and deterministic. Report selected engine, model/profile, elapsed time, input/output duration, and failure/fallback reason without logging secrets or raw private audio.

Headline quality is speaker identity from `speaker_identity.py`, not median pitch, a 16-band envelope, or RMS. Those stay in `legacy_heuristic` and must not be reported as clone accuracy. Acoustic fingerprints cannot pass draft, studio, or pro. Studio and pro fail closed when the engine is WORLD/DSP or gTTS.

## Production pipeline
Preferred song workflow:
`ingest -> validate -> separate vocals if needed -> normalize/clean -> select authorized voice -> RVC conversion -> preserve timing/prosody -> loudness/peak guard -> remix -> QA -> export`.

Reference/TTS workflow:
`authorized reference -> validate -> Qwen3-TTS/XTTS/hosted provider -> QA -> export`.

## Quality gates
At minimum:
- Python compile/import sanity for changed modules.
- Focused unit tests for changed behavior.
- Existing voice safety, RVC training, conversion, worker, and upstream-error tests.
- No zero-byte placeholder model accepted as a real model.
- Dataset validation before expensive training (`rvc_training.validate_training_dataset`: at least 3 files, 90 seconds, quality >= 0.55, clipping <= 0.5%).
- Deterministic error messages for missing engines/models.
- Audio output must be non-empty, finite, and decodable.
- Where fixtures permit, verify duration drift, clipping/peak, loudness, and basic pitch/prosody preservation.
- Benchmark expensive paths separately; do not turn GPU/network benchmarks into mandatory unit tests.

## Training
Use `rvc_training_cli.py` for real RVC preparation/import. Require `--i-have-permission`. Validate the dataset before launching expensive training. Prefer GPU workers (local CUDA or configured Kaggle worker) over CPU training. Training must produce a real non-trivial `.pth` (>10 KB); use an `.index` when available.

Never create empty `.pth` placeholders and call them trained models. `models/Pacaveli/checkpoint.json` is metadata, not a model.

## Skills
Load the matching skill before the task. Do not paste skill bodies into this file. Skills live in the agent skill directory; if a named skill is missing, follow the procedure named here.

| When | Skill | Do |
|---|---|---|
| Starting a session on this repo | `prime-codebase` | Map entry points before editing. Production CLI is `clone_any_voice.py`. Training gate is `rvc_training.py`. Identity gate is `speaker_identity.py`. |
| Backend-only change | `prime-backend` | Stay in engines, workers, and CLIs. Do not load Tkinter app code unless the task touches it. |
| UI-only change | `prime-frontend` | `app_minimal.py` is the light default and is DSP/persona, not a clone. Do not describe it as near-precision. |
| New feature or ticket | `piv-plan-implementation` then `piv-implement` | Plan against the real files, then implement with a test at each step. |
| Bug with a GitHub issue | `piv-investigate-issue` then `piv-implement-issue` | Root cause with evidence before a patch. |
| Ready to commit | `piv-commit` | One conventional commit. Never include datasets, `.pth`, wavs, or secrets. |
| Ready for review | `piv-create-pr` then `piv-review-pr` | PR into `main`. Do not merge red checks. |
| Review findings | `piv-fix-review-findings` | Fix chosen findings with tests; defer the rest in the PR. |
| Before commit or PR | `piv-validate` | `python -m compileall` on changed modules, then the focused test file. |
| Rules feel stale | `rules-check-drift` | Update this file only when a rule would cause a mistake if left false. |
| Same vocal procedure prompted again | `skills-create` | Bank it as a repo skill under `.agents/skills/<name>/SKILL.md` and add one row to this table. |
| Route or confidence gate | `jev-gate` | Use it to pick retry vs stop vs ask. Do not use it to draft audio claims. |
| Mid-task new request | `route-interrupts` | Fold steering into the current task. Queue a new task. Stop only on an explicit halt. |

Studio procedures an agent must run without a separate skill file:

- **Test a voice.** Require `--i-have-permission`. Use an authorized or public demo reference, never a celebrity acapella. Run `clone_any_voice.py` at `--quality-target studio`. A DSP result must exit non-zero. Draft may write audio only if the report verdict is `not_a_clone` or `draft` and the log does not call the legacy heuristic accuracy.
- **Train Pacaveli.** Clean authorized vocals only. `python rvc_training_cli.py --voice-dir models/voices/pacaveli --dataset <clean-dir> --epochs 300 --i-have-permission`. Reject a dataset that fails the readiness report. Register only a real `.pth`.
- **Claim near-precision.** Only if `speaker_identity.precision_verdict` returns `near_precision`: neural engine, identity >= 0.82, reference >= 15s, reference quality >= 0.55, and the identity backend is neural. Otherwise say what failed.

## Git discipline
Keep commits scoped and reviewable. Update README/docs whenever behavior or setup changes. Prefer a PR into `main`; do not merge while checks are failing. Generated audio, datasets, caches, virtualenvs, credentials, and model binaries belong in ignored/local/object storage.

## Definition of done
A feature is done only when the implementation, tests, documentation, runtime configuration, and failure paths agree. “Production ready” means verified by the applicable automated checks and a real end-to-end smoke test on the target runtime—not merely that code was written.


## Shared agent skills
Before substantive work, consult the shared skill catalog at https://github.com/coden607/skills and apply every relevant skill automatically. Treat that repository as the canonical cross-agent skill source; do not require the user to ask for a skill by name. Preserve this repository's own project rules and use them when they are more specific.

Compatibility: Codex/OpenAI-compatible agents use AGENTS.md directly. Claude, Gemini, Copilot, Kimi, Grok, and other coding agents should treat this section and coden607/skills as shared guidance whenever their environment can read repository instructions or GitHub. Never claim a skill, MCP, hook, CLI, or external tool is available unless it is actually installed/accessible in the current runtime.

## Vendored skills
Skills are copied from https://github.com/coden607/skills (there is no `coden697/skills`) into `.agents/skills/<name>/SKILL.md`. Read that file before the matching job. Do not invent a slash command.

Core skills to apply on this repo:
- `route-interrupts`: a new request mid-task is steering, a side question, or a queue item. Stop only on an explicit halt.
- `isolate-agent-runs`: do not train, delete datasets, or push model binaries from an unattended run. No celebrity acapellas.
- `enforce-with-hooks`: studio/pro must fail closed in code, not only in a prompt. The gate is `speaker_identity.py`.
- `maintain-second-brain`: project facts that can go stale live in memory as state; merge SHAs and test results are events.
- `route-with-jev` and `jev-gate`: use them to pick retry, stop, or ask. Do not use them to draft a clone claim.
- `run-software-factory` and `build-dark-factory`: a song or clone change still needs the focused test before a PR.
- `compress-token-spend`: read the file you will edit, not the whole tree.
- `legal-war-room`: use only for a real filing or consent question. It does not authorize a voice.

Song render uses `song_pipeline_cli.py render`. That command is local until GitHub auth can push `song-verse-render`.
