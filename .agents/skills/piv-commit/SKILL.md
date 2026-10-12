---
name: piv-commit
description: Creates a new git commit for all uncommitted changes with an atomic, conventionally-tagged message. Use when work is complete and ready to be committed.
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


# Commit: Create a New Commit

Create a new commit for all of our uncommitted changes.

## Process

0. **Read this project's conventions.** If `.claude/references/conventions.md` exists, read its `## commit`
   section and follow it — those rules win over the defaults below. That file is where a project's specifics
   live; this skill stays general.
1. Run `git status && git diff HEAD && git status --porcelain` to see what files are uncommitted.
2. Add the untracked and changed files.
3. Write an atomic commit message with an appropriate, descriptive summary.
4. Add a tag such as `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, etc. that reflects our work.

## Output

A single commit containing all uncommitted changes, with a conventional-commit-style message
(`<tag>: <atomic description>`) that accurately reflects the work done.

After the commit succeeds, print two clearly labelled summaries:

### What Changed
One short paragraph (3–6 sentences) describing the feature/fix/refactor that was committed — what problem it solves and what files were the key touch points. Write for a developer skimming the git log.

### AI Layer Changes
Only include this section if any files under `.claude/` were modified or added (CLAUDE.md, `.claude/references/`, `.claude/skills/`, `.claude/agents/`, etc.).

List each changed AI-layer file with a one-line note on what evolved and why. If nothing in `.claude/` changed, omit this section entirely.
