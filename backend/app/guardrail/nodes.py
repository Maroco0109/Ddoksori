"""
Guardrail LangGraph Nodes
"""

import logging
from typing import Any, Dict

from .moderation import MODERATION_ENABLED, check_input, check_output

logger = logging.getLogger(__name__)


def input_guardrail_node(state: Dict[str, Any]) -> Dict[str, Any]:
    if not MODERATION_ENABLED:
        return {}

    user_query = state.get("user_query", "")
    if not user_query:
        messages = state.get("messages", [])
        if messages:
            last_msg = messages[-1]
            if hasattr(last_msg, "content"):
                user_query = last_msg.content
            elif isinstance(last_msg, dict):
                user_query = last_msg.get("content", "")

    if not user_query:
        return {}

    result = check_input(user_query)

    if result["blocked"]:
        logger.warning(f"[InputGuardrail] Blocked input: {user_query[:50]}...")
        return {
            "guardrail_blocked": True,
            "guardrail_type": "input",
            "final_answer": result["fallback_message"],
            "user_query": user_query,  # 추출한 user_query를 state에 저장
        }

    return {
        "guardrail_blocked": False,
        "user_query": user_query,  # 추출한 user_query를 state에 저장
    }


def output_guardrail_node(state: Dict[str, Any]) -> Dict[str, Any]:
    # === PR-6: draft_answer를 final_answer로 복사 ===
    draft_answer = state.get("draft_answer") or ""
    final_answer = state.get("final_answer") or ""

    # DEBUG: 입력 값 확인
    logger.info(
        f"[OutputGuardrail] draft_answer length: {len(draft_answer) if draft_answer else 'None'}"
    )
    logger.info(
        f"[OutputGuardrail] final_answer length: {len(final_answer) if final_answer else 'None'}"
    )
    if "[출처]" in draft_answer:
        source_start = draft_answer.find("[출처]")
        logger.info(
            f"[OutputGuardrail] Source in draft: {draft_answer[source_start : source_start + 100]}..."
        )
    if "[출처]" in final_answer:
        source_start = final_answer.find("[출처]")
        logger.info(
            f"[OutputGuardrail] Source in final: {final_answer[source_start : source_start + 100]}..."
        )

    # 우선순위: final_answer > draft_answer
    if not final_answer:
        final_answer = draft_answer
        logger.info("[OutputGuardrail] Using draft_answer as final_answer")

    # 안전 체크: 둘 다 비어있으면 에러 로그 + fallback 메시지
    if not final_answer:
        logger.error(
            "[OutputGuardrail] CRITICAL BUG: Both draft_answer and final_answer are empty! "
            f"State keys: {list(state.keys())}"
        )
        # Fallback 메시지로 사용자 경험 개선
        final_answer = "죄송합니다. 일시적인 오류로 답변을 생성하지 못했습니다. 잠시 후 다시 시도해주세요."

    # ALWAYS set final_answer (빈 문자열이어도 설정)
    updates = {"final_answer": final_answer}
    # === PR-6 끝 ===

    if not MODERATION_ENABLED:
        # === PR-6: L1 캐시 저장 (moderation 비활성화 시에도) ===
        _save_to_l1_cache({**state, **updates})
        # === PR-6 끝 ===
        return updates

    # Moderation 체크 (final_answer가 fallback 메시지라도 체크)
    result = check_output(final_answer)

    if result["blocked"]:
        logger.warning("[OutputGuardrail] Blocked output")
        return {
            **updates,
            "guardrail_blocked": True,
            "guardrail_type": "output",
            "final_answer": result["fallback_message"],
        }

    # === PR-6: L1 캐시 저장 ===
    _save_to_l1_cache({**state, **updates})
    # === PR-6 끝 ===

    # DEBUG: 최종 반환 값 확인
    returned_answer = updates.get("final_answer", "")
    logger.info(
        f"[OutputGuardrail] Returning final_answer length: {len(returned_answer)}"
    )
    if "[출처]" in returned_answer:
        source_start = returned_answer.find("[출처]")
        logger.info(
            f"[OutputGuardrail] Final source section: {returned_answer[source_start : source_start + 100]}..."
        )

    return {**updates, "guardrail_blocked": False}


def _save_to_l1_cache(state: Dict[str, Any]) -> None:
    """
    PR-6: L1 Supervisor 응답 캐시 저장

    조건:
    - _cache_hit가 True면 저장 안 함 (이미 캐시에서 온 응답)
    - guardrail_blocked가 True면 저장 안 함
    - final_answer가 없으면 저장 안 함
    """
    # 캐시에서 온 응답이면 저장하지 않음
    if state.get("_cache_hit"):
        return

    # Guardrail에서 차단된 응답은 저장하지 않음
    if state.get("guardrail_blocked"):
        return

    final_answer = state.get("final_answer")
    if not final_answer:
        return

    # 메시지에서 user_query 추출
    messages = state.get("messages", [])
    if not messages:
        return

    last_msg = messages[-1]
    if hasattr(last_msg, "content"):
        user_query = last_msg.content
    elif isinstance(last_msg, dict):
        user_query = last_msg.get("content", "")
    else:
        user_query = str(last_msg)

    if not user_query:
        return

    session_id = state.get("session_id")

    # 캐시 데이터 준비
    from ..supervisor.cache import SupervisorResponseCache

    cache_data = {
        "final_answer": final_answer,
        "mode": state.get("mode"),
        "query_analysis": state.get("query_analysis", {}),
        "citations": state.get("citations", []),
    }

    SupervisorResponseCache.set(user_query, cache_data, session_id)
    logger.debug(f"[L1 Cache] Saved response for: {user_query[:30]}...")
