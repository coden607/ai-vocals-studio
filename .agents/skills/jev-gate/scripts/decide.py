#!/usr/bin/env python3
"""Jev-shaped decision runner.

Live TypeSafe/OpenRouter when a key is present; otherwise a local
keyword/rubric scorer that emits the same JSON answers + a policy gate.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[1]
BANKS = SKILL_ROOT / "references" / "banks"


def softmax(xs: list[float]) -> list[float]:
    m = max(xs) if xs else 0.0
    ex = [math.exp(x - m) for x in xs]
    s = sum(ex) or 1.0
    return [e / s for e in ex]


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9][a-z0-9+\-/#]{1,}", text.lower()))


def flatten_state(state: Any) -> str:
    if isinstance(state, str):
        return state
    return json.dumps(state, ensure_ascii=False)


def score_text(hay: set[str], needle: str) -> float:
    words = tokenize(needle)
    if not words:
        return 0.15
    hit = len(words & hay)
    # light stemming via prefix: grant/funding vs grants
    extra = 0
    for w in words:
        if any(h.startswith(w[:4]) and len(w) >= 4 for h in hay):
            extra += 0.25
    return hit + extra


def local_noul(state_l: str, q: dict) -> dict:
    hay = tokenize(state_l)
    crit = q.get("criteria") or {}
    t = str(crit.get("true") or q.get("instructions") or "")
    f = str(crit.get("false") or "")
    st = score_text(hay, t) + score_text(hay, str(q.get("instructions") or ""))
    sf = score_text(hay, f) if f else 0.4
    # map to 0.08..0.92 so we never claim certainty locally
    p = 0.08 + 0.84 * (st / (st + sf + 0.35))
    p = max(0.08, min(0.92, p))
    return {"type": "noul", "noul": round(p, 4)}


def local_choice(state_l: str, q: dict) -> dict:
    hay = tokenize(state_l)
    crit = q.get("criteria") or q.get("options") or {}
    if isinstance(crit, list):
        crit = {str(i): str(v) for i, v in enumerate(crit)}
    labels = list(crit.keys())
    raw = []
    for lab in labels:
        blob = f"{lab} {crit[lab]}"
        raw.append(score_text(hay, blob) + 0.15 * score_text(hay, lab.replace("-", " ")))
    if not raw:
        return {"type": "choice", "choice": None, "confidence": 0.0, "probabilities": {}}
    # mild prior toward first? no — uniform bias
    raw = [r + 0.35 for r in raw]
    probs = softmax(raw)
    dist = {lab: round(p, 4) for lab, p in zip(labels, probs)}
    best = max(dist, key=dist.get)
    # confidence = best - second
    ordered = sorted(dist.values(), reverse=True)
    gap = ordered[0] - (ordered[1] if len(ordered) > 1 else 0)
    conf = round(min(0.95, ordered[0] * (0.55 + gap)), 4)
    return {
        "type": "choice",
        "choice": best,
        "confidence": conf,
        "probabilities": dist,
    }


def local_score(state_l: str, q: dict) -> dict:
    hay = tokenize(state_l)
    crit = q.get("criteria") or ["low", "mid", "high"]
    if isinstance(crit, dict):
        legend = {str(k): str(v) for k, v in crit.items()}
        keys = sorted(legend, key=lambda k: int(k) if str(k).isdigit() else k)
    else:
        keys = [str(i) for i in range(len(crit))]
        legend = {str(i): str(v) for i, v in enumerate(crit)}
    raw = [score_text(hay, legend[k]) + 0.2 * i / max(len(keys) - 1, 1) for i, k in enumerate(keys)]
    # high-stakes lexicon bump
    hi = tokenize("court filing lawsuit grant money medicaid habeas serve irreversible")
    if hay & hi and keys:
        raw[-1] += 1.4
    probs = softmax([r + 0.4 for r in raw])
    dist = {k: round(p, 4) for k, p in zip(keys, probs)}
    expected = sum(int(k) * dist[k] if k.isdigit() else i * dist[k] for i, k in enumerate(keys))
    best = max(dist, key=dist.get)
    conf = round(dist[best], 4)
    return {
        "type": "score",
        "score": round(expected, 4),
        "confidence": conf,
        "probabilities": dist,
        "legend": legend,
    }


def local_evaluate(state: Any, questions: dict) -> dict:
    text = flatten_state(state)
    answers = {}
    for name, q in questions.items():
        t = (q.get("type") or "noul").lower()
        if t == "choice":
            answers[name] = local_choice(text, q)
        elif t == "score":
            answers[name] = local_score(text, q)
        else:
            answers[name] = local_noul(text, q)
    return answers


def mix_priors(answers: dict, prior: dict, alpha: float = 0.25) -> dict:
    """posterior ∝ prior^α * jev^(1-α) for overlapping noul/choice."""
    out = json.loads(json.dumps(answers))
    for key, ans in out.items():
        if key not in prior:
            continue
        pr = prior[key]
        if ans.get("type") == "noul" and "noul" in pr:
            p = (float(pr["noul"]) ** alpha) * (float(ans["noul"]) ** (1 - alpha))
            # renormalize against complement similarly
            c = ((1 - float(pr["noul"])) ** alpha) * ((1 - float(ans["noul"])) ** (1 - alpha))
            ans["noul"] = round(p / (p + c) if (p + c) else ans["noul"], 4)
        if ans.get("type") == "choice" and "probabilities" in pr:
            mixed = {}
            for lab, jp in ans["probabilities"].items():
                pp = float(pr["probabilities"].get(lab, 1.0 / max(len(ans["probabilities"]), 1)))
                mixed[lab] = (pp ** alpha) * (float(jp) ** (1 - alpha))
            s = sum(mixed.values()) or 1.0
            mixed = {k: round(v / s, 4) for k, v in mixed.items()}
            best = max(mixed, key=mixed.get)
            ordered = sorted(mixed.values(), reverse=True)
            gap = ordered[0] - (ordered[1] if len(ordered) > 1 else 0)
            ans["probabilities"] = mixed
            ans["choice"] = best
            ans["confidence"] = round(min(0.95, ordered[0] * (0.55 + gap)), 4)
    return out


def policy_from(answers: dict, floor: float) -> dict:
    reasons = []
    action = "act"
    # contradiction helpers
    lane = (answers.get("lane") or {}).get("choice")
    urg = answers.get("urgency")
    if lane == "ignore" and urg and float(urg.get("score") or 0) >= 1.6:
        action = "ask_human"
        reasons.append("urgency high but lane=ignore")
    if (answers.get("repeat_failure") or {}).get("noul", 0) >= 0.80:
        action = "stop"
        reasons.append("repeat_failure noul>=0.80")
    if (answers.get("irreversible") or {}).get("noul", 0) >= 0.75 and lane == "act":
        action = "ask_human"
        reasons.append("irreversible + act")
    # confidence floors on choices
    for name, ans in answers.items():
        if ans.get("type") == "choice":
            if float(ans.get("confidence") or 0) < floor:
                action = "ask_human"
                reasons.append(f"{name} confidence {ans.get('confidence')} < floor {floor}")
        if ans.get("type") == "noul" and name in {"lock_now", "file_ready"}:
            # low lock_now → don't lock
            if name == "lock_now" and float(ans.get("noul") or 0) < floor:
                if action == "act":
                    action = "ask_human"
                reasons.append(f"lock_now {ans.get('noul')} < floor")
    if not reasons:
        reasons.append("clears floor; no disagreement")
    return {"action": action, "reason": "; ".join(reasons), "floor": floor}


def live_evaluate(state: Any, questions: dict) -> tuple[dict, str, str] | None:
    ts = os.environ.get("TYPESAFE_API_KEY")
    ork = os.environ.get("OPENROUTER_API_KEY")
    if ts:
        url = os.environ.get("TYPESAFE_API_URL", "https://api.typesafe.ai/v1/systemone")
        model = os.environ.get("JEV_MODEL", "jev-1.13")
        key = ts
        provider = "typesafe"
    elif ork:
        url = "https://openrouter.ai/api/alpha/decisions"
        model = os.environ.get("JEV_MODEL", "typesafe/jev-1.13")
        key = ork
        provider = "openrouter"
    else:
        return None
    body = json.dumps({"model": model, "state": state, "questions": questions}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://x.ai",
            "X-Title": "jev-gate-skill",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"[warn] live Jev failed ({exc}); falling back to local", file=sys.stderr)
        return None
    answers = data.get("answers") or data.get("data", {}).get("answers")
    if not answers:
        return None
    return answers, provider, data.get("model") or model


def load_bank(name: str) -> dict:
    path = BANKS / f"{name}.json"
    if not path.exists():
        raise SystemExit(f"unknown bank: {name} ({path})")
    return json.loads(path.read_text())


def main() -> int:
    p = argparse.ArgumentParser(description="Jev-shaped decide + policy gate")
    p.add_argument("--file", help="full request JSON (state + questions)")
    p.add_argument("--bank", help="named bank in references/banks")
    p.add_argument("--state", help="state string")
    p.add_argument("--state-file", help="read state from file")
    p.add_argument("--prior", help="prior JSON for mixing")
    p.add_argument("--alpha", type=float, default=0.25)
    p.add_argument("--floor", type=float, default=0.72)
    p.add_argument("--force-local", action="store_true")
    p.add_argument("--out", help="write JSON here as well as stdout")
    args = p.parse_args()

    if args.file:
        req = json.loads(Path(args.file).read_text())
        state = req.get("state", "")
        questions = req.get("questions") or {}
    else:
        if args.bank:
            bank = load_bank(args.bank)
            questions = bank["questions"]
        else:
            raise SystemExit("need --file or --bank")
        if args.state_file:
            state = Path(args.state_file).read_text()
        else:
            state = args.state or sys.stdin.read()

    provider = "local-heuristic"
    model = "local-jev-gate"
    answers = None
    if not args.force_local:
        live = live_evaluate(state, questions)
        if live:
            answers, provider, model = live
    if answers is None:
        answers = local_evaluate(state, questions)

    if args.prior:
        prior = json.loads(Path(args.prior).read_text())
        answers = mix_priors(answers, prior, args.alpha)

    result = {
        "provider": provider,
        "model": model,
        "answers": answers,
        "policy": policy_from(answers, args.floor),
    }
    text = json.dumps(result, indent=2)
    print(text)
    if args.out:
        Path(args.out).write_text(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
