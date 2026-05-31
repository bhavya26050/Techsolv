from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import threading
from typing import Any

from .config import settings


@dataclass(frozen=True)
class StorageConfig:
    mongo_uri: str
    mongo_db_name: str
    mongo_server_selection_timeout_ms: int
    mongo_connect_timeout_ms: int


_MONGO_CLIENT: Any | None = None
_MONGO_CLIENT_LOCK = threading.Lock()


def _storage_config() -> StorageConfig:
    cfg = settings()
    try:
        server_selection_timeout_ms = int(cfg.get("mongo_server_selection_timeout_ms", "5000"))
    except Exception:
        server_selection_timeout_ms = 5000
    try:
        connect_timeout_ms = int(cfg.get("mongo_connect_timeout_ms", "5000"))
    except Exception:
        connect_timeout_ms = 5000
    return StorageConfig(
        mongo_uri=cfg.get("mongo_uri", "").strip(),
        mongo_db_name=cfg.get("mongo_db_name", "techsolv").strip() or "techsolv",
        mongo_server_selection_timeout_ms=server_selection_timeout_ms,
        mongo_connect_timeout_ms=connect_timeout_ms,
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _mongo_client():
    global _MONGO_CLIENT
    if _MONGO_CLIENT is not None:
        return _MONGO_CLIENT
    with _MONGO_CLIENT_LOCK:
        if _MONGO_CLIENT is not None:
            return _MONGO_CLIENT
        cfg = _storage_config()
        if not cfg.mongo_uri:
            raise RuntimeError("MONGO_URI is required.")
        from pymongo import MongoClient

        _MONGO_CLIENT = MongoClient(
            cfg.mongo_uri,
            serverSelectionTimeoutMS=cfg.mongo_server_selection_timeout_ms,
            connectTimeoutMS=cfg.mongo_connect_timeout_ms,
        )
    return _MONGO_CLIENT


def _mongo_db():
    client = _mongo_client()
    cfg = _storage_config()
    return client[cfg.mongo_db_name]


def _pairs_collection():
    return _mongo_db().pairs


def _chat_collection():
    return _mongo_db().chat_messages


def _credit_collection():
    return _mongo_db().credit_usage


def initialize() -> None:
    db = _mongo_db()
    db.pairs.create_index("pair_id", unique=True)
    db.chat_messages.create_index([("pair_id", 1), ("thread_id", 1), ("created_at", 1)])
    db.credit_usage.create_index([("pair_id", 1), ("thread_id", 1), ("provider", 1), ("created_at", 1)])
    db.video_chunks.create_index([("pair_id", 1), ("video_id", 1), ("chunk_id", 1)], unique=True)


def save_pair(pair_id: str, payload: dict) -> None:
    created_at = _utc_now()
    _pairs_collection().update_one(
        {"pair_id": pair_id},
        {"$set": {"pair_id": pair_id, "payload": payload, "created_at": created_at}},
        upsert=True,
    )


def load_pair(pair_id: str) -> dict | None:
    doc = _pairs_collection().find_one({"pair_id": pair_id}, {"_id": 0, "payload": 1})
    if not doc:
        return None
    return doc.get("payload")


def append_message(pair_id: str, thread_id: str, role: str, content: str) -> None:
    _chat_collection().insert_one(
        {
            "pair_id": pair_id,
            "thread_id": thread_id,
            "role": role,
            "content": content,
            "created_at": _utc_now(),
        }
    )


def load_messages(pair_id: str, thread_id: str, limit: int = 12) -> list[dict[str, str]]:
    docs = list(
        _chat_collection()
        .find(
            {"pair_id": pair_id, "thread_id": thread_id},
            {"_id": 0, "role": 1, "content": 1, "created_at": 1},
        )
        .sort("created_at", -1)
        .limit(limit)
    )
    return [{"role": str(doc["role"]), "content": str(doc["content"])} for doc in reversed(docs)]


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
    _credit_collection().insert_one(
        {
            "pair_id": pair_id,
            "thread_id": thread_id,
            "provider": provider,
            "model": model,
            "input_tokens_est": int(input_tokens_est),
            "output_tokens_est": int(output_tokens_est),
            "credits_used_usd": float(credits_used_usd),
            "created_at": _utc_now(),
        }
    )


def credit_usage_totals(
    pair_id: str,
    thread_id: str | None = None,
    provider: str | None = None,
    date_from_iso: str | None = None,
) -> dict[str, float]:
    filters: dict[str, Any] = {"pair_id": pair_id}
    if thread_id:
        filters["thread_id"] = thread_id
    if provider:
        filters["provider"] = provider
    if date_from_iso:
        try:
            filters["created_at"] = {"$gte": datetime.fromisoformat(date_from_iso)}
        except ValueError as exc:
            raise ValueError(f"Invalid ISO datetime for date_from_iso: {date_from_iso}") from exc

    result = list(
        _credit_collection().aggregate(
            [
                {"$match": filters},
                {
                    "$group": {
                        "_id": None,
                        "input_tokens": {"$sum": "$input_tokens_est"},
                        "output_tokens": {"$sum": "$output_tokens_est"},
                        "credits_used": {"$sum": "$credits_used_usd"},
                    }
                },
            ]
        )
    )
    if not result:
        return {"input_tokens": 0.0, "output_tokens": 0.0, "credits_used": 0.0}
    row = result[0]
    return {
        "input_tokens": float(row.get("input_tokens", 0.0)),
        "output_tokens": float(row.get("output_tokens", 0.0)),
        "credits_used": float(row.get("credits_used", 0.0)),
    }
