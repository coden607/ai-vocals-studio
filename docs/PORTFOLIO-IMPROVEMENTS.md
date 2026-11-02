# Portfolio engineering improvement backlog

Recorded: 2026-11-02. Source: 2026-11-02 portfolio review based on GitHub READMEs and repository metadata. Scores and recommendations were subjective preliminary assessments, **not** validated code audits or verified current CI results.

Tracking: ContinuityOS is coordination only; execution belongs in this repository under its own AGENTS.md and approvals. Do not confuse a planned enhancement with an implemented capability. No automatic merges, production deployment, customer messaging or destructive actions.

## P1 — Verify real audio processing
- [ ] Exercise input/upload/chunking → Demucs separation → authorized Seed-VC/RVC conversion → timing/remix → export end to end.
- [ ] Measure latency, file-size ceilings, worker resources, interruptions/retries and actual speaker similarity on authorized samples.
- [ ] Document model/checkpoint requirements and distinguish preview DSP, zero-shot conversion and separately trained voice models.
- [ ] Publish authorized before/after samples, automated checks, deployment and worker-health evidence.

## Cross-repository quality standard
- [ ] Verify repo origin/default branch/AGENTS.md and exact commit; keep worktree, credentials and PR strictly scoped.
- [ ] Choose one narrow end-to-end use case and explicit acceptance criteria; test before adding feature breadth.
- [ ] Document verified vs experimental vs planned capabilities; no unsupported production claims.
- [ ] Require exact-head CI evidence, test coverage, security and accessibility checks where applicable.
- [ ] Show a runnable demo, 60–120s walkthrough, architecture diagram, setup, limitations and personal engineering contribution.
- [ ] Seek approval before merge, deployment, destructive cleanup, external sending or paying.

## Definition of done
- [ ] Reproduce baseline issue or evidence gap, capture current commit and existing behavior.
- [ ] Create minimal repository-scoped plan (PIV): scope, risks, tests, rollback, approval tier.
- [ ] Implement in reviewable PR(s), verify tests and demo against the exact branch HEAD.
- [ ] Record results, source URLs and evidence; mark unknowns **UNVERIFIED**.
- [ ] Obtain explicit user approval before merging or changing live systems.

## Priority
Fix credibility and reproducible vertical slices before adding more features. Apply canonical coden607/skills, smallest relevant skills, token efficiency and JEV routing when available; otherwise note unverified routing.
