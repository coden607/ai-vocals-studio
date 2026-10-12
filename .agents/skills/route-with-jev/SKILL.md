---
name: route-with-jev
description: >-
  Route decisions through Jev (typesafe/jev-1.13, the "system-one" decision
  model) via OpenRouter's /v1/systemone endpoint, instead of spending LLM
  calls on classification, routing, and guardrails. USE when: (1) routing a
  task, ticket, PR, or user query to a model tier or pipeline before invoking
  an expensive LLM (see workspace/orchestration/models.yaml tiers); (2) adding
  a pre-tool-use guardrail hook (is this action exposing secrets? destroying
  data? exfiltrating? off-task?) with near-zero false positives; (3) a loop
  needs fast repeated next-action decisions (browser automation, gameplay
  testing, workflow classification); (4) replacing regex/keyword classifiers
  with calibrated probability decisions. Trigger phrases: "route with Jev",
  "Jev classify", "model tier", "Jev guardrail", "decision endpoint",
  "system one", "cheap routing layer". DO NOT USE for: text generation,
  reasoning, creative writing, multi-step analysis, or anything a simple
  function/regex does cheaper — Jev decides, it does not think or write.
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


# Route With Jev

Make cheap, fast, calibrated decisions with Jev (`typesafe/jev-1.13` on
OpenRouter) so expensive LLM calls only fire where they earn their tokens.

## The Iron Rule: Never Jev Alone

Jev is a system-one decision model. It generates decisions — not text, not
reasoning, not code. Every Jev call lives inside an LLM sandwich:

```
LLM builds the harness  →  Jev decides  →  LLM acts on the decision
```

1. **LLM builds the harness.** The LLM writes the state serializer, the typed
   questions, the thresholds, and the action mapping. This is one-time design
   work — reasoning work, which is LLM territory.
2. **Jev decides.** Given state + multiple-choice questions, Jev returns a
   calibrated probability per question in ~0.2s.
3. **LLM acts.** The LLM (or plain code) executes the chosen branch, then
   handles anything Jev flagged — review, block, escalate.

If you find yourself wanting Jev to "explain why," stop. That is a hint the
question belongs to the LLM layer, or the state doesn't contain the answer.

## When to Offload a Decision to Jev

Offload when ALL of these hold:

- **Multiple-choice.** The answer space is a small fixed set (yes/no, tier
  names, next actions). If the answer is open-ended prose, use an LLM.
- **Repeated or latency-sensitive.** The decision fires per tool call, per
  tick (60fps gameplay), per incoming item, or per loop iteration where an
  LLM call (seconds, whole cents) is untenable.
- **Judgment, not computation.** The decision needs semantic understanding
  (is this destructive? is this off-task?) — too fuzzy for regex, too cheap
  for an LLM.
- **Calibrated thresholds help.** You act on confidence (`block if p > 0.8`),
  which requires Jev's calibrated probabilities, not vibes.

Use plain code (not even Jev) when the rule is exact and enumerable — a
deterministic check (path prefix, command name) is free and cannot drift.

## Cost Discipline

Internalize these numbers before designing anything:

- **Jev pricing (1.13):** ~$0.042/M input tokens; **output is free**.
- **A Jev decision call costs roughly 1/1000th of an LLM call.** Dozens of
  routing decisions run about $0.004 total. The logged end-to-end pipeline
  test classified a task at 97% confidence for $0.0000168.
- **Input is the only meter.** Keep state compact — a Jev call fed a bloated
  state stops being "practically free."
- **Routing saves more than it spends.** Mis-tiering costs $2–$50/M tokens of
  LLM overkill. One $0.000017 Jev call per job pays for itself on the first
  prevented over-tier.

Grade non-trivial routed jobs in `workspace/orchestration/outcomes.jsonl`
(skip chitchat/simple). Two consecutive grades < 3 on the same task_type →
raise that task_type's tier permanently. Steve can pin any task_type to any
tier — human override beats the loop.

## State Design

State is the situation description Jev scores. Design it like a brief for a
fast reader, not a dump for a database.

- **Include:** the minimum facts that determine the answer. For hooks: tool
  name, input args, cwd, current objective. For routing: the raw query/ticket
  text plus task hints (source, labels, size).
- **Cut:** logs, full file contents, history, anything not load-bearing for
  the questions. Every token is billed input.
- **Keep it structured when cheap:** a short JSON or labeled lines parse
  better than a wall of prose. `jev_decide.py` accepts `@file.json` for
  structured state.
- **Write questions against the state you actually send.** If the question
  needs a fact missing from state, the calibration is fiction. Fix the state,
  not the threshold.

## Typed Questions

