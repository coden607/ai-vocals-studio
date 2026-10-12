---
name: isolate-agent-runs
description: >-
  Isolate autonomous / yolo-mode agent runs so a runaway agent cannot destroy
  the host — sandbox the run, control network egress, gate destructive
  operations, and protect secrets. Use when running a coding agent in
  skip-permissions / autonomous / yolo mode, when a session is approaching
  context limits ("dumb zone"), when wiring agent runs into CI or TaskFlow,
  or when an agent will touch production-shaped resources (databases, git
  remotes, SSH keys). Triggers: "yolo mode", "skip permissions", "run this
  autonomously", "let the agent loose on the repo", "sandbox the agent",
  "don't let it wipe anything", "dumb zone", "context limit errors",
  "agent deleted", "rm -rf", "agent keeps making mistakes late in a long
  session", "prompt guardrails keep failing".
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


# isolate-agent-runs

**YOLO / autonomous mode is an isolation problem, not a prompt problem.**
Never try to talk an agent out of being destructive. Put walls around it
so destruction is physically impossible, then let it run free inside.

## The core law

Prompt-based guardrails DO NOT WORK for long autonomous runs. An agent may
refuse a risky operation early in a chat, then comply after one follow-up.
Instructions — even system-prompt instructions — decay as context fills.

## The dumb zone

Past roughly **200–300K tokens of context**, agents forget instructions
(including system prompt) and start making catastrophic, confident
decisions. This is the dumb zone.

Signals you are entering it:
- The agent forgets earlier constraints it followed perfectly an hour ago.
- It "helpfully" runs destructive commands it refused to run earlier.
- It re-litigates settled decisions or re-litigates your guardrails.
- Late-session refactors that touch unrelated files; "cleanup" nobody asked for.
- It drops or rewrites git history, stashes, or config it was told to protect.

Rules:
1. **Split long sessions BEFORE the band.** Hand off to a fresh session with
   a state file (see `harness-engineering`) once you approach ~200K tokens.
2. **Never start an autonomous run inside the dumb zone.** A degraded agent
   plus full permissions is how machines get wiped.
3. **Judge isolation, not obedience.** Assume the agent WILL eventually try
   something you told it not to. Design for that moment.

## The isolation stack

Isolation has independent layers. Use as many as the risk warrants —
they stack, and each covers a different failure mode.

### 1. Hypervisor / process isolation
The agent gets full root power INSIDE a sandbox, but the sandbox cannot
touch the host filesystem, processes, or home directory. The host's
`~/.ssh`, browser profiles, dotfiles, and other projects are invisible.

### 2. Network egress control (allow-list)
Outbound requests to non-allowed URLs are blocked by the sandbox proxy
(403 before leaving the box). This is your main defense against
**prompt-injection exfiltration** — a malicious page or dependency README
tricking the agent into curling your API keys to an attacker.

Start with an empty allow-list and add only what the task needs:
package registries, the git remote, specific API hosts.

### 3. Nested engine isolation
The sandbox runs its own Docker daemon / runtime, so host containers,
volumes, and orchestration are untouched even if the agent runs
container commands.

### 4. Workspace isolation
Mount the working directory read-only where possible. For destructive
or git-heavy runs, give the agent a **copy** of the repo so host git
history, stashes, and uncommitted work are physically unreachable.

## Sandbox run pattern (verbatim commands)

Docker Sandboxes (`sbx`) is the reference implementation of this stack —
free, one-command install on Mac/Windows, purpose-built for coding agents.
Adapt the same pattern to any sandbox (VM, container, remote runner).

```bash
# Run the coding agent inside the sandbox (mounts CWD into the VM)
sbx run claude

# Full-isolation mode: sandbox works on a COPY of the repo.
# Host git history, stashes, and uncommitted files are never touched.
sbx run claude --clone

# Destroy the sandbox VM and everything inside it
sbx rm
```

In-sandbox verification (run these the first time, every time):

```bash
!ls            # mounted workspace visible
!ls ~/.ssh     # NOT FOUND — host files invisible
```

## Verify isolation BEFORE trusting the sandbox

Do not give an autonomous run real work until it passes this audit. Give
the agent this prompt inside the sandbox:

