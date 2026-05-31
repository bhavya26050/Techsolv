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


def _date_start_iso_utc() -> str:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    start = datetime(year=now.year, month=now.month, day=now.day, tzinfo=timezone.utc)
    return start.isoformat()


def provider_credit_status(pair_id: str, provider: str, thread_id: str | None = None) -> dict[str, float]:
    cfg = settings()
    daily_reset = str(cfg.get("daily_reset_enabled", "true")).lower() in ("1", "true", "yes")
    date_from = _date_start_iso_utc() if daily_reset else None
    totals = credit_usage_totals(pair_id, thread_id=thread_id, provider=provider, date_from_iso=date_from)

    if provider == "gemini":
        budget_usd = max(0.0, _safe_float(cfg.get("gemini_credit_budget_usd", cfg.get("credit_budget_usd", 1.5)), 1.5))
    else:
        budget_usd = max(0.0, _safe_float(cfg.get("credit_budget_usd", 3.0), 3.0))

    used_usd = round(totals["credits_used"], 8)
    remaining_usd = round(max(0.0, budget_usd - used_usd), 8)
    used_pct = round((used_usd / budget_usd * 100.0) if budget_usd > 0 else 100.0, 2)
    return {
        "provider": provider,
        "budget_usd": budget_usd,
        "used_usd": used_usd,
        "remaining_usd": remaining_usd,
        "used_percent": min(100.0, used_pct),
        "input_tokens_est": totals["input_tokens"],
        "output_tokens_est": totals["output_tokens"],
    }
