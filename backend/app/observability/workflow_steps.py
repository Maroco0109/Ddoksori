"""똑소리 프로젝트 - workflow_steps 영속화 계층 (M3-4).

run 1건의 실행 경로를 step N행으로 저장한다. A(MAS)/B(Agentic) 공통.

설계 (M3-4 계획서):
- workflow_runs(run_id)를 FK로 참조. run 1 : step N.
- `category`로 A 노드와 B 블록을 공통 범주로 묶어 A/B를 SQL 비교 가능하게 한다.
- A 출처: build_pipeline_summary().per_node (seq+node+duration) + _node_timings(start).
- B 출처: run_b trace + run_b 내부 단계 타이머(duration_ms).
- best-effort(비차단): 저장 실패가 /chat 응답을 깨지 않도록 예외를 삼킨다.
- batch INSERT ... ON CONFLICT (run_id, seq) DO NOTHING 으로 멱등.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

from app.common.config import DatabaseConfig, get_config

logger = logging.getLogger(__name__)

# 허용 category (006_workflow_steps.sql CHECK과 일치). 매핑은 항상 이 집합 내 값 반환.
_A_NODE_CATEGORY = {
    "supervisor": "analysis",
    "query_analysis": "analysis",
    "generation": "generation",
    "review": "review",
    "retrieval_law": "retrieval",
    "retrieval_criteria": "retrieval",
    "retrieval_case": "retrieval",
    "retrieval_merge": "retrieval",
    "input_guardrail": "guardrail",
    "output_guardrail": "guardrail",
}

_B_STEP_CATEGORY = {
    "guardrail_input": "guardrail",
    "guardrail_output": "guardrail",
    "gate_retrieval": "retrieval",
    "react": "generation",
    "clarify": "clarify",
}


def category_for_a_node(node: str) -> str:
    if node in _A_NODE_CATEGORY:
        return _A_NODE_CATEGORY[node]
    if node.startswith("retrieval"):
        return "retrieval"
    if "guardrail" in node:
        return "guardrail"
    return "other"


def category_for_b_step(step: str) -> str:
    return _B_STEP_CATEGORY.get(step, "other")


def build_a_steps(
    per_node: List[Dict[str, Any]],
    node_timings: Optional[Dict[str, Dict]] = None,
) -> List[Dict[str, Any]]:
    """A: build_pipeline_summary().per_node → step 행 목록."""
    node_timings = node_timings or {}
    steps: List[Dict[str, Any]] = []
    for item in per_node:
        node = item.get("node", "unknown")
        start = (node_timings.get(node) or {}).get("start")
        steps.append(
            {
                "seq": item.get("seq", len(steps)),
                "step_name": node,
                "category": category_for_a_node(node),
                "duration_ms": item.get("duration_ms"),
                "started_at": datetime.fromtimestamp(start) if start else None,
            }
        )
    return steps


def build_b_steps(trace: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """B: run_b trace(타이머 포함) → step 행 목록."""
    steps: List[Dict[str, Any]] = []
    for i, t in enumerate(trace):
        name = t.get("step", "unknown")
        steps.append(
            {
                "seq": i,
                "step_name": name,
                "category": category_for_b_step(name),
                "duration_ms": t.get("duration_ms"),
                "started_at": None,
            }
        )
    return steps


class WorkflowStepDB:
    """workflow_steps 테이블 접근 계층 (ConversationDB 패턴)."""

    def __init__(self, db_config: Optional[DatabaseConfig] = None):
        self.db_config = db_config or get_config().database

    def _get_connection(self):
        return psycopg2.connect(**self.db_config.get_connection_dict())

    def insert_steps(self, run_id: str, steps: List[Dict[str, Any]]) -> None:
        if not steps:
            return
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO workflow_steps
                        (run_id, seq, step_name, category, duration_ms, started_at)
                    VALUES %s
                    ON CONFLICT (run_id, seq) DO NOTHING
                    """,
                    [
                        (
                            run_id,
                            s["seq"],
                            s["step_name"],
                            s["category"],
                            s.get("duration_ms"),
                            s.get("started_at"),
                        )
                        for s in steps
                    ],
                )
            conn.commit()
        finally:
            conn.close()


async def save_workflow_steps(
    run_id: str,
    steps: List[Dict[str, Any]],
    db: Optional[WorkflowStepDB] = None,
) -> bool:
    """workflow_steps에 step N행을 best-effort로 저장한다.

    저장 실패 시 예외를 삼키고 False를 반환한다 (호출자 흐름을 깨지 않음).
    """
    if not steps:
        return False
    runner = db or WorkflowStepDB()
    try:
        await asyncio.to_thread(runner.insert_steps, run_id, steps)
        logger.info(
            f"[workflow_steps] saved run={run_id[:8]} steps={len(steps)}"
        )
        return True
    except Exception as e:
        logger.warning(
            f"[workflow_steps] save failed (non-blocking) run={run_id[:8]}: {e}"
        )
        return False
