# Stale branch audit (2026-11-02)

Checked every remote branch against the current `main` tree. A commit counts as unused only when its change is not already present. Later edits often stop an old patch from applying in reverse even after the feature landed.

## Recovered in this PR

| Commit | Branch | What was missing | Action |
|---|---|---|---|
| `b9bc6ab` | `precision-speaker-id` | Empty speaker name was accepted by `validate_voice_clone_request` | Restored the name check and covered it in `test_voice_safety.py` |
| `c8ebf1a` | `streamlit-cloud-free` | Hosted app warning did not forbid unauthorized celebrity or private-person clones | Warning restored in `streamlit_cloud/app.py` and `app_streamlit.py` |

`streamlit-cloud-free` has no merge base with `main`. This branch records that history with `merge -s ours` so the commits stay reachable without taking its `__pycache__` file. The other commit on that branch, `93ecc70`, is the same hosted app already under `streamlit_cloud/`.

## Already on main

These commits did not reverse-apply exactly, and the current tree already has the behavior:

- `92e62c0`, `d01b877`, `81face5`, `ad8f887`: verse report, `match`, and `render-multi` are in `song_pipeline_cli.py`.
- `c9bad55`, `3ceffc9`: frontdoor UX and job controls were rebuilt on `main`. `vercel_frontdoor/index.html` is newer than the old branch.
- `93e5f07`: neural song replacement landed as `#67`.
- `1f095c4`: Ubuntu 24.04 browser-image pin is in `.github/workflows/full-quality.yml`.
- `f6f93b1`, `4219f9e`: `speaker_identity.py` on `main` is the later module.
- `2624b7b`, `6359d46`: speaker-identity `__main__` runner and `.gitleaks.toml` are present. The Twilio rule on `main` is `(?i)\bAC[a-f0-9]{32}\b`.
- `4133fc1`, `229249c`: voice-clone package is on `main`. The old pin that disabled the RVC extra was not copied over the current `pyproject.toml`.
- Dependabot commits `8056338`, `c66944d`, `6334ffa`, `b986d58`, `b532b18`: pins on `main` are `soundfile>=0.14.0`, `gTTS>=2.5.4`, `elevenlabs>=2.74.1`, `streamlit>=1.65.0`, `librosa>=0.11.0`.

## Rejected

| Commit | Reason |
|---|---|
| `6fc47d3` | Lowers numpy, Pillow, requests, and pyworld below the pins already on `main`. |
| `03fe6fa` | Deletes near-precision assertions from the clone pipeline smoke test. |

## Kept branch

`gh-pages` (`4530c7a`) is the live GitHub Pages source for https://coden607.github.io/ai-vocals-studio/. It is not a stale feature branch. Deleting it would unpublish the site. Its `index.html` is an older, smaller copy of the frontdoor, not a missing app feature.
