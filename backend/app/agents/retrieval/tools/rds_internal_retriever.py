# -*- coding: utf-8 -*-
"""RDS retriever (stored functions): dense, BM25, and hybrid searches."""

import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import psycopg2


@dataclass
class SimilarChunkResult:
    chunk_id: str
    dataset_type: str
    text: str
    similarity: float
    law_name: Optional[str]
    chunk_type: Optional[str]
    category: Optional[str]
    document_type: Optional[str]
    source_url: Optional[str]
    source_file: Optional[str]
    printed_page: Optional[int]
    source_year: Optional[int]
    metadata: Optional[Dict]
    vector_similarity: Optional[float] = None
    rrf_score: Optional[float] = None


class RDSInternalRetriever:
    """Client for calling stored DB functions on vector_chunks."""

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
        """쿼리 임베딩 생성 (OpenAI text-embedding-3-large), Redis 캐시 지원"""
        model_name = "text-embedding-3-large"

        # 캐시 조회
        from app.common.cache import EmbeddingCache

        cached = EmbeddingCache.get_embedding(query, model_name)
        if cached is not None:
            return cached

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
            model=model_name,
            input=[query],
            dimensions=1536,
        )
        embedding = response.data[0].embedding

        # 캐시 저장
        EmbeddingCache.set_embedding(query, model_name, embedding)

        return embedding

    def dense_search(
        self,
        query: str,
        filter_dataset: Optional[str] = None,
        filter_category: Optional[str] = None,
        filter_law_name: Optional[str] = None,
        filter_year: Optional[int] = None,
        result_limit: int = 10,
    ) -> List[SimilarChunkResult]:
        if not self.conn:
            raise RuntimeError(
                "Database connection is not initialized. Call connect() first."
            )

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
                        document_type=None,
                        source_url=row[7],
                        source_file=row[8],
                        printed_page=row[9],
                        source_year=row[10],
                        metadata=row[11],
                    )
                )

        return results

    def hybrid_search(
        self,
        query: str,
        law_limit: int = 5,
        case_limit: int = 5,
        filter_category: Optional[str] = None,
        filter_year: Optional[int] = None,
    ) -> List[Dict]:
        if not self.conn:
            raise RuntimeError(
                "Database connection is not initialized. Call connect() first."
            )

        query_embedding = self.embed_query(query)

        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM search_hybrid(
                    %s::vector, %s, %s, %s, %s
                )
                """,
                (
                    query_embedding,
                    law_limit,
                    case_limit,
                    filter_category,
                    filter_year,
                ),
            )

            results: List[Dict] = []
            for row in cur.fetchall():
                results.append(
                    {
                        "source": row[0],
                        "chunk_id": row[1],
                        "text": row[2],
                        "similarity": float(row[3]),
                        "law_name": row[4],
                        "category": row[5],
                        "source_url": row[6],
                        "source_file": row[7],
                        "printed_page": row[8],
                        "source_year": row[9],
                        "metadata": row[10],
                    }
                )

        return results

    def search_with_keywords(
        self,
        query: str,
        keyword: str,
        result_limit: int = 10,
    ) -> List[Dict]:
        if not self.conn:
            raise RuntimeError(
                "Database connection is not initialized. Call connect() first."
            )

        query_embedding = self.embed_query(query)

        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM search_with_keywords(
                    %s::vector, %s, %s
                )
                """,
                (
                    query_embedding,
                    keyword,
                    result_limit,
                ),
            )

            results: List[Dict] = []
            for row in cur.fetchall():
                results.append(
                    {
                        "chunk_id": row[0],
                        "dataset_type": row[1],
                        "text": row[2],
                        "similarity": float(row[3]),
                        "metadata": row[4],
                    }
                )

        return results

    def bm25_search(
        self,
        query_text: str,
        filter_dataset: Optional[str] = None,
        filter_category: Optional[str] = None,
        filter_document_type: Optional[str] = None,
        result_limit: int = 100,
    ) -> List[Dict]:
        if not self.conn:
            raise RuntimeError(
                "Database connection is not initialized. Call connect() first."
            )

        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM search_bm25(
                    %s, %s, %s, %s, %s
                )
                """,
                (
                    query_text,
                    filter_dataset,
                    filter_category,
                    filter_document_type,
                    result_limit,
                ),
            )

            results: List[Dict] = []
            for row in cur.fetchall():
                results.append(
                    {
                        "chunk_id": row[0],
                        "dataset_type": row[1],
                        "text": row[2],
                        "bm25_score": float(row[3]),
                        "bm25_rank": int(row[4]),
                    }
                )

        return results

    def hybrid_rrf_search(
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
            raise RuntimeError(
                "Database connection is not initialized. Call connect() first."
            )

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
                        "law_name": row[6],
                        "chunk_type": row[7],
                        "category": row[8],
                        "document_type": row[9],
                        "source_url": row[10],
                        "source_file": row[11],
                        "printed_page": row[12],
                        "source_year": row[13],
                        "metadata": row[14],
                    }
                )

        return results

    def search_hybrid_rrf_2(
        self,
        query_text: str,
        filter_dataset: Optional[str] = None,
        filter_category: Optional[str] = None,
        filter_document_type: Optional[List[str]] = None,
        filter_chunk_type: Optional[List[str]] = None,
        filter_year_from: Optional[int] = None,
        filter_year_to: Optional[int] = None,
        result_limit: int = 10,
        rrf_k: int = 60,
    ) -> Tuple[List[Dict], float]:
        """
        Hybrid RRF search with metadata support.

        This version includes JSONB metadata search for better matching on
        items stored in metadata fields (소분류, 중분류, dispute_type, etc.)
        """
        if not self.conn:
            raise RuntimeError(
                "Database connection is not initialized. Call connect() first."
            )

        query_embedding = self.embed_query(query_text)
        sql_start = time.time()

        # Build WHERE clause components
        where_conditions = []
        params = {
            "query_text": query_text,
            "query_pattern": f"%{query_text}%",  # For ILIKE matching
            "query_embedding": query_embedding,
            "rrf_k": rrf_k,
            "result_limit": result_limit,
        }

        # Base filters
        if filter_dataset:
            where_conditions.append("vc.dataset_type = %(filter_dataset)s")
            params["filter_dataset"] = filter_dataset

        if filter_category:
            where_conditions.append("vc.category = %(filter_category)s")
            params["filter_category"] = filter_category

        if filter_document_type:
            where_conditions.append("vc.document_type = ANY(%(filter_document_type)s)")
            params["filter_document_type"] = filter_document_type

        if filter_chunk_type:
            where_conditions.append("vc.chunk_type = ANY(%(filter_chunk_type)s)")
            params["filter_chunk_type"] = filter_chunk_type

        if filter_year_from:
            where_conditions.append("vc.source_year >= %(filter_year_from)s")
            params["filter_year_from"] = filter_year_from

        if filter_year_to:
            where_conditions.append("vc.source_year <= %(filter_year_to)s")
            params["filter_year_to"] = filter_year_to

        where_clause = " AND ".join(where_conditions) if where_conditions else "TRUE"

        # Enhanced BM25 search with metadata fields
        # Searches: text_tsv (main) + JSONB metadata fields (소분류, 중분류, 품목, dispute_type)
        bm25_query = f"""
            WITH bm25_results AS (
                SELECT
                    vc.chunk_id,
                    ts_rank_cd('{{0.1, 0.2, 0.4, 0.6}}', vc.text_tsv, plainto_tsquery('simple', %(query_text)s))::FLOAT as score,
                    ROW_NUMBER() OVER (ORDER BY ts_rank_cd('{{0.1, 0.2, 0.4, 0.6}}', vc.text_tsv, plainto_tsquery('simple', %(query_text)s)) DESC) as rank
                FROM vector_chunks vc
                WHERE
                    (
                        vc.text_tsv @@ plainto_tsquery('simple', %(query_text)s)
                        OR (vc.metadata->>'소분류') ILIKE %(query_pattern)s
                        OR (vc.metadata->>'중분류') ILIKE %(query_pattern)s
                        OR (vc.metadata->>'품목') ILIKE %(query_pattern)s
                        OR (vc.metadata->>'dispute_type') ILIKE %(query_pattern)s
                        OR (vc.metadata->>'category_name') ILIKE %(query_pattern)s
                        OR (vc.metadata->>'subcategory_name') ILIKE %(query_pattern)s
                    )
                    AND {where_clause}
                ORDER BY score DESC
                LIMIT 100
            ),
            vector_results AS (
                SELECT
                    vc.chunk_id,
                    (1 - (vc.embedding <=> %(query_embedding)s::vector))::FLOAT as similarity,
                    ROW_NUMBER() OVER (ORDER BY vc.embedding <=> %(query_embedding)s::vector) as rank
                FROM vector_chunks vc
                WHERE {where_clause}
                ORDER BY vc.embedding <=> %(query_embedding)s::vector
                LIMIT 100
            ),
            rrf_combined AS (
                SELECT
                    COALESCE(b.chunk_id, v.chunk_id) as chunk_id,
                    (COALESCE(1.0 / (%(rrf_k)s + b.rank), 0) +
                     COALESCE(1.0 / (%(rrf_k)s + v.rank), 0))::FLOAT as rrf_score,
                    COALESCE(b.score, 0)::FLOAT as bm25_score,
                    COALESCE(v.similarity, 0)::FLOAT as vector_similarity
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
                vc.law_name,
                vc.chunk_type,
                vc.category,
                vc.document_type,
                vc.source_url,
                vc.source_file,
                vc.printed_page,
                vc.source_year,
                vc.metadata
            FROM rrf_combined rc
            JOIN vector_chunks vc ON rc.chunk_id = vc.chunk_id
            ORDER BY rc.rrf_score DESC
            LIMIT %(result_limit)s
        """

        with self.conn.cursor() as cur:
            cur.execute(bm25_query, params)

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
                        "law_name": row[6],
                        "chunk_type": row[7],
                        "category": row[8],
                        "document_type": row[9],
                        "source_url": row[10],
                        "source_file": row[11],
                        "printed_page": row[12],
                        "source_year": row[13],
                        "metadata": row[14],
                    }
                )

        sql_ms = (time.time() - sql_start) * 1000
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


__all__ = [
    "SimilarChunkResult",
    "RDSInternalRetriever",
    "search_hybrid_rrf_2",
]


def search_hybrid_rrf_2(
    query_text: str,
    *,
    filter_dataset: Optional[str] = None,
    filter_category: Optional[str] = None,
    filter_document_type: Optional[List[str]] = None,
    filter_chunk_type: Optional[List[str]] = None,
    filter_year_from: Optional[int] = None,
    filter_year_to: Optional[int] = None,
    result_limit: int = 10,
    rrf_k: int = 60,
) -> Tuple[List[Dict], float]:
    client = RDSInternalRetriever()
    client.connect()
    try:
        return client.search_hybrid_rrf_2(
            query_text=query_text,
            filter_dataset=filter_dataset,
            filter_category=filter_category,
            filter_document_type=filter_document_type,
            filter_chunk_type=filter_chunk_type,
            filter_year_from=filter_year_from,
            filter_year_to=filter_year_to,
            result_limit=result_limit,
            rrf_k=rrf_k,
        )
    finally:
        client.close()
