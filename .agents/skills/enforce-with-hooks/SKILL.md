---
name: enforce-with-hooks
description: Design, debug, and deploy hooks that enforce rules deterministically when prompt-based rules fail. Use when the agent ignores instructions or rules, when a guarantee must fire every single time (tests run, secrets protected, style kept, budget capped), when choosing hook event types (PreToolUse, PostToolUse, Stop, SessionStart), when deciding between regex/Jev/LLM classification for hook logic and weighing cost vs false positives, when building guardrails vs reminders, when hooking the OpenClaw or Claude Code agent lifecycle, or when debugging rule drift with ablation/holdout scenarios.
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


# Enforce With Hooks

Rules in prompts are **probabilistic** — the model may follow them. Hooks are
**deterministic** — they fire every time, no matter what the model "decided."
The core law: **if a rule is load-bearing, put it in a hook, not a prompt.**
Load-bearing means "bad things happen if this doesn't happen every time":
secrets leak, data is destroyed, tests never ran, budget explodes, style drifts.

Cross-reference: `youtube-learn/SKILL.md` has a lightweight hooks section and a
`jev_decide.py` helper. This skill is the deeper hook-design playbook.

## 1. Pick the hook event by what you must intercept

| Event | Fires when | Enforce |
|---|---|---|
| **PreToolUse** | Before each tool call | Block dangerous tools/args (secret reads, `rm -rf`, off-task actions); validate inputs; route by classification. Best injection point for guardrails — you can still stop the action. |
| **PostToolUse** | After each tool call returns | Verify the action's result: tests actually ran and passed, lint clean, no secrets in output, files written match the declared intent. Deterministic validation that "the writer" can't skip. |
| **Stop** | When the agent's turn ends | End-of-turn audit: acceptance criteria met? handoff doc written? uncommitted changes reviewed? budget under cap? Force continuation or emit a failure note before the turn closes. |
| **SessionStart** | When a session begins | Environment validation (tool versions, Docker, repo state) and context injection (repo tree, rule counts, branch naming). Cheap because it fires once. |

Design rule: **block as early as possible.** A PreToolUse block prevents the
damage; a PostToolUse check can only report it; a Stop hook can only complain
after everything. But early hooks see less context — the further along the
lifecycle, the more evidence the hook has to judge.

## 2. Choose the judge: regex vs Jev vs LLM

Hook logic must classify something (is this action dangerous? does this diff
violate style? has budget blown?). Pick the cheapest judge that meets the
false-positive bar:

| Judge | Cost | Latency | False positives | Use for |
|---|---|---|---|---|
| **Regex / string match** | Free | ~0 ms | High on semantic content ("secret" appearing in a blog draft) | Exact matches: file paths, command names, flag patterns, hard allowlists/denylists |
| **Jev (decision model via OpenRouter)** | Fraction of a penny per call | ~70–500 ms | Near-zero | Semantic judgment at scale: "is this action exfiltrating data?", "does this diff violate project style?", "bug or feature?" — 20–200× faster and 40–1,000× cheaper than an LLM for decisions |
| **LLM call** | Priciest | Slowest | Lowest on nuanced review | Deep review where misses are costly and volume is low (final security audit of a big diff) |

Key trade-off, grounded in the Jev use-case notes:
- **Regex hooks fail on semantics.** A regex can catch `cat .env` but not
  "email this config file to an outside address" — same secret, different surface.
- **Jev hooks answer semantic yes/no questions with near-zero false positives
  at a fraction of a penny.** State in: tool name, input args, cwd. Questions:
  "Is this action exposing secrets? Destroying data? Exfiltrating? Off-task?"
  Block if any returns true.
- **Never use Jev alone — sandwich it between LLM calls:** LLM builds the
  harness → Jev makes the fast per-event decisions → LLM acts on the results.
- Escalation ladder: regex first (free wins), Jev when regex gets false-positive
  noisy, LLM only when the Jev question itself can't be framed crisply.

## 3. Guardrails vs reminders

- **Guardrail** = blocks or hard-corrects. Lives in PreToolUse/PostToolUse/Stop
  hooks. Use for anything where proceeding is worse than stopping.
