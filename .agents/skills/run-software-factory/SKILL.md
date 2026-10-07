---
name: run-software-factory
description: >-
  Build and run an autonomous software factory ("dark factory"): PRDs or
  issues go in, validated reviewed PRs come out — no human reading the
  code. Covers Dan Shapiro's 5 autonomy levels and when work graduates
  from human-in-loop (level 3, see piv-loop) to human-on-the-loop (level
  4) to full auto (level 5); the PRD→spec→slice→build/validate→PR
  pipeline; builder/validator agent separation with holdout test
  scenarios; the guidance layer (global rules / factory rules /
  mission.md); the 30-minute stateful triage cron loop; headless agent
  auth via device-code flows; blue-green deploys; escalation fail-safes.
  Use when setting up a repo that ships its own code, running a 24/7
  autonomous coding pipeline, hardening agent reliability by removing
  yourself from the loop, or deciding how much autonomy a project
  deserves. Triggers: "software factory", "dark factory", "autonomous
  coding pipeline", "issue to PR", "factory mode", "level 4/5 autonomy",
  "ship code without reviewing it", "24/7 coding agent", "PRD in PR
  out".
---

## Grok runtime

This skill is installed for Grok, not Claude Code. Follow the procedure below with these substitutions:

- Do not invoke slash commands. Name the skill and do the steps.
- `CLAUDE.md` means the repo rules file that exists (`CLAUDE.md`, `AGENTS.md`, or neither). Do not require `.claude/`.
- There are no Claude subagents. Do the step inline.
- Browser work uses the built-in browser tools. Do not require the `agent-browser` CLI.
- Desktop control is not available in this sandbox. Skip `drive-screen` steps and say so.
- GitHub work uses the connected GitHub tools.
- Jev decisions use the local `jev-gate` skill. Do not require OpenRouter `/v1/systemone`.
- Hooks cannot be registered in Grok settings. Describe the guarantee and enforce it in the current run.


# run-software-factory

A software factory is a repo that ships its own code: spec in → validated,
reviewed PR out → merged → deployed, with no human looking at the code.
This is NOT vibe coding. It is heavy engineering up front — guidance layer,
validation harness, builder/validator separation — so the loop survives
without you. The payoff: reliability-by-removal. Taking yourself out of the
loop forces you to harden the harness, which improves even your in-loop
agentic engineering.

## Positioning (read first, don't duplicate)

- **`piv-loop`** = level 3 autonomy. Human plans and validates every ticket.
  That is where most work should live. This skill is the graduation path:
  when your proven PIV loop makes YOU the bottleneck, factory mode removes
  the human gates progressively.
- **`harness-engineering`** = the generic multi-session toolbox (state files,
  handoffs, checkpoints). This skill composes those parts into one specific
  machine: the issue-to-PR factory.

## Step 0 — pick the autonomy level (Dan Shapiro's 5 levels)

| Level | Name | Who does what | Use when |
|---|---|---|---|
| 0 | Autocomplete | Human drives; agent suggests | Exploration |
| 1–2 | Assisted | Human drives; agent executes chunks | Learning the codebase |
| 3 | Pair-programmer, mostly hands-off | **Agent writes most code; human plans and validates every ticket** | Default. Most work stays here (see `piv-loop`) |
| 4 | Human-on-the-loop | Human sets direction, reviews outcomes only; loop runs between check-ins | The loop is PROVEN: validation passes consistently, failure patterns already patched into the guidance layer |
| 5 | Full auto | High-level direction only; agent makes all small decisions | Only after level 4 runs clean for a sustained period |

Rule: **level 3 until the system is proven, then graduate.** You can chain
skills into full autonomy — don't until the system is proven. Most teams
overestimate readiness and lose trust in the "productivity mirage" (code is
written fast, but fixing the agent's mistakes costs more than writing it
yourself). Trust is lost because there's no system, not because the models
are bad.

