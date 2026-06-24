"""똑소리 프로젝트 - workflow 관측 조회 계층 (M3-8, read-only).

M3-3~M3-7 저장 계층(workflow_runs/steps/retrieval_events/llm_calls/
guardrail_events)을 읽어 최근 run 목록과 run detail을 반환한다.

- SELECT만(read-only). 저장 경로·A/B 무변경.
- ConversationDB 패턴: psycopg2 RealDictCursor, 호출마다 연결 생성/종료,
  asyncio.to_thread로 async 래핑.
"""

import asyncio
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

from app.common.config import DatabaseConfig, get_config

# detail에서 묶을 자식 테이블 (seq 순)
_CHILD_TABLES = [
    "workflow_steps",
    "retrieval_events",
    "llm_calls",
    "guardrail_events",
    "protocol_events",
]


class RunQueryDB:
    """workflow_runs 및 자식 테이블 조회 계층 (read-only)."""

    def __init__(self, db_config: Optional[DatabaseConfig] = None):
        self.db_config = db_config or get_config().database

    def _get_connection(self):
        return psycopg2.connect(**self.db_config.get_connection_dict())

    def list_runs(
        self,
        limit: int = 50,
        offset: int = 0,
        variant: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        where = []
        params: List[Any] = []
        if variant:
            where.append("variant = %s")
            params.append(variant)
        if status:
            where.append("status = %s")
            params.append(status)
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        params.extend([limit, offset])

        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT run_id, variant, status, query, chat_type,
                           total_time_ms, clarified, blocked, started_at, created_at
                    FROM workflow_runs
                    {where_sql}
                    ORDER BY started_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    params,
                )
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def get_run_detail(self, run_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM workflow_runs WHERE run_id = %s", (run_id,)
                )
                run = cur.fetchone()
                if not run:
                    return None

                detail: Dict[str, Any] = {"run": dict(run)}
                for table in _CHILD_TABLES:
                    cur.execute(
                        f"SELECT * FROM {table} WHERE run_id = %s ORDER BY seq",
                        (run_id,),
                    )
                    detail[table] = [dict(r) for r in cur.fetchall()]
                return detail
        finally:
            conn.close()


_query_db: Optional[RunQueryDB] = None


def get_run_query_db() -> RunQueryDB:
    global _query_db
    if _query_db is None:
        _query_db = RunQueryDB()
    return _query_db


async def list_runs(
    limit: int = 50,
    offset: int = 0,
    variant: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return await asyncio.to_thread(
        get_run_query_db().list_runs, limit, offset, variant, status
    )


async def get_run_detail(run_id: str) -> Optional[Dict[str, Any]]:
    return await asyncio.to_thread(get_run_query_db().get_run_detail, run_id)
