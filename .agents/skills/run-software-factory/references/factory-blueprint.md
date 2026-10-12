# Factory Blueprint — Worked Example + Templates

Grounded in Cole Medin's dark-factory builds (DynaChat, built end-to-end by
a factory without a human reading a line of its code; 24/7 VPS deployment
running Codex/GPT-6 Astra under Archon workflows). Adapt names/commands to
your stack — the structure is the invariant.

---

## Part 1 — Worked setup example: "DynaChat-style" factory from empty repo to 24/7 loop

**Goal:** an AI tutor app grounded in existing content, built and shipped
entirely by the factory.

### Phase A — foundations (human does this once, by hand or with a coding agent)

1. **Empty repo + guidance layer.** Create the repo. Write the three
   guidance files (templates in Part 2). This is the human's main creative
   act — everything downstream is mechanical.
2. **Validation harness.** Standing test suite (`make test` / `npm test` /
   `pytest` — whatever the stack), lint, typecheck, build. The factory
   cannot iterate against validation that doesn't exist. Add the CI
   workflow that runs the suite on every PR.
3. **Holdout scenarios.** Write 5–10 observable-behavior scenarios BEFORE
   any ticket exists ("a learner asks X and receives an answer that cites
   the source video"; "empty question yields a helpful prompt, not a
   crash"). Store in `/holdouts/` — validator sessions mount it, builder
   sessions must not.
4. **Deploy scaffolding.** Blue-green pair (even if just two processes on
   one VPS behind a flip script). The factory will target green only.

### Phase B — first slice through the manual loop (prove the loop at level 3)

5. Write ONE real issue: "Serve a static landing page at /".
6. Run it through the full pipeline by hand: triage → spec → slice →
   builder session → validator session → merge → blue-green flip.
7. Fix what broke — in the guidance files, not just the code. This is the
   system-evolution ritual; do it now, small, before autonomy amplifies
   every flaw.

### Phase C — graduate (human-on-the-loop, level 4)

8. **Headless auth on the host that will run the loop:**
   ```bash
   gh auth login                # GitHub device-code flow
   <agent> login --device-auth  # device flow for the coding agent
   <agent> exec "say hi"        # smoke test — no smoke, no factory
   ```
9. **Install the cron triage loop** (every 30 min), implementing the
   priority order: fix PR → review PR → build next → triage new. The cron
   job reads issue labels as state, acts, writes new labels, exits.
10. **End-to-end test:** file a test issue ("Add a /health endpoint").
    Watch it flow: triage accepts → builder opens PR → validator runs
    visible tests + holdouts → merge → green updated → flip → live.
11. **Go 24/7.** File real issues. Human reviews outcomes at whatever
    cadence the mission demands (daily at first).

### Phase D — level 5, only when earned

12. After sustained clean level-4 runs, widen the mission.md scope, raise
    the escalation threshold (or set "never escalate" explicitly), and let
    small decisions (naming, structure, test coverage, refactors) belong to
    the agent. You now steer with direction only.

---

## Part 2 — Templates

### GLOBAL_RULES.md (loaded in EVERY session — builder, validator, triage)

```markdown
# Global Rules

## Repo layout
- App code: `src/` — tests: `tests/` — docs: `docs/`
- Never guess a path. Search or list before referencing files.

## Commands
- Test: `make test`  Lint: `make lint`  Typecheck: `make typecheck`
- Build: `make build`
- All four must pass before any PR is opened.

## Git discipline
- Branch per issue: `factory/<issue-number>-<slug>`
- Conventional commits. No force-push. No direct pushes to main.

## Style
- Match existing conventions. Smallest change that satisfies the spec.
- Comment WHY, not what. No dead code, no debug prints.
```

### FACTORY_RULES.md (autonomous sessions only — the guardrails)

```markdown
# Factory Rules (autonomous mode)

## Hard stops (escalate to human)
- After 3 failed validation attempts on the same slice.
- Any change to secrets, CI config, deploy scripts, or holdout files.
- Any command that would delete data or force-push.

## Never
- Merge your own PR.
- Skip or weaken a test to make it pass.
- Add dependencies not justified in the spec.
- Touch `main` directly.

## Always
- Run the full visible validation suite; iterate until green.
- Open a PR and stop — do not merge.
- Report blockers as a PR comment and halt.
```

### mission.md (the mission the factory defends — includes NON-goals)

```markdown
# Mission: <product one-liner>

## Goals
- <Goal 1 — the problem being solved>
- <Goal 2 — who it's for>
- <Goal 3 — what "working" means observably>

## Non-goals (the factory may REJECT specs that require these)
- <Explicitly out of scope 1 — e.g. "no multi-tenancy">
- <Out of scope 2 — e.g. "no mobile app; web only">
- <Out of scope 3 — e.g. "no paid billing in v1">

## Current priorities
1. <Priority now>
2. <Next>

## Definition of done (per issue)
- Visible validation suite green; holdouts green; deployed to green and
  flipped without downtime.
```

### Issue state machine (labels = state between 30-min cron runs)

```
rejected          (triage: violates mission non-goals — comment explains why)
accepted          (triage: ranked and ready)
in-progress       (builder session running)
needs-review      (PR open, waiting for validator)
blocked           (failed attempts / waiting on human)
merged            (validator approved, deployed)
```

### Cron triage prompt (runs every 30 minutes, in priority order)

```text
You are the factory triage cron. Read issue labels as state. Execute ONLY
the first applicable step, in this priority order:

1. FIX PR       — an open PR has review comments → builder addresses them.
2. REVIEW PR    — an issue labeled needs-review has an open PR → run the
                  validator (fresh session: diff + holdouts + global rules +
                  mission; NO plan/spec/builder context).
3. BUILD NEXT   — highest-ranked accepted issue with no PR → run the
                  builder (fresh session: spec + slice + global rules +
                  factory rules; NO holdouts).
4. TRIAGE NEW   — unlabeled issues → accept/reject/rank per FACTORY_RULES +
                  mission.md (non-goals ⇒ reject with explanatory comment).

After acting, update labels to the new state and exit. Never do two steps
in one run. Never merge: validator approves, human-or-policy merges per
FACTORY_RULES.
```

### Builder session prompt skeleton

```text
You are the BUILDER. Inputs: this issue's spec + assigned slice +
GLOBAL_RULES.md + FACTORY_RULES.md. You do not have access to holdout
scenarios — do not ask for them. Implement the slice, run the full visible
validation suite, and iterate until it passes. Optimize for correctness,
not speed. Then commit on a factory branch, open a PR describing what
changed and how it was validated, and STOP. Do not merge. Do not alter
tests to pass.
```

### Validator session prompt skeleton

```text
You are the VALIDATOR. Inputs: the PR diff + holdout scenarios +
GLOBAL_RULES.md + mission.md. You receive NO plan, spec, or builder
reasoning — judge only what the diff does. Run the visible suite AND the
holdout scenarios. Approve only if both pass and the change serves the
mission. Post one review comment: verdict + evidence (what you ran, what
passed, what failed).
```
