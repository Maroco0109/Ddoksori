#!/usr/bin/env python3
"""Smoke test for Case/Counsel retrieval using DB function hybrid RRF.

Includes rule-based case routing (상담/조정/해결) with quota mixing.
"""

import argparse
import asyncio
import os
import sys
import logging
from dotenv import load_dotenv
load_dotenv()


REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))

from app.agents.retrieval.base_retrieval_agent import _get_db_config, _get_embed_api_url
from app.agents.retrieval.case_agent import CaseRetrievalAgent
from app.agents.retrieval.tools.rds_retriever import RDSRetriever
import psycopg2


def _check_required_fields(item: dict) -> list:
    missing = []
    for key in ("title", "doc_title", "url", "similarity"):
        value = item.get(key)
        if value in (None, ""):
            missing.append(key)
    return missing


async def _run_one(
    agent,
    query: str,
    label: str,
    top_k: int,
    filter_category: str | None,
) -> int:
    request = {
        "context": {"user_query": query, "query_analysis": {}},
        "params": {"top_k": top_k, "filter_category": filter_category},
    }
    response = await agent.process(request)
    result = response.get("result") or {}
    formatted = result.get("results") or []
    raw_count = len(formatted)
    formatted_count = len(formatted)
    dedup_removed = max(raw_count - formatted_count, 0)
    soft_scores = [f.get("soft_score") for f in formatted if f.get("soft_score") is not None]
    soft_score_stats = {}
    if soft_scores:
        soft_score_stats = {
            "min": min(soft_scores),
            "max": max(soft_scores),
            "avg": sum(soft_scores) / len(soft_scores),
        }

    if not formatted:
        print(f"[FAIL] {label}: no results")
        return 1

    first = formatted[0]
    missing = _check_required_fields(first)
    if missing:
        print(f"[FAIL] {label}: missing fields {missing}")
        return 1

    print(
        f"[OK] {label}: count={len(formatted)}, title={first.get('title')}, "
        f"url={first.get('url')}, similarity={first.get('similarity')}"
    )
    print(
        f"[INFO] {label}: raw={raw_count}, formatted={formatted_count}, "
        f"dedup_removed={dedup_removed}"
    )
    if soft_score_stats:
        print(
            f"[INFO] {label}: soft_score min={soft_score_stats['min']:.4f}, "
            f"max={soft_score_stats['max']:.4f}, avg={soft_score_stats['avg']:.4f}"
        )
    return 0


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    parser = argparse.ArgumentParser(description="Smoke test for case/counsel retrieval")
    parser.add_argument("--query", default="환불 거부 분쟁 조정 사례", help="search query")
    parser.add_argument("--top-k", type=int, default=5, help="top_k")
    args = parser.parse_args()

    if os.getenv("SMOKE_CASE_AGENT_ONLY_NOTE", "false").lower() == "true":
        print("[SMOKE] This script calls case_agent directly; retrieval_merge is NOT involved.")

    db_config = _get_db_config()
    print(
        f"[INFO] DB target: {db_config.get('user')}@{db_config.get('host')}:{db_config.get('port')} "
        f"db={db_config.get('dbname')}"
    )
    retriever = RDSRetriever(_get_db_config(), _get_embed_api_url())
    try:
        retriever.connect()
    except psycopg2.OperationalError as exc:
        print("[FAIL] DB connection failed. Is Postgres running and reachable?")
        print(f"[DETAIL] {exc}")
        return 2
    finally:
        retriever.close()

    case_agent = CaseRetrievalAgent()
    rc = 0
    rc |= asyncio.run(
        _run_one(
            case_agent,
            args.query,
            "case_combined(rule_based)",
            args.top_k,
            None,
        )
    )
    return rc


if __name__ == "__main__":
    sys.exit(main())
