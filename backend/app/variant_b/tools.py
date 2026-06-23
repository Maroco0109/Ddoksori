"""Variant B retrieval tool + shared search helper.

`search()` wraps A's SQL `search_hybrid_rrf` (no filter) so B uses the SAME
retrieval primitive as the M2-4R A baseline (A/B parity). It also returns
`max_cosine`, which the deterministic clarification gate consumes.

DB connection defaults to localhost (EVAL_DB_* overridable). OPENAI_API_KEY is
read from the environment (load .env before importing/using).
"""

import os
from typing import Dict, List, Tuple

import psycopg2
from langchain_core.tools import tool
from openai import OpenAI

EMBED_MODEL = "text-embedding-3-large"
EMBED_DIM = 1536

_openai: OpenAI | None = None


def _client() -> OpenAI:
    global _openai
    if _openai is None:
        _openai = OpenAI()
    return _openai


def _conn():
    return psycopg2.connect(
        host=os.getenv("EVAL_DB_HOST", "localhost"),
        port=int(os.getenv("EVAL_DB_PORT", "5432")),
        dbname=os.getenv("EVAL_DB_NAME", "ddoksori"),
        user=os.getenv("EVAL_DB_USER", "postgres"),
        password=os.getenv("EVAL_DB_PASSWORD", "postgres"),
    )


def embed(text: str) -> List[float]:
    return (
        _client()
        .embeddings.create(model=EMBED_MODEL, input=text, dimensions=EMBED_DIM)
        .data[0]
        .embedding
    )


def search(query: str, top_k: int = 5, rrf_k: int = 10) -> Tuple[List[Dict], float]:
    """Core retriever (same SQL function A uses). Returns (docs, max_cosine)."""
    emb = embed(query)
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT chunk_id, dataset_type, category, vector_similarity, text "
        "FROM search_hybrid_rrf(%s::text, %s::vector(1536), NULL::varchar(20), "
        "NULL::varchar(50), NULL::varchar(20), NULL::integer, %s::integer, %s::integer)",
        (query, str(emb), top_k, rrf_k),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    docs = [
        {"chunk_id": r[0], "dataset_type": r[1], "category": r[2],
         "cosine": float(r[3]), "text": r[4]}
        for r in rows
    ]
    max_cosine = max((d["cosine"] for d in docs), default=0.0)
    return docs, max_cosine


@tool
def search_consumer_disputes(query: str, top_k: int = 5) -> str:
    """한국 소비자분쟁 코퍼스(법령·분쟁해결기준·상담/조정 사례)에서 query와 관련된 근거를 검색한다.

    답변에 필요한 사실/기준/사례 근거를 찾을 때 사용한다.
    """
    docs, _ = search(query, top_k=top_k)
    if not docs:
        return "검색 결과 없음."
    return "\n\n".join(
        f"[{i + 1}] ({d['dataset_type']}/{d['category']}) {d['text'][:400]}"
        for i, d in enumerate(docs)
    )
