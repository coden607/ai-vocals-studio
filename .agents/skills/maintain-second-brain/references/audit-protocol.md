# Audit Protocol — Checklist, Decision Tree, Deep-Audit Procedure

Reference for `maintain-second-brain`. Read this when running a deep audit,
when a classification is non-obvious, or when preparing the batch of
proposed changes for Steve's approval.

## Contents

1. Classification decision tree (incoming information)
2. Contradiction reconciliation matrix
3. Weekly sweep checklist (lightweight)
4. Deep-audit checklist (full)
5. Proposed-changes report format
6. Quick reference: tier routing

---

## 1. Classification decision tree

Start at the top; take the first branch that matches.

```
INCOMING FACT
│
├─ Session-scoped only? (joke, one-off command, transient context,
│   no value beyond this conversation)
│   → FILE NOTHING. Say it, move on.
│
├─ Did something HAPPEN? (delivery, decision, meeting, signing, failure,
│   completed task, session milestone)
│   → EVENT. Append one timestamped line to today's daily log:
│     `- HH:MM — <what happened> (<source/context>)`
│   └─ Does the event CHANGE a current value? (rate changed, tool swapped,
│      plan superseded, version bumped)
│      → ALSO update the state line for that key (see STATE branch) and
│        prepend the log entry with `Replaced <key>: <old> → <new>.`
│
├─ Does it describe how the world IS NOW? (current rate, active config,
│   standing preference, current version, present tool, roadmap focus)
│   → STATE. Update MEMORY.md (or the KB page) IN PLACE:
│     1. Pull the existing line for this key (Protocol 3 pulls).
│     2. No existing line → add one, dated, sourced.
│     3. Existing line, same value → refresh the date, done.
│     4. Existing line, different value → REPLACEMENT:
│        - Old value → today's daily log with `Replaced by:`.
│        - MEMORY.md line rewritten to the new value, re-dated,
│          source cited.
│        - Cascade-check related lines (budget↔rate, tool↔workflow).
│     5. KB page holds the state → edit the page, refresh its frontmatter
│        `updated:` date, and keep the claim's Sources entry honest.
│
├─ Is it reference knowledge? (a technique, framework, concept, tool,
│   person, organization, synthesized lesson — knowledge future sessions
│   will SEARCH for)
│   → KB. Ingestion procedure:
│     1. Read the KB's SCHEMA.md + index.md.
│     2. Read every concept/entity page the material touches.
│     3. Additive (fits existing pages) → merge into those pages; update
│        `updated:`; extend Sources.
│     4. New idea meeting the page-creation threshold (≥2 sources or
│        ≥2 inbound links — per the KB's own schema) → create the page,
│        link it from index/theme, add to the KB's log.md.
│     5. Conflicts with an existing page → CONTRADICTION. Go to §2.
│     6. Raw source material (transcript, document) → write to raw/,
│        immutable + timestamped; a sources/ summary page is its pointer.
│
└─ Big/complex (a full analysis, a long story, a project writeup)?
   → SPLIT ACROSS TIERS:
     - Daily log: the narrative, dated.
     - MEMORY.md: one pointer line — `See memory/YYYY-MM-DD.md — <topic>`.
     - KB: the synthesis, if the content is durable reference knowledge.
```

Rules that apply at every branch:

- Every write is dated. State writes additionally cite the source
  (`Source: <path or URL>`).
- An event line never rewrites another event line. A state line never
  survives unchanged when its value changes.
- Hybrid facts (dated happening + new value) always produce BOTH the event
  record and the state update. Missing one half is the classic rot source.
- When Steve says "remember this": today's log gets the event record AND
  the state/reference branch runs immediately if the content is durable.

## 2. Contradiction reconciliation matrix

Detected during Protocol 3 pre-write pulls, weekly sweeps, deep audits, or
when the user corrects a "known" fact.

| Case | Signals | Resolution |
|---|---|---|
| State vs state, both dated | Two different current values with different dates | Newer authoritative source wins. Replace stale; log correction in today's daily log; cascade-check dependents. |
| State vs state, ambiguous | Undated, same date, or unclear which source is authoritative | STOP. Present both values + sources to Steve; ask. Never guess. |
| Event chain vs state | Event log's latest entry implies a different current value than the state line | Latest event wins. Update state; add a `state lagged behind events` note to the audit findings. |
| MEMORY.md vs KB | Always-loaded line disagrees with a synthesized page | KB page wins IF its Sources section traces the claim — cite the page in the corrected MEMORY.md line. If the page is unsourced, treat as ambiguous and ask. |
| KB vs KB | Two pages describe the same fact differently | Check both pages' Sources timestamps; newer-sourced wins; fix the loser; if sources are the same age, ask Steve. |
| KB duplicate concepts | Same idea under two slugs (e.g. `piv-loop` vs `plan-implement-validate`) | Merge into the canonical slug per the KB's taxonomy; leave the loser as a redirect link; add to log.md. |
| Raw vs synthesized | A sources/concepts/entities page misquotes or contradicts its own raw/ transcript | raw/ is immutable truth. Fix the synthesized page; never edit raw/. |

After ANY reconciliation, run the cascade check: list every other line or
page that referenced the old value, and add each to the proposed-changes
batch.

## 3. Weekly sweep checklist (lightweight, heartbeat-cadence)

