"""Variant B tools + shared search helper.

`search()` wraps A's SQL `search_hybrid_rrf` so B uses the SAME retrieval
primitive as the M2-4R A baseline (A/B parity). A `domain` argument restricts
to law / criteria / case via WHERE filters (law & criteria each span 2
`document_type` values, handled by a join to `vector_chunks` since the SQL
function's `filter_document_type` is singular). `domain="all"` = no filter.

Also exposes B's M2-3R tool catalog: search_consumer_disputes, verify_citation
(anti-hallucinated-citation), get_law_article, get_case_detail.

DB defaults to localhost (EVAL_DB_* overridable). OPENAI_API_KEY from env.
A (MAS) is NOT imported or modified — read-only DB access only.
"""

import contextvars
import os
import re
from typing import Dict, List, Optional, Tuple

import psycopg2
from langchain_core.tools import tool
from openai import OpenAI

EMBED_MODEL = "text-embedding-3-large"
EMBED_DIM = 1536

# domain -> document_type values (law_guide is split into law vs criteria)
DOMAIN_DOC_TYPES = {"law": ["법률", "시행령"], "criteria": ["별표", "행정규칙"]}

_openai: OpenAI | None = None

# --- Retrieval recorder (M2-7R measurement) -------------------------------
# When active, every search() records the chunk_ids it returned (ranked), so a
# measurement harness can score B's *agentic* retrieval (model query
# reformulation + domain). Off by default -> zero effect on normal runs.
_retrieval_recorder: contextvars.ContextVar[Optional[List[str]]] = contextvars.ContextVar(
    "b_retrieval_recorder", default=None
)


def start_retrieval_recording() -> None:
    """Begin recording chunk_ids returned by search() in this context."""
    _retrieval_recorder.set([])


def get_recorded_retrievals() -> List[str]:
    """Recorded chunk_ids (rank order, with duplicates) since recording start."""
    return list(_retrieval_recorder.get() or [])


def _record_retrieval(chunk_ids: List[str]) -> None:
    rec = _retrieval_recorder.get()
    if rec is not None:
        rec.extend(chunk_ids)


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


def search(
    query: str, top_k: int = 5, rrf_k: int = 10, domain: str = "all"
) -> Tuple[List[Dict], float]:
    """Core retriever (same SQL function A uses) with optional domain filter.

    Returns (docs, max_cosine). domain in {all, law, criteria, case}.
    """
    emb = embed(query)
    conn = _conn()
    cur = conn.cursor()
    # search_hybrid_rrf(query_text, embedding, filter_dataset, filter_category,
    #                   filter_document_type, filter_year, result_limit, rrf_k)
    sql = (
        "SELECT chunk_id, dataset_type, category, vector_similarity, text "
        "FROM search_hybrid_rrf(%s::text, %s::vector(1536), %s::varchar(20), "
        "%s::varchar(50), %s::varchar(20), NULL::integer, %s::integer, %s::integer)"
    )
    try:
        if domain == "case":
            cur.execute(sql, (query, str(emb), "case", None, None, top_k, rrf_k))
            rows = cur.fetchall()
        elif domain in DOMAIN_DOC_TYPES:
            # filter_document_type is singular -> search within each document_type
            # of the domain (법률+시행령 / 별표+행정규칙) and merge by cosine.
            merged: Dict[str, tuple] = {}
            for dtype in DOMAIN_DOC_TYPES[domain]:
                cur.execute(sql, (query, str(emb), "law_guide", None, dtype, top_k, rrf_k))
                for r in cur.fetchall():
                    if r[0] not in merged or r[3] > merged[r[0]][3]:
                        merged[r[0]] = r
            rows = sorted(merged.values(), key=lambda r: r[3], reverse=True)[:top_k]
        else:  # all
            cur.execute(sql, (query, str(emb), None, None, None, top_k, rrf_k))
            rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()
    docs = [
        {"chunk_id": r[0], "dataset_type": r[1], "category": r[2],
         "cosine": float(r[3]), "text": r[4]}
        for r in rows
    ]
    _record_retrieval([d["chunk_id"] for d in docs])
    max_cosine = max((d["cosine"] for d in docs), default=0.0)
    return docs, max_cosine


