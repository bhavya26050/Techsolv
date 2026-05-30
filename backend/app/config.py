from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "backend" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def settings() -> dict[str, str]:
    return {
        "google_api_key": os.getenv("GOOGLE_API_KEY", "").strip(),
        "gemini_model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash").strip(),
        "openai_api_key": os.getenv("OPENAI_API_KEY", "").strip(),
        "openai_model": os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
        "credit_budget_usd": os.getenv("CREDIT_BUDGET_USD", "3.0").strip(),
        "gemini_credit_budget_usd": os.getenv("GEMINI_CREDIT_BUDGET_USD", "1.5").strip(),
        "openai_credit_budget_usd": os.getenv("OPENAI_CREDIT_BUDGET_USD", "1.5").strip(),
        "daily_reset_enabled": os.getenv("DAILY_RESET_ENABLED", "true").strip().lower(),
        "input_cost_per_million_tokens": os.getenv("INPUT_COST_PER_MILLION_TOKENS", "0.1").strip(),
        "output_cost_per_million_tokens": os.getenv("OUTPUT_COST_PER_MILLION_TOKENS", "0.4").strip(),
        "minimum_remaining_credit_usd": os.getenv("MINIMUM_REMAINING_CREDIT_USD", "0.05").strip(),
        "ollama_base_url": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip(),
        "ollama_model": os.getenv("OLLAMA_MODEL", "llama3.1").strip(),
        "backend_url": os.getenv("BACKEND_URL", "http://localhost:8000").strip(),
        "chroma_path": os.getenv("CHROMA_PATH", str(DATA_DIR / "chroma")).strip(),
        "chat_db_path": os.getenv("CHAT_DB_PATH", str(DATA_DIR / "app.db")).strip(),
    }