Runs alongside the agent-memory reflection pass. ~10 minutes, no approval
needed for findings — produce a proposed list.

- [ ] Read the last 7 days of daily logs (oldest first).
- [ ] Extract every event that implies a state change (rate/version/plan/
      tool/preference changes).
- [ ] For each: is the corresponding MEMORY.md line updated? If not →
      proposed change.
- [ ] Read MEMORY.md line by line: does any line contradict anything in the
      week's logs? Does any line reference something superseded this week?
- [ ] Check every MEMORY.md line still has a current `Source:` that exists.
- [ ] Check for new duplicate keys in MEMORY.md (two lines about the same
      fact) → merge proposal.
- [ ] If any KB work happened this week: confirm new pages were logged in
      log.md and linked from index.md.
- [ ] Output: proposed-changes list in §5 format. Apply only after Steve
      approves.

## 4. Deep-audit checklist (full, user-triggered or rot-suspected)

Scope: MEMORY.md + daily logs + every KB under `learning/`. Read the KB's
SCHEMA.md before touching anything inside it.

### Tier 1 — MEMORY.md

- [ ] Every line dated. Undated line → date it or flag for replacement.
- [ ] Every line sourced and the source path still exists.
- [ ] Exactly one line per fact key — no duplicate-key lines.
- [ ] Each line still TRUE today. Doubtful → verification question for
      Steve (batch them; don't interrogate one at a time).
- [ ] Any "as of" older than ~60 days → recheck against logs and KB.
- [ ] Superseded decisions marked superseded, with the replacement named.
- [ ] Size check: if MEMORY.md has grown since the last audit, confirm
      every added line passes the promotion filter (durable + would change
      a future session). Demote the rest.

### Tier 2 — Daily logs

- [ ] State-change events that never propagated to MEMORY.md → proposed
      updates.
- [ ] Event chains with gaps (decision referenced but no deciding event) →
      note in findings; do not fabricate the missing event.
- [ ] Recent logs carry `memory_search`-friendly keywords (names, projects,
      key nouns) so retrieval can find them later.

### Tier 3 — Knowledge base(s)

- [ ] Every concepts/entities/sources page ends with a `## Sources`
      section, and every claim traces to a source. Unsourced strong claims
      → flag.
- [ ] Frontmatter `updated:` dates exist and are plausible (not older than
      the newest source cited on the page).
- [ ] Duplicate/near-duplicate concept pages under different slugs → merge
      proposal (keep canonical per taxonomy; loser becomes a link).
- [ ] raw/ files untouched and `immutable: true` — no hand-edits anywhere.
- [ ] index.md navigation still matches reality: no links to deleted pages,
      new pages linked in.
- [ ] log.md ingestion entries vs roadmap.md scope — un-ingested queued
      work and stale scope statements → findings.
- [ ] KB-vs-MEMORY.md cross-tier consistency: every fact that exists in
      both tiers agrees in both tiers.
- [ ] After applying approved KB changes: run `python lint.py` from the KB
      root; fix anything it flags.

### Wrap-up

- [ ] Assemble ALL findings into the §5 report — one batch.
- [ ] Steve approves/rejects line by line (or whole-batch).
- [ ] Apply approved changes tier by tier using Protocols 1–3 (correct
      classification per change, not bulk sed).
- [ ] Record the audit itself as an EVENT in today's daily log: scope,
      findings count, changes applied count, lint result.

## 5. Proposed-changes report format

One batch, so approval is one decision:

```markdown
## Second-brain audit — <date> — <scope>

### Proposed changes (<n>)
1. [MEMORY.md] Update "<line>" → "<new line>" (why: <event/source>)
2. [MEMORY.md] Demote "<line>" → daily log 2026-10-05 (why: superseded by #1)
3. [KB entities/tools/foo.md] Update version 1.2 → 2.0, extend Sources (why: <source>)
4. [KB concepts/] Merge bar.md into foo.md (why: duplicate concept, canonical slug foo)
5. [ASK] "<fact>" — two conflicting values: MEMORY.md says X (<date>), KB says Y (<date>). Which is current?

### Findings needing no action (<n>)
- <observations worth knowing but not worth changing>

### Skipped (<n>)
- <considered and deliberately left alone, with reason>
```

Items marked [ASK] block on Steve's answer; everything else can be applied
in one pass after approval.

## 6. Quick reference: tier routing

| What it is | Class | Tier | Write op |
|---|---|---|---|
| "Happened today" — delivery, call, decision | Event | Daily log | Append |
| "Current rate is X" / "I now use Y" | State | MEMORY.md | Replace in place |
| Standing preference, durable constraint | State | MEMORY.md | Replace in place |
| Technique/framework/tool/person/org | Reference | KB concept/entity | Merge or create page |
| Full transcript / source document | Event (raw) | KB raw/ + sources/ | Write once, immutable |
| Synthesized lesson, cross-video pattern | Reference | KB concepts/ | Merge into canonical page |
| Session narrative, too big for a line | Event | Daily log + MEMORY.md pointer | Append + one pointer line |
| Superseded version/rate/plan | State (stale) | Demote to daily log | Append `Replaced by:` |
| Superseded KB page | Reference (stale) | KB — mark `Superseded by` | Edit page, keep link |
