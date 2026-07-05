"""M1-9 local Redis cache smoke.

This script verifies real Redis connectivity plus answer/retrieval cache
read/write/delete behavior using unique, self-cleaning keys. It is intended for
local compose only and never flushes Redis or deletes broad prefixes.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, TypeVar

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from app.agents.answer_generation.cache import AnswerCache
from app.common.cache.base import reset_redis_client
from app.supervisor.cache import RetrievalResultCache

T = TypeVar("T")


def _redis_kwargs() -> dict[str, Any]:
    return {
        "host": os.getenv("REDIS_HOST", "localhost"),
        "port": int(os.getenv("REDIS_PORT", "6379")),
        "db": int(os.getenv("REDIS_DB", "0")),
        "password": os.getenv("REDIS_PASSWORD") or None,
        "decode_responses": True,
        "socket_connect_timeout": 2,
        "socket_timeout": 2,
    }


def _timed(fn: Callable[[], T]) -> tuple[T, float]:
    start = time.perf_counter()
    result = fn()
    return result, round((time.perf_counter() - start) * 1000, 3)


def run_smoke() -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    run_id = f"m1-9:{int(time.time())}:{uuid.uuid4().hex[:8]}"

    # Ensure singleton clients are initialized from the current environment.
    reset_redis_client()
    RetrievalResultCache.reset_metrics()

    import redis

    redis_client = redis.Redis(**_redis_kwargs())
    ping_ok, ping_ms = _timed(lambda: bool(redis_client.ping()))
    if not ping_ok:
        failures.append("redis ping failed")

    answer_query = f"{run_id}:answer"
    answer_type = "m1_9_smoke"
    answer_payload = {
        "answer": "M1-9 Redis answer cache smoke payload",
        "run_id": run_id,
        "citations": ["docs/plans/modules/M1-9-redis-cache-smoke-plan.md"],
    }

    answer_cache = AnswerCache()
    answer_cache.reset_metrics()
    answer_key = answer_cache._generate_cache_key(answer_query, answer_type)

    answer_set, answer_set_ms = _timed(
        lambda: answer_cache.set(answer_query, answer_type, answer_payload)
    )
    answer_get, answer_get_ms = _timed(
        lambda: answer_cache.get(answer_query, answer_type)
    )
    answer_deleted, answer_delete_ms = _timed(
        lambda: answer_cache.invalidate(answer_query, answer_type)
    )
    answer_remaining = redis_client.exists(answer_key)

    if not answer_cache.enabled or not answer_cache._redis:
        failures.append("AnswerCache is not enabled/connected")
    if not answer_set:
        failures.append("AnswerCache set failed")
    if answer_get != answer_payload:
        failures.append("AnswerCache get did not return the stored payload")
    if not answer_deleted:
        failures.append("AnswerCache delete failed")
    if answer_remaining:
        failures.append("AnswerCache test key remained after cleanup")

    retrieval_session_id = f"{run_id}:retrieval-session"
    retrieval_payload = {
        "agency": {"name": "KCA", "score": 1.0},
        "disputes": [{"chunk_id": f"{run_id}:dispute", "similarity": 0.99}],
        "counsels": [],
        "laws": [],
        "criteria": [],
        "max_similarity": 0.99,
        "avg_similarity": 0.99,
    }
    retrieval_key = RetrievalResultCache._build_cache_key(retrieval_session_id)

    def set_retrieval() -> bool:
        RetrievalResultCache.set_by_session(retrieval_session_id, retrieval_payload)
        return bool(redis_client.exists(retrieval_key))

    retrieval_set, retrieval_set_ms = _timed(set_retrieval)
    retrieval_get, retrieval_get_ms = _timed(
        lambda: RetrievalResultCache.get_by_session(retrieval_session_id)
    )
    retrieval_deleted, retrieval_delete_ms = _timed(
        lambda: RetrievalResultCache.invalidate_session(retrieval_session_id)
    )
    retrieval_remaining = redis_client.exists(retrieval_key)

    if not retrieval_set:
        failures.append("RetrievalResultCache set failed")
    if not retrieval_get or retrieval_get.get("disputes") != retrieval_payload["disputes"]:
        failures.append("RetrievalResultCache get did not return the stored payload")
    if not retrieval_deleted:
        failures.append("RetrievalResultCache delete failed")
    if retrieval_remaining:
        failures.append("RetrievalResultCache test key remained after cleanup")

    answer_metrics = answer_cache.get_metrics()
    retrieval_metrics = RetrievalResultCache.get_metrics()

    summary = {
        "status": "ok" if not failures else "failed",
        "run_id": run_id,
        "redis": {
            "host": os.getenv("REDIS_HOST", "localhost"),
            "port": int(os.getenv("REDIS_PORT", "6379")),
            "db": int(os.getenv("REDIS_DB", "0")),
            "password_present": bool(os.getenv("REDIS_PASSWORD")),
            "ping": ping_ok,
            "ping_ms": ping_ms,
        },
        "answer_cache": {
            "set": answer_set,
            "hit": answer_get == answer_payload,
            "deleted": answer_deleted,
            "set_ms": answer_set_ms,
            "get_ms": answer_get_ms,
            "delete_ms": answer_delete_ms,
            "hit_count": answer_metrics.get("hit_count"),
            "miss_count": answer_metrics.get("miss_count"),
            "error_count": answer_metrics.get("error_count"),
        },
        "retrieval_cache": {
            "set": retrieval_set,
            "hit": bool(retrieval_get),
            "deleted": retrieval_deleted,
            "set_ms": retrieval_set_ms,
            "get_ms": retrieval_get_ms,
            "delete_ms": retrieval_delete_ms,
            "hit_count": retrieval_metrics.get("hit_count"),
            "miss_count": retrieval_metrics.get("miss_count"),
            "error_count": retrieval_metrics.get("error_count"),
        },
        "cleanup": {
            "answer_key_remaining": int(answer_remaining),
            "retrieval_key_remaining": int(retrieval_remaining),
            "test_keys_remaining": int(answer_remaining) + int(retrieval_remaining),
        },
    }
    return summary, failures


def main() -> int:
    try:
        summary, failures = run_smoke()
    except Exception as exc:  # pragma: no cover - local smoke diagnostic path
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1

    if failures:
        summary["failures"] = failures
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
