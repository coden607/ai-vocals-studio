# Factory rules

Level 3. A person plans the release and merges. The factory does not merge.

- Never force-push.
- Never skip the validation command.
- Never merge your own pull request.
- Never read or print secrets, tokens, or `.env` values.
- Stop after 3 failed attempts on the same blocker and leave the pull request open.
- Do not edit `MISSION.md`, `FACTORY_RULES.md`, `harness/harness.config.json`, `harness/END-TO-END.md`, or `.factory/holdout/`.