@tool
def search_consumer_disputes(query: str, domain: str = "all", top_k: int = 5) -> str:
    """한국 소비자분쟁 코퍼스에서 query 관련 근거를 검색한다.

    domain으로 검색 대상을 좁힐 수 있다:
    - "law": 법률·시행령
    - "criteria": 소비자분쟁해결기준(별표·행정규칙)
    - "case": 분쟁조정·상담 사례
    - "all"(기본): 전체
    답변에 필요한 사실/기준/사례 근거를 찾을 때 사용한다.
    """
    if domain not in ("all", "law", "criteria", "case"):
        domain = "all"
    docs, _ = search(query, top_k=top_k, domain=domain)
    if not docs:
        return f"검색 결과 없음 (domain={domain})."
    return "\n\n".join(
        f"[{i + 1}] ({d['dataset_type']}/{d['category']}) {d['text'][:400]}"
        for i, d in enumerate(docs)
    )


@tool
def verify_citation(reference: str) -> str:
    """인용한 법령/사례가 코퍼스에 실제 존재하는지 확인한다(허위인용 방지).

    reference 예: 'chunk_id', '전자상거래 등에서의 소비자보호에 관한 법률 제17조',
    또는 사례 식별 문구. 존재하면 발췌와 함께 확인, 없으면 신뢰하지 말라고 알린다.
    """
    conn = _conn()
    cur = conn.cursor()
    row = None
    # 1) exact chunk_id
    cur.execute(
        "SELECT chunk_id, law_name, article_number, dataset_type, left(text, 200) "
        "FROM vector_chunks WHERE chunk_id = %s LIMIT 1",
        (reference,),
    )
    row = cur.fetchone()
    # 2) law name + article number
    if not row:
        m = re.search(r"제\s*\d+\s*조(?:의\s*\d+)?", reference)
        article = m.group(0).replace(" ", "") if m else None
        name = re.sub(r"제\s*\d+.*$", "", reference).strip()
        if name:
            if article:
                cur.execute(
                    "SELECT chunk_id, law_name, article_number, dataset_type, left(text, 200) "
                    "FROM vector_chunks WHERE law_name ILIKE %s "
                    "AND replace(article_number, ' ', '') ILIKE %s LIMIT 1",
                    (f"%{name}%", f"%{article}%"),
                )
            else:
                cur.execute(
                    "SELECT chunk_id, law_name, article_number, dataset_type, left(text, 200) "
                    "FROM vector_chunks WHERE law_name ILIKE %s LIMIT 1",
                    (f"%{name}%",),
                )
            row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return (
            f"확인됨(exists): chunk_id={row[0]}, 법령={row[1]}, 조문={row[2]}, 유형={row[3]}\n"
            f"발췌: {row[4]}"
        )
    return f"확인 안 됨(NOT FOUND): '{reference}' — 코퍼스에 일치 항목 없음. 이 인용은 신뢰하지 말 것."


@tool
def get_law_article(law_name: str, article_number: str) -> str:
    """법령명과 조문번호(예: '제17조')로 조문 원문을 정확히 조회한다."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT chunk_id, law_name, article_number, text FROM vector_chunks "
        "WHERE dataset_type = 'law_guide' AND law_name ILIKE %s "
        "AND replace(article_number, ' ', '') ILIKE %s "
        "ORDER BY length(text) DESC LIMIT 1",
        (f"%{law_name}%", f"%{article_number.replace(' ', '')}%"),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return f"해당 조문을 찾지 못함: {law_name} {article_number}"
    return f"[{row[1]} {row[2]}] (chunk_id={row[0]})\n{row[3]}"


@tool
def get_case_detail(identifier: str) -> str:
    """사례 chunk_id 또는 식별 문구로 분쟁/상담 사례 상세를 조회한다."""
    conn = _conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT chunk_id, category, text FROM vector_chunks "
        "WHERE dataset_type = 'case' AND (chunk_id = %s OR chunk_id ILIKE %s) "
        "ORDER BY length(text) DESC LIMIT 1",
        (identifier, f"%{identifier}%"),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return f"해당 사례를 찾지 못함: {identifier}"
    return f"[case/{row[1]}] (chunk_id={row[0]})\n{row[2]}"


B_TOOLS = [search_consumer_disputes, verify_citation, get_law_article, get_case_detail]
