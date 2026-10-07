---
name: compress-token-spend
description: >-
  Cut token and dollar spend across every model call without cutting quality.
  USE when: choosing which model tier a task deserves (frontier is the
  last resort, not the default); structuring prompts to maximize provider
  prompt-caching hits; deciding what deserves a full LLM call vs a Jev
  decision vs a regex; writing or reviewing agent replies that are longer
  than they need to be (output tokens cost 3-5x input); setting up quality
  grading loops (grade a 10% sample, not 100%); loading context before a
  task (search first, dump files second); scheduling recurring reviews of
  model prices. Trigger phrases: "save tokens", "cheaper", "reduce cost",
  "prompt caching", "why is this so expensive", "trim the context",
  "grade a sample", "which model should handle this", "token budget".
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


# Compress Token Spend

Spend tokens like they cost money — because they do. Five levers, in order of typical impact:

## 1. Route before you spend

- Classify the duty FIRST, model SECOND. Simple/chitchat/reasoning/code/research/long-doc/creative/frontier each get the cheapest capable model, not the most capable one.
- Frontier models are for genuinely novel, high-stakes, or multi-constraint work — typically <20% of traffic. If everything is "important," nothing is, and the bill shows it.
- Repeated classification/routing/guardrail decisions go to a system-one decision model (Jev) or regex — see the judge ladder in `enforce-with-hooks`. A decision that costs 1/1000th of an LLM call is the same decision.
- Right-size subagents: give workers the smallest context that can do the job; batch work to amortize the bootstrap.

## 2. Structure for the cache

Provider prompt caching (automatic on most modern providers via OpenRouter, Kimi, Anthropic, Gemini, DeepSeek) discounts repeated input — but only prefixes that are byte-identical hit the cache:

- **Stable first, variable last.** System prompt, rules, skills, and conversation shape go at the FRONT; user-specific content, timestamps, and random IDs go at the END. A nonce in paragraph one invalidates everything after it.
- Reuse sessions for long threads instead of re-sending full history in new calls.
- Don't paraphrase standing instructions between calls — keep them verbatim.
- Cache-aware test: if two requests share nothing but the model name, you built the prompt backwards.

## 3. Output discipline (the priciest line)

Output tokens cost 3–5× input on most models, and verbosity is a spending decision:

- Shortest answer that is COMPLETE. No preamble ("Great question!"), no recap of what was just done, no restating the user's message.
- Prefer structured density (table, list, one-liner) over paragraph prose when the surface allows it.
- When writing code/docs/emails through an agent, cap length explicitly ("≤150 words", "under 30 lines") — unbounded output is unbounded spend.
- For multi-step work, report deltas and decisions, not narration.

## 4. Judge a sample, not the stream

Quality loops drown in cost when every outcome gets a grader pass:

- Grade a random 10% sample; ALWAYS grade failures in full and always grade the first use of any new model tier.
- Implement: `JEV_GRADE_SAMPLE=0.10` env (duty-dispatch's dispatch.py `--outcome` mode honors it and appends to outcomes.jsonl). Set to 1.0 for debugging only.
- If the sample's pass rate drifts down, widen the sample — adaptive beats static.

## 5. Load less context

- Search before you dump: semantic recall + targeted reads beat pasting whole files or histories.
- Digests over raw: a 600-token study note replaces a 20k-token transcript forever.
- Subagents inherit the workspace, not your whole conversation — spawn light, hand off state files.
- Prune dead memory on a cadence; every stale line taxes every future call.

## Standing cadence

Monthly: review the tier map against current market prices (models drift down; new cheap entrants appear). Daily: apply levers 1–5 without being asked. Both are part of the job, not extra credit.
