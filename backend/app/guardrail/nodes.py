"""
Guardrail LangGraph Nodes - 역할 분리 버전
"""

import logging
from typing import Any, Dict

from langchain_core.messages import HumanMessage

from .moderation import MODERATION_ENABLED, check_input, check_output

logger = logging.getLogger(__name__)

# [시스템 가이드 문구] 루프 차단이나 심각한 오류 시에만 가드레일이 직접 출력합니다.
SYSTEM_GUIDE_MESSAGE = (
    "안녕하세요! 똑똑한 소비자지킴이 '똑소리'입니다. 저는 소비자 분쟁 해결을 위해 "
    "법령, 분쟁해결기준, 유사 사례 정보를 전문적으로 제공하고 있습니다.\n\n"
    "환불 거부, 위약금 분쟁, 제품 하자 등 겪고 계신 문제를 구체적으로 말씀해 주시면 "
    "정확한 해결 방안을 안내해 드리겠습니다."
)


def input_guardrail_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    [역할 1] 보안 및 오류 방지
    - 유해성 검사 및 무한 루프 방지만 수행합니다.
    - 안전한 문장은 무조건 '질의 분석 에이전트'로 전달합니다.
    """
    if not MODERATION_ENABLED:
        return {}

    user_query = state.get("user_query") or ""
    user_query = user_query.strip()

    # 1. Extract user message (fallback only when user_query is empty)
    if not user_query:
        messages = state.get("messages", [])
        last_user_msg = None
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                last_user_msg = msg
                break
            elif isinstance(msg, dict) and (
                msg.get("role") == "user" or msg.get("type") == "human"
            ):
                last_user_msg = msg
                break

        # No user message found
        if not last_user_msg:
            logger.warning(
                "[InputGuardrail] No HumanMessage found. Blocking for safety."
            )
            return {
                "guardrail_blocked": True,
                "guardrail_type": "loop_prevention",
                "final_answer": SYSTEM_GUIDE_MESSAGE,
                "user_query": "",
            }

        # Extract user content
        if hasattr(last_user_msg, "content"):
            user_query = last_user_msg.content.strip()
        elif isinstance(last_user_msg, dict):
            user_query = last_user_msg.get("content", "").strip()

    # 2. 루프 감지 (자기 답변에 자기가 답하는 현상 방지)
    BOT_INDICATORS = [
        "소비자 분쟁 상담",
        "똑소리입니다",
        "안내해 드립니다",
        "소비자지킴이",
    ]
    if any(indicator in user_query for indicator in BOT_INDICATORS):
        logger.warning("[InputGuardrail] Self-response loop detected. Blocking.")
        return {
            "guardrail_blocked": True,
            "guardrail_type": "input_loop",
            "final_answer": SYSTEM_GUIDE_MESSAGE,
            "user_query": "",
        }

    # 3. 유해성 검사 (Moderation)
    result = check_input(user_query)
    if result["blocked"]:
        logger.warning("[InputGuardrail] Blocked by moderation.")
        return {
            "guardrail_blocked": True,
            "guardrail_type": "input",
            "final_answer": result["fallback_message"],
            "user_query": user_query,
        }

    # 4. [중요] 모든 보안 검사 통과 시
    # 에이전트가 일을 할 수 있도록 guardrail_blocked를 False로 반환합니다.
    logger.info("[InputGuardrail] Safety check passed. Handing over to Query Analyst.")
    return {
        "guardrail_blocked": False,  # 에이전트를 깨우는 신호
        "user_query": user_query,
    }


def output_guardrail_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    [역할 2] 출력물 최종 검수
    """
    draft_answer = state.get("draft_answer", "")
    final_answer = state.get("final_answer", "")

    if not final_answer:
        final_answer = draft_answer

    if not final_answer:
        logger.error("[OutputGuardrail] Final answer is empty!")
        final_answer = "죄송합니다. 오류가 발생했습니다. 다시 질문해 주세요."

    updates = {"final_answer": final_answer}

    if not MODERATION_ENABLED:
        _save_to_l1_cache({**state, **updates})
        return updates

    result = check_output(final_answer)
    if result["blocked"]:
        return {
            **updates,
            "guardrail_blocked": True,
            "guardrail_type": "output",
            "final_answer": result["fallback_message"],
        }

    _save_to_l1_cache({**state, **updates})
    return {**updates, "guardrail_blocked": False}


def _save_to_l1_cache(state: Dict[str, Any]) -> None:
    # (기존 캐시 저장 로직 동일)
    pass