Jev answers three question types, each as a calibrated probability:

| Type | Meaning | Criteria shape | Example |
|---|---|---|---|
| `noul` | yes/no probability 0..1 | none (or guidance) | "Is this action exposing secrets?" |
| `choice` | pick one option | `{option: definition}` map | tier selection across 8 tiers |
| `score` | level on ordered scale | ordered list of level descriptions | urgency 1–5 |

Rules for good questions:

- **One decision per key.** "Which tier?" is a `choice`. "Is it urgent AND
  which tier?" is two questions. Jev answers each in parallel — split them.
- **Write definitions into the criteria.** A `choice` with bare option names
  forces Jev to guess your taxonomy. One line of definition per option fixes
  drift across domains — this is what makes Jev general where task-specific
  classifiers aren't.
- **Set thresholds before you see answers.** Decide "block if p > 0.8" up
  front. Tuning thresholds to observed outputs defeats calibration.

## Calling Jev

Use the existing bridge — do not re-implement the client:

```
/root/.openclaw/skills/youtube-learn/scripts/jev_decide.py
```

```bash
# Key resolution: $OPENROUTER_API_KEY → ~/.config/jev/api_key → workspace/.jev_key
jev_decide.py --state "Convert this bash script to PowerShell" \
  --questions '{"tier": {"type": "choice", "instructions": "Which model tier should handle this?", "criteria": {"simple": "extraction/rewrite", "code": "patches/scripts", "reasoning": "analysis/planning"}}}'

jev_decide.py --state @ticket.txt --questions @qs.json   # file-based
jev_decide.py --selftest                                   # verify the key
```

It POSTs `{model, state, questions}` to `https://openrouter.ai/api/v1/systemone`
(model `typesafe/jev-1.13`) and prints the full response JSON: `answers` +
`usage` (including cost) + confidence scores. Exit codes: 0 ok, 3 bad
input/missing key, 4 API error — wire 3/4 to fail-closed in guardrails.

## Worked Patterns

Full annotated examples (hook guardrail, tier router, PR triage, browser
loop, anti-pattern teardowns) live in `references/examples.md` — read it
before implementing a new pattern. Summary:

1. **Hook guardrail.** Pre-tool-use hook sends `{tool_name, args, cwd,
   objective}` as state; four `noul` questions (secrets? destruction?
   exfiltration? off-task?); block the tool call if any returns true above
   threshold. Replaces regex hooks with near-zero false positives at a
   fraction of a penny per call. Fail closed on API error.
2. **Tier router.** Task text as state; one `choice` question over the tier
   names defined in `workspace/orchestration/models.yaml` (simple/chitchat/
   reasoning/code/research/long-doc/creative/frontier), each option defined
   by its `when:` line. Log the decision to outcomes.jsonl, grade the job,
   let the feedback loop move tiers.
3. **Intake triage.** Issue/PR text as state; `choice` for work type
   (bug/feature/docs), `noul` for "needs human review" — routes to review
   depth before any LLM work happens.

## Alignment With Steve's Stack

- **Tier map:** `workspace/orchestration/models.yaml` is the single source of
  truth for tier names and their `when:` conditions. Quote those conditions
  verbatim as `choice` criteria so routing and the map can never drift apart.
- **Learning loop:** `workspace/orchestration/outcomes.jsonl` records graded
  routed jobs; the feedback rules (retry one tier up on grade < 3; bump the
  task_type after two bad grades) close the loop.
- **Review cadence:** models.yaml is refreshed monthly — the model market
  rots. Jev questions that name model tiers must be re-checked then.

## Anti-Patterns

- **Jev alone.** No harness, no acting layer. Jev is the middle of the
  sandwich, never the meal.
- **Free-text questions.** Jev scores fixed options; "summarize this" and
  "what should we do here?" are LLM calls.
- **Bloated state.** Pasting logs or whole files into state burns the one
  meter Jev charges on. Ship the deciding facts only.
- **Regex-grade determinism.** If a rule is exact (path == `/etc/passwd`),
  code it. Jev is for judgment, not string matching.
- **Threshold tuning after peeking.** Setting cutoffs from observed answers
  destroys calibration and re-imports the bias you offloaded Jev to remove.
- **Silent failure.** Jev returning low confidence everywhere usually means
  state/questions mismatch — the state doesn't contain what the questions
  ask. Log and inspect; don't just lower thresholds.
- **Frontier tokens on banter.** Not Jev-related, but same disease: never
  route casual conversation to expensive tiers. chitchat tier exists.

## Resources

- `references/examples.md` — worked examples with config snippets: hook
  guardrail, tier router, intake triage, browser automation loop, and
  anti-pattern teardowns.
