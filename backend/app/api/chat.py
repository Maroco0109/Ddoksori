"""
똑소리 프로젝트 - 채팅 라우터

LangGraph 기반 멀티턴 챗봇 응답 생성 엔드포인트입니다.
SSE 스트리밍과 일반 응답 모두 지원합니다.
"""

import time
import asyncio
import uuid
import json
import logging
from typing import Dict, Any, cast

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.common.logger import get_rag_logger
from app.orchestrator import get_graph_for_chat_type, create_initial_state
from app.orchestrator.memory import ConversationMemory, should_use_memory

from .models import (
    ChatRequest,
    ChatResponse,
    AgencyRecommendation,
    CaseReference,
    LawReference,
    CriteriaReference,
    SimilarCases,
    NodeTiming,
)


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Chat"])

# RAG 로거 인스턴스
rag_logger = get_rag_logger()

# 세션별 대화 메모리 저장소 (in-memory)
# 프로덕션에서는 Redis 등 사용 권장
_session_memories: Dict[str, ConversationMemory] = {}

# SSE 실시간 상태 표시용 노드 라벨 및 진행률
NODE_LABELS: Dict[str, tuple[str, int]] = {
    'input_guardrail': ('입력 검증중...', 5),
    'query_analysis': ('질의 분석중...', 15),
    'ask_clarification': ('추가 정보 요청중...', 20),
    'react_think': ('추론중...', 25),
    'react_act': ('정보 검색중...', 50),
    'generation': ('답변 생성중...', 80),
    'review': ('검토중...', 95),
    'output_guardrail': ('완료', 100),
}


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    LangGraph 기반 멀티턴 챗봇 응답 생성

    워크플로우: query_analysis → retrieval → generation → review → END

    Args:
        request: 채팅 요청 (message, session_id, chat_type 등)

    Returns:
        ChatResponse: 생성된 답변과 관련 정보

    Note:
        session_id가 없으면 새 세션 생성, 있으면 기존 세션 이어서 대화
    """
    start_time = time.time()
    log_entry = rag_logger.create_entry(query=request.message)

    rag_logger.log_input(
        entry=log_entry,
        message=request.message,
        session_id=request.session_id,
        chat_type=request.chat_type,
        onboarding=request.onboarding,
        top_k=request.top_k or 5,
        chunk_types=request.chunk_types,
        agencies=request.agencies
    )

    try:
        session_id = request.session_id or str(uuid.uuid4())

        graph = get_graph_for_chat_type(request.chat_type)

        # Recursion limit 증가 (기본 25 → 50)
        GRAPH_RECURSION_LIMIT = 50

        # 세션 메모리 가져오기/생성
        memory_context = {}
        if should_use_memory(request.chat_type):
            if session_id not in _session_memories:
                _session_memories[session_id] = ConversationMemory(chat_type=request.chat_type)
            session_memory = _session_memories[session_id]

            # 사용자 메시지를 메모리에 추가
            session_memory.add_turn(role='user', content=request.message)

            # 메모리 컨텍스트 가져오기
            memory_context = session_memory.get_context_for_llm()

        # 통합 상태 초기화
        initial_state = create_initial_state(
            user_query=request.message,
            chat_type=request.chat_type,
            onboarding=cast(Any, request.onboarding),
        )

        # 메모리 컨텍스트를 초기 상태에 병합
        if memory_context:
            initial_state['conversation_history'] = memory_context.get('conversation_history', [])
            initial_state['compact_summary'] = memory_context.get('compact_summary')
            initial_state['total_turn_count'] = _session_memories[session_id].get_total_turn_count()

        config = cast(Any, {
            "configurable": {"thread_id": session_id},
            "recursion_limit": GRAPH_RECURSION_LIMIT
        })
        final_state = await asyncio.to_thread(graph.invoke, initial_state, config)

        retrieval = final_state.get('retrieval') or {}
        agency_info = retrieval.get('agency', {})
        disputes = retrieval.get('disputes', [])
        counsels = retrieval.get('counsels', [])
        laws = retrieval.get('laws', [])
        criteria = retrieval.get('criteria', [])

        rag_logger.log_structured_retrieval(
            entry=log_entry,
            agency_info=agency_info,
            disputes=disputes,
            counsels=counsels,
            laws=laws,
            criteria=criteria
        )

        answer = final_state.get('final_answer', '')
        sources = final_state.get('sources', [])
        has_evidence = final_state.get('has_sufficient_evidence', True)
        questions = final_state.get('clarifying_questions', [])

        # 어시스턴트 응답을 메모리에 추가
        if should_use_memory(request.chat_type) and session_id in _session_memories:
            _session_memories[session_id].add_turn(role='assistant', content=answer)

        node_timings = final_state.get('_node_timings', {})
        if node_timings:
            rag_logger.log_node_timings(log_entry, node_timings)

        rag_logger.log_response(
            entry=log_entry,
            answer=answer,
            chunks_used=len(sources),
            sources_count=len(sources),
            status="success"
        )
        rag_logger.finalize(log_entry, start_time)
        rag_logger.save(log_entry)

        # 응답 구성
        domain_response = None
        if agency_info:
            try:
                domain_response = AgencyRecommendation(**agency_info)
            except Exception:
                pass

        similar_cases_response = None
        if disputes or counsels:
            similar_cases_response = SimilarCases(
                disputes=[CaseReference(**d) for d in disputes],
                counsels=[CaseReference(**c) for c in counsels]
            )

        laws_response = [LawReference(**law) for law in laws] if laws else None
        criteria_response = [CriteriaReference(**c) for c in criteria] if criteria else None

        # debug 모드일 때 타이밍 정보 변환
        timing_response = None
        if request.debug and node_timings:
            timing_response = [
                NodeTiming(
                    node_name=name,
                    duration_ms=info.get('duration_ms', 0),
                    start_time=info.get('start_time', ''),
                    end_time=info.get('end_time', '')
                )
                for name, info in node_timings.items()
            ]

        return ChatResponse(
            session_id=session_id,
            answer=answer,
            chunks_used=len(sources),
            model='gpt-4o-mini',
            sources=sources,
            has_sufficient_evidence=has_evidence,
            clarifying_questions=questions,
            domain=domain_response,
            similar_cases=similar_cases_response,
            related_laws=laws_response,
            related_criteria=criteria_response,
            node_timings=timing_response if request.debug else None,
            request_id=log_entry.request_id if request.debug else None,
            total_time_ms=log_entry.total_time_ms if request.debug else None
        )

    except Exception as e:
        rag_logger.log_response(
            entry=log_entry,
            answer="",
            chunks_used=0,
            sources_count=0,
            status="error",
            error_message=str(e)
        )
        rag_logger.finalize(log_entry, start_time)
        rag_logger.save(log_entry)

        raise HTTPException(status_code=500, detail=f"답변 생성 중 오류 발생: {str(e)}")


@router.post("/chat/stream")
async def chat_stream_sse(request: ChatRequest):
    """
    LangGraph astream 기반 SSE 스트리밍 챗봇 응답 생성

    SSE 이벤트 타입:
        - status: 노드별 진행 상태 (node, status, progress)
        - complete: 최종 결과 (session_id, answer, sources)
        - error: 오류 발생 시

    Example SSE events:
        data: {"type": "status", "data": {"node": "query_analysis", "status": "질의 분석중...", "progress": 15}}
        data: {"type": "complete", "data": {"session_id": "...", "answer": "...", "sources": [...]}}
    """
    async def event_generator():
        session_id = request.session_id or str(uuid.uuid4())
        final_state = None

        try:
            graph = get_graph_for_chat_type(request.chat_type)
            GRAPH_RECURSION_LIMIT = 50

            # 세션 메모리 가져오기/생성
            memory_context = {}
            if should_use_memory(request.chat_type):
                if session_id not in _session_memories:
                    _session_memories[session_id] = ConversationMemory(chat_type=request.chat_type)
                session_memory = _session_memories[session_id]
                session_memory.add_turn(role='user', content=request.message)
                memory_context = session_memory.get_context_for_llm()

            # 초기 상태 생성
            initial_state = create_initial_state(
                user_query=request.message,
                chat_type=request.chat_type,
                onboarding=cast(Any, request.onboarding),
            )

            # 메모리 컨텍스트 병합
            if memory_context:
                initial_state['conversation_history'] = memory_context.get('conversation_history', [])
                initial_state['compact_summary'] = memory_context.get('compact_summary')
                initial_state['total_turn_count'] = _session_memories[session_id].get_total_turn_count()

            config = cast(Any, {
                "configurable": {"thread_id": session_id},
                "recursion_limit": GRAPH_RECURSION_LIMIT
            })

            # LangGraph astream으로 노드별 진행 상황 스트리밍
            async for event in graph.astream(initial_state, config):
                if event:
                    node_name = list(event.keys())[0]
                    final_state = event[node_name]

                    label, progress = NODE_LABELS.get(node_name, ('처리중...', 0))

                    status_event = {
                        'type': 'status',
                        'data': {
                            'node': node_name,
                            'status': label,
                            'progress': progress
                        }
                    }
                    yield f"data: {json.dumps(status_event, ensure_ascii=False)}\n\n"

            # 최종 결과 전송
            if final_state:
                answer = final_state.get('final_answer', '')
                retrieval = final_state.get('retrieval') or {}

                # 어시스턴트 응답을 메모리에 추가
                if should_use_memory(request.chat_type) and session_id in _session_memories:
                    _session_memories[session_id].add_turn(role='assistant', content=answer)

                # 소스 정보 수집
                sources = []
                for dispute in retrieval.get('disputes', [])[:3]:
                    sources.append({
                        'type': 'dispute',
                        'title': dispute.get('doc_title', ''),
                        'source_org': dispute.get('source_org', ''),
                        'similarity': dispute.get('similarity', 0)
                    })
                for law in retrieval.get('laws', [])[:3]:
                    sources.append({
                        'type': 'law',
                        'title': f"{law.get('law_name', '')} {law.get('full_path', '')}",
                        'similarity': law.get('similarity', 0)
                    })

                complete_event = {
                    'type': 'complete',
                    'data': {
                        'session_id': session_id,
                        'answer': answer,
                        'sources': sources,
                        'awaiting_user_choice': final_state.get('awaiting_user_choice', False),
                        'clarifying_questions': final_state.get('clarifying_questions', [])
                    }
                }
                yield f"data: {json.dumps(complete_event, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"[chat_stream_sse] Error: {e}")
            error_event = {
                'type': 'error',
                'data': {
                    'message': f"답변 생성 중 오류 발생: {str(e)}"
                }
            }
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Nginx buffering 비활성화
        }
    )


__all__ = ['router']
