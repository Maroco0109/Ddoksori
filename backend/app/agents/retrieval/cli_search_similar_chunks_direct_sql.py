# -*- coding: utf-8 -*-
"""CLI (direct SQL): dense, BM25, and hybrid RRF search."""

import argparse
import os
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import psycopg2
import requests

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


@dataclass
class SimilarChunkResult:
    chunk_id: str
    dataset_type: str
    text: str
    similarity: float
    law_name: Optional[str]
    chunk_type: Optional[str]
    category: Optional[str]
    source_url: Optional[str]
    source_file: Optional[str]
    printed_page: Optional[int]
    source_year: Optional[int]
    metadata: Optional[Dict]


class DirectSQLSearchClient:
    """Direct SQL client for vector_chunks search."""

    def __init__(
        self,
        db_config: Optional[Dict[str, str]] = None,
        embed_api_url: Optional[str] = None,
    ) -> None:
        self.db_config = db_config or self._get_db_config()
        self.embed_api_url = embed_api_url or self._get_embed_api_url()
        self.conn = None

    def connect(self) -> None:
        self.conn = psycopg2.connect(**self.db_config)

    def close(self) -> None:
        if self.conn:
            self.conn.close()

    def embed_query(self, query: str) -> List[float]:
        use_openai = os.getenv("USE_OPENAI_EMBEDDING", "false").lower() == "true"
        has_openai_key = bool(os.getenv("OPENAI_API_KEY"))

        if use_openai or has_openai_key:
            return self._embed_query_openai(query)

        response = requests.post(
            self.embed_api_url,
            json={"texts": [query]},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()["embeddings"][0]

    def _embed_query_openai(self, query: str) -> List[float]:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "openai package is required for OpenAI embeddings. "
                "Install it with: pip install openai"
            ) from exc

        model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
        dimensions = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))

        client = OpenAI()
        response = client.embeddings.create(
            model=model,
            input=[query],
            dimensions=dimensions,
        )
        return response.data[0].embedding

    def dense_search(
        self,
        query: str,
        filter_dataset: Optional[str] = None,
        filter_category: Optional[str] = None,
        filter_law_name: Optional[str] = None,
        filter_document_type: Optional[List[str]] = None,
        filter_year: Optional[int] = None,
        result_limit: int = 10,
        exclude_deleted: bool = True,
    ) -> Tuple[List[SimilarChunkResult], float, float]:
        if not self.conn:
            raise RuntimeError("Database connection is not initialized. Call connect() first.")

        embed_start = time.time()
        query_embedding = self.embed_query(query)
        embed_ms = (time.time() - embed_start) * 1000

        document_types = list(filter_document_type) if filter_document_type else None
        where_doc_type = ""
        params_doc_type: List = []
        if document_types:
            placeholders = ", ".join(["%s"] * len(document_types))
            where_doc_type = f"AND vc.document_type IN ({placeholders})"
            params_doc_type = document_types

        where_deleted = ""
        if exclude_deleted:
            where_deleted = "AND NOT (vc.text_tsv @@ to_tsquery('simple', '삭제'))"

        with self.conn.cursor() as cur:
            sql_start = time.time()
            cur.execute(
                f"""
                SELECT
                    vc.chunk_id,
                    vc.dataset_type,
                    vc.text,
                    1 - (vc.embedding <=> %s::vector) AS similarity,
                    vc.law_name,
                    vc.chunk_type,
                    vc.category,
                    vc.source_url,
                    vc.source_file,
                    vc.printed_page,
                    vc.source_year,
                    vc.metadata
                FROM vector_chunks vc
                WHERE
                    (%s IS NULL OR vc.dataset_type = %s)
                    AND (%s IS NULL OR vc.category = %s)
                    AND (%s IS NULL OR vc.law_name = %s)
                    AND (%s IS NULL OR vc.source_year = %s)
                    {where_doc_type}
                    {where_deleted}
                ORDER BY vc.embedding <=> %s::vector
                LIMIT %s
                """,
                (
                    query_embedding,
                    filter_dataset, filter_dataset,
                    filter_category, filter_category,
                    filter_law_name, filter_law_name,
                    filter_year, filter_year,
                    *params_doc_type,
                    query_embedding,
                    result_limit,
                ),
            )

            rows = cur.fetchall()
            sql_ms = (time.time() - sql_start) * 1000

        results: List[SimilarChunkResult] = []
        for row in rows:
            results.append(
                SimilarChunkResult(
                    chunk_id=row[0],
                    dataset_type=row[1],
                    text=row[2],
                    similarity=float(row[3]),
                    law_name=row[4],
                    chunk_type=row[5],
                    category=row[6],
                    source_url=row[7],
                    source_file=row[8],
                    printed_page=row[9],
                    source_year=row[10],
                    metadata=row[11],
                )
            )

        return results, embed_ms, sql_ms

    def keyword_search(
        self,
        query_text: str,
        filter_dataset: Optional[str] = None,
        filter_category: Optional[str] = None,
        filter_document_type: Optional[List[str]] = None,
        result_limit: int = 100,
        exclude_deleted: bool = True,
    ) -> Tuple[List[Dict], float]:
        if not self.conn:
            raise RuntimeError("Database connection is not initialized. Call connect() first.")

        document_types = list(filter_document_type) if filter_document_type else None
        where_doc_type = ""
        params_doc_type: List = []
        if document_types:
            placeholders = ", ".join(["%s"] * len(document_types))
            where_doc_type = f"AND vc.document_type IN ({placeholders})"
            params_doc_type = document_types

        where_deleted = ""
        if exclude_deleted:
            where_deleted = "AND NOT (vc.text_tsv @@ to_tsquery('simple', '삭제'))"

        with self.conn.cursor() as cur:
            sql_start = time.time()
            cur.execute(
                f"""
                SELECT
                    vc.chunk_id,
                    vc.dataset_type,
                    vc.text,
                    ts_rank_cd(vc.text_tsv, plainto_tsquery('simple', %s))::FLOAT as bm25_score,
                    ROW_NUMBER() OVER (
                        ORDER BY ts_rank_cd(vc.text_tsv, plainto_tsquery('simple', %s)) DESC
                    ) as bm25_rank
                FROM vector_chunks vc
                WHERE
                    vc.text_tsv @@ plainto_tsquery('simple', %s)
                    AND (%s IS NULL OR vc.dataset_type = %s)
                    AND (%s IS NULL OR vc.category = %s)
                    {where_doc_type}
                    {where_deleted}
                ORDER BY bm25_score DESC
                LIMIT %s
                """,
                (
                    query_text,
                    query_text,
                    query_text,
                    filter_dataset, filter_dataset,
                    filter_category, filter_category,
                    *params_doc_type,
                    result_limit,
                ),
            )

            rows = cur.fetchall()
            sql_ms = (time.time() - sql_start) * 1000

        results: List[Dict] = []
        for row in rows:
            results.append(
                {
                    "chunk_id": row[0],
                    "dataset_type": row[1],
                    "text": row[2],
                    "bm25_score": float(row[3]),
                    "bm25_rank": int(row[4]),
                }
            )

        return results, sql_ms

    def keyword_search_split(
        self,
        query_text: str,
        filter_dataset: Optional[str] = None,
        filter_category: Optional[str] = None,
        filter_document_type: Optional[List[str]] = None,
        result_limit: int = 100,
        exclude_deleted: bool = True,
    ) -> Tuple[List[Dict], float]:
        article_match = re.search(r"(제?\s*\d+\s*조)", query_text)
        article_token = article_match.group(1).replace(" ", "") if article_match else None
        main_query = query_text
        if article_match:
            main_query = (query_text.replace(article_match.group(1), " ")).strip()

        main_results, main_sql_ms = self.keyword_search(
            query_text=main_query if main_query else query_text,
            filter_dataset=filter_dataset,
            filter_category=filter_category,
            filter_document_type=filter_document_type,
            result_limit=result_limit,
            exclude_deleted=exclude_deleted,
        )

        if not article_token:
            return main_results, main_sql_ms

        article_results, article_sql_ms = self.keyword_search(
            query_text=article_token,
            filter_dataset=filter_dataset,
            filter_category=filter_category,
            filter_document_type=filter_document_type,
            result_limit=result_limit,
            exclude_deleted=exclude_deleted,
        )

        merged: Dict[str, Dict] = {}
        for r in main_results:
            merged[r["chunk_id"]] = {
                **r,
                "bm25_score_main": r["bm25_score"],
                "bm25_score_article": 0.0,
            }
        for r in article_results:
            existing = merged.get(r["chunk_id"])
            if existing:
                existing["bm25_score_article"] = r["bm25_score"]
            else:
                merged[r["chunk_id"]] = {
                    **r,
                    "bm25_score_main": 0.0,
                    "bm25_score_article": r["bm25_score"],
                }

        merged_list = list(merged.values())
        for r in merged_list:
            r["bm25_score"] = r.get("bm25_score_main", 0.0) + 0.5 * r.get(
                "bm25_score_article", 0.0
            )

        merged_list.sort(key=lambda x: x["bm25_score"], reverse=True)
        merged_list = merged_list[:result_limit]

        return merged_list, (main_sql_ms + article_sql_ms)

    def hybrid_rrf_search(
        self,
        query_text: str,
        filter_dataset: Optional[str] = None,
        filter_category: Optional[str] = None,
        filter_document_type: Optional[List[str]] = None,
        filter_year: Optional[int] = None,
        result_limit: int = 10,
        rrf_k: int = 60,
        exclude_deleted: bool = True,
    ) -> Tuple[List[Dict], float]:
        if not self.conn:
            raise RuntimeError("Database connection is not initialized. Call connect() first.")

        query_embedding = self.embed_query(query_text)

        document_types = list(filter_document_type) if filter_document_type else None
        where_doc_type = ""
        params_doc_type: List = []
        if document_types:
            placeholders = ", ".join(["%s"] * len(document_types))
            where_doc_type = f"AND vc.document_type IN ({placeholders})"
            params_doc_type = document_types

        where_deleted = ""
        if exclude_deleted:
            where_deleted = "AND NOT (vc.text_tsv @@ to_tsquery('simple', '삭제'))"

        with self.conn.cursor() as cur:
            sql_start = time.time()
            cur.execute(
                f"""
                WITH bm25_results AS (
                    SELECT
                        vc.chunk_id,
                        ts_rank_cd(vc.text_tsv, plainto_tsquery('simple', %s))::FLOAT as score,
                        ROW_NUMBER() OVER (
                            ORDER BY ts_rank_cd(vc.text_tsv, plainto_tsquery('simple', %s)) DESC
                        ) as rank
                    FROM vector_chunks vc
                    WHERE
                        vc.text_tsv @@ plainto_tsquery('simple', %s)
                        AND (%s IS NULL OR vc.dataset_type = %s)
                        AND (%s IS NULL OR vc.category = %s)
                        AND (%s IS NULL OR vc.source_year = %s)
                        {where_doc_type}
                        {where_deleted}
                    ORDER BY score DESC
                    LIMIT 100
                ),
                vector_results AS (
                    SELECT
                        vc.chunk_id,
                        1 - (vc.embedding <=> %s::vector) as similarity,
                        ROW_NUMBER() OVER (ORDER BY vc.embedding <=> %s::vector) as rank
                    FROM vector_chunks vc
                    WHERE
                        (%s IS NULL OR vc.dataset_type = %s)
                        AND (%s IS NULL OR vc.category = %s)
                        AND (%s IS NULL OR vc.source_year = %s)
                        {where_doc_type}
                        {where_deleted}
                    ORDER BY vc.embedding <=> %s::vector
                    LIMIT 100
                ),
                rrf_combined AS (
                    SELECT
                        COALESCE(b.chunk_id, v.chunk_id) as chunk_id,
                        COALESCE(1.0::double precision / (%s + b.rank), 0.0::double precision) +
                        COALESCE(1.0::double precision / (%s + v.rank), 0.0::double precision)
                        AS rrf_score,
                        COALESCE(b.score, 0.0)::double precision as bm25_score,
                        COALESCE(v.similarity, 0.0)::double precision as vector_similarity
                    FROM bm25_results b
                    FULL OUTER JOIN vector_results v ON b.chunk_id = v.chunk_id
                )
                SELECT
                    vc.chunk_id,
                    vc.dataset_type,
                    vc.text,
                    rc.rrf_score,
                    rc.bm25_score,
                    rc.vector_similarity,
                    vc.source_url,
                    vc.source_file,
                    vc.printed_page,
                    vc.source_year,
                    vc.metadata
                FROM rrf_combined rc
                JOIN vector_chunks vc ON rc.chunk_id = vc.chunk_id
                ORDER BY rc.rrf_score DESC
                LIMIT %s
                """,
                (
                    query_text,
                    query_text,
                    query_text,
                    filter_dataset, filter_dataset,
                    filter_category, filter_category,
                    filter_year, filter_year,
                    *params_doc_type,
                    query_embedding,
                    query_embedding,
                    filter_dataset, filter_dataset,
                    filter_category, filter_category,
                    filter_year, filter_year,
                    *params_doc_type,
                    query_embedding,
                    rrf_k,
                    rrf_k,
                    result_limit,
                ),
            )

            rows = cur.fetchall()
            sql_ms = (time.time() - sql_start) * 1000

        results: List[Dict] = []
        for row in rows:
            results.append(
                {
                    "chunk_id": row[0],
                    "dataset_type": row[1],
                    "text": row[2],
                    "rrf_score": float(row[3]),
                    "bm25_score": float(row[4]),
                    "vector_similarity": float(row[5]),
                    "source_url": row[6],
                    "source_file": row[7],
                    "printed_page": row[8],
                    "source_year": row[9],
                    "metadata": row[10],
                }
            )

        return results, sql_ms

    @staticmethod
    def _get_db_config() -> Dict[str, str]:
        return {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": os.getenv("DB_PORT", "5432"),
            "dbname": os.getenv("DB_NAME", "ddoksori"),
            "user": os.getenv("DB_USER", "postgres"),
            "password": os.getenv("DB_PASSWORD", "postgres"),
        }

    @staticmethod
    def _get_embed_api_url() -> str:
        return os.getenv("EMBED_API_URL", "http://localhost:8001/embed")


def hybrid_rrf_search(
    query_text: str,
    *,
    filter_dataset: Optional[str] = None,
    filter_category: Optional[str] = None,
    filter_document_type: Optional[List[str]] = None,
    filter_year: Optional[int] = None,
    result_limit: int = 10,
    rrf_k: int = 60,
) -> Tuple[List[Dict], float]:
    client = DirectSQLSearchClient()
    client.connect()
    try:
        results, sql_ms = client.hybrid_rrf_search(
            query_text=query_text,
            filter_dataset=filter_dataset,
            filter_category=filter_category,
            filter_document_type=filter_document_type,
            filter_year=filter_year,
            result_limit=result_limit,
            rrf_k=rrf_k,
        )
    finally:
        client.close()

    return results, sql_ms


def main() -> int:
    parser = argparse.ArgumentParser(description="Direct SQL search (dense, bm25, hybrid_rrf).")
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
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend", ".env")
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

