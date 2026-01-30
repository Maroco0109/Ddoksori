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
from typing import Dict, Any, cast, Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse

from app.common.logger import get_rag_logger
from app.common.config import get_config
from app.supervisor import get_graph_for_chat_type, create_initial_state
from app.supervisor.memory import ConversationMemory, should_use_memory
from app.auth.dependencies import get_current_user_optional
from app.auth.models import User

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
async def chat(
    request: ChatRequest,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    LangGraph 기반 멀티턴 챗봇 응답 생성

    워크플로우: query_analysis → retrieval → generation → review → END

    Args:
        request: 채팅 요청 (message, session_id, chat_type 등)
        current_user: 현재 인증된 사용자 (선택, JWT 토큰에서 추출)

    Returns:
        ChatResponse: 생성된 답변과 관련 정보

    Note:
        session_id가 없으면 새 세션 생성, 있으면 기존 세션 이어서 대화
        로그인 사용자의 경우 user_id를 DB에 저장하여 대화 이력 관리
    """
    start_time = time.time()
    log_entry = rag_logger.create_entry(query=request.message)

    # Get user_id from JWT token
    user_id = current_user.user_id if current_user else None

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

        # Create memory with DB persistence
        config = get_config()
        use_db = config.memory.backend == 'db'

        session_memory = None
        memory_context = {}
        if should_use_memory(request.chat_type):
            session_memory = ConversationMemory(
                chat_type=request.chat_type,
                session_id=session_id,
                user_id=user_id,
                use_db=use_db
            )

            # 사용자 메시지를 메모리에 추가 (DB에 저장됨)
            await session_memory.add_turn(role='user', content=request.message)

            # 메모리 컨텍스트 가져오기
            memory_context = session_memory.get_context_for_llm()

        # 통합 상태 초기화
        initial_state = create_initial_state(
            user_query=request.message,
            chat_type=request.chat_type,
            onboarding=cast(Any, request.onboarding),
        )

        # 메모리 컨텍스트를 초기 상태에 병합
        if memory_context and session_memory:
            initial_state['conversation_history'] = memory_context.get('conversation_history', [])
            initial_state['compact_summary'] = memory_context.get('compact_summary')
            initial_state['total_turn_count'] = session_memory.get_total_turn_count()

        # 세션 ID를 state에 포함 (L4 캐시 키로 사용)
        initial_state['session_id'] = session_id

        # Progressive Disclosure: 이전 턴의 conversation_phase/dispute_slots 복원
        from app.common.cache import get_redis_client
        _redis = get_redis_client()
        if _redis and request.session_id:
            import json as _json
            _phase_key = f"session_phase:{session_id}"
            _saved = _redis.get(_phase_key)
            if _saved:
                try:
                    _phase_data = _json.loads(_saved)
                    initial_state['conversation_phase'] = _phase_data.get('conversation_phase', 'initial')
                    if _phase_data.get('dispute_slots'):
                        initial_state['dispute_slots'] = _phase_data['dispute_slots']
                    if _phase_data.get('dispute_slot_status'):
                        initial_state['dispute_slot_status'] = _phase_data['dispute_slot_status']
                    logger.info(f"[chat] Restored phase={initial_state['conversation_phase']} for session={session_id[:8]}...")
                except Exception as e:
                    logger.warning(f"[chat] Failed to restore phase: {e}")

        config = cast(Any, {
            "configurable": {"thread_id": session_id},
            "recursion_limit": GRAPH_RECURSION_LIMIT
        })

        # === PR-6: L1 Supervisor Response Cache Check ===
        from app.supervisor.cache import SupervisorResponseCache
        cached_response = SupervisorResponseCache.get(request.message, session_id)
        if cached_response:
            logger.info(f"[L1 Cache HIT] Returning cached response for: {request.message[:30]}...")
            # 캐시에서 복원한 응답을 사용
            final_state = {
                'final_answer': cached_response.get('final_answer', ''),
                'mode': cached_response.get('mode'),
                'query_analysis': cached_response.get('query_analysis', {}),
                'citations': cached_response.get('citations', []),
                'sources': [],
                'retrieval': {},
                '_cache_hit': True,
            }
        else:
            # === PR-6 끝 ===
            # MAS graph includes async nodes; prefer the async API when available.
            GRAPH_TIMEOUT_SECONDS = getattr(get_config(), 'graph_timeout_seconds', 120)
            logger.info(f"[chat] Starting graph execution for session={session_id[:8]}...")
            try:
                if hasattr(graph, 'ainvoke'):
                    final_state = await asyncio.wait_for(
                        graph.ainvoke(initial_state, config),
                        timeout=GRAPH_TIMEOUT_SECONDS
                    )
                else:
                    final_state = await asyncio.wait_for(
                        asyncio.to_thread(graph.invoke, initial_state, config),
                        timeout=GRAPH_TIMEOUT_SECONDS
                    )
            except asyncio.TimeoutError:
                logger.error(f"[chat] Graph execution timed out after {GRAPH_TIMEOUT_SECONDS}s for session={session_id[:8]}")
                raise HTTPException(status_code=504, detail="요청 처리 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.")
            logger.info(f"[chat] Graph execution completed for session={session_id[:8]}")

            # === PR-6: L1 Cache Save ===
            if final_state.get('final_answer') and not final_state.get('guardrail_blocked'):
                SupervisorResponseCache.set(request.message, {
                    'final_answer': final_state.get('final_answer'),
                    'mode': final_state.get('mode'),
                    'query_analysis': final_state.get('query_analysis', {}),
                    'citations': final_state.get('citations', []),
                }, session_id)
                logger.debug(f"[L1 Cache SAVE] Cached response for: {request.message[:30]}...")
            # === PR-6 끝 ===

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

        answer = final_state.get('final_answer') or ''
        sources = final_state.get('sources', [])
        has_evidence = final_state.get('has_sufficient_evidence', True)

        # Progressive Disclosure: conversation_phase 저장
        if _redis:
            import json as _json
            _phase_key = f"session_phase:{session_id}"
            _phase_data = {
                'conversation_phase': final_state.get('conversation_phase', 'initial'),
                'dispute_slots': final_state.get('dispute_slots', {}),
                'dispute_slot_status': final_state.get('dispute_slot_status', {}),
            }
            try:
                _redis.setex(_phase_key, 3600, _json.dumps(_phase_data, default=str))
            except Exception as e:
                logger.warning(f"[chat] Failed to save phase: {e}")
        questions = final_state.get('clarifying_questions', [])
        followup_questions = final_state.get('followup_questions', [])

        # Progressive Disclosure: 후속 질문 옵션 생성
        _conv_phase = final_state.get('conversation_phase', 'initial')
        if _conv_phase == 'providing_case_summary' and not followup_questions:
            followup_questions = ["네, 법령/기준도 알려주세요", "아니요, 괜찮습니다"]
        elif _conv_phase == 'providing_law_detail' and not followup_questions:
            followup_questions = ["네, 절차도 안내해주세요", "아니요, 충분합니다"]

        # 어시스턴트 응답을 메모리에 추가
        if session_memory:
            await session_memory.add_turn(role='assistant', content=answer)

        node_timings = final_state.get('_node_timings', {})
        if node_timings:
            rag_logger.log_node_timings(log_entry, node_timings)

        # 에이전트 트레이스 로깅
        trace_entries = final_state.get('_agent_trace_entries', [])
        if trace_entries:
            from app.supervisor.graph import build_pipeline_summary
            pipeline_summary = build_pipeline_summary(
                trace_entries,
                total_duration_ms=log_entry.total_time_ms or 0,
            )
            rag_logger.log_pipeline_trace(log_entry, pipeline_summary)

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
            followup_questions=followup_questions,
            domain=domain_response,
            similar_cases=similar_cases_response,
            related_laws=laws_response,
            related_criteria=criteria_response,
            node_timings=timing_response if request.debug else None,
            request_id=log_entry.request_id if request.debug else None,
            total_time_ms=log_entry.total_time_ms if request.debug else None
        )

    except Exception as e:
        logger.exception("[chat] Unhandled error")
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
async def chat_stream_sse(
    request: ChatRequest,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
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

        session_id = request.session_id or str(uuid.uuid4())
        final_state = None

        # 즉시 연결 확인 이벤트 전송 (클라이언트에 연결 성공 알림)
        yield f"data: {json.dumps({'type': 'status', 'data': {'node': 'init', 'status': '연결됨', 'progress': 0}}, ensure_ascii=False)}\n\n"

        # Get user_id from JWT token
        user_id = current_user.user_id if current_user else None

        try:
            graph = get_graph_for_chat_type(request.chat_type)
            GRAPH_RECURSION_LIMIT = 50

            # Create memory with DB persistence
            config = get_config()
            use_db = config.memory.backend == 'db'

            session_memory = None
            memory_context = {}
            if should_use_memory(request.chat_type):
                session_memory = ConversationMemory(
                    chat_type=request.chat_type,
                    session_id=session_id,
                    user_id=user_id,
                    use_db=use_db
                )
                await session_memory.add_turn(role='user', content=request.message)
                memory_context = session_memory.get_context_for_llm()

            # 초기 상태 생성
            initial_state = create_initial_state(
                user_query=request.message,
                chat_type=request.chat_type,
                onboarding=cast(Any, request.onboarding),
            )

            # 메모리 컨텍스트 병합
            if memory_context and session_memory:
                initial_state['conversation_history'] = memory_context.get('conversation_history', [])
                initial_state['compact_summary'] = memory_context.get('compact_summary')
                initial_state['total_turn_count'] = session_memory.get_total_turn_count()

            # 세션 ID를 state에 포함 (L4 캐시 키로 사용)
            initial_state['session_id'] = session_id

            # Progressive Disclosure: 이전 턴의 conversation_phase 복원
            _redis_stream = None
            try:
                from app.common.cache import get_redis_client
                _redis_stream = get_redis_client()
                if _redis_stream and request.session_id:
                    import json as _json_s
                    _phase_key_s = f"session_phase:{session_id}"
                    _saved_s = _redis_stream.get(_phase_key_s)
                    if _saved_s:
                        try:
                            _phase_data_s = _json_s.loads(_saved_s)
                            initial_state['conversation_phase'] = _phase_data_s.get('conversation_phase', 'initial')
                            if _phase_data_s.get('dispute_slots'):
                                initial_state['dispute_slots'] = _phase_data_s['dispute_slots']
                            if _phase_data_s.get('dispute_slot_status'):
                                initial_state['dispute_slot_status'] = _phase_data_s['dispute_slot_status']
                        except Exception as e:
                            logger.warning(f"[chat_stream] Failed to restore phase: {e}")
            except Exception as e:
                logger.warning(f"[chat_stream] Redis unavailable, skipping phase restore: {e}")

            runnable_config = cast(Any, {
                "configurable": {"thread_id": session_id},
                "recursion_limit": GRAPH_RECURSION_LIMIT
            })

            logger.info(f"[chat_stream] Starting graph streaming for session={session_id[:8]}...")

            # LangGraph astream_events로 실시간 토큰 스트리밍 + 노드 진행 상황
            # on_custom_event: 토큰, fallback 이벤트 (generation_node가 발생)
            # on_chain_start/end: 노드 시작/종료
            full_answer = ""
            final_state = {}
            SSE_HEARTBEAT_INTERVAL = 15  # 초
            last_heartbeat = time.monotonic()

            async for event in graph.astream_events(initial_state, runnable_config, version="v2"):
                event_type = event.get("event")

                # 1. Custom Events (token, fallback, error)
                if event_type == "on_custom_event":
                    custom_event_name = event.get("name")
                    custom_data = event.get("data", {})

                    if custom_event_name == "generation_token":
                        # Token from LLM streaming
                        full_answer += custom_data.get('content', '')
                        sse_event = {
                            'type': 'token',
                            'data': {
                                'content': custom_data.get('content'),
                                'model': custom_data.get('model', 'unknown')
                            }
                        }
                        yield f"data: {json.dumps(sse_event, ensure_ascii=False)}\n\n"

                    elif custom_event_name == "generation_fallback":
                        # Fallback model switch
                        fallback_event = {
                            'type': 'fallback',
                            'data': {
                                'model': custom_data.get('model', 'unknown'),
                                'message': custom_data.get('message', 'Fallback triggered')
                            }
                        }
                        yield f"data: {json.dumps(fallback_event, ensure_ascii=False)}\n\n"

                    elif custom_event_name == "generation_error":
                        # Error during generation
                        error_event = {
                            'type': 'error',
                            'data': {'message': custom_data.get('message', 'Unknown error')}
                        }
                        yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

                # 2. Node Start Events (status updates)
                elif event_type == "on_chain_start":
                    node_name = event.get("name", "")
                    if node_name in NODE_LABELS:
                        label, progress = NODE_LABELS[node_name]
                        status_event = {
                            'type': 'status',
                            'data': {
                                'node': node_name,
                                'status': label,
                                'progress': progress
                            }
                        }
                        yield f"data: {json.dumps(status_event, ensure_ascii=False)}\n\n"

                # 3. Node End Events (capture final state)
                elif event_type == "on_chain_end":
                    # Capture node outputs to build final_state
                    node_output = event.get("data", {}).get("output", {})
                    if isinstance(node_output, dict):
                        final_state.update(node_output)

                # 4. Heartbeat: 프록시/브라우저 idle timeout 방지
                now = time.monotonic()
                if now - last_heartbeat >= SSE_HEARTBEAT_INTERVAL:
                    yield ": heartbeat\n\n"
                    last_heartbeat = now

            # 최종 결과 전송
            if final_state:
                answer = final_state.get('final_answer', '')
                retrieval = final_state.get('retrieval') or {}

                # retrieval 정보 추출 (기존 /chat endpoint와 동일)
                agency_info = retrieval.get('agency', {})
                disputes = retrieval.get('disputes', [])
                counsels = retrieval.get('counsels', [])
                laws = retrieval.get('laws', [])
                criteria = retrieval.get('criteria', [])

                # 어시스턴트 응답을 메모리에 추가
                if session_memory:
                    await session_memory.add_turn(role='assistant', content=answer)

                # 소스 정보를 /chat endpoint와 동일하게 확장
                sources = []
                for dispute in disputes[:3]:
                    sources.append({
                        'type': 'dispute',
                        'title': dispute.get('doc_title', ''),
                        'source_org': dispute.get('source_org', ''),
                        'similarity': dispute.get('similarity', 0),
                        'content': dispute.get('content', ''),
                        'case_uid': dispute.get('case_uid'),
                        'product_name': dispute.get('product_name'),
                    })
                for counsel in counsels[:3]:
                    sources.append({
                        'type': 'counsel',
                        'title': counsel.get('doc_title', ''),
                        'source_org': counsel.get('source_org', ''),
                        'similarity': counsel.get('similarity', 0),
                        'content': counsel.get('content', ''),
                    })
                for law in laws[:3]:
                    sources.append({
                        'type': 'law',
                        'title': f"{law.get('law_name', '')} {law.get('full_path', '')}",
                        'similarity': law.get('similarity', 0),
                        'content': law.get('content', ''),
                        'law_name': law.get('law_name'),
                        'article': law.get('article'),
                    })
                for criterion in criteria[:3]:
                    sources.append({
                        'type': 'criteria',
                        'title': criterion.get('title', ''),
                        'similarity': criterion.get('similarity', 0),
                        'content': criterion.get('content', ''),
                    })

                # Progressive Disclosure: conversation_phase 저장
                if _redis_stream:
                    import json as _json_s2
                    _phase_key_s2 = f"session_phase:{session_id}"
                    _phase_data_s2 = {
                        'conversation_phase': final_state.get('conversation_phase', 'initial'),
                        'dispute_slots': final_state.get('dispute_slots', {}),
                        'dispute_slot_status': final_state.get('dispute_slot_status', {}),
                    }
                    try:
                        _redis_stream.setex(_phase_key_s2, 3600, _json_s2.dumps(_phase_data_s2, default=str))
                    except Exception:
                        pass

                # Progressive Disclosure: 후속 질문 옵션 생성
                _followup_qs = final_state.get('followup_questions', [])
                _conv_phase = final_state.get('conversation_phase', 'initial')
                if _conv_phase == 'providing_case_summary' and not _followup_qs:
                    _followup_qs = ["네, 법령/기준도 알려주세요", "아니요, 괜찮습니다"]
                elif _conv_phase == 'providing_law_detail' and not _followup_qs:
                    _followup_qs = ["네, 절차도 안내해주세요", "아니요, 충분합니다"]

                complete_event = {
                    'type': 'complete',
                    'data': {
                        'session_id': session_id,
                        'answer': answer,
                        'sources': sources,
                        'awaiting_user_choice': final_state.get('awaiting_user_choice', False),
                        'clarifying_questions': final_state.get('clarifying_questions', []),
                        'followup_questions': _followup_qs,
                        'has_sufficient_evidence': final_state.get('has_sufficient_evidence', True),
                        'domain': agency_info if agency_info else None,
                        'similar_cases': {
                            'disputes': [{'doc_title': d.get('doc_title'), 'source_org': d.get('source_org'), 'similarity': d.get('similarity')} for d in disputes],
                            'counsels': [{'doc_title': c.get('doc_title'), 'source_org': c.get('source_org'), 'similarity': c.get('similarity')} for c in counsels],
                        } if (disputes or counsels) else None,
                        'related_laws': [{'law_name': l.get('law_name'), 'article': l.get('article'), 'similarity': l.get('similarity')} for l in laws] if laws else None,
                        'related_criteria': [{'title': c.get('title'), 'similarity': c.get('similarity')} for c in criteria] if criteria else None,
                    }
                }
                yield f"data: {json.dumps(complete_event, ensure_ascii=False)}\n\n"

                # 에이전트 트레이스 로깅
                trace_entries = final_state.get('_agent_trace_entries', []) if final_state else []
                if trace_entries:
                    from app.supervisor.graph import build_pipeline_summary
                    pipeline_summary = build_pipeline_summary(
                        trace_entries,
                        total_duration_ms=(time.time() - start_time) * 1000,
                    )
                    rag_logger.log_pipeline_trace(log_entry, pipeline_summary)

                # RAG 로깅 - /chat 엔드포인트와 동일
                rag_logger.log_structured_retrieval(
                    entry=log_entry,
                    agency_info=agency_info,
                    disputes=disputes,
                    counsels=counsels,
                    laws=laws,
                    criteria=criteria
                )
                rag_logger.log_response(
                    entry=log_entry,
                    answer=answer,
                    chunks_used=len(sources),
                    sources_count=len(sources),
                    status="success"
                )
                rag_logger.finalize(log_entry, start_time)
                rag_logger.save(log_entry)

        except asyncio.CancelledError:
            logger.info(f"[chat_stream] Client disconnected during streaming, session={session_id[:8]}")
            rag_logger.log_response(
                entry=log_entry,
                answer="",
                chunks_used=0,
                sources_count=0,
                status="cancelled",
                error_message="Client disconnected"
            )
            rag_logger.finalize(log_entry, start_time)
            rag_logger.save(log_entry)
            return
        except Exception as e:
            logger.error(f"[chat_stream_sse] Error: {e}", exc_info=True)
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
