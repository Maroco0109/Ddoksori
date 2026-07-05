"""똑소리 프로젝트 - protocol_events 영속화 계층 (M3-9).

run의 내부 의사결정 궤적 = row N개.
- A: supervisor 라우팅/노드별 protocol_summary (inter-agent 소통).
- B: ReAct 메시지 궤적 (AIMessage 추론+tool_calls, ToolMessage 관찰).

설계 (M3-9 계획서):
- workflow_runs(run_id)를 FK로 참조. kind(node/ai/tool)로 A/B 구분.
- A는 _agent_trace_entries에서 read-only(A frozen). B는 run_b가 distill한
  protocol_messages를 받는다(B만 계측, 답변 무변경).
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

CONTENT_PREVIEW = 500  # B reasoning/관찰 본문 절단 길이


def build_a_protocol_events(
    trace_entries: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """A: _agent_trace_entries → node 궤적 행 목록 (read-only).

    timestamp 순 정렬(M3-4 pipeline_summary와 동일 순서).
    """
    entries = sorted(trace_entries or [], key=lambda e: e.get("timestamp", 0))
    events: List[Dict[str, Any]] = []
    for seq, e in enumerate(entries):
        events.append(
            {
                "seq": seq,
                "kind": "node",
                "name": e.get("node_name"),
                "summary": e.get("protocol_summary"),
                "content": None,
            }
        )
    return events


def build_b_protocol_events(
    protocol_messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """B: run_b가 distill한 protocol_messages → ai/tool 궤적 행 목록."""
    events: List[Dict[str, Any]] = []
    for seq, m in enumerate(protocol_messages):
        kind = m.get("kind")
        if kind == "ai":
            tool_calls = m.get("tool_calls") or []
            events.append(
                {
                    "seq": seq,
                    "kind": "ai",
                    "name": None,
                    "summary": {"tool_calls": tool_calls} if tool_calls else None,
                    "content": m.get("content"),
                }
            )
        elif kind == "tool":
            events.append(
                {
                    "seq": seq,
                    "kind": "tool",
                    "name": m.get("name"),
                    "summary": None,
                    "content": m.get("content"),
                }
            )
    return events


class ProtocolEventDB:
    """protocol_events 테이블 접근 계층 (ConversationDB 패턴)."""

    def __init__(self, db_config: Optional[DatabaseConfig] = None):
        self.db_config = db_config or get_config().database

    def _get_connection(self):
        return psycopg2.connect(**self.db_config.get_connection_dict())

    def insert_events(
        self, run_id: str, variant: str, events: List[Dict[str, Any]]
    ) -> None:
        if not events:
            return
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO protocol_events
                        (run_id, seq, variant, kind, name, summary, content)
                    VALUES %s
                    ON CONFLICT (run_id, seq) DO NOTHING
                    """,
                    [
                        (
                            run_id,
                            e["seq"],
                            variant,
                            e["kind"],
                            e.get("name"),
                            psycopg2.extras.Json(e.get("summary"))
                            if e.get("summary") is not None
                            else None,
                            e.get("content"),
                        )
                        for e in events
                    ],
                )
            conn.commit()
        finally:
            conn.close()


async def save_protocol_events(
    run_id: str,
    variant: str,
    events: List[Dict[str, Any]],
    db: Optional[ProtocolEventDB] = None,
) -> bool:
    """protocol_events에 행을 best-effort로 저장한다 (실패 시 예외 삼킴)."""
    if not events:
        return False
    runner = db or ProtocolEventDB()
    try:
        await asyncio.to_thread(runner.insert_events, run_id, variant, events)
        logger.info(
            f"[protocol_events] saved run={run_id[:8]} variant={variant} events={len(events)}"
        )
        return True
    except Exception as e:
        logger.warning(
            f"[protocol_events] save failed (non-blocking) run={run_id[:8]}: {e}"
        )
        return False
