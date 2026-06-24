"""똑소리 프로젝트 - guardrail_events 영속화 계층 (M3-7).

보안 판단 1회 = row 1개. A(input/output moderation + review)/B(input/output).

설계 (M3-7 계획서):
- workflow_runs(run_id)를 FK로 참조. run 1 : guardrail N.
- A는 _node_timings[node].output_snapshot에서 read-only로 구성(A frozen):
  input_guardrail/output_guardrail(guardrail_blocked/type), review(passed/violations).
- B는 run_b trace의 guardrail_input/output(blocked/flagged + categories 계측).
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


def _snapshot(node_timings: Dict[str, Dict], node: str) -> Optional[Dict]:
    t = (node_timings or {}).get(node)
    if not t:
        return None
    return t.get("output_snapshot") or {}


def build_a_guardrail_events(
    node_timings: Optional[Dict[str, Dict]] = None,
) -> List[Dict[str, Any]]:
    """A: input_guardrail/output_guardrail(moderation) + review(legal) → 행 목록.

    실행된 노드(_node_timings 존재)만 행 생성. read-only.
    """
    node_timings = node_timings or {}
    events: List[Dict[str, Any]] = []
    seq = 0

    # input_guardrail (moderation)
    snap = _snapshot(node_timings, "input_guardrail")
    if snap is not None:
        blocked = bool(snap.get("guardrail_blocked"))
        events.append(
            {
                "seq": seq,
                "stage": "input",
                "source": "moderation",
                "decision": "block" if blocked else "pass",
                "reason": snap.get("guardrail_type") if blocked else None,
                "detail": None,
            }
        )
        seq += 1

    # output_guardrail (moderation) — snapshot lacks guardrail_type -> reason NULL
    snap = _snapshot(node_timings, "output_guardrail")
    if snap is not None:
        blocked = bool(snap.get("guardrail_blocked"))
        events.append(
            {
                "seq": seq,
                "stage": "output",
                "source": "moderation",
                "decision": "block" if blocked else "pass",
                "reason": None,
                "detail": None,
            }
        )
        seq += 1

    # review (legal_review, rule-based violations)
    snap = _snapshot(node_timings, "review")
    if snap is not None:
        review = snap.get("review") or {}
        passed = review.get("passed", True)
        violations = review.get("violations") or []
        reason = ",".join(
            sorted({v.get("type") for v in violations if v.get("type")})
        ) or None
        events.append(
            {
                "seq": seq,
                "stage": "review",
                "source": "legal_review",
                "decision": "pass" if passed else "flag",
                "reason": reason,
                "detail": {"violations": violations} if violations else None,
            }
        )
        seq += 1

    return events


def build_b_guardrail_events(trace: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """B: run_b trace의 guardrail_input/output 스텝 → 행 목록."""
    stage_for = {"guardrail_input": "input", "guardrail_output": "output"}
    events: List[Dict[str, Any]] = []
    seq = 0
    for step in trace:
        stage = stage_for.get(step.get("step"))
        if not stage:
            continue
        blocked = bool(step.get("blocked"))
        flagged = bool(step.get("flagged"))
        decision = "block" if blocked else ("flag" if flagged else "pass")
        cats = step.get("categories") or []  # M3-7: flagged category names
        events.append(
            {
                "seq": seq,
                "stage": stage,
                "source": "moderation",
                "decision": decision,
                "reason": ",".join(cats) if cats else None,
                "detail": {"categories": cats} if cats else None,
            }
        )
        seq += 1
    return events


class GuardrailEventDB:
    """guardrail_events 테이블 접근 계층 (ConversationDB 패턴)."""

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
                    INSERT INTO guardrail_events
                        (run_id, seq, stage, source, decision, reason, detail)
                    VALUES %s
                    ON CONFLICT (run_id, seq) DO NOTHING
                    """,
                    [
                        (
                            run_id,
                            e["seq"],
                            e["stage"],
                            e["source"],
                            e["decision"],
                            e.get("reason"),
                            psycopg2.extras.Json(e.get("detail"))
                            if e.get("detail") is not None
                            else None,
                        )
                        for e in events
                    ],
                )
            conn.commit()
        finally:
            conn.close()


async def save_guardrail_events(
    run_id: str,
    events: List[Dict[str, Any]],
    db: Optional[GuardrailEventDB] = None,
) -> bool:
    """guardrail_events에 행을 best-effort로 저장한다 (실패 시 예외 삼킴)."""
    if not events:
        return False
    runner = db or GuardrailEventDB()
    try:
        await asyncio.to_thread(runner.insert_events, run_id, events)
        logger.info(
            f"[guardrail_events] saved run={run_id[:8]} events={len(events)}"
        )
        return True
    except Exception as e:
        logger.warning(
            f"[guardrail_events] save failed (non-blocking) run={run_id[:8]}: {e}"
        )
        return False
