# -*- coding: utf-8 -*-
"""RDS retriever (direct SQL): dense, BM25, and hybrid RRF search."""

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import psycopg2
import requests

logger = logging.getLogger(__name__)

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


class RDSRetriever:
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

    def search_similar_chunks(
        self,
        query: str,
        filter_dataset: Optional[str] = None,
        filter_category: Optional[str] = None,
        filter_law_name: Optional[str] = None,
        filter_year: Optional[int] = None,
        result_limit: int = 10,
    ) -> List[SimilarChunkResult]:
        if not self.conn:
            raise RuntimeError("Database connection is not initialized. Call connect() first.")

        query_embedding = self.embed_query(query)

        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM search_similar_chunks(
                    %s::vector, %s, %s, %s, %s, %s
                )
                """,
                (
                    query_embedding,
                    filter_dataset,
                    filter_category,
                    filter_law_name,
                    filter_year,
                    result_limit,
                ),
            )

            results: List[SimilarChunkResult] = []
            for row in cur.fetchall():
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

        return results

    def search_hybrid_rrf(
        self,
        query_text: str,
        filter_dataset: Optional[str] = None,
        filter_category: Optional[str] = None,
        filter_document_type: Optional[str] = None,
        filter_year: Optional[int] = None,
        result_limit: int = 10,
        rrf_k: int = 60,
    ) -> List[Dict]:
        if not self.conn:
            raise RuntimeError("Database connection is not initialized. Call connect() first.")

        query_embedding = self.embed_query(query_text)

        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM search_hybrid_rrf(
                    %s, %s::vector, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    query_text,
                    query_embedding,
                    filter_dataset,
                    filter_category,
                    filter_document_type,
                    filter_year,
                    result_limit,
                    rrf_k,
                ),
            )

            results: List[Dict] = []
            for row in cur.fetchall():
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

        return results

    def _search_hybrid_rrf_fn(
        self,
        fn_name: str,
        query_text: str,
        filter_dataset: Optional[str],
        filter_category: Optional[str],
        filter_document_type: Optional[str],
        filter_year: Optional[int],
        result_limit: int,
        rrf_k: int,
    ) -> List[Dict]:
        if not self.conn:
            raise RuntimeError("Database connection is not initialized. Call connect() first.")

        query_embedding = self.embed_query(query_text)

        with self.conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT * FROM {fn_name}(
                    %s, %s::vector, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    query_text,
                    query_embedding,
                    filter_dataset,
                    filter_category,
                    filter_document_type,
                    filter_year,
                    result_limit,
                    rrf_k,
                ),
            )

            results: List[Dict] = []
            for row in cur.fetchall():
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

        return results

    def search_hybrid_rrf_s2(
        self,
        query_text: str,
        filter_dataset: Optional[str] = None,
        filter_category: Optional[str] = None,
        filter_document_type: Optional[str] = None,
        filter_year: Optional[int] = None,
        result_limit: int = 10,
        rrf_k: int = 60,
    ) -> List[Dict]:
        results = self._search_hybrid_rrf_fn(
            "search_hybrid_rrf_s2",
            query_text,
            filter_dataset,
            filter_category,
            filter_document_type,
            filter_year,
            result_limit,
            rrf_k,
        )

        if (
            filter_dataset == "case"
            and isinstance(filter_category, str)
            and filter_category.strip()
        ):
            patched_count = 0
            for doc in results:
                if not isinstance(doc, dict):
                    continue
                current = doc.get("category")
                if current not in (None, ""):
                    continue
                doc["category"] = filter_category
                meta = doc.get("metadata") or {}
                if meta.get("category") in (None, ""):
                    meta["category"] = filter_category
                    doc["metadata"] = meta
                patched_count += 1
            if patched_count > 0:
                logger.info(
                    json.dumps(
                        {
                            "event": "retriever_category_patch",
                            "selected_fn": "s2",
                            "filter_category": filter_category,
                            "patched_count": patched_count,
                        },
                        ensure_ascii=False,
                    )
                )

        return results

    def search_hybrid_rrf_s2_v2(
        self,
        query_text: str,
        filter_dataset: Optional[str] = None,
        filter_category: Optional[str] = None,
        filter_document_type: Optional[str] = None,
        filter_year: Optional[int] = None,
        result_limit: int = 10,
        rrf_k: int = 60,
    ) -> List[Dict]:
        if not self.conn:
            raise RuntimeError("Database connection is not initialized. Call connect() first.")

        query_embedding = self.embed_query(query_text)

        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM search_hybrid_rrf_s2_v2(
                    %s, %s::vector, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    query_text,
                    query_embedding,
                    filter_dataset,
                    filter_category,
                    filter_document_type,
                    filter_year,
                    result_limit,
                    rrf_k,
                ),
            )

            results: List[Dict] = []
            patched_count = 0
            for row in cur.fetchall():
                # s2_v2 doc_id patch (metadata normalization)
                metadata = row[11] if isinstance(row[11], dict) else {}
                if not isinstance(metadata, dict):
                    metadata = {}
                if metadata.get("doc_id") in (None, ""):
                    doc_id = metadata.get("doc_id") or metadata.get("document_id")
                    if not doc_id:
                        doc_id = metadata.get("case_number") or metadata.get("case_no")
                    if not doc_id:
                        source_url = row[7]
                        if source_url:
                            doc_id = hashlib.sha1(source_url.encode("utf-8")).hexdigest()
                    if not doc_id:
                        doc_id = row[0]
                    if doc_id:
                        metadata["doc_id"] = doc_id
                        patched_count += 1
                results.append(
                    {
                        "chunk_id": row[0],
                        "dataset_type": row[1],
                        "category": row[2],
                        "text": row[3],
                        "rrf_score": float(row[4]),
                        "bm25_score": float(row[5]),
                        "vector_similarity": float(row[6]),
                        "source_url": row[7],
                        "source_file": row[8],
                        "printed_page": row[9],
                        "source_year": row[10],
                        "metadata": metadata,
                    }
                )

        if patched_count > 0:
            logger.info(
                json.dumps(
                    {
                        "event": "retriever_doc_id_patch",
                        "selected_fn": "s2_v2",
                        "patched_count": patched_count,
                    },
                    ensure_ascii=False,
                )
            )
        if results and logger.isEnabledFor(logging.DEBUG):
            logger.debug("hybrid_rrf_s2_v2: first_category=%s", results[0].get("category"))

        return results

    def search_hybrid_rrf_s3(
        self,
        query_text: str,
        filter_dataset: Optional[str] = None,
        filter_category: Optional[str] = None,
        filter_document_type: Optional[str] = None,
        filter_year: Optional[int] = None,
        result_limit: int = 10,
        rrf_k: int = 60,
    ) -> List[Dict]:
        return self._search_hybrid_rrf_fn(
            "search_hybrid_rrf_s3",
            query_text,
            filter_dataset,
            filter_category,
            filter_document_type,
            filter_year,
            result_limit,
            rrf_k,
        )

    def search_hybrid_rrf_best(
        self,
        query_text: str,
        filter_dataset: Optional[str] = None,
        filter_category: Optional[str] = None,
        filter_document_type: Optional[str] = None,
        filter_year: Optional[int] = None,
        result_limit: int = 10,
        rrf_k: int = 60,
    ) -> List[Dict]:
        fn_choice = os.getenv("RETRIEVAL_HYBRID_FN", "s2").lower()
        use_s3 = fn_choice == "s3"
        use_s2_v2 = fn_choice == "s2_v2"
        if use_s3:
            selected = "s3"
        elif use_s2_v2:
            selected = "s2_v2"
        else:
            selected = "s2"
        logger.info(
            "hybrid_rrf_best: selected=%s filter_dataset=%s filter_category=%s",
            selected,
            filter_dataset,
            filter_category,
        )
        if use_s3:
            return self.search_hybrid_rrf_s3(
                query_text=query_text,
                filter_dataset=filter_dataset,
                filter_category=filter_category,
                filter_document_type=filter_document_type,
                filter_year=filter_year,
                result_limit=result_limit,
                rrf_k=rrf_k,
            )
        if use_s2_v2:
            return self.search_hybrid_rrf_s2_v2(
                query_text=query_text,
                filter_dataset=filter_dataset,
                filter_category=filter_category,
                filter_document_type=filter_document_type,
                filter_year=filter_year,
                result_limit=result_limit,
                rrf_k=rrf_k,
            )
        return self.search_hybrid_rrf_s2(
            query_text=query_text,
            filter_dataset=filter_dataset,
            filter_category=filter_category,
            filter_document_type=filter_document_type,
            filter_year=filter_year,
            result_limit=result_limit,
            rrf_k=rrf_k,
        )

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
    client = RDSRetriever()
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


def hybrid_rrf_search_s3(
    query_text: str,
    *,
    filter_dataset: Optional[str] = None,
    filter_category: Optional[str] = None,
    filter_document_type: Optional[str] = None,
    filter_year: Optional[int] = None,
    result_limit: int = 10,
    rrf_k: int = 60,
) -> Tuple[List[Dict], float]:
    client = RDSRetriever()
    client.connect()
    try:
        results = client.search_hybrid_rrf_s3(
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

    return results, 0.0


__all__ = [
    "SimilarChunkResult",
    "RDSRetriever",
    "hybrid_rrf_search",
    "hybrid_rrf_search_s3",
]
