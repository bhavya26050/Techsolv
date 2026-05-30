from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import settings


def _db_path() -> Path:
    return Path(settings()["chat_db_path"])


def connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def initialize() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pairs (
                pair_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_lookup ON chat_messages(pair_id, thread_id, id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS credit_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pair_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                input_tokens_est INTEGER NOT NULL,
                output_tokens_est INTEGER NOT NULL,
                credits_used_usd REAL NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_credit_lookup ON credit_usage(pair_id, thread_id, id)")


def save_pair(pair_id: str, payload: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO pairs (pair_id, payload_json, created_at) VALUES (?, ?, ?)",
            (pair_id, json.dumps(payload), datetime.now(timezone.utc).isoformat()),
        )


def load_pair(pair_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT payload_json FROM pairs WHERE pair_id = ?", (pair_id,)).fetchone()
    if not row:
        return None
    return json.loads(row["payload_json"])


def append_message(pair_id: str, thread_id: str, role: str, content: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO chat_messages (pair_id, thread_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (pair_id, thread_id, role, content, datetime.now(timezone.utc).isoformat()),
        )


def load_messages(pair_id: str, thread_id: str, limit: int = 12) -> list[dict[str, str]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT role, content
            FROM chat_messages
            WHERE pair_id = ? AND thread_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (pair_id, thread_id, limit),
        ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


def record_credit_usage(
    *,
    pair_id: str,
    thread_id: str,
    provider: str,
    model: str,
    input_tokens_est: int,
    output_tokens_est: int,
    credits_used_usd: float,
) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO credit_usage (
                pair_id,
                thread_id,
                provider,
                model,
                input_tokens_est,
                output_tokens_est,
                credits_used_usd,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pair_id,
                thread_id,
                provider,
                model,
                input_tokens_est,
                output_tokens_est,
                credits_used_usd,
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def credit_usage_totals(
    pair_id: str,
    thread_id: str | None = None,
    provider: str | None = None,
    date_from_iso: str | None = None,
) -> dict[str, float]:
    """
    Returns aggregated totals for credit usage filtered by optional thread, provider, and date_from_iso (inclusive).
    If date_from_iso is provided it should be an ISO timestamp string; commonly used to implement daily resets.
    """
    with connect() as conn:
        clauses = ["pair_id = ?"]
        params: list[object] = [pair_id]
        if thread_id:
            clauses.append("thread_id = ?")
            params.append(thread_id)
        if provider:
            clauses.append("provider = ?")
            params.append(provider)
        if date_from_iso:
            clauses.append("created_at >= ?")
            params.append(date_from_iso)

        where = " AND ".join(clauses)
        sql = f"""
            SELECT
                COALESCE(SUM(input_tokens_est), 0) AS input_tokens,
                COALESCE(SUM(output_tokens_est), 0) AS output_tokens,
                COALESCE(SUM(credits_used_usd), 0.0) AS credits_used
            FROM credit_usage
            WHERE {where}
            """
        row = conn.execute(sql, tuple(params)).fetchone()

    return {
        "input_tokens": float(row["input_tokens"]),
        "output_tokens": float(row["output_tokens"]),
        "credits_used": float(row["credits_used"]),
    }
