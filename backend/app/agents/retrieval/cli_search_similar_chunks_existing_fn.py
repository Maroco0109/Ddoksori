"""CLI (existing DB function): python <file> "<query>" -> prints results."""

import os
import sys
import argparse
from dataclasses import dataclass
from typing import Dict, List, Optional

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


class SearchSimilarChunksClient:
    """Client for calling the search_similar_chunks() function."""

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

        try:
            response = requests.post(
                self.embed_api_url,
                json={"texts": [query]},
                timeout=10,
            )
            response.raise_for_status()
            return response.json()["embeddings"][0]
        except requests.exceptions.RequestException as exc:
            raise Exception(f"Embed API error: {exc}")

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

    def search(
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

            results = []
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

            results = []
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Search using existing DB functions (dense or hybrid RRF)."
    )
    parser.add_argument("query", help="Search query text")
    parser.add_argument(
        "--mode",
        choices=["dense_fn", "hybrid_rrf"],
        default="dense_fn",
        help="Search mode (default: dense_fn)",
    )
    parser.add_argument("--dataset", dest="filter_dataset", default=None)
    parser.add_argument("--category", dest="filter_category", default=None)
    parser.add_argument("--law-name", dest="filter_law_name", default=None)
    parser.add_argument("--year", dest="filter_year", type=int, default=None)
    parser.add_argument("--document-type", dest="filter_document_type", default=None)
    parser.add_argument("--limit", dest="result_limit", type=int, default=5)
    parser.add_argument("--rrf-k", dest="rrf_k", type=int, default=60)

    args = parser.parse_args()

    if load_dotenv:
        env_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "backend", ".env")
        )
        load_dotenv(env_path)

    query = args.query

    client = SearchSimilarChunksClient()
    client.connect()
    try:
        if args.mode == "hybrid_rrf":
            results = client.search_hybrid_rrf(
                query_text=query,
                filter_dataset=args.filter_dataset,
                filter_category=args.filter_category,
                filter_document_type=args.filter_document_type,
                filter_year=args.filter_year,
                result_limit=args.result_limit,
                rrf_k=args.rrf_k,
            )
        else:
            results = client.search(
                query=query,
                filter_dataset=args.filter_dataset,
                filter_category=args.filter_category,
                filter_law_name=args.filter_law_name,
                filter_year=args.filter_year,
                result_limit=args.result_limit,
            )
    finally:
        client.close()

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
