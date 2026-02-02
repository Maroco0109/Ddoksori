# -*- coding: utf-8 -*-
"""RDS retriever (stored functions): dense, BM25, and hybrid searches."""

import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import psycopg2
import requests


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
        if not self.conn:
            raise RuntimeError(
                "Database connection is not initialized. Call connect() first."
            )

        query_embedding = self.embed_query(query_text)

        with self.conn.cursor() as cur:
            sql_start = time.time()
            cur.execute(
                """
                SELECT * FROM search_hybrid_rrf_2(
                    %s, %s::vector, %s, %s, %s::varchar[], %s::varchar[], %s, %s, %s, %s
                )
                """,
                (
                    query_text,
                    query_embedding,
                    filter_dataset,
                    filter_category,
                    filter_document_type,
                    filter_chunk_type,
                    filter_year_from,
                    filter_year_to,
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

    @staticmethod
    def _get_embed_api_url() -> str:
        return os.getenv("EMBED_API_URL", "http://localhost:8001/embed")


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
