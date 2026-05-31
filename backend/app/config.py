from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def settings() -> dict[str, str]:
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                os.environ.setdefault(key, val)
        except Exception:
            pass

    return {
        "google_api_key": os.getenv("GOOGLE_API_KEY", "").strip(),
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip(),
        "credit_budget_usd": os.getenv("CREDIT_BUDGET_USD", "3.0").strip(),
        "gemini_credit_budget_usd": os.getenv("GEMINI_CREDIT_BUDGET_USD", "1.5").strip(),
        "mongo_uri": os.getenv("MONGO_URI", "").strip(),
        "mongo_db_name": os.getenv("MONGO_DB_NAME", "techsolv").strip(),
        "daily_reset_enabled": os.getenv("DAILY_RESET_ENABLED", "true").strip().lower(),
        "input_cost_per_million_tokens": os.getenv("INPUT_COST_PER_MILLION_TOKENS", "0.1").strip(),
        "output_cost_per_million_tokens": os.getenv("OUTPUT_COST_PER_MILLION_TOKENS", "0.4").strip(),
        "minimum_remaining_credit_usd": os.getenv("MINIMUM_REMAINING_CREDIT_USD", "0.05").strip(),
    }
