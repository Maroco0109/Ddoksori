#!/usr/bin/env python3
"""Smoke test for Case/Counsel retrieval using DB function hybrid RRF."""

import argparse
import os
import sys

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")
)
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))

from app.agents.retrieval.base_retrieval_agent import _get_db_config, _get_embed_api_url
from app.agents.retrieval.case_agent import CaseRetrievalAgent
from app.agents.retrieval.counsel_agent import CounselRetrievalAgent
from app.agents.retrieval.tools.rds_retriever import RDSRetriever
import psycopg2


def _check_required_fields(item: dict) -> list:
    missing = []
    for key in ("title", "doc_title", "url", "similarity"):
        value = item.get(key)
        if value in (None, ""):
            missing.append(key)
    return missing


def _run_one(retriever: RDSRetriever, agent, query: str, dataset: str, top_k: int) -> int:
    results = retriever.search_hybrid_rrf(
        query_text=query,
        filter_dataset=dataset,
        filter_category=None,
        filter_document_type=None,
        filter_year=None,
        result_limit=top_k,
        rrf_k=60,
    )

    if not results:
        print(f"[FAIL] {dataset}: no results")
        return 1

    formatted = agent._format_results(results)
    first = formatted[0]
    missing = _check_required_fields(first)
    if missing:
        print(f"[FAIL] {dataset}: missing fields {missing}")
        return 1

    print(
        f"[OK] {dataset}: count={len(formatted)}, title={first.get('title')}, "
        f"url={first.get('url')}, similarity={first.get('similarity')}"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test for case/counsel retrieval")
    parser.add_argument("--query", default="환불 거부 분쟁 조정 사례", help="search query")
    parser.add_argument("--top-k", type=int, default=3, help="top_k")
    args = parser.parse_args()

    retriever = RDSRetriever(_get_db_config(), _get_embed_api_url())
    try:
        retriever.connect()
    except psycopg2.OperationalError as exc:
        print("[FAIL] DB connection failed. Is Postgres running and reachable?")
        print(f"[DETAIL] {exc}")
        return 2
    try:
        case_agent = CaseRetrievalAgent()
        counsel_agent = CounselRetrievalAgent()
        rc = 0
        rc |= _run_one(retriever, case_agent, args.query, "mediation_case", args.top_k)
        rc |= _run_one(retriever, counsel_agent, args.query, "counsel_case", args.top_k)
        return rc
    finally:
        retriever.close()


if __name__ == "__main__":
    sys.exit(main())
