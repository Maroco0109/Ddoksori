"""똑소리 프로젝트 - llm_calls 영속화 계층 (M3-6).

LLM 호출 1회 = row 1개. A 노드(supervisor/query_analysis/generation)/B(react).

설계 (M3-6 계획서):
- workflow_runs(run_id)를 FK로 참조. run 1 : llm_call N.
- A는 final_state/_node_timings에서 read-only로 구성(A frozen). model은
  generation_model_used(실제) 또는 config 파생, token은 미표면화 → NULL.
- B는 run당 1행 집계(react model + usage_metadata 합산 + n_calls).
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

# A에서 LLM을 호출하는 노드(순서). review는 ENABLE_LLM_REVIEW=false면 미호출.
_A_LLM_NODES = ["query_analysis", "supervisor", "generation"]
_RULE_LABELS = {"rule_based", "safe_fallback", "none", "cached"}


def provider_for(model: Optional[str]) -> Optional[str]:
    """model 문자열에서 provider를 파생."""
    if not model:
        return None
    m = model.lower()
    if m in _RULE_LABELS:
        return "rule_based"
    if "exaone" in m or "/" in model:
        return "runpod_vllm"
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith(("gpt-", "o1-", "o3-", "text-")):
        return "openai"
    return "other"


def _row(seq: int, component: str, model: Optional[str], **kw) -> Dict[str, Any]:
    return {
        "seq": seq,
        "component": component,
        "provider": provider_for(model),
        "model": model,
        "prompt_tokens": kw.get("prompt_tokens"),
        "completion_tokens": kw.get("completion_tokens"),
        "total_tokens": kw.get("total_tokens"),
        "n_calls": kw.get("n_calls", 1),
        "fallback": kw.get("fallback"),
        "status": kw.get("status", "ok"),
        "error_message": kw.get("error_message"),
    }


def build_a_llm_calls(
    final_state: Dict[str, Any],
    node_timings: Optional[Dict[str, Dict]] = None,
    models: Any = None,
) -> List[Dict[str, Any]]:
    """A: 실행된 LLM 호출 노드별 1행 (read-only). token은 미표면화 → NULL.

    - generation: generation_model_used(실제, rule_based/safe_fallback 가능).
    - supervisor/query_analysis: config 파생 model(설정상 호출 모델).
    """
    ran = set(node_timings or {})
    models = models or get_config().models
    # query_analysis 분류기 기본 모델(현재 IntentClassifier 기본).
    qa_model = "gpt-4o-mini"
    node_model = {
        "query_analysis": qa_model,
        "supervisor": getattr(models, "supervisor", "gpt-4o"),
        "generation": final_state.get("generation_model_used")
        or getattr(models, "draft_agent", "gpt-4o"),
    }
    events: List[Dict[str, Any]] = []
    seq = 0
    for node in _A_LLM_NODES:
        if node not in ran:
            continue
        model = node_model.get(node)
        fallback = (model in _RULE_LABELS) if model else None
        events.append(_row(seq, node, model, fallback=fallback))
        seq += 1
    return events


def build_b_llm_call(b_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """B: run_b의 llm_summary(react model + 합산 token + n_calls) → 1행."""
    s = b_result.get("llm_summary")
    if not s:
        return []
    return [
        _row(
            0,
            "react",
            s.get("model"),
            prompt_tokens=s.get("prompt_tokens"),
            completion_tokens=s.get("completion_tokens"),
            total_tokens=s.get("total_tokens"),
            n_calls=s.get("n_calls", 1),
            status=s.get("status", "ok"),
        )
    ]


class LLMCallDB:
    """llm_calls 테이블 접근 계층 (ConversationDB 패턴)."""

    def __init__(self, db_config: Optional[DatabaseConfig] = None):
        self.db_config = db_config or get_config().database

    def _get_connection(self):
        return psycopg2.connect(**self.db_config.get_connection_dict())

    def insert_calls(self, run_id: str, calls: List[Dict[str, Any]]) -> None:
        if not calls:
            return
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO llm_calls
                        (run_id, seq, component, provider, model, prompt_tokens,
                         completion_tokens, total_tokens, n_calls, fallback,
                         status, error_message)
                    VALUES %s
                    ON CONFLICT (run_id, seq) DO NOTHING
                    """,
                    [
                        (
                            run_id,
                            c["seq"],
                            c["component"],
                            c.get("provider"),
                            c.get("model"),
                            c.get("prompt_tokens"),
                            c.get("completion_tokens"),
                            c.get("total_tokens"),
                            c.get("n_calls", 1),
                            c.get("fallback"),
                            c.get("status", "ok"),
                            c.get("error_message"),
                        )
                        for c in calls
                    ],
                )
            conn.commit()
        finally:
            conn.close()


async def save_llm_calls(
    run_id: str,
    calls: List[Dict[str, Any]],
    db: Optional[LLMCallDB] = None,
) -> bool:
    """llm_calls에 행을 best-effort로 저장한다 (실패 시 예외 삼킴)."""
    if not calls:
        return False
    runner = db or LLMCallDB()
    try:
        await asyncio.to_thread(runner.insert_calls, run_id, calls)
        logger.info(f"[llm_calls] saved run={run_id[:8]} calls={len(calls)}")
        return True
    except Exception as e:
        logger.warning(
            f"[llm_calls] save failed (non-blocking) run={run_id[:8]}: {e}"
        )
        return False
