"""Append-only token and cost log for paid pilot steps.

Events go to ``PAPER_CURATION_USAGE_LOG`` or
``pilot_artifacts/literacy/usage-events.jsonl``. Prompts and API keys are
never written.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

_LOCK = threading.Lock()

# README cost guide. Sonnet 5 intro rates ended 2026-08-31; this log uses
# the post-intro rates ($3 / $15 per 1M tokens).
_RATES = {
    "claude-sonnet-5": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-opus-5": (5.0, 25.0),
}


def rates_for(model: str) -> tuple[float, float]:
    if model in _RATES:
        return _RATES[model]
    low = (model or "").lower()
    if "opus" in low:
        return (5.0, 25.0)
    if "haiku" in low:
        return (1.0, 5.0)
    return (3.0, 15.0)


def log_path() -> Path:
    env = os.environ.get("PAPER_CURATION_USAGE_LOG", "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "pilot_artifacts" / "literacy" / "usage-events.jsonl"


def _usage_pair(usage) -> tuple[int, int]:
    if usage is None:
        return 0, 0
    if isinstance(usage, dict):
        return int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)
    return (
        int(getattr(usage, "input_tokens", 0) or 0),
        int(getattr(usage, "output_tokens", 0) or 0),
    )


def record(step: str, model: str, usage, *, note: str = "") -> dict:
    inp, out = _usage_pair(usage)
    pin, pout = rates_for(model)
    usd = inp * pin / 1_000_000 + out * pout / 1_000_000
    event = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "step": step,
        "model": model,
        "input_tokens": inp,
        "output_tokens": out,
        "usd": round(usd, 6),
        "note": note[:120],
    }
    path = log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def totals() -> dict:
    path = log_path()
    if not path.exists():
        return {"input_tokens": 0, "output_tokens": 0, "usd": 0.0, "events": 0, "by_step": {}}
    inp = out = 0
    usd = 0.0
    n = 0
    by_step: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        step = row.get("step") or "?"
        bucket = by_step.setdefault(step, {"input_tokens": 0, "output_tokens": 0, "usd": 0.0, "events": 0})
        ti = int(row.get("input_tokens") or 0)
        to = int(row.get("output_tokens") or 0)
        tu = float(row.get("usd") or 0)
        inp += ti
        out += to
        usd += tu
        n += 1
        bucket["input_tokens"] += ti
        bucket["output_tokens"] += to
        bucket["usd"] = round(bucket["usd"] + tu, 6)
        bucket["events"] += 1
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "usd": round(usd, 6),
        "events": n,
        "by_step": by_step,
    }


def projected_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = rates_for(model)
    return input_tokens * pin / 1_000_000 + output_tokens * pout / 1_000_000


def abort_if_over(limit: float = 3.0, extra_usd: float = 0.0, step: str = "") -> None:
    """Stop before a call whose worst-case addition would pass ``limit``."""
    spent = totals()["usd"]
    projected = spent + extra_usd
    if projected > limit:
        raise SystemExit(
            f"ABORT {step}: projected ${projected:.4f} exceeds ${limit:.2f} "
            f"(spent ${spent:.4f} + next ${extra_usd:.4f}). No further call."
        )
