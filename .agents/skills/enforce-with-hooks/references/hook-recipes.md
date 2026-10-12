# Hook Recipes

Concrete, ready-to-adapt hook configurations. Each recipe states the event,
the judge (regex / Jev / LLM), the state/questions where relevant, and the
action. Adapt paths, tool names, and thresholds to your environment.

---

## Recipe 1 — Security guardrail (PreToolUse + Jev)

The flagship use case: semantic secret/destruction/exfiltration detection with
near-zero false positives at a fraction of a penny per call. Replaces regex
hooks that either miss semantics or drown you in false alarms.

```json
{
  "event": "PreToolUse",
  "matcher": { "tool_name": "*" },
  "judge": "jev",
  "state": {
    "tool_name": "{{tool.name}}",
    "tool_input_args": "{{tool.args}}",
    "current_working_directory": "{{session.cwd}}"
  },
  "questions": [
    { "id": "exposing_secrets", "type": "noul",
      "instructions": "Is this action exposing secrets? (e.g., reading .env, credentials, key material)" },
    { "id": "destroying_data", "type": "noul",
      "instructions": "Is this action destroying data? (e.g., removing an entire folder, force-pushing over history)" },
    { "id": "exfiltrating", "type": "noul",
      "instructions": "Is this action exfiltrating sensitive data to an external party?" },
    { "id": "off_task", "type": "noul",
      "instructions": "Is the agent going off-task from the current objective?" }
  ],
  "action": {
    "if_any_true": "block",
    "block_message": "Guardrail blocked: {{matched_question}}. If this is a false positive, ask the human to approve explicitly."
  }
}
```

Notes:
- Sandwiched pattern: the agent (LLM) proposed the tool call; Jev judges it; the
  LLM receives the block and can re-plan. Never let Jev act alone.
- Keep the human-override path explicit — guardrails decide routine, humans
  decide exceptions.
- Cheap regex pre-filter is fine to add (`cat`, `curl`, `rm -rf` short-circuit),
  but let Jev carry the semantic weight.

---

## Recipe 2 — Style-enforcement hook (PostToolUse + Jev)

Enforce project-specific conventions (the rules that survive ablation) on every
edit — without trusting the writer to self-review.

```json
{
  "event": "PostToolUse",
  "matcher": { "tool_name": "edit|write" },
  "judge": "jev",
  "state": {
    "file_path": "{{tool.args.path}}",
    "diff_or_content": "{{tool.result.preview}}",
    "project_conventions": "see .claude/CONVENTIONS.md (import order, test registration, function style)"
  },
  "questions": [
    { "id": "violates_convention", "type": "noul",
      "instructions": "Does this change violate the project conventions listed in the state?" },
    { "id": "unregistered_test", "type": "noul",
      "instructions": "If this adds a test, is it registered/run by the project's test runner?" }
  ],
  "action": {
    "if_any_true": "inject_warning",
    "warning": "Style guardrail: {{matched_question}}. Fix before continuing.",
    "severity": "warn"
  }
}
```

Notes:
- `severity: warn` nudges; flip to `block` for conventions that have broken
  production before. Match severity to regret-if-skipped.
- Feed the conventions as state (a short excerpt), not as a giant prompt — keep
  per-call cost tiny.

---

## Recipe 3 — Budget cap hook (Stop + regex/accounting)

End-of-turn audit that stops token bleed deterministically. Pure accounting —
no judgment needed, so no LLM/Jev required.

```json
{
  "event": "Stop",
  "matcher": {},
  "judge": "regex",
  "checks": [
    { "id": "budget", "type": "threshold",
      "metric": "session.tokens.total",
      "max": 200000,
      "action": "inject_warning",
      "warning": "Budget cap reached ({{session.tokens.total}}/200000). Wrap up: write the handoff doc now." },
    { "id": "no_output_no_exit", "type": "assert",
      "condition": "session.produced_artifact OR session.wrote_handoff",
      "action": "continue",
      "message": "Turn ended with no deliverable and no handoff doc. Resume or document the blocker." },
    { "id": "uncommitted_review", "type": "assert",
      "condition": "git.status.clean OR session.review_passed",
      "action": "inject_warning",
      "warning": "Uncommitted changes exist. Open a separate review session — never let the writer approve its own work." }
  ]
}
```

Notes:
- Budget numbers are per-session; scale to your plan. The point is the number
  lives in a hook, not in a hopeful prompt line.
- `/usage`-style analytics (weekly %, parallel sub-agent spend) inform where to
  set the cap. Check before tuning.

---

## Recipe 4 — SessionStart environment check (SessionStart + regex)

Fires once per session: validate the environment and inject live context so the
agent starts from facts, not assumptions.

```json
{
  "event": "SessionStart",
  "matcher": {},
  "judge": "regex",
  "checks": [
    { "id": "tools_present", "type": "assert",
      "condition": "which git docker node", "action": "inject_warning",
      "warning": "Missing expected tool: {{missing}}." },
    { "id": "branch_convention", "type": "regex",
      "source": "git branch --show-current",
      "pattern": "^(feature|bug)/",
      "action": "inject_warning",
      "warning": "Branch '{{branch}}' does not match feature/ or bug/ convention." }
  ],
  "inject": [
    { "id": "repo_tree", "command": "git ls-tree -r --name-only HEAD | head -200" },
    { "id": "rule_count", "command": "wc -l AGENTS.md CLAUDE.md 2>/dev/null" }
  ]
}
```

Notes:
- Injection gives the agent real, current context (repo tree, rule counts)
  instead of relying on stale memory of the codebase.
- One-time per session = cheap. Reminders that shape the whole session belong
  here, not repeated in every prompt.

---

## Tuning checklist (applies to all recipes)

1. Smoke-test each hook: trigger the blocked case deliberately.
2. Log every block/warn for a week; count false positives.
3. If false positives climb on a regex rule, reframe it as a Jev question.
4. If a Jev question can't be framed crisply, escalate to an LLM review hook —
  and expect to pay for it.
5. Re-test the whole layer against real tasks every model generation; ablate
  line by line when in doubt.
