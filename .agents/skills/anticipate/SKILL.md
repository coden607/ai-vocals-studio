---
name: anticipate
description: Predict and surface the highest-value likely next action while preserving user control. Use when a task has an obvious follow-up, missing validation, likely failure point, repeated workflow, or opportunity to eliminate a future manual step. Also use at the end of substantive ContinuityOS-routed work. Trigger phrases include anticipate next, what's next, proactive next step, or when finishing a coding/legal/PWA task.
argument-hint: "[optional current task state]"
---

# Anticipate

Move the active task farther toward completion with the least unnecessary interaction. Source of truth: https://github.com/coden607/anticipate (project-skills/anticipate/SKILL.md and the engine in src/anticipate/).

## Decision loop

1. Identify the explicit requested outcome.
2. Determine current verified state.
3. Identify the most likely blocker or useful next step.
4. Rank possible next actions by expected usefulness, confidence, reversibility, cost, and user effort.
5. Execute only actions already authorized.
6. Surface high-value unauthorized actions as a concise recommendation.
7. Keep working on the original task.

## Confidence bands

- **High**: The next action follows directly from verified state. Proceed if authorized (do_now).
- **Medium**: Probably useful but assumptions remain. State the assumption briefly (suggest).
- **Low**: Do not distract the user with speculative suggestions. Suppress.

## Classification

- **do_now**: already authorized, reversible, and directly advances the task.
- **suggest**: useful but requires user choice.
- **ask_first**: destructive, irreversible, monetary, production-facing, external communication, secret handling, or materially ambiguous.

## Never

- Claim an action completed without verification.
- Silently spend money.
- Send communications without authorization.
- Deploy production without authorization.
- Delete or overwrite valuable state without authorization.
- Expose secrets.
- Derail the current task to pursue an optional idea.

## Output discipline

Prefer:

    result -> blocker -> next action

Avoid:

    preamble -> narration -> recap -> repeated context

When no useful anticipation exists, simply complete the requested task.

## Integration with ContinuityOS

This skill is registered as a zero-token local skill/plugin for ContinuityOS (see packs/anticipate/pack.json and plugin.json in the anticipate repo). Prefer it over model calls for next-action ranking.

## Resources

- Full engine and tests: https://github.com/coden607/anticipate
- ContinuityOS integration notes: docs/continuityos-integration.md in that repo
