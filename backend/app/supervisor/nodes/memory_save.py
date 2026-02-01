"""
똑소리 프로젝트 - memory_save 노드

output_guardrail 이후 실행되어 NEED_RAG 대화 턴을 선별 저장합니다.
그래프 위치: output_guardrail → memory_save → END

NO_RETRIEVAL(인사, 시스템 질문) 턴은 저장하지 않습니다.

작성일: 2026-01-31
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def memory_save_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    NEED_RAG/FOLLOWUP_WITH_CONTEXT 대화 턴을 rag_conversation_memory에 저장하는 노드.

    동작:
    1. state['mode']가 'NEED_RAG'인지 확인
    2. NEED_RAG면: user_query + final_answer(200자 요약) 저장
    3. 윈도우 크기(기본 5) 초과 시 가장 오래된 턴 제거
    4. Phase D: NEED_RAG/FOLLOWUP_WITH_CONTEXT 모드에서는 last_turn_context 저장
       - followup_questions, available_details, retrieval 보존
    5. 다른 모드면 빈 dict 반환 (메모리 저장 스킵)

    Args:
        state: ChatState (LangGraph 상태)

    Returns:
        Dict with 'rag_conversation_memory' and/or '_last_turn_context' keys (변경 시)
        또는 빈 Dict (스킵 시)
    """
    mode = state.get('mode', '')
    updates = {}

    # Save RAG conversation memory (NEED_RAG only)
    if mode == 'NEED_RAG':
        user_query = state.get('user_query', '')
        final_answer = state.get('final_answer', '')

        if user_query and final_answer:
            # 기존 메모리 복원
            from app.supervisor.state.memory import RAGConversationMemory

            existing = state.get('rag_conversation_memory', [])
            memory = RAGConversationMemory.from_state(existing)

            # 턴 추가
            saved = memory.add_turn(
                mode=mode,
                query=user_query,
                answer_summary=final_answer
            )

            if saved:
                logger.info(f"[memory_save] 저장 완료: 총 {len(memory)}턴 (query={user_query[:30]}...)")

            updates['rag_conversation_memory'] = memory.to_state()

    # Phase D: Save last turn context for FOLLOWUP_WITH_CONTEXT
    # Save for NEED_RAG and FOLLOWUP_WITH_CONTEXT modes (both have useful context)
    if mode in ('NEED_RAG', 'FOLLOWUP_WITH_CONTEXT'):
        followup_questions = state.get('followup_questions', [])
        available_details = state.get('available_details')
        retrieval = state.get('retrieval')

        if followup_questions or available_details or retrieval:
            last_turn_context = {
                'followup_questions': followup_questions,
                'available_details': available_details,
                'retrieval': retrieval,
            }
            updates['_last_turn_context'] = last_turn_context
            logger.info(f"[memory_save] Phase D context saved: followups={len(followup_questions)}, details={'yes' if available_details else 'no'}, retrieval={'yes' if retrieval else 'no'}")

            # Phase 3-C: Also save to L4 RetrievalResultCache for cross-turn persistence
            session_id = state.get('session_id')
            if session_id and retrieval:
                try:
                    from app.supervisor.cache import RetrievalResultCache
                    RetrievalResultCache.set_by_session(session_id, retrieval)
                    logger.info(f"[memory_save] L4 RetrievalResultCache saved for session={session_id[:8]}")
                except Exception as e:
                    logger.warning(f"[memory_save] L4 cache save failed: {e}")

    if not updates:
        logger.info(f"[memory_save] 스킵: mode={mode}")

    return updates


__all__ = ['memory_save_node']
