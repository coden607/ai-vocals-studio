# Shared Agent Skills

This repository consumes the canonical skills maintained at:
https://github.com/coden607/skills

Do not vendor the full skills bundle into this repository. Keeping one canonical source avoids prompt/context duplication and skill drift.

## Precedence

1. Repository safety and product rules in `AGENTS.md` are authoritative.
2. Repository-specific runtime guidance in `CLAUDE.md` remains authoritative for Claude Code.
3. Applicable procedures from `coden607/skills` may optimize execution, but must not weaken the repository's consent-first voice authorization, testing, secret-handling, or Git discipline.

## Skills to apply

Use the canonical skill when its trigger matches, especially:

- `compress-token-spend`: route to the cheapest capable model, preserve cacheable prompt prefixes, keep outputs concise, sample graders, and load targeted context.
- `route-with-jev` / `jev-gate`: use low-cost deterministic/system-one routing for repetitive classification or guardrail decisions when available.
- `route-interrupts`: queue unrelated interruptions rather than silently abandoning active work.
- `isolate-agent-runs`: isolate autonomous/yolo agent work and gate destructive operations.
- `enforce-with-hooks`: prefer deterministic hooks/regex, then low-cost judges, then full LLM judgment.
- `maintain-second-brain`: distinguish durable state from transient events and avoid stale memory.
- `run-software-factory`: use the PRD-to-PR/autonomy workflow for substantial autonomous changes.

## Local installation

For agents that support SKILL.md directories, install from the canonical checkout rather than copying instructions into prompts:

```bash
git clone https://github.com/coden607/skills.git ~/skills 2>/dev/null || git -C ~/skills pull --ff-only
~/skills/scripts/install-skills-everywhere.sh -A -s ~/skills -t ~/.codex/skills
```

Use the corresponding target directory for Claude Code/OpenClaw or another SKILL.md-compatible agent.

## Context budget

Search/read only the skill needed for the current duty. Do not load the entire bundle into every model call. Stable repository rules come first; variable task context comes last.
