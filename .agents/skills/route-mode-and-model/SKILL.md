---
name: route-mode-and-model
description: >-
  Route each task to the cheapest capable execution mode and model tier.
  Bidirectionally recommends Chat vs Work based on task requirements, and
  selects the smallest capable model tier using token/cost discipline.
  USE when deciding whether a task needs Work/computer-use/connected-app
  execution, whether plain Chat is enough, or which model tier should handle
  the task. Never silently switch modes or silently fall back to a paid/higher
  tier.
---

# Route Mode and Model

Use this skill before expensive or multi-step work. Its job is to make two
independent decisions:

1. **Execution mode:** Chat or Work.
2. **Model tier:** cheapest capable tier for the task.

Apply `compress-token-spend` and `route-with-jev` as supporting policy.

## 1. Mode routing

Choose **Chat** when the task can be completed directly in the current
conversation with available chat-native tools and does not need a persistent
workspace, cloud browser/computer interaction, or long-running multi-app
workflow.

Choose **Work** when the task materially benefits from or requires one or more
of:

- cloud-browser or GUI interaction across websites/apps;
- substantial multi-step execution across files/apps;
- persistent artifact/workspace creation and iteration;
- computer-use style navigation;
- extended autonomous implementation where Work materially reduces manual
  handoffs.

### Bidirectional behavior

- If currently in **Work** and Chat is sufficient, recommend switching to Chat.
- If currently in **Chat** and Work is materially useful or required,
  recommend switching to Work.
- Present the recommendation as a single clear one-click choice when the
  product surface supports it.
- **Never silently switch modes.**
- If switching would not materially improve cost, capability, or completion,
  stay in the current mode and continue.

## 2. Model routing

Classify duty first, model second. Use the smallest tier that can reliably
complete the task.

Default tier map:

- **chitchat** — casual conversation, tiny clarifications.
- **simple** — extraction, rewrite, formatting, short factual transforms.
- **code** — ordinary coding, debugging, patches, scripts.
- **reasoning** — planning, analysis, multi-constraint decisions.
- **research** — web/source synthesis and current-information tasks.
- **long-doc** — large-document reading/synthesis.
- **creative** — substantial original creative generation.
- **frontier** — genuinely novel, high-stakes, deeply multi-constraint work
  where lower tiers are insufficient.

Rules:

- Prefer the cheapest capable tier.
- Do not use frontier by default.
- Do not silently upgrade to a paid/higher tier.
- If the selected tier fails or confidence is inadequate, escalate one tier
  at a time.
- Respect explicit user pins/overrides.
- Re-check current price/capability mappings periodically; model names and
  prices change, while these abstract tiers remain stable.

## 3. Token-efficiency rules

Apply `compress-token-spend`:

- Search/read only the minimum relevant context before loading whole files.
- Keep stable prompt material first and variable material last for cache hits.
- Keep outputs as short as possible while complete.
- Avoid repeating state already present in the active context.
- Use deterministic rules for deterministic decisions; use Jev only for
  repeated fuzzy classification where it is actually cheaper.
- Sample quality grading rather than grading every successful run; always
  inspect failures and first use of a new tier.

## 4. Routing decision order

Use this order every time:

1. Can the task be solved deterministically without another model call?
2. Does it require Work-only capabilities?
3. If not, keep/use Chat.
4. Classify the task duty.
5. Select the cheapest capable model tier.
6. Execute.
7. Escalate only if the selected tier is inadequate.

## 5. One-click recommendation text

When a mode change is warranted, use concise UI-facing copy:

- **To Chat:** "This task doesn’t need Work. Switch to Chat to save Work usage."
- **To Work:** "This task needs Work capabilities. Switch to Work to continue."

If the surface can render an action/button, attach the recommendation to that
action. If it cannot, state the recommendation once and continue with what is
possible in the current mode.

## 6. Safety / user control

Mode routing is advisory unless the host product provides an explicit switch
action. Never claim a switch happened unless the product confirms it.

Model routing must preserve the user's explicit rule: cheapest capable model,
mid-conversation changes allowed, and no silent paid fallback.
