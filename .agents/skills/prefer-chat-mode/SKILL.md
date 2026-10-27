---
name: prefer-chat-mode
description: Prefers Chat mode when Work mode adds no necessary capability, while preserving the active task. Use when the user says "get out of work mode", "go into chat mode", "work mode is unnecessary", "just talk", or invokes /prefer-chat-mode; also apply at task transitions when remaining work can be completed in Chat.
---

# Prefer Chat Mode

- Assess the remaining task using the capabilities actually available in each mode. Prefer Chat for conversation, explanations, call guidance, and other work that can be completed there.
- Retain Work only while a required capability, active operation, or pending approval depends on it. Do not assume that all searches, links, files, or app actions require Work.
- Honor an explicit mode request as soon as the current operation can safely hand off. Never cancel authorized work merely to change modes.
- Preserve the objective, verified results, user constraints, permissions, and next step. Carry forward call outcomes and excluded numbers; never restart the task or repeat a completed call.
- Use an exposed mode-switch capability when available and authorized. Confirm its returned state before claiming the switch succeeded.
- If no mode-switch capability exists, state once: "I can't switch the app mode directly; switch to Chat and we'll continue." Give exact UI steps only when verified for the current app.
- Continue any permitted work while awaiting the user's switch. Do not repeatedly prompt, invent a mode-control tool, or claim that conversational style changes the app's mode.
- Keep the handoff to one or two sentences. Load only relevant context and skills. Do not claim token savings or permanent installation without evidence.