```text
"Can you see any of my host files, no matter how hard you try?
Can you reach a service on my host machine? Can you touch the host
Docker socket / mess with my containers?"
```

Expected: every probe fails. If ANY probe succeeds, the sandbox is leaking
— fix it before proceeding. See `references/isolation-playbook.md` for the
full pre-flight checklist.

## Secret & credential handling

Assume every credential reachable by the agent can eventually leak —
through the dumb zone, through prompt injection, through a dependency
README that says "run this to fix your build."

Rules:
1. **The host's secrets must be unreachable.** SSH keys, cloud credentials,
   browser cookies, and dotfiles stay OUTSIDE the sandbox. The `~/.ssh not
   found` check is your proof.
2. **Issue scoped, short-lived credentials.** Give the run a token that can
   only do what the task needs (e.g. one repo, read/write but not admin),
   and expire it when the run ends.
3. **Never put secrets in the prompt or the repo.** If a tool needs a key,
   inject it via environment variable inside the sandbox, not in files the
   agent can read and echo.
4. **Network allow-list limits blast radius.** Even if a key leaks, an
   egress proxy that only allows known hosts prevents it from being phoned
   home.

## Destructive-operation approval gates

These are the horror stories, straight from real agent runs — treat ANY of
them as an automatic STOP and route to a human, no matter what the agent
"says":

- `rm -rf` on anything outside an explicitly-scoped temp directory.
- Dropping, truncating, or migrating a production database.
- `git push --force`, history rewrite, or dropping a stash the user didn't
   explicitly ask to discard.
- Deleting or overwriting files the task never touched ("cleanup").
- Modifying CI/CD, deploy, or IAM configuration.
- Installing packages from unreviewed sources when a lockfile exists.

Implementation:
1. **Deterministic gates, not agent judgment.** Scripts and sandbox policy
   enforce the gate the same way every time. A second agent "reviewing" is
   probabilistic-on-probabilistic — same blind spots as the implementer.
   (See `references/isolation-playbook.md` for gate examples.)
2. **Prefer making destructive ops impossible over making them gated.**
   Read-only mounts, `--clone` mode, and disposable VMs beat approvals.
3. **Human checkpoints at plan approval and done-declaration** — the agent
   never closes its own loop on destructive work. (Overlaps `piv-loop`.)

## Deterministic verification after the run

An agent that finishes its task has NOT proven the task is done — late in
a session it may have "quietly noticed" an issue and only mentioned it in
passing while the fix never happened. After any isolated run:

1. Run the checks via a **script** (tests, lint, type-check, build) — not
   by asking the agent "did it work?"
2. Feed failures back to the agent to iterate; re-run the script; only a
   green script counts as done.
3. In workflow form: `implement → open PR → deterministic scan → agent
   fixes red → re-scan → assert green → ready`.

## Pre-flight checklist (summary)

Full checklist in `references/isolation-playbook.md`. Minimum before any
autonomous run:

- [ ] Run happens inside a sandbox (never yolo on the host).
- [ ] `~/.ssh` and host secrets confirmed unreachable in-sandbox.
- [ ] Network allow-list set; only task-required hosts reachable.
- [ ] Workspace mounted read-only, or repo cloned (`--clone`) for destructive work.
- [ ] Scoped, expirable credentials issued — no long-lived keys.
- [ ] Destructive-op gates scripted, not prompt-based.
- [ ] Session well under the dumb-zone band (~200–300K tokens).
- [ ] Verification script defined BEFORE the run starts.
- [ ] Cleanup path known (`sbx rm` / VM teardown).

## Anti-patterns

- "I told it not to delete things, so it's safe." — prompts decay; isolation doesn't.
- Running skip-permissions / yolo mode directly on the host. Ever.
- Letting one mega-session grind to 500K tokens "to save setup time."
- Approving destructive ops via agent conversation instead of a script gate.
- Trusting a sandbox without running the isolation-verification audit.
- Mounting the whole home directory "for convenience."

## Related skills

- `piv-loop` — human-owned checkpoints (plan approval, done-declaration)
  that pair with these isolation walls.
- `harness-engineering` — state files, handoffs, and multi-session loops
  that keep runs short and out of the dumb zone.
- `taskflow` — durable orchestration for isolated long-running jobs.
