# -*- coding: utf-8 -*-
"""
Build a RAGAS-style retrieval log (query -> top-k retrieved contexts) from queries_llm.

Example usage:
  python backend/app/agents/retrieval/build_ragas_retrieval_log.py --max-queries 10
  python backend/app/agents/retrieval/build_ragas_retrieval_log.py --max-queries 300 --top-k 10
"""

import argparse
import json
import os
import random
from datetime import datetime
from importlib.util import module_from_spec, spec_from_file_location
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
                queries.append((q, {"case_index": case_index, "query_index": q_idx, **row}))
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


def build_log(
    *,
    input_path: str,
    output_path: str,
    max_queries: int,
    top_k: int,
    filter_document_type: List[str],
    rrf_k: int,
    shuffle: bool,
    seed: int,
    continue_on_error: bool,
    dry_run: bool,
) -> None:
    repo_root = _find_repo_root()

    if load_dotenv:
        env_path = os.path.join(repo_root, "backend", ".env")
        load_dotenv(env_path)

    module_path = os.path.join(
        repo_root,
        "backend",
        "app",
        "agents",
        "retrieval",
        "cli_search_similar_chunks_direct_sql.py",
    )
    spec = spec_from_file_location("cli_search_similar_chunks_direct_sql", module_path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    hybrid_rrf_search = module.hybrid_rrf_search

    queries = _load_queries(input_path)
    queries = _apply_query_limit(
        queries, max_queries=max_queries, shuffle=shuffle, seed=seed
    )

    if dry_run:
        print(f"queries_loaded: {len(queries)}")
        print(f"output_path: {output_path}")
        return

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as out:
        for q, meta in queries:
            try:
                results, sql_ms = hybrid_rrf_search(
                    q,
                    filter_document_type=['법률', '시행령'],
                    result_limit=top_k,
                    rrf_k=rrf_k,
                )
            except Exception as exc:
                if not continue_on_error:
                    raise
                record = {
                    "query_id": _make_query_id(
                        meta.get("case_index", -1), meta.get("query_index", -1)
                    ),
                    "user_input": q,
                    "error": str(exc),
                }
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                continue

            record = {
                "query_id": _make_query_id(
                    meta.get("case_index", -1), meta.get("query_index", -1)
                ),
                "user_input": q,
                "retrieved_contexts": [r.get("text", "") for r in results],
                "retrieved_ids": [r.get("chunk_id") for r in results],
                "scores": {
                    "rrf": [r.get("rrf_score") for r in results],
                    "bm25": [r.get("bm25_score") for r in results],
                    "vector": [r.get("vector_similarity") for r in results],
                },
                "sql_ms": sql_ms,
                "retriever": "hybrid_rrf",
                "top_k": top_k,
                "source": {
                    "case_index": meta.get("case_index"),
                    "query_index": meta.get("query_index"),
                    "decision_date": meta.get("decision_date"),
                    "article_ids": meta.get("article_ids"),
                },
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")


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
    default_output = os.path.join(
        repo_root,
        "backend",
        "data",
        "golden_set",
        f"ragas_retrieval_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl",
    )

    parser = argparse.ArgumentParser(description="Build RAGAS retrieval log (retriever-only).")
    parser.add_argument("--input", dest="input_path", default=default_input)
    parser.add_argument("--output", dest="output_path", default=default_output)
    parser.add_argument("--max-queries", type=int, default=300)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--filter-document-type",
        default="",
        help="Comma-separated document_type filter (e.g., '법령,시행령').",
    )

    args = parser.parse_args()
    doc_types = [s.strip() for s in args.filter_document_type.split(",") if s.strip()]

    build_log(
        input_path=args.input_path,
        output_path=args.output_path,
        max_queries=args.max_queries,
        top_k=args.top_k,
        filter_document_type=doc_types,
        rrf_k=args.rrf_k,
        shuffle=args.shuffle,
        seed=args.seed,
        continue_on_error=args.continue_on_error,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
