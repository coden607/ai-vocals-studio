# Jev request / response shape

## Request

```json
{
  "model": "typesafe/jev-1.13",
  "state": "plain text or JSON object",
  "questions": {
    "is_bug": {
      "type": "noul",
      "instructions": "Is the customer reporting a software defect?",
      "criteria": {
        "true": "Broken or unexpected product behavior.",
        "false": "Question, request, or billing only."
      }
    },
    "team": {
      "type": "choice",
      "instructions": "Which team owns this?",
      "criteria": {
        "payments": "Charges, refunds, checkout money path",
        "frontend": "UI, blank screens, CSS",
        "account": "Login, profile, permissions"
      }
    },
    "urgency": {
      "type": "score",
      "instructions": "How urgent is this?",
      "criteria": ["Can wait", "This week", "Now"]
    }
  }
}
```

Score `criteria` may be an array (legend by index) or an object keyed `0`..`n`.

## Response (normalized by decide.py)

```json
{
  "provider": "local-heuristic",
  "model": "local-jev-gate",
  "answers": {
    "is_bug": { "type": "noul", "noul": 0.91 },
    "team": {
      "type": "choice",
      "choice": "frontend",
      "confidence": 0.64,
      "probabilities": { "frontend": 0.64, "payments": 0.28, "account": 0.08 }
    },
    "urgency": {
      "type": "score",
      "score": 2.1,
      "confidence": 0.55,
      "probabilities": { "0": 0.1, "1": 0.2, "2": 0.7 },
      "legend": { "0": "Can wait", "1": "This week", "2": "Now" }
    }
  },
  "policy": {
    "action": "ask_human",
    "reason": "choice confidence 0.64 < floor 0.72",
    "floor": 0.72
  }
}
```

## Live endpoints (only if a key exists)

- TypeSafe direct — `TYPESAFE_API_KEY` → `https://api.typesafe.ai` (wins)
- OpenRouter — `OPENROUTER_API_KEY` → `POST https://openrouter.ai/api/alpha/decisions` with `model: typesafe/jev-1.13`

Chat completions will reject Jev. Do not use them.
