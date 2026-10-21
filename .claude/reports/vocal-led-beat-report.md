# Vocal-led beat implementation

Plan: `.claude/plans/vocal-led-beat.md`
Branch: `feat/vocal-led-beat-20261021`

Implemented protected mixing, beat-only resampling/stretching/ducking/headroom,
floating-point exports and audit metadata. Song replacement/worker calls inherit
protection through change_song; render inherits it through combine_tracks. A new
CLI mix command accepts completed cloned stems. Conversion failures now stop before
mixing. Existing input files remain unchanged.

Validation: whole-repo compile succeeded; full CPU suite 58 passed (7 warnings);
upload contracts 23 passed; CLI help and synthetic CLI mix succeeded; diff whitespace
check passed. Tests verify recovered vocal samples, full duration, sample rates,
stereo behavior, beat pitch preservation, failure paths and production integration.
Local Python 3.12 / librosa 1.0.0. GitHub Python 3.11 checks pending.

Review: explicit legacy mixer opt-out retained; duration bounds fail closed; vocal
gain rejected rather than silently ignored. Hashing is streamed for large audio and
Python 3.10 compatibility. No new dependencies or input/model fixtures committed.

Scope/limits: duration conforming assumes aligned starts; musical-key matching,
downbeat inference, variable-tempo warping, new beat composition and listening/model
quality are not implemented or claimed. Existing unrelated PR failures are not fixed
by this change. No production deployment or merge. No live GPU/API runs.

Intentional behavior changes: protected vocals bypass envelope polish and lossy
source-matched delivery. Nonzero vocal gain must use explicit legacy mode. Synthetic
tests replace production listening validation only for measurable preservation,
not artistic quality.
