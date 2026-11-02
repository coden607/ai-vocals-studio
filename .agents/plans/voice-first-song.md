# Voice-first one-click song replacement

User direction: use the selected authorized voice, one action, adapt instrumental to the cloned vocal, retain honest identity claims. PR67 merged as 32ac722.

Architecture: retain `change_song` and its protected mixer. Add optional quality selection before remix; the desktop button seeks near-precision, returning the best verified Studio candidate when that goal is unmet, as requested in the user clarification. Explicit Pro remains fail-closed. Existing callers retain current defaults. Evaluate bounded RVC retrieval candidates without changing pitch, duration, or speaker. Forward retrieval settings through the sidecar. Reuse speaker_identity gates and write a quality report for failures as well as successes. Never publish a completed song when the requested gate fails. Keep original cloned vocal bytes unchanged through remix; existing instrumental resampling/stretching/ducking/headroom remains authoritative. A source-song instrumental already shares the melody's key; do not invent an automatic key shift.

Tasks:
1. Test candidate ranking, audio rejection, and failed-quality blocks remix.
2. Implement bounded RVC candidate evaluation and optional quality contract.
3. Wire single desktop action and CLI to that contract; show selected engine and quality result.
4. Measure real licensed p226 output; preserve truthful failure if .82 is unmet.
5. Compile, focused tests, full Python/Node tests, PR and CI. Never commit model/audio/private reference.

Validation: pytest test_song_quality.py test_song_pipeline_production.py test_vocal_led_mix.py test_rvc_engine_runtime.py; full pytest; node --test test_upload_contract.cjs; actual authorized CPU render and identity report.

No open product questions: user explicitly requires high fidelity and instrumental-only adaptation. Identity threshold is evidence, not a guarantee of perceptual indistinguishability. Future merge requires human instruction.

Implemented validation: real three-candidate CPU run completed in 172.71s; .75/.5/1 retrieval gave .7777/.7641/.7887 identity. Best selection was index1, Studio; near-precision unmet and disclosed. Protected mixer report records vocal_modified=false. Unit tests cover strict Pro rejection before remix, best Studio selection, clipped audio rejection, repeated-run stale isolation, and unchanged vocal samples. Explicit reference quality and exclusively neural comparisons are now required by near-precision.