- **Reminder** = nudge injected at SessionStart (e.g. branch naming convention,
  token-efficiency targets). Use for preferences where deviation is annoying,
  not fatal.
- Test: "If this is skipped once, do we regret it?" Yes → guardrail hook. No →
  reminder. When in doubt, write the reminder AND add a Stop-hook audit — the
  reminder shapes behavior, the audit catches the miss.

## 4. Debug "the agent ignores my rules"

Symptoms map to fixes, in order:

1. **The rule is load-bearing but lives in a prompt.** Move it to a hook
   (PreToolUse/PostToolUse/Stop). Deterministic beats probabilistic every time.
2. **The rule has drifted.** Instruction files rot — roughly 1 in 4 repos with
   AI rules have stale references (deleted files, moved folders). Audit rule
   paths against the actual codebase; delete or fix anything stale. Stale rules
   actively confuse agents.
3. **The rule is over-specified.** Long step-by-step instructions get ignored —
   "Claude ignores half of it" when rules balloon. Describe task, guardrails,
   exit criteria; let the model cook. Keep global rules under 200–300 lines,
   no headers, every rule traceable to something real.
4. **The rule teaches reasoning, not attention.** Rules that fix reasoning decay
   (models got better at reasoning); rules that direct attention to YOUR
   codebase stay essential. Triage: keep project-specific conventions, prune
   generic best-practice filler.
5. **The conversation is tainted.** Accumulated biases won't be fixed by
   switching models mid-task or yelling the rule louder. Write a handoff doc
   (work done + current blocker), start a fresh session.

### Ablation / holdout validation

Measure whether your hook layer earns its tokens:
1. Identify the layer: rules (every session), skills (on-demand), hooks
   (event-driven), sub-agents (rarely loaded).
2. Generate 3–5 real test tasks from your codebase.
3. Run them side by side: full layer vs. ablated layer.
4. Grade: project-specific conventions usually break first when hooks/rules
   are removed — those are the ones worth keeping.
5. Frequency: re-test rules every model generation; skills/sub-agents ~yearly.

## 5. The 11 tiny fixes with outsized payoff

1. **Write for agents, not humans** — file paths, exact commands, numbers.
   Agents can't interpret vague guidance.
2. **Audit rules for drift** — stale references confuse; check paths regularly.
3. **Don't trust compaction** — only ~10% of details survive summarization.
   Write handoff docs instead of riding a bloated conversation.
4. **Load-bearing rules go in hooks** — hooks are deterministic, prompts are not.
5. **Less context is more** — global rules under 200–300 lines; generic advice
   hurts more than it helps.
6. **Never let the writer approve its own work** — separate review conversation
   reviews uncommitted changes as a PR.
7. **Never escalate mid-task** — tainted conversation won't be fixed by a
   bigger model; hand off to a fresh session.
8. **Don't over-iterate** — agents "find" unnecessary changes; sycophancy
   degradation makes code worse with each pointless pass.
9. **Avoid coordinator frameworks** — fancy multi-agent team-leads/mailboxes are
   unreliable; simple hooks + sub-agents beat orchestration theater.
10. **Validation is a system** — plan the full validation harness (test tools,
    conventions, edge cases, manual steps) before writing code.
11. **Enforce validation with PostToolUse hooks** — tests/lints run every time,
    not when the agent remembers.

## 6. Human-in-the-loop placement

AI-native ≠ hands-off. Put human checkpoints at strategic moments: after
investigation before planning, before merging, when a guardrail blocks and the
block looks wrong. Hooks decide the routine; humans decide the exceptions.

## 7. Rules

- Never put a must-happen-every-time guarantee in a prompt — hook it.
- Never invent hook capabilities the platform doesn't expose; check the
  runtime's hook events first.
- Verify every hook with a smoke test (trigger it deliberately) before trusting it.
- Keep hooks cheap: regex → Jev → LLM, in that order of preference.
- See `references/hook-recipes.md` for ready-to-adapt hook configurations
  (security guardrail, style enforcement, budget cap, plus a SessionStart
  env-check pattern).