## Step 1 — decide if a project graduates to factory mode

A project qualifies when ALL are true:

1. **Ticket-shaped work** — a backlog of separable issues/PRDs, not one
   ambiguous goal. Re-architecture starts a NEW loop, not a bigger ticket.
2. **A writable mission** — you can state goals AND non-goals precisely
   enough that an agent can reject bad specs (see mission.md below).
3. **Automatable validation** — tests, lint, type-check, build, and/or E2E
   checks the agent can run and iterate against without you. If validation
   requires your judgment every time, you are the loop — stay at level 3.
4. **Proven loop** — you have already shipped several tickets through the
   manual PIV loop with the same guidance files. The factory hardens what
   already works; it does not invent it.

PoC/spiking product ideas is a legitimate factory use even today: the
output is disposable, so lower reliability is acceptable. Production
services demand the full harness below.

## Step 2 — build the guidance layer (3 files, non-negotiable)

The guidance layer is the difference between an agent with a task and a
factory with a mission. Three files, distinct audiences:

1. **`GLOBAL_RULES.md`** — loaded into EVERY session (builder, validator,
   triage). Coding conventions, repo layout, commands ("never guess a
   path"), git discipline. Keep it small — it is loaded everywhere. Update
   it from failure analysis (see Step 7).
2. **`FACTORY_RULES.md`** — stricter rules loaded ONLY in autonomous
   sessions: never force-push, never skip validation, never merge your own
   PR, never touch secrets/prod config, stop after N failed attempts and
   escalate. This is where autonomy gets its guardrails.
3. **`mission.md`** — goals + non-goals + current priorities. The non-goals
   are the killer feature: they let the agent REJECT your specs when out of
   scope. The agent corrects YOU, not just vice versa. The triage step uses
   mission.md to accept/reject/rank incoming issues.

See `references/factory-blueprint.md` for templates of all three.

## Step 3 — write holdout scenarios BEFORE building anything

Holdout scenarios are success tests written before work starts and hidden
from the builder agent — so it cannot design the app just to pass them.
This is the single highest-leverage reliability feature.

- Write them at mission-definition time, not ticket time.
- Store them where the validator can read them and the builder cannot.
- Each scenario = observable behavior ("user can X and sees Y"), not
  implementation detail.
- If a PR passes the builder's visible tests but fails a holdout, that is a
  builder-bias signal — tighten the hidden set.

## Step 4 — wire the pipeline: PRD → spec → slice → build/validate → PR

1. **Triage (gate).** Every incoming issue/PRD is compared against
   `FACTORY_RULES.md` + `mission.md`: accept / reject (out of scope per
   non-goals) / rank. Rejections post a comment explaining why — the agent
   correcting the human is working as designed.
2. **Spec.** Accepted issues get a structured spec: feature description,
   user story, problem statement, context references, files to create/edit,
   task list, and a validation strategy (unit/integration/e2e, lint,
   typecheck). The spec is a **handoff document** — it must carry everything
   a fresh implementation session needs, because context rot kills long
   sessions. A plan that requires the planning conversation is not a plan.
3. **Slice.** Split the spec into slices small enough for ONE fresh
   agent session each: one slice = one build+validate+PR cycle. Small
   slices beat big plans; one mega-prompt for many tickets fails.
4. **Build (builder agent).** Fresh session per slice. The builder gets the
   spec + slice + `GLOBAL_RULES.md` + `FACTORY_RULES.md`. It does NOT get
   holdout scenarios. It implements, runs the visible validation suite, and
   **iterates until validation passes** — optimize for correctness, not
   speed. Then it commits, opens a PR, and stops.
5. **Validate (validator agent — SEPARATE session).** The validator gets:
   the PR diff + holdout scenarios + `GLOBAL_RULES.md` + the mission. It
   does NOT get the plan, the spec, or the builder's reasoning. Run the
   visible tests AND the holdouts. Zero shared context = zero shared bias.
6. **Merge.** Validator approves → merge. Builder never merges its own PR.
7. **Deploy.** Blue-green (see Step 6).

## Step 5 — run the 30-minute triage cron loop

The factory is stateful between runs via labels/state on issues. Cron every
30 minutes, executing in strict priority order:

1. **Fix PR** — address review comments on open PRs.
2. **Review PR** — run the validator on PRs marked needs-review.
3. **Build next approved issue** — pick the highest-ranked accepted issue
   with no open PR; run Step 4.
4. **Triage new** — classify newly filed issues (accept/reject/rank).

State machine per issue: `accepted → in-progress → needs-review → merged`
(or `rejected` at triage, `blocked` on failure). The label IS the state —
the cron run reads state, acts, writes new state, exits. Stateless runs are
what make 30-minute cycles reliable.

- One job per trigger by default. Parallelism (multiple builders) is
  possible but watch rate limits and lock contention on shared files.
- Set an **escalation fail-safe**: after N failed attempts on the same
  blocker, stop and escalate to a human. Configurable to never escalate —
  that is a level-5 choice, own it explicitly.
- When a loop fails twice with the same blocker: STOP. Autonomy is not
  stubbornness.

## Step 6 — deploy blue-green

A factory that only opens PRs is a PR generator, not a shipper. Blue-green:
run two app versions (blue = live, green = standby). The factory updates
green, validates, flips traffic, and the old blue becomes the new standby.
Zero downtime, instant rollback (flip back), and the deploy itself is
verifiable by the validator agent. Even without full infra, adopt the
principle: deploy to standby, verify, switch.

## Step 7 — headless agent auth (device-code flows)

The factory runs on a server with no browser. Manual auth is the ONLY
manual step, done once:

```bash
gh auth login                # GitHub device-code flow
<agent> login --device-auth  # e.g. codex login --device-auth
<agent> exec "say hi"        # smoke test before trusting the loop
```

Pattern: whatever tool the builder/validator agents use, prefer
`--device-auth` (or equivalent device-code) flows — they are designed for
exactly this headless case. Do the auth on the machine that will run the
loop; tokens live there.

## Step 8 — harden reliability continuously

- **Fresh-factory reps.** Iterate reliability by repeatedly spinning up
  factories from scratch and building real applications with them. Each
  fresh build surfaces stale-assumption bugs in the harness itself.
- **Conversation mining.** Session transcripts (JSONL) are a goldmine.
  Periodically mine them for failure patterns (structured tables/SQL beat
  reading raw JSONL token-by-token), then patch the AI layer — rules,
  factory rules, hooks — so the same mistake can't recur. Example wins:
  "never guess a path" in global rules; a session-start hook injecting the
  live repo tree instead of a stale static layout.
- **System evolution ritual.** After every agent failure, run a sidebar:
  which rule or skill change prevents this next time? Land it as its own
  small PR referencing the ticket. The whole factory improves because the
  guidance layer is in source control.
- **Your existing code review IS the eval.** Optionally add LLM-as-judge
  scoring of rule/skill compliance on PRs.

## Anti-patterns

- Jumping to level 4/5 because the demo looked good. Graduate only on a
  proven level-3 loop.
- Letting the builder see holdout scenarios — that defeats their entire
  purpose.
- Validator sharing the builder's plan/spec context — that re-introduces
  the bias the separation was built to remove.
- One mega-ticket instead of slices — context rot eats it; fresh session
  per slice is the whole point.
- Skipping validation "because it looks right" — unvalidated progress
  doesn't count, ever.
- The agent closing its own tickets — merge/done decisions belong to the
  validator or the human, never the builder.

## Reference

`references/factory-blueprint.md` — a worked factory-setup example
(end-to-end from empty repo to 24/7 loop) plus copy-ready templates for
`GLOBAL_RULES.md`, `FACTORY_RULES.md`, `mission.md`, the issue state
machine, and the cron triage prompt.
