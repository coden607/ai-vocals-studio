# Vocal-led beat arrangement

The cloned vocal is the immutable timing, pitch, dynamics and sample-rate reference.
Use the existing song/worker conversion and CLI paths. Adapt an existing instrumental;
this feature does not generate a new composition or infer musical key.

1. Add a protected mixer in song_converter.py: validate finite mono/stereo audio,
   resample/stretch only the beat, bound stretch to 0.8–1.25, duck only the beat,
   preserve every vocal frame, export floating-point WAV plus adjusted beat and audit JSON.
   Validate: compile and synthetic waveform tests, including sample subtraction.
2. Route combine_tracks and change_song through protection by default. Keep explicit
   legacy opt-out for existing callers. Skip vocal polish and lossy delivery in protected
   mode; reject failed conversion before mixing. Add CLI mix for existing cloned stems.
   Validate: pipeline regression and CLI integration tests.
3. Document limits and run CPU suite, upload tests and syntax checks. Review before PR.

Acceptance: input files unchanged; output sample rate/frame count follows vocal;
mix minus adapted beat equals decoded vocal within float32 rounding; no clipping,
silent destructive fallback, or expensive model/network test. Reject extreme duration
mismatch with an actionable error rather than distort either source.

User direction settles the master-track choice. Existing libraries supply beat-only
stretching. Same-song separation supplies an already aligned beat; automatic downbeat,
key detection and variable-tempo musical alignment are not claimed by duration conforming.
Live model quality and listening validation remain separate from synthetic verification.
