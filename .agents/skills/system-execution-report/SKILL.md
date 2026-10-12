---
name: system-execution-report
description: Generates a structured implementation report reflecting on a just-completed feature — what was done, divergences, challenges. Use right after finishing an implementation, as the input to a system review.
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


# Execution Report

Review and deeply analyze the implementation you just completed.

## Context

You have just finished implementing a feature. Before moving on, reflect on:

- What you implemented
- How it aligns with the plan
- What challenges you encountered
- What diverged and why

## Generate Report

Save to: `.claude/execution-reports/[feature-name].md`

### Meta Information

- Plan file: [path to plan that guided this implementation]
- Files added: [list with paths]
- Files modified: [list with paths]
- Lines changed: +X -Y

### Validation Results

- Syntax & Linting: ✓/✗ [details if failed]
- Type Checking: ✓/✗ [details if failed]
- Unit Tests: ✓/✗ [X passed, Y failed]
- Integration Tests: ✓/✗ [X passed, Y failed]

### What Went Well

List specific things that worked smoothly:

- [concrete examples]

### Challenges Encountered

List specific difficulties:

- [what was difficult and why]

### Divergences from Plan

For each divergence, document:

**[Divergence Title]**

- Planned: [what the plan specified]
- Actual: [what was implemented instead]
- Reason: [why this divergence occurred]
- Type: [Better approach found | Plan assumption wrong | Security concern | Performance issue | Other]

### Skipped Items

List anything from the plan that was not implemented:

- [what was skipped]
- Reason: [why it was skipped]

### Recommendations

Based on this implementation, what should change for next time?

- Plan skill improvements: [suggestions]
- Execute skill improvements: [suggestions]
- CLAUDE.md additions: [suggestions]
