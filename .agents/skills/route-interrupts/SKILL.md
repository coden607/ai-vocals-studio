---
name: route-interrupts
description: >-
  Handle mid-task user interruptions without losing the active task. USE when a
  user message arrives while long work is in flight (subagents running, batches
  processing, multi-step builds) and the message is NOT a stop order: classify
  it as (1) steering addition — folds into the current task, (2) side question
  — answer tersely then resume, (3) new task — queue behind current work and
  report position, or (4) urgent redirect — halt safely at the next checkpoint
  and pivot. Trigger phrases: "also do X" mid-run, "while you're at it",
  "quick question —", user changes requirements during a long operation, "add
  this to what you're doing", "queue this for after", "don't lose track of X".
  ALSO USE when several queued asks compete: keep one visible task stack,
  finish the current item, then pull the next automatically. DO NOT USE for
  genuine stop/abort messages ("stop", "forget it", "halt") — those execute
  immediately, safely.
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


# Route Interrupts

One rule above all: **an interruption adds to the work or queues behind it — it never silently kills the work already in flight.**

## The four-way classification

On ANY user message that arrives while a task is active, classify before answering:

| Class | Signal | Action |
|---|---|---|
| **Steering** | Refines/extends the current task ("also…", "make sure it…", "change X to Y") | Acknowledge in ≤1 line, fold into the plan, **continue without restarting** unless scope changed materially |
| **Side question** | Unrelated quick ask ("by the way, what's…") | Answer in ≤3 lines, then explicitly resume: "Back to `<task>` —" |
| **New task** | A full new ask ("next I need…", "after this do…") | Append to the task stack, reply with its queue position, start only when current completes — unless the user escalates |
| **Urgent redirect** | "Stop", "forget that", "actually, drop everything" | Halt at the next safe checkpoint (never mid-write), confirm what was preserved, then pivot |

Default assumption when unclear: **steering > new task.** A short message during active work usually means "fold this in," not "abandon ship."

## Protocol

1. **Extract the class first, answer second.** Never let a quick reply derail in-flight subagents or half-written files.
2. **Steering:** state the fold-in in one line ("Got it — adding Y to the current run"). Update the running plan/memory note. Do NOT restart completed work for cosmetic steering.
3. **Side question:** answer terse and completely, then one resume line naming the active task so the thread is never lost.
4. **New task:** maintain the stack visibly — "Queued: (1) current `<task>` → (2) `<new>`". When the current item finishes, pull the next automatically and announce it.
5. **Redirect:** pause at a checkpoint, snapshot state (what's done, what's preserved, what's killed), confirm with the user if anything valuable is in flight, then switch.
6. **Subagent hygiene:** in-flight subagent work is only killed deliberately — check what it already wrote to disk before deciding; partial output often counts as progress.
7. **Completion handoff:** when a task completes and the stack is non-empty, announce the next item in the same message. Silence about the queue reads as "done forever" and wastes the user's momentum.

## Anti-patterns

- Answering a side question and *never* resuming the original task.
- Treating every mid-task message as a full context switch.
- Letting a steering message trigger a full redo of finished steps.
- Killing background work without checking its on-disk output first.
- Queueing silently — the user should always know the stack's shape.
