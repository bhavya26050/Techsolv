from __future__ import annotations

import math

from .config import settings
from .storage import credit_usage_totals


def _safe_float(value: str, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def estimate_tokens_from_text(text: str) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    return int(math.ceil(len(stripped) / 4.0))


def estimate_credits_used_usd(input_tokens_est: int, output_tokens_est: int) -> float:
    config = settings()
    input_cost_per_million = _safe_float(config["input_cost_per_million_tokens"], 0.1)
    output_cost_per_million = _safe_float(config["output_cost_per_million_tokens"], 0.4)
    input_cost = (max(0, input_tokens_est) / 1_000_000.0) * input_cost_per_million
    output_cost = (max(0, output_tokens_est) / 1_000_000.0) * output_cost_per_million
    return round(input_cost + output_cost, 8)


def minimum_remaining_credit_usd() -> float:
    return max(0.0, _safe_float(settings()["minimum_remaining_credit_usd"], 0.05))


def credit_status(pair_id: str, thread_id: str | None = None) -> dict[str, float]:
    totals = credit_usage_totals(pair_id, thread_id)
    budget_usd = max(0.0, _safe_float(settings()["credit_budget_usd"], 3.0))
    used_usd = round(totals["credits_used"], 8)
    remaining_usd = round(max(0.0, budget_usd - used_usd), 8)
    used_pct = round((used_usd / budget_usd * 100.0) if budget_usd > 0 else 100.0, 2)
    return {
        "budget_usd": budget_usd,
        "used_usd": used_usd,
        "remaining_usd": remaining_usd,
        "used_percent": min(100.0, used_pct),
        "input_tokens_est": totals["input_tokens"],
        "output_tokens_est": totals["output_tokens"],
    }
