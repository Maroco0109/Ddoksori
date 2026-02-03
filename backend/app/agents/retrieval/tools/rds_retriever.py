# -*- coding: utf-8 -*-
"""RDS retriever (direct SQL): dense, BM25, and hybrid RRF search."""

import os
import re
import time
from typing import Dict, List, Optional, Tuple

import psycopg2

from .rds_internal_retriever import SimilarChunkResult


class RDSRetriever:
    """Direct SQL client for vector_chunks search."""

    def __init__(
        self,
        db_config: Optional[Dict[str, str]] = None,
    ) -> None:
        self.db_config = db_config or self._get_db_config()
        self.conn = None
        self._openai_client = None

    def connect(self) -> None:
        self.conn = psycopg2.connect(**self.db_config)

    def close(self) -> None:
        if self.conn:
            self.conn.close()

    def embed_query(self, query: str) -> List[float]:
        """쿼리 임베딩 생성 (OpenAI text-embedding-3-large)"""
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "openai package is required for OpenAI embeddings. "
                "Install it with: pip install openai"
            ) from exc

        if self._openai_client is None:
            self._openai_client = OpenAI()

        response = self._openai_client.embeddings.create(
            model="text-embedding-3-large",
            input=[query],
            dimensions=1536,
        )
        return response.data[0].embedding

    def dense_search(
        self,
        query: str,
        filter_dataset: Optional[str] = None,
        filter_category: Optional[str] = None,
        filter_law_name: Optional[str] = None,
        filter_document_type: Optional[List[str]] = None,
        filter_metadata: Optional[Dict[str, str]] = None,
        filter_chunk_type: Optional[str] = None,
        filter_year: Optional[int] = None,
        result_limit: int = 10,
        exclude_deleted: bool = True,
    ) -> Tuple[List[SimilarChunkResult], float, float]:
        if not self.conn:
            raise RuntimeError(
                "Database connection is not initialized. Call connect() first."
            )

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
        where_metadata = ""
        params_metadata: List = []
        if filter_metadata:
            for key, value in filter_metadata.items():
                where_metadata += " AND (vc.metadata ->> %s) = %s"
                params_metadata.extend([key, str(value)])

        where_deleted = ""

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
                    vc.document_type,
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
                    AND (%s IS NULL OR vc.chunk_type = %s)
                    AND (%s IS NULL OR vc.source_year = %s)
                    {where_doc_type}
                    {where_metadata}
                    {where_deleted}
                ORDER BY vc.embedding <=> %s::vector
                LIMIT %s
                """,
                (
                    query_embedding,
                    filter_dataset,
                    filter_dataset,
                    filter_category,
                    filter_category,
                    filter_law_name,
                    filter_law_name,
                    filter_chunk_type,
                    filter_chunk_type,
                    filter_year,
                    filter_year,
                    *params_doc_type,
                    *params_metadata,
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
                    document_type=row[7],
                    source_url=row[8],
                    source_file=row[9],
                    printed_page=row[10],
                    source_year=row[11],
                    metadata=row[12],
                )
            )

        return results, embed_ms, sql_ms

    def keyword_search(
        self,
        query_text: str,
        filter_dataset: Optional[str] = None,
        filter_category: Optional[str] = None,
        filter_law_name: Optional[str] = None,
        filter_document_type: Optional[List[str]] = None,
        filter_metadata: Optional[Dict[str, str]] = None,
        filter_chunk_type: Optional[str] = None,
        filter_year: Optional[int] = None,
        result_limit: int = 100,
        exclude_deleted: bool = True,
    ) -> Tuple[List[Dict], float]:
        if not self.conn:
            raise RuntimeError(
                "Database connection is not initialized. Call connect() first."
            )

        document_types = list(filter_document_type) if filter_document_type else None
        where_doc_type = ""
        params_doc_type: List = []
        if document_types:
            placeholders = ", ".join(["%s"] * len(document_types))
            where_doc_type = f"AND vc.document_type IN ({placeholders})"
            params_doc_type = document_types
        where_metadata = ""
        params_metadata: List = []
        if filter_metadata:
            for key, value in filter_metadata.items():
                where_metadata += " AND (vc.metadata ->> %s) = %s"
                params_metadata.extend([key, str(value)])

        where_deleted = ""

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
                    AND (%s IS NULL OR vc.law_name = %s)
                    AND (%s IS NULL OR vc.chunk_type = %s)
                    AND (%s IS NULL OR vc.source_year = %s)
                    {where_doc_type}
                    {where_metadata}
                    {where_deleted}
                ORDER BY bm25_score DESC
                LIMIT %s
                """,
                (
                    query_text,
                    query_text,
                    query_text,
                    filter_dataset,
                    filter_dataset,
                    filter_category,
                    filter_category,
                    filter_law_name,
                    filter_law_name,
                    filter_chunk_type,
                    filter_chunk_type,
                    filter_year,
                    filter_year,
                    *params_doc_type,
                    *params_metadata,
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
        filter_law_name: Optional[str] = None,
        filter_document_type: Optional[List[str]] = None,
        filter_metadata: Optional[Dict[str, str]] = None,
        filter_chunk_type: Optional[str] = None,
        filter_year: Optional[int] = None,
        result_limit: int = 100,
        exclude_deleted: bool = True,
    ) -> Tuple[List[Dict], float]:
        article_match = re.search(r"(제?\s*\d+\s*조)", query_text)
        article_token = (
            article_match.group(1).replace(" ", "") if article_match else None
        )
        main_query = query_text
        if article_match:
            main_query = (query_text.replace(article_match.group(1), " ")).strip()

        main_results, main_sql_ms = self.keyword_search(
            query_text=main_query if main_query else query_text,
            filter_dataset=filter_dataset,
            filter_category=filter_category,
            filter_law_name=filter_law_name,
            filter_document_type=filter_document_type,
            filter_metadata=filter_metadata,
            filter_chunk_type=filter_chunk_type,
            filter_year=filter_year,
            result_limit=result_limit,
            exclude_deleted=exclude_deleted,
        )

        if not article_token:
            return main_results, main_sql_ms

        article_results, article_sql_ms = self.keyword_search(
            query_text=article_token,
            filter_dataset=filter_dataset,
            filter_category=filter_category,
            filter_law_name=filter_law_name,
            filter_document_type=filter_document_type,
            filter_metadata=filter_metadata,
            filter_chunk_type=filter_chunk_type,
            filter_year=filter_year,
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
        filter_law_name: Optional[str] = None,
        filter_document_type: Optional[List[str]] = None,
        filter_metadata: Optional[Dict[str, str]] = None,
        filter_chunk_type: Optional[str] = None,
        filter_year: Optional[int] = None,
        result_limit: int = 10,
        rrf_k: int = 60,
        exclude_deleted: bool = True,
    ) -> Tuple[List[Dict], float]:
        if not self.conn:
            raise RuntimeError(
                "Database connection is not initialized. Call connect() first."
            )

        query_embedding = self.embed_query(query_text)

        document_types = list(filter_document_type) if filter_document_type else None
        where_doc_type = ""
        params_doc_type: List = []
        if document_types:
            placeholders = ", ".join(["%s"] * len(document_types))
            where_doc_type = f"AND vc.document_type IN ({placeholders})"
            params_doc_type = document_types
        where_metadata = ""
        params_metadata: List = []
        if filter_metadata:
            for key, value in filter_metadata.items():
                where_metadata += " AND (vc.metadata ->> %s) = %s"
                params_metadata.extend([key, str(value)])

        where_deleted = ""

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
                        AND (%s IS NULL OR vc.law_name = %s)
                        AND (%s IS NULL OR vc.chunk_type = %s)
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
                        AND (%s IS NULL OR vc.law_name = %s)
                        AND (%s IS NULL OR vc.chunk_type = %s)
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
                    filter_dataset,
                    filter_dataset,
                    filter_category,
                    filter_category,
                    filter_law_name,
                    filter_law_name,
                    filter_chunk_type,
                    filter_chunk_type,
                    filter_year,
                    filter_year,
                    *params_doc_type,
                    *params_metadata,
                    query_embedding,
                    query_embedding,
                    filter_dataset,
                    filter_dataset,
                    filter_category,
                    filter_category,
                    filter_law_name,
                    filter_law_name,
                    filter_chunk_type,
                    filter_chunk_type,
                    filter_year,
                    filter_year,
                    *params_doc_type,
                    *params_metadata,
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


def hybrid_rrf_search(
    query_text: str,
    *,
    filter_dataset: Optional[str] = None,
    filter_category: Optional[str] = None,
    filter_law_name: Optional[str] = None,
    filter_document_type: Optional[List[str]] = None,
    filter_metadata: Optional[Dict[str, str]] = None,
    filter_chunk_type: Optional[str] = None,
    filter_year: Optional[int] = None,
    result_limit: int = 10,
    rrf_k: int = 60,
) -> Tuple[List[Dict], float]:
    client = RDSRetriever()
    client.connect()
    try:
        results, sql_ms = client.hybrid_rrf_search(
            query_text=query_text,
            filter_dataset=filter_dataset,
            filter_category=filter_category,
            filter_law_name=filter_law_name,
            filter_document_type=filter_document_type,
            filter_metadata=filter_metadata,
            filter_chunk_type=filter_chunk_type,
            filter_year=filter_year,
            result_limit=result_limit,
            rrf_k=rrf_k,
        )
    finally:
        client.close()

    return results, sql_ms


__all__ = [
    "SimilarChunkResult",
    "RDSRetriever",
    "hybrid_rrf_search",
]
