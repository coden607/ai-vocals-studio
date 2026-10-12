---
name: jev-gate
description: Jev-style typed decision layer. Use when routing, gating, scoring confidence, picking a persona or next act, deciding retry vs stop vs ask-human, or the user says jev, system one, noul, choice vs score, decide don't write, confidence gate. Pair with adaptive-persona. Do not use Jev to draft text.
license: MIT
metadata:
  type: workflow
  version: "1.0"
user-invocable: true
---

# Jev Gate

Jev (TypeSafe System One) decides. Grok writes and acts. This skill is the decision fork.

Jev never drafts. It answers only three primitives against a `state` blob:

| Primitive | Question | Return |
|---|---|---|
| noul | does this hold? | P(yes) in 0..1 |
| choice | which option? | argmax + full distribution |
| score | where on this rubric? | expected level + distribution |

Live TypeSafe/OpenRouter if `TYPESAFE_API_KEY` or `OPENROUTER_API_KEY` is set. Otherwise `scripts/decide.py` runs a local calibrated-style scorer with the same JSON shape so the loop still works.

## When to call

Call at a **loop boundary**, not every sentence:

- first message of a thread, or a clear task-type change
- after a failed command / before a third retry
- before irreversible action (send, file, post, spend, legal serve)
- when two skills or personas both fit
- when the user says "jev this", "gate this", "should we proceed"

Do not call Jev to write emails, code, or explanations.

## Procedure

1. Write `state` (facts only — user ask, files touched, last error, constraints). Keep it under ~2k tokens.
2. Pick a question bank from `references/banks/` or write ≤20 questions.
3. Run:

```bash
python3 /home/workdir/.grok/skills/jev-gate/scripts/decide.py \
  --bank mode-router \
  --state-file /tmp/jev-state.txt \
  --floor 0.72
```

Or pipe JSON:

```bash
python3 /home/workdir/.grok/skills/jev-gate/scripts/decide.py --file /tmp/jev-req.json
```

4. Read `answers` + `policy`.
5. Apply policy (below). Then Grok acts.

## Policy (always)

- **Act** if choice/noul confidence ≥ `--floor` (default 0.72) and no disagreement flag.
- **Ask human** if confidence < floor, or two questions contradict (example — `urgency=now` and `lane=ignore`).
- **Stop retry** if `repeat_failure` noul ≥ 0.85.
- Safety/system rules still win over any answer.
- Never treat local-heuristic output as TypeSafe-calibrated. The `provider` field says which engine answered. Say so if the user asks.

## Built-in banks

| Bank | Use |
|---|---|
| `mode-router` | pick adaptive-persona persona + overlay |
| `act-gate` | proceed / gather / ask-human / stop |
| `retry-stop` | retry same, change tactic, stop |
| `legal-risk` | file-ready vs draft-only vs need-cite |

Banks live in `references/banks/<name>.json`.

After a `mode-router` decision that clears the floor, lock adaptive-persona and write:

`/home/workdir/.grok/skills/adaptive-persona/state/current-mode.json`

## Mode lock line (when routing persona)

```
Mode: <persona> / <overlay> — Jev <provider> conf=<n>. Say "switch mode" to change.
```

## Do not

- Send Jev to `/chat/completions`. Decisions only (`/api/alpha/decisions` or `/api/v1/systemone`).
- Ask more than 20 questions per call.
- Invent a TypeSafe score when running local.
- Use Jev as the only agent. It cannot write.

## References

- Loop and mixing — `references/loop.md`
- API shape — `references/api-shape.md`
