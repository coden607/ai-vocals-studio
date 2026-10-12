# Decide → gate → act

```
state + questions
        │
        ▼
   decide.py  (Jev live or local)
        │
        ▼
   answers + policy
        │
   ┌────┴────┐
   │         │
  act     ask_human / stop
   │
   Grok writes, tools run, files ship
```

## Mixing priors (optional)

If you have a prior (last mode, user habit), mix:

`posterior ∝ prior^α * jev^(1-α)` with α default 0.25.

`decide.py --prior prior.json` applies this on choice and noul.

Hard-fact veto still wins — if state contains an explicit user mode name, skip Jev for that field.

## Pairing with adaptive-persona

1. Run `--bank mode-router`.
2. If policy.action is `act`, write current-mode.json and print the Mode lock line.
3. Work in that persona until switch / drop / task-type change.
4. On "switch mode", re-run the bank with the new state.
