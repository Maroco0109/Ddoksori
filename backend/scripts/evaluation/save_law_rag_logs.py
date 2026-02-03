# -*- coding: utf-8 -*-
"""
Save Law RAG retrieval logs to a single JSONL file (one row per query).

Example:
  python backend/scripts/evaluation/save_law_rag_logs.py --max-queries 10 --top-k 10
  python backend/scripts/evaluation/save_law_rag_logs.py --max-queries 300 --top-k 10 --shuffle
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime
from typing import Dict, Iterable, List, Tuple

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def _find_repo_root() -> str:
    cwd = os.getcwd()
    repo_root = cwd
    while repo_root and not os.path.isdir(os.path.join(repo_root, "backend")):
        parent = os.path.dirname(repo_root)
        if parent == repo_root:
            break
        repo_root = parent
    return repo_root


def _load_queries(path: str) -> List[Tuple[str, Dict]]:
    queries: List[Tuple[str, Dict]] = []
    with open(path, "r", encoding="utf-8") as f:
        for case_index, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            for q_idx, q in enumerate(row.get("queries_llm", []) or []):
                queries.append(
                    (q, {"case_index": case_index, "query_index": q_idx, **row})
                )
    return queries


def _apply_query_limit(
    queries: List[Tuple[str, Dict]],
    *,
    max_queries: int,
    shuffle: bool,
    seed: int,
) -> List[Tuple[str, Dict]]:
    if shuffle:
        rng = random.Random(seed)
        rng.shuffle(queries)
    if max_queries > 0:
        return queries[:max_queries]
    return queries


def _make_query_id(case_index: int, query_index: int) -> str:
    return f"case{case_index:04d}_q{query_index:02d}"


def save_logs(
    *,
    input_path: str,
    output_path: str,
    max_queries: int,
    top_k: int,
    rrf_k: int,
    shuffle: bool,
    seed: int,
    continue_on_error: bool,
    dry_run: bool,
) -> None:
    repo_root = _find_repo_root()

    if load_dotenv:
        env_path = os.path.join(repo_root, ".env")
        load_dotenv(env_path)

    backend_root = os.path.join(repo_root, "backend")
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

    from app.agents.retrieval.tools.rds_retriever import hybrid_rrf_search

    queries = _load_queries(input_path)
    queries = _apply_query_limit(
        queries, max_queries=max_queries, shuffle=shuffle, seed=seed
    )

    if dry_run:
        print(f"queries_loaded: {len(queries)}")
        print(f"output_dir: {output_dir}")
        return

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as out:
        for query, meta in queries:
            query_id = _make_query_id(
                meta.get("case_index", -1), meta.get("query_index", -1)
            )
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            try:
                results, sql_ms = hybrid_rrf_search(
                    query,
                    filter_document_type=["법률", "시행령"],
                    result_limit=top_k,
                    rrf_k=rrf_k,
                )
                payload = {
                    "timestamp": timestamp,
                    "query_id": query_id,
                    "query": query,
                    "sql_ms": sql_ms,
                    "results": results,
                    "top_k": top_k,
                    "retriever": "hybrid_rrf",
                    "source": {
                        "case_index": meta.get("case_index"),
                        "query_index": meta.get("query_index"),
                        "decision_date": meta.get("decision_date"),
                        "article_ids": meta.get("article_ids"),
                    },
                }
            except Exception as exc:
                if not continue_on_error:
                    raise
                payload = {
                    "timestamp": timestamp,
                    "query_id": query_id,
                    "query": query,
                    "error": str(exc),
                    "top_k": top_k,
                    "retriever": "hybrid_rrf",
                    "source": {
                        "case_index": meta.get("case_index"),
                        "query_index": meta.get("query_index"),
                        "decision_date": meta.get("decision_date"),
                        "article_ids": meta.get("article_ids"),
                    },
                }

            out.write(json.dumps(payload, ensure_ascii=False) + "\n")

    print("saved:", output_path)


def main() -> int:
    repo_root = _find_repo_root()
    default_input = os.path.join(
        repo_root,
        "backend",
        "data",
        "golden_set",
        "dispute_law_gold",
        "data",
        "samples",
        "dispute_law_gold_improve_sample_300_with_queries_llm.jsonl",
    )
    default_output_path = os.path.join(
        repo_root,
        "backend",
        "data",
        "golden_set",
        f"ragas_retrieval_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl",
    )

    parser = argparse.ArgumentParser(
        description="Save per-query Law RAG retrieval logs (JSON)."
    )
    parser.add_argument("--input", dest="input_path", default=default_input)
    parser.add_argument("--output", dest="output_path", default=default_output_path)
    parser.add_argument("--max-queries", type=int, default=300)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    save_logs(
        input_path=args.input_path,
        output_path=args.output_path,
        max_queries=args.max_queries,
        top_k=args.top_k,
        rrf_k=args.rrf_k,
        shuffle=args.shuffle,
        seed=args.seed,
        continue_on_error=args.continue_on_error,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
