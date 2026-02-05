# -*- coding: utf-8 -*-
"""CLI (direct SQL): dense, BM25, and hybrid RRF search."""

import argparse
import os

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from .tools.rds_retriever import RDSRetriever

DirectSQLSearchClient = RDSRetriever


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Direct SQL search (dense, bm25, hybrid_rrf)."
    )
    parser.add_argument("query", help="Search query text")
    parser.add_argument(
        "--mode",
        choices=["dense", "bm25", "hybrid_rrf"],
        default="dense",
        help="Search mode (default: dense)",
    )
    parser.add_argument("--dataset", dest="filter_dataset", default=None)
    parser.add_argument("--category", dest="filter_category", default=None)
    parser.add_argument("--law-name", dest="filter_law_name", default=None)
    parser.add_argument("--document-type", dest="filter_document_type", default=None)
    parser.add_argument("--year", dest="filter_year", type=int, default=None)
    parser.add_argument("--limit", dest="result_limit", type=int, default=5)
    parser.add_argument("--rrf-k", dest="rrf_k", type=int, default=60)

    args = parser.parse_args()

    if load_dotenv:
        env_path = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__), "..", "..", "..", "..", "backend", ".env"
            )
        )
        load_dotenv(env_path)

    query = args.query

    doc_types = (
        [s.strip() for s in args.filter_document_type.split(",") if s.strip()]
        if args.filter_document_type
        else None
    )

    client = DirectSQLSearchClient()
    client.connect()
    try:
        if args.mode == "hybrid_rrf":
            results, sql_ms = client.hybrid_rrf_search(
                query_text=query,
                filter_dataset=args.filter_dataset,
                filter_category=args.filter_category,
                filter_document_type=doc_types,
                filter_year=args.filter_year,
                result_limit=args.result_limit,
                rrf_k=args.rrf_k,
            )
        elif args.mode == "bm25":
            results, sql_ms = client.keyword_search_split(
                query_text=query,
                filter_dataset=args.filter_dataset,
                filter_category=args.filter_category,
                filter_document_type=doc_types,
                result_limit=args.result_limit,
            )
        else:
            results, embed_ms, sql_ms = client.dense_search(
                query=query,
                filter_dataset=args.filter_dataset,
                filter_category=args.filter_category,
                filter_law_name=args.filter_law_name,
                filter_document_type=doc_types,
                filter_year=args.filter_year,
                result_limit=args.result_limit,
            )
    finally:
        client.close()

    if args.mode in ("bm25", "hybrid_rrf"):
        print(f"sql_ms={sql_ms:.1f}")
    else:
        print(f"embed_ms={embed_ms:.1f} sql_ms={sql_ms:.1f}")

    if not results:
        print("No results.")
        return 0

    if args.mode == "hybrid_rrf":
        for i, r in enumerate(results, 1):
            print(
                f"[{i}] rrf={r['rrf_score']:.4f} bm25={r['bm25_score']:.4f} "
                f"vec={r['vector_similarity']:.4f} id={r['chunk_id']}"
            )
            if r.get("source_year") is not None:
                print(f"year: {r['source_year']}")
            if r.get("source_url"):
                print(f"url: {r['source_url']}")
            print(r["text"])
            print("-" * 60)
    elif args.mode == "bm25":
        for i, r in enumerate(results, 1):
            print(
                f"[{i}] bm25={r['bm25_score']:.4f} rank={r['bm25_rank']} id={r['chunk_id']}"
            )
            print(r["text"])
            print("-" * 60)
    else:
        for i, r in enumerate(results, 1):
            print(f"[{i}] sim={r.similarity:.4f} id={r.chunk_id}")
            if r.law_name:
                print(f"law_name: {r.law_name}")
            if r.chunk_type:
                print(f"chunk_type: {r.chunk_type}")
            if r.category:
                print(f"category: {r.category}")
            if r.source_year is not None:
                print(f"year: {r.source_year}")
            if r.source_url:
                print(f"url: {r.source_url}")
            print(r.text)
            print("-" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
