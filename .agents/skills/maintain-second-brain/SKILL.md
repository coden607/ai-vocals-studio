---
name: maintain-second-brain
description: >-
  Classification and audit layer for the second-brain memory stack:
  MEMORY.md + memory/YYYY-MM-DD.md + learning/*-knowledge-base/. Classifies
  each new fact as STATE (replaceable current truth — overwrites stale
  values) or EVENT (timestamped history — append-only), triages it to the
  right tier, detects contradictions between upfront memory and KB pulls,
  runs anti-rot audits, and promotes/demotes knowledge between tiers. Use
  when the user says "remember this" or shares a new fact; when MEMORY.md
  and a KB page disagree; when knowledge feels stale or contradictory; for
  "audit my memory", "audit the knowledge base", "second-brain audit",
  "clean up / curate memory", "is this still true?"; before bulk KB
  ingestion; or when unsure which tier a fact belongs in. Complements
  agent-memory (which owns reflection timing) — this skill owns the HOW:
  classification, contradiction reconciliation, audit procedure.
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


# Maintain Second Brain

Append-only memory rots. Every incoming fact must be classified **state vs
event** and written so stale values get REPLACED, not accumulated. A
convention like "date everything" gets ~8% compliance; a mandatory
classification step gets 100%. Framework beats convention.

Relationship to `agent-memory`: that skill decides WHEN to reflect and
promote (heartbeat/stop-hook loop). This skill decides HOW: the
classification call, the tier routing, the contradiction reconciliation, and
the audit sweep. Run them together, never as duplicates.

## The stack (Steve's layout)

| Tier | Path | Class | Write rule |
|---|---|---|---|
| Daily log | `memory/YYYY-MM-DD.md` | Event log | APPEND timestamped lines. Never edit history. |
| Curated memory | `MEMORY.md` | Living state | REPLACED in place. Current truth only, one line per fact, every entry dated + sourced. |
| Knowledge base | `learning/*-knowledge-base/` | Mixed | `raw/` = immutable events; `concepts/` + `entities/` + `sources/` = replaceable state. |

KB internals (OKF): `index.md` + `SCHEMA.md` are the agent entry points —
read them before navigating; never load the whole bundle. `raw/<slug>.md` is
`immutable: true` — never hand-edit. Concept/entity pages are synthesized
across sources, each ending in a `## Sources` section tracing every claim to
a video/timestamp. Validate structural changes with the KB's `lint.py`.
Ingestion history lives in the KB's `log.md`; scope in `roadmap.md`.

The KB already implements the state/event split by design — the audit's job
is to keep it honest, not to restructure it.

## Protocol 1 — Classify: state vs event

Ask of every incoming fact: **"If this changed tomorrow, would I edit an
existing line or add a new one?"**

- **STATE** — describes the world AS IT IS NOW. Rates, prices, versions,
  roadmaps, active configs, current tools, standing preferences, contracts,
  "X is now Y". Replaceable: a new value makes the old one FALSE. State has
  exactly one current value per key.
- **EVENT** — something that HAPPENED at a point in time. Deliveries,
  decisions, sessions, signings, failures, "on <date> we did X". Append-only:
  a new event never falsifies an old one. The history itself is the value.

Hybrid rule: a fact that arrives wrapped in a dated happening ("rate
increased to $9.5k on 2026-06-01") is BOTH — record the event AND update
the state. Never let the event record become the state record: state must
read as current truth ("Current rate: $9,500"), not as a timeline you must
reconstruct.

Edge calls: durable user preferences = state; one-off requests = event;
versions of tools/models = state, but pin the old value in the daily log
before replacing ("replaced: X → Y") so the trail survives.

## Protocol 2 — Triage: route to the right tier

Follow the decision tree in
[references/audit-protocol.md](references/audit-protocol.md) — the full
version with edge cases. Summary:

1. **Session-scoped, no future value** → say it, file nothing.
2. **Raw event** → append one timestamped line to today's daily log.
3. **Current-state fact** → update `MEMORY.md` in place: merge into the
   existing line for that key; never add a second line about the same key.
   Date the line and cite the source (`Source: path`).
4. **Durable, structured, search-target** (concept, technique, tool,
   person, framework) → KB. Read `SCHEMA.md` + `index.md` + the pages the
   new material touches BEFORE writing (synthesis, not accretion — the unit
   of knowledge is the idea, not the video). Merge into existing pages when
   additive; create new pages only when the KB's page-creation threshold is
   met; if the new material conflicts with an existing page → Protocol 3.
5. **Too big for MEMORY.md, too general for one daily file** → daily log
   holds the narrative; MEMORY.md gets a one-line pointer
   (`See memory/YYYY-MM-DD.md — <topic>`); the KB gets the synthesis.
6. **"Remember this"** → write to today's log AND apply rule 3/4 immediately
   if durable.

## Protocol 3 — Contradiction detection

The #1 failure mode: always-loaded memory and KB pulls disagree, the agent
sees both, and behaves unpredictably. Prevention is structural; detection
runs at every write.

Before writing state anywhere:
1. Pull the current value from EVERY tier that could hold one: `MEMORY.md`,
  relevant lines in recent daily logs, and the KB (via `index.md` →
  concept/entity pages, or `rg` for the term).
2. Compare. Exact agreement → write. No existing value → write.
3. Conflict → reconcile before writing:
   - **Both dated, one unambiguously newer and authoritative** → newer wins.
     Replace the stale value. Log the correction in today's daily log:
     `Corrected <key>: <old> → <new> (<source>)`.
   - **Ambiguous** (undated, same date, or unclear authority) → do NOT pick.
     Present both values to Steve and ask. Stale memory is worse than no
     memory; a guessed reconciliation is worse than a visible one.
   - **Event chain vs state mismatch** (event log implies a different
     current value than the state line) → the latest event wins; update the
     state and flag the gap in the audit notes.
   - **KB vs MEMORY.md conflict** → KB page cites sources/timestamps and
     wins; MEMORY.md gets corrected with `Source:` pointing at the page.

After reconciling, cascade-check: a changed value often invalidates other
lines (old rate → old budget → old timeline). Follow the chain.

## Protocol 4 — Anti-rot audit

Three cadences, one rule: **propose, don't touch.** The agent flags every
finding; Steve approves; then write using Protocols 1–3. That loop is what
makes audits safe enough to run often.

1. **Pre-write check** — runs at every MEMORY.md write (automatic, part of
   Protocol 3). Cost: seconds.
2. **Weekly sweep** — during an agent-memory heartbeat reflection: scan the
   week's daily logs for state-change events that never updated MEMORY.md;
   check each MEMORY.md line against the week's events for silent overrides.
   Propose corrections as a list.
3. **Deep audit** — on user request ("audit my second brain") or when rot is
   suspected. Full procedure + checklist:
   [references/audit-protocol.md](references/audit-protocol.md). Covers
   MEMORY.md currency, traceability, KB Sources-section integrity, raw/
   immutability, duplicate-concept detection, and `log.md` / `roadmap.md`
   drift. Finish a KB-touching audit with `python lint.py`.

Rot signals that justify a deep audit: agent answers about Steve's own
setup wrong; two confident answers to the same question disagree; MEMORY.md
or KB pages undated; "as of" strings older than ~60 days; the user corrects
a fact the memory system already "knew".

## Protocol 5 — Promotion / demotion between tiers

**Promote** (up = distilled, load-bearing):
- Daily log → MEMORY.md: the fact is durable AND would change a future
  session's behavior AND keeps recurring in logs. One line, dated, sourced.
  This is a filter, not a copy — most log lines stay in the log.
- Log/MEMORY.md → KB: the fact is reference knowledge — a technique, tool,
  person, framework, or synthesized lesson — that future sessions will
  search for. It becomes a concept/entity/source page, or merges into one.

**Demote** (down = archived, searchable):
- MEMORY.md → daily log: a state value goes stale and a newer one replaces
  it — the old value lands in the log with `Replaced by:` (history kept,
  context freed). A MEMORY.md line grows past one line → distill; the full
  version goes to a dated log entry or KB page, MEMORY.md keeps the index
  card. A decision is superseded → demote with the replacement date.
- KB: superseded concept/entity pages are NOT deleted — mark them
  `Superseded by <page>` so links and citations survive. Only raw/ files are
  untouchable; everything else is maintained state.

Never demote silently — always leave a pointer (`Replaced by`, `See`,
`Superseded by`) so retrieval can follow the trail.

## Failure modes this skill exists to prevent

1. **Contradictory tiers** — MEMORY.md says X, KB says Y, agent sees both.
2. **Append-only rot** — outdated state accumulating because nothing gets
   replaced.
3. **Convention without enforcement** — "date everything" style rules that
   rely on the model remembering to comply. Classification is a mandatory
   step, not a style preference.
4. **Unbounded MEMORY.md** — every line costs tokens every turn; stale lines
   are pure cost. Ruthless currency.
5. **Unguarded raw layer** — editing `raw/` transcripts destroys the event
   trail; edits to synthesized pages without updating their Sources section
   break traceability.
6. **Guessing through ambiguity** — reconciling undated conflicts by vibes
   instead of asking.

## Working rules

- Every MEMORY.md line: dated, sourced, one line.
- Every event: timestamped, append-only, in the daily log.
- Every KB claim: traceable to a `## Sources` entry.
- When memory and KB disagree: reconcile BEFORE answering, never after.
- Reconciliation target: exactly one current truth per fact per tier, with
  the history preserved in the event layer.
- Batch the write phase (one proposed-changes list → one approval → apply),
  not ask-per-line.
