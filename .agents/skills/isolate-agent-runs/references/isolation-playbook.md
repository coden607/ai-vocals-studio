# Isolation Playbook — Pre-Flight Checklist & Sandbox Setup

Detailed procedures referenced by `SKILL.md`. Grounded in Cole Medin's
sandboxing/security walkthroughs (see `learning/cole-medin/notes/` in the
workspace: `zb2LyMro77M`, `SGodxQHnVxc`, `SWEThyRHMgQ`).

---

## 1. Full pre-flight isolation checklist

Run through this BEFORE any autonomous / skip-permissions agent run.
Every box must be checked; a single unchecked box is a stop.

### Sandbox & process isolation
- [ ] Agent runs inside a sandbox (VM/container), not on the host.
- [ ] Sandbox has its own runtime/Docker daemon (nested engine) so host
      containers and volumes are unreachable.
- [ ] Host home directory is NOT mounted. Only the task workspace is.
- [ ] For destructive or git-heavy tasks: repo is COPIED into the sandbox
      (`--clone` mode) — host git history/stashes unreachable.

### Secret & credential isolation
- [ ] In-sandbox probe: `!ls ~/.ssh` → **not found**.
- [ ] No host dotfiles, browser profiles, cloud credentials, or env files
      reachable from inside.
- [ ] Credentials issued for this run only: scoped (least privilege),
      short-lived, revocable on completion.
- [ ] Secrets injected via environment, never written to files the agent
      can read/echo, never pasted into prompts.

### Network egress
- [ ] Allow-list configured; default-deny (empty list) start.
- [ ] Only task-required hosts allowed: package registries, git remote,
      specific API endpoints.
- [ ] Verified in-sandbox: request to a non-allowed URL returns 403 from
      the proxy before leaving the box.
- [ ] Test method: ask the agent "can we reach X?" → expect 403 → allow X
      in sandbox config → retest succeeds.

### Context health (dumb-zone check)
- [ ] Session starts well under ~200–300K tokens of context.
- [ ] A handoff/state-file plan exists if the run may grow long
      (see `harness-engineering`).
- [ ] No autonomous run starts inside the dumb zone.

### Destructive-op gates
- [ ] Gates are deterministic (scripts/policy), not agent promises.
- [ ] Any `rm -rf`, prod DB op, force-push, history rewrite, or
      out-of-scope file deletion requires explicit human approval.
- [ ] Verification script (tests/lint/scan) defined BEFORE the run starts
      and run AFTER it finishes — green script = done, not agent's word.

### Cleanup & teardown
- [ ] Teardown path ready: `sbx rm` (or VM delete) destroys the sandbox
      and everything inside it.
- [ ] Run-scoped credentials revoked after teardown.
- [ ] Results extracted (diff/patch/PR) BEFORE teardown.

---

## 2. Docker Sandboxes (`sbx`) setup & commands

Reference sandbox for coding agents. Free; single-command install on
Mac/Windows (see the sbx docs); otherwise hand the docs URL to your coding
agent and have it perform the install inside a throwaway environment.

```bash
# Install Docker Sandboxes (Mac/Windows single command — see docs)

# Run coding agent inside sandbox (mounts current dir into VM)
sbx run claude

# Full isolation: sandbox works on a COPY of the repo
# Host git history, stashes, uncommitted files never touched
sbx run claude --clone

# Remove sandbox VM + everything inside it
sbx rm
```

First-run in-sandbox checks:

```bash
!ls            # mounted workspace visible
!ls ~/.ssh     # not found — host files invisible
```

Allow-list tuning loop (repeat until the task's hosts are reachable and
nothing else is):

1. In sandbox: attempt to reach a needed host → expect 403.
2. Add the host to the sandbox network config allow-list.
3. Retest → succeeds.
4. Attempt a non-allowed host → still 403.

---

## 3. Isolation-verification audit prompt

Give this to the agent the first time (and after any sandbox config change):

```text
"Can you see any of my host files, no matter how hard you try?
Can you reach a service on my host machine? Can you touch the host
Docker socket / mess with my containers?"
```

Expected result: EVERY probe fails. If any probe succeeds, stop, fix the
leak, and re-audit before real work.

---

## 4. Destructive-op gate examples (deterministic, not conversational)

Pattern: a script/policy makes the decision the same way every time.
A second agent reviewing is NOT a gate — same blind spots as the builder.

Examples:

- Filesystem: run with a read-only mount of the workspace; give write
  access only to an explicitly-scoped temp/build directory.
- Git: sandbox clone has no push credentials; pushing requires a
  separate, human-run step outside the sandbox.
- Database: no production DSN exists inside the sandbox; only a seeded
  disposable database is reachable.
- Dependencies: `npm audit` / `bandit` / `trivy` / SonarQube scan runs as a
  script node AFTER implementation, BEFORE merge — red blocks, green passes,
  and the agent iterates until green. (Sub-dependency CVEs count: a clean
  top-level package can still pull in vulnerable sub-dependencies.)
- Workflow form: `implement → open PR → deterministic scan → agent fixes
  red → re-scan → assert green → ready PR`.

Human checkpoints (never skipped): plan approval before implementation;
done-declaration after green verification. The agent never closes its own
loop on destructive work.

---

## 5. Failure stories to keep you honest

Real reported agent failures these gates exist to prevent:

- `rm -rf` of a home directory during an autonomous run.
- Production database wiped by a "cleanup" migration.
- `git stash` dropped — uncommitted work lost permanently.
- API keys exfiltrated after a prompt-injection payload in a fetched
  page/dependency instructed the agent to curl them out.

If your setup would have allowed any of these, the isolation is not done.
