"""똑소리 프로젝트 - workflow_runs 영속화 계층 (M3-3).

요청 1건 = row 1개. A(MAS)/B(Agentic) 공통.

설계 (M3-3 계획서):
- ConversationDB(supervisor/persistence/db.py)와 동일 관례:
  psycopg2, 호출마다 연결 생성/종료, asyncio.to_thread로 async 래핑.
- best-effort(비차단): 저장 실패가 /chat 응답을 절대 깨뜨리지 않도록
  예외를 삼키고 warning만 남긴다. 관측이 UX를 저해하면 안 된다.
- INSERT ... ON CONFLICT (run_id) DO NOTHING 으로 멱등.

상세(node step, retrieval, llm, guardrail)는 자식 테이블(M3-4~M3-7) 몫이다.
"""

import asyncio
import logging
from typing import Optional

import psycopg2

from app.common.config import DatabaseConfig, get_config

logger = logging.getLogger(__name__)


class WorkflowRunDB:
    """workflow_runs 테이블 접근 계층.

    각 메서드 호출마다 새 연결을 생성/종료한다 (동시성 안전, ConversationDB 패턴).
    """

    def __init__(self, db_config: Optional[DatabaseConfig] = None):
        self.db_config = db_config or get_config().database

    def _get_connection(self):
        return psycopg2.connect(**self.db_config.get_connection_dict())

    def insert_run(
        self,
        *,
        run_id: str,
        variant: str,
        query: str,
        status: str = "success",
        session_id: Optional[str] = None,
        chat_type: Optional[str] = None,
        error_message: Optional[str] = None,
        total_time_ms: Optional[float] = None,
        clarified: Optional[bool] = None,
        blocked: Optional[bool] = None,
    ) -> None:
        """workflow_runs에 row 1건 삽입 (동기). run_id 중복 시 무시."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO workflow_runs
                        (run_id, variant, session_id, chat_type, query, status,
                         error_message, total_time_ms, clarified, blocked)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (run_id) DO NOTHING
                    """,
                    (
                        run_id,
                        variant,
                        session_id,
                        chat_type,
                        query,
                        status,
                        error_message,
                        total_time_ms,
                        clarified,
                        blocked,
                    ),
                )
            conn.commit()
        finally:
            conn.close()


async def save_workflow_run(
    *,
    run_id: str,
    variant: str,
    query: str,
    status: str = "success",
    session_id: Optional[str] = None,
    chat_type: Optional[str] = None,
    error_message: Optional[str] = None,
    total_time_ms: Optional[float] = None,
    clarified: Optional[bool] = None,
    blocked: Optional[bool] = None,
    db: Optional[WorkflowRunDB] = None,
) -> bool:
    """workflow_runs에 run 1건을 best-effort로 저장한다.

    저장 실패 시 예외를 삼키고 False를 반환한다 (호출자 흐름을 깨지 않음).
    성공 시 True.
    """
    runner = db or WorkflowRunDB()
    try:
        await asyncio.to_thread(
            runner.insert_run,
            run_id=run_id,
            variant=variant,
            query=query,
            status=status,
            session_id=session_id,
            chat_type=chat_type,
            error_message=error_message,
            total_time_ms=total_time_ms,
            clarified=clarified,
            blocked=blocked,
        )
        logger.info(
            f"[workflow_runs] saved run={run_id[:8]} variant={variant} "
            f"status={status} ms={round(total_time_ms) if total_time_ms else None}"
        )
        return True
    except Exception as e:
        # best-effort: 관측 저장 실패가 /chat 응답을 깨면 안 된다.
        logger.warning(f"[workflow_runs] save failed (non-blocking) run={run_id[:8]}: {e}")
        return False
