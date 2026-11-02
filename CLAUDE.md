Shared agent rules and skills live in [AGENTS.md](AGENTS.md). Read that before editing.

# CLAUDE.md — AI Vocals Studio

Consent-first neural vocal studio: Demucs separation → authorized voice conversion (RVC primary) → vocal-led remix → QA. AGENTS.md holds the non-negotiable rules (consent gate, no silent DSP fallback, studio/pro fail closed). This file is the working runbook.

## Entry points (what is actually production)

| Path | Role |
|---|---|
| `clone_any_voice.py` | **Production CLI.** Use `--quality-target draft\|studio\|pro` and `--i-have-permission`. |
| `song_pipeline_cli.py render` | Full-song render (Demucs → convert → vocal-led mix). |
| `supabase_worker.py` | Queue worker. Supabase mode needs `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`; otherwise local mode via `LOCAL_STORAGE_DIR`. |
| `vercel_frontdoor/` | Vercel static page + `api/*.js` (upload tickets, queue, capabilities). Root dir on Vercel is `vercel_frontdoor`. |
| `speaker_identity.py` | Identity gate. The only number that may be called clone accuracy. |
| `rvc_training.py` / `rvc_training_cli.py` | Dataset gate and RVC training. |
| `app_minimal.py`, `app_modern.py`, `app.py` | Tkinter/legacy UIs. `app_minimal.py` is DSP/persona only, never a clone. `CODEMAP.md` is legacy and describes these. |

## Setup and checks

```bash
python3 -m venv venv && venv/bin/pip install pytest numpy soundfile librosa pydub requests scipy resemblyzer demucs
venv/bin/python -m pytest -q          # 75 tests, ~25 s, CPU only
node test_upload_contract.cjs         # 23 frontdoor upload tests
```

CI is `.github/workflows/ci.yml` (Python 3.11, gitleaks). Do not merge red checks.

## RVC sidecar (required for any real clone)

RVC runs in a separate **Python 3.10** venv at `venv_rvc_engines/` (fairseq breaks on 3.11+). `install_voice_engines.sh` builds it when `uv` is present:

```bash
uv python install 3.10 && uv venv --python 3.10 venv_rvc_engines
uv pip install --python venv_rvc_engines/bin/python "setuptools<81" wheel pip
uv pip install --python venv_rvc_engines/bin/python -r requirements_rvc_sidecar.txt --extra-index-url https://download.pytorch.org/whl/cpu
```

Gotchas learned the hard way:
- The sidecar must use `torch<2.6`. With newer torch, fairseq's HuBERT load fails and the pipeline falls back to DSP with `'tuple' object has no attribute 'dtype'`. This is pinned in `requirements_rvc_sidecar.txt`.
- `.rvc_engine_sidecar` is tracked in git and points at `venv_rvc_py310_engines/`, which usually does not exist. The code then falls back to `venv_rvc_engines/bin/python`. Override with `VOICE_ENGINE_SIDECAR`.
- The voice model lives at `models/voices/<name>/rvc_model.pth` (gitignored). Never commit `.pth`, datasets, or audio.
- A studio run needs reference audio of 15 s or more and a neural engine. A DSP result must exit non-zero.

## Test voices (legal only)

Do not use celebrity voices or acapellas. For plumbing tests use a licensed model, such as the VCTK-trained RVC voices at Hugging Face `Nekochu/RVC-VCTK_Voice-sample` (VCTK is CC BY 4.0; credit it). Base pretrained weights (`lj1995/VoiceConversionWebUI`) are not a speaker and cannot pass the studio gate.

## Local end-to-end recipe (no Supabase, no Vercel)

1. Queue a job through the real handler in local mode: import `vercel_frontdoor/api/queue-job.js` with `LOCAL_STORAGE_DIR=<dir>` set and no Supabase env, POST a small inline voice sample (under 3 MB) and target.
2. Run the worker: `LOCAL_STORAGE_DIR=<dir> python supabase_worker.py --once --work-dir <work>`.
3. Confirm the job in `<dir>/jobs.json` is `complete` and the output exists. Report the engine used and the verdict. Do not call a WORLD/DSP result a clone.

## Deployment and environment

- Live site: https://ai-vocals-studio.vercel.app/ . Vercel project root directory is `vercel_frontdoor`.
- Large (direct, resumable) uploads need Supabase Storage and a bearer token. The server reads **`UPLOAD_ACCESS_TOKEN`** (falls back to `ELEVENLABS_API_KEY`). The variable name must be exact; a differently named variable is ignored and uploads return 401. Env var changes apply only to new deployments.
- Limits: 512 MB per file, 1 GB and 7 files per upload batch (`upload-ticket.js`), 5 MB request body on `queue-job.js`. Supabase's free plan likely caps files lower; check its pricing page.
- `GET /api/capabilities`, `/api/storage-health`, `/api/jobs` are public read endpoints for smoke checks.
- Jobs sit at `queued` until a worker runs: `scripts/run_supabase_worker.sh` with the Supabase service-role key (secret; never commit or paste into logs).
- ElevenLabs is optional. Free/local alternatives already in the repo: Qwen3-TTS, XTTS v2. ElevenLabs voice samples are sent as multipart field `files`.

## Git workflow

Work on a feature branch and open a PR into `main`. Commits end with the attribution lines from the session. In this environment `GH_TOKEN` is often invalid, but git push through the session proxy works, and PRs can be opened with `gh api repos/Coden607/ai-vocals-studio/pulls` (GraphQL is blocked). The stop hook can report phantom "unpushed" commits when the local `origin/<branch>` ref is missing; fix with `git fetch origin <branch>:refs/remotes/origin/<branch>`.

## Definition of done

Implementation, tests, docs and runtime config agree, and a real smoke run on the target runtime passed. If something was not run, say "unverified".
