# route-with-jev — Worked Examples

Each example is copy-adaptable. State is deliberately compact — input tokens
are the only thing Jev bills.

---

## 1. Pre-Tool-Use Hook Guardrail

The flagship use case: replace regex hooks with near-zero false positives.
Fires before every tool call; blocks dangerous actions.

**State per call** (build it in the hook, don't cache):

```json
{
  "tool_name": "exec",
  "args": "rm -rf /root/.openclaw/workspace",
  "cwd": "/root/.openclaw/workspace",
  "objective": "clean up temp files from the cole-medin ingest run"
}
```

**Questions** (four nouls, answered in parallel):

```json
{
  "exposes_secrets":  {"type": "noul", "instructions": "Is this action exposing secrets? (reading .env, credentials, key files)"},
  "destroys_data":    {"type": "noul", "instructions": "Is this action destroying data? (removing folders, dropping tables, force-pushing)"},
  "exfiltrates":      {"type": "noul", "instructions": "Is this action sending sensitive data to an external destination?"},
  "off_task":         {"type": "noul", "instructions": "Is this action off-task from the stated objective?"}
}
```

**Decision logic** (plain code, not an LLM):

```python
BLOCK_THRESHOLD = 0.8
if api_error:                       # exit code 4 from jev_decide.py
    block_and_log(...)              # fail closed — never fail open
elif any(a["noul"] > BLOCK_THRESHOLD for a in answers.values()):
    block_and_log(flagged_keys)     # hand the flagged action to the LLM layer
                                    # for a human-readable explanation
else:
    allow()
```

Why this beats regex: `rm -rf ./build` and `rm -rf /root/.openclaw/workspace`
are the same string pattern, very different decisions. Jev reads objective +
args together; regex can't.

---

## 2. Model-Tier Router

Routes a task to a tier in `workspace/orchestration/models.yaml` before any
LLM call. The `criteria` definitions are copied verbatim from the map's
`when:` lines — keep them in sync on the monthly review.

**State:** the task text, plus one line of source context:

```
Task: "patch the date formatter to ISO-8601 and add tests"
Source: user chat · prior tier for this task_type: code (grades: 4,5)
```

**Questions:**

```json
{
  "tier": {
    "type": "choice",
    "instructions": "Which model tier should handle this task? Judge by the task content alone.",
    "criteria": {
      "simple":   "extraction, classification, rewrites, short summaries, formatting",
      "chitchat": "casual conversation, quick Q&A, morale replies",
      "reasoning":"analysis, planning, math, multi-step logic, judgment calls",
      "code":     "patches, migrations, tests, scripts, debugging",
      "research": "web research, cited summaries, competitive intel",
      "long-doc": "transcripts, huge PDFs, repo scans, big corpora",
      "creative": "ad copy, storytelling, voice-heavy writing",
      "frontier": "final review of high-stakes output, hardest problems — needs explicit ask"
    }
  }
}
```

**Act layer:** dispatch to the tier's `primary` model; log the row to
`outcomes.jsonl` after grading. Expected Jev response: `code, confidence ~98%`.
Cost: $0.000017-ish. One wrong route to `frontier` would have cost ~1000×.

Add a second question when intake volume justifies it:
`"needs_human": {"type": "noul", "instructions": "Is this request ambiguous enough that a human should look first?"}` — route p > 0.8 to Steve instead of guessing.

---

## 3. Intake Triage (Issues / PRs / Tickets)

Classifies work before review depth is chosen. State is the raw issue text —
issues are short, so this stays cheap.

**Questions:**

```json
{
  "work_type": {
    "type": "choice",
    "instructions": "What kind of work is this?",
    "criteria": {
      "bug":     "something is broken or behaving incorrectly",
      "feature": "new capability or enhancement",
      "docs":    "documentation-only change",
      "chore":   "refactor, dependency bump, config, no behavior change"
    }
  },
  "security_sensitive": {"type": "noul", "instructions": "Does this touch auth, secrets, payments, or data access?"},
  "review_depth": {
    "type": "score",
    "instructions": "How deep should review go?",
    "criteria": [
      "level 1: skim — title + diff stat",
      "level 2: standard — read the diff",
      "level 3: careful — read the diff and its tests",
      "level 4: deep — read everything plus surrounding context"
    ]
  }
}
```

**Act layer:** security_sensitive p > 0.7 → level 4 + notify; bug → standard
path; chore → skim. PR triage at intake means the expensive review LLM only
reads what deserves it.

---

## 4. Browser / Loop Automation (Decision-Per-Tick)

For loops that iterate faster than any LLM can: browser automation, gameplay
testing (60fps), scrape-and-click walks.

**Sandwich setup (one-time, LLM does this):**
- Translate the page/game state into a compact structured state (element
  labels, visible text, goal line).
- Generate the `choice` question over possible next actions: click X, focus
  Y, scroll, type (free-form text input is pre-generated by the LLM between
  ticks — Jev never writes prose), stop.
- Set the stop threshold.

**Per tick:** serialize state → Jev (~0.2s) → execute → repeat.
**Post-loop:** LLM analyzes what the run surfaced (bugs, anomalies, stuck
points). Jev drove; the LLM reviews.

If Jev keeps picking the same action with confidence collapsing, that's the
low-confidence signal — stop the loop and hand the trace to the LLM.

---

## 5. Anti-Pattern Teardowns

**"Let me add Jev to summarize incoming emails."** — Summarization is
generation. Wrong model class entirely. Jev could decide `needs_reply:
noul`, and the LLM writes the reply. Decision and generation stay split.

**"I'll feed the last 200 tool calls as state for context."** — 200 calls of
args ≈ thousands of billed input tokens per decision, and most of it is
noise. The deciding facts are objective + this call's args + cwd. Ship those.

**"Jev said 0.51 for destroys_data, let me lower the block threshold to 0.5
so it catches more."** — You tuned the threshold to the answer after peeking.
Calibration is the product. At 0.51 with a sane state, the honest read is
"uncertain" → route to the LLM layer for one cheap judgment call, or block.
Thresholds set ex-ante or not at all.

**"Skip the LLM harness step — I'll hand-write the questions inline each
time."** — Works once. Then domains drift and questions quietly rot. The
harness step is what makes questions versioned, reviewable, and re-usable.
One LLM design pass per pattern, not per call.
