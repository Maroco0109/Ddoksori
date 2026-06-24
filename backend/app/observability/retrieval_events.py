"""똑소리 프로젝트 - retrieval_events 영속화 계층 (M3-5).

검색 호출 1회 = row 1개. A(MAS 4섹션)/B(gate + tool) 공통.

설계 (M3-5 계획서):
- workflow_runs(run_id)를 FK로 참조. run 1 : retrieval N.
- top-k의 (chunk_id, similarity, rank)를 top_chunks JSONB로 보존(retrieval 품질).
- A 출처: final_state["retrieval"] 4섹션(laws/criteria/disputes/counsels).
- B 출처: run_b retrieval_records (gate + per-search tool 계측).
- best-effort(비차단): 저장 실패가 /chat 응답을 깨지 않도록 예외를 삼킨다.
- batch INSERT ... ON CONFLICT (run_id, seq) DO NOTHING 으로 멱등.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

from app.common.config import DatabaseConfig, get_config

logger = logging.getLogger(__name__)

# A: 섹션 키 → (source 라벨, id 필드 후보)
_A_SECTIONS = [
    ("laws", "law"),
    ("criteria", "criteria"),
    ("disputes", "case"),
    ("counsels", "counsel"),
]


def _agg(sims: List[float]) -> Dict[str, Optional[float]]:
    vals = [s for s in sims if s is not None]
    if not vals:
        return {"max": None, "avg": None}
    return {"max": max(vals), "avg": sum(vals) / len(vals)}


def build_a_retrieval_events(
    retrieval: Dict[str, Any], top_k: int, query: str
) -> List[Dict[str, Any]]:
    """A: final_state["retrieval"] 4섹션 → retrieval_event 행 목록."""
    events: List[Dict[str, Any]] = []
    seq = 0
    for section_key, source in _A_SECTIONS:
        items = retrieval.get(section_key) or []
        if not items:
            continue
        sims = [it.get("similarity") for it in items]
        stats = _agg(sims)
        top_chunks = [
            {
                "chunk_id": it.get("chunk_id") or it.get("unit_id"),
                "similarity": it.get("similarity"),
                "rank": i,
            }
            for i, it in enumerate(items[:top_k])
        ]
        events.append(
            {
                "seq": seq,
                "source": source,
                "query": query,
                "domain": None,
                "top_k": top_k,
                "result_count": len(items),
                "max_similarity": stats["max"],
                "avg_similarity": stats["avg"],
                "top_chunks": top_chunks,
            }
        )
        seq += 1
    return events


def build_b_retrieval_events(
    retrieval_records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """B: run_b retrieval_records(gate + tool, 각 docs=[{chunk_id,cosine}]) → 행 목록."""
    events: List[Dict[str, Any]] = []
    for seq, rec in enumerate(retrieval_records):
        docs = rec.get("docs") or []
        sims = [d.get("cosine") for d in docs]
        stats = _agg(sims)
        top_chunks = [
            {"chunk_id": d.get("chunk_id"), "similarity": d.get("cosine"), "rank": i}
            for i, d in enumerate(docs[: (rec.get("top_k") or len(docs))])
        ]
        events.append(
            {
                "seq": seq,
                "source": rec.get("source", "other"),
                "query": rec.get("query"),
                "domain": rec.get("domain"),
                "top_k": rec.get("top_k"),
                "result_count": len(docs),
                "max_similarity": stats["max"],
                "avg_similarity": stats["avg"],
                "top_chunks": top_chunks,
            }
        )
    return events


class RetrievalEventDB:
    """retrieval_events 테이블 접근 계층 (ConversationDB 패턴)."""

    def __init__(self, db_config: Optional[DatabaseConfig] = None):
        self.db_config = db_config or get_config().database

    def _get_connection(self):
        return psycopg2.connect(**self.db_config.get_connection_dict())

    def insert_events(self, run_id: str, events: List[Dict[str, Any]]) -> None:
        if not events:
            return
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO retrieval_events
                        (run_id, seq, source, query, domain, top_k,
                         result_count, max_similarity, avg_similarity, top_chunks)
                    VALUES %s
                    ON CONFLICT (run_id, seq) DO NOTHING
                    """,
                    [
                        (
                            run_id,
                            e["seq"],
                            e["source"],
                            e.get("query"),
                            e.get("domain"),
                            e.get("top_k"),
                            e["result_count"],
                            e.get("max_similarity"),
                            e.get("avg_similarity"),
                            psycopg2.extras.Json(e.get("top_chunks")),
                        )
                        for e in events
                    ],
                )
            conn.commit()
        finally:
            conn.close()


async def save_retrieval_events(
    run_id: str,
    events: List[Dict[str, Any]],
    db: Optional[RetrievalEventDB] = None,
) -> bool:
    """retrieval_events에 행을 best-effort로 저장한다 (실패 시 예외 삼킴)."""
    if not events:
        return False
    runner = db or RetrievalEventDB()
    try:
        await asyncio.to_thread(runner.insert_events, run_id, events)
        logger.info(
            f"[retrieval_events] saved run={run_id[:8]} events={len(events)}"
        )
        return True
    except Exception as e:
        logger.warning(
            f"[retrieval_events] save failed (non-blocking) run={run_id[:8]}: {e}"
        )
        return False
