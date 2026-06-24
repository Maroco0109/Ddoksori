"""
똑소리 프로젝트 - 채팅 라우터

LangGraph 기반 멀티턴 챗봇 응답 생성 엔드포인트입니다.
SSE 스트리밍과 일반 응답 모두 지원합니다.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Any, Dict, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.auth.dependencies import get_current_user, get_current_user_optional
from app.auth.models import User
from app.common.config import get_config
from app.common.logger import get_rag_logger
from app.middleware.rate_limiter import RateLimits, limiter
from app.supervisor import create_initial_state, get_graph_for_chat_type
from app.supervisor.memory import ConversationMemory, should_use_memory

from .models import (
    ChatRequest,
    ChatResponse,
    NodeTiming,
)
from .response_builder import build_chat_response_data

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Chat"])

# RAG 로거 인스턴스
rag_logger = get_rag_logger()

# SSE 실시간 상태 표시용 노드 라벨 및 진행률
NODE_LABELS: Dict[str, tuple[str, int]] = {
    "input_guardrail": ("입력 검증중...", 5),
    "query_analysis": ("질의 분석중...", 15),
    "react_think": ("추론중...", 25),
    "react_act": ("정보 검색중...", 50),
    "generation": ("답변 생성중...", 80),
    "review": ("검토중...", 95),
    "output_guardrail": ("완료", 100),
}

# on_chain_end 이벤트 필터링: 등록된 그래프 노드만 final_state에 반영
KNOWN_GRAPH_NODES = {
    "cache_check",
    "cache_response",
    "input_guardrail",
    "output_guardrail",
    "supervisor",
    "query_analysis",
    "generation",
    "review",
    "retrieval_law",
    "retrieval_criteria",
    "retrieval_case",
    "retrieval_merge",
}


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(RateLimits.CHAT_GUEST)
async def chat(
    request: Request,
    body: ChatRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
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
    log_entry = rag_logger.create_entry(query=body.message)

    # Get user_id from JWT token
    user_id = current_user.user_id if current_user else None

    rag_logger.log_input(
        entry=log_entry,
        message=body.message,
        session_id=body.session_id,
        chat_type=body.chat_type,
        onboarding=body.onboarding,
        top_k=body.top_k or 5,
        chunk_types=body.chunk_types,
        agencies=body.agencies,
    )

    try:
        session_id = body.session_id or str(uuid.uuid4())

        # Variant B (Agentic RAG) — isolated comparison path. A path below unchanged.
        if body.variant == "B":
            from app.observability import save_workflow_run
            from app.variant_b.agent import run_b

            b_run_id = str(uuid.uuid4())
            b_result = await asyncio.to_thread(
                run_b, body.message, top_k=body.top_k or 5
            )
            clarified = bool(b_result.get("clarified", False))
            b_blocked = bool(b_result.get("blocked", False))

            # M3-3: best-effort workflow run 저장. blocked/clarify는 정책상 정상
            # 완료이므로 status='success' + 별도 플래그로 기록 (예외만 'error').
            await save_workflow_run(
                run_id=b_run_id,
                variant="B",
                query=body.message,
                status="success",
                session_id=session_id,
                chat_type=body.chat_type,
                total_time_ms=(time.time() - start_time) * 1000.0,
                clarified=clarified,
                blocked=b_blocked,
            )

            # M3-4: best-effort workflow step 저장 (B trace + 단계 타이머).
            from app.observability.workflow_steps import (
                build_b_steps,
                save_workflow_steps,
            )

            await save_workflow_steps(
                b_run_id, build_b_steps(b_result.get("trace", []))
            )

            return ChatResponse(
                session_id=session_id,
                answer=b_result["answer"],
                chunks_used=0,
                model="variant-b",
                sources=[],
                has_sufficient_evidence=not clarified,
                clarifying_questions=[b_result["answer"]] if clarified else [],
            )

        graph = get_graph_for_chat_type(body.chat_type)

        # Recursion limit 증가 (기본 25 → 50)
        GRAPH_RECURSION_LIMIT = 50

        # Create memory with DB persistence
        config = get_config()
        use_db = config.memory.backend == "db"

        logger.info(
            f"[chat] Memory backend: {config.memory.backend}, use_db: {use_db}, user_id: {user_id}"
        )
        if not use_db:
            logger.warning(
                "[chat] DB persistence disabled (CONVERSATION_MEMORY_BACKEND != 'db'). "
                "Chat history will NOT be saved to PostgreSQL."
            )

        session_memory = None
        memory_context = {}
        if should_use_memory(body.chat_type):
            session_memory = ConversationMemory(
                chat_type=body.chat_type,
                session_id=session_id,
                user_id=user_id,
                use_db=use_db,
            )
            logger.info(
                f"[chat] ConversationMemory created: session={session_id[:8]}, use_db={use_db}"
            )

            # 사용자 메시지를 메모리에 추가 (DB에 저장됨)
            await session_memory.add_turn(role="user", content=body.message)

            # 메모리 컨텍스트 가져오기
            memory_context = session_memory.get_context_for_llm()

        # 통합 상태 초기화
        initial_state = create_initial_state(
            user_query=body.message,
            chat_type=body.chat_type,
            onboarding=cast(Any, body.onboarding),
        )

        # 온보딩 데이터 영속화
        if body.onboarding and session_memory:
            session_memory.save_metadata("onboarding", dict(body.onboarding))
        elif session_memory:
            saved_onboarding = session_memory.get_metadata("onboarding")
            if saved_onboarding:
                initial_state["onboarding"] = saved_onboarding

        # 메모리 컨텍스트를 초기 상태에 병합
        if memory_context and session_memory:
            initial_state["conversation_history"] = memory_context.get(
                "conversation_history", []
            )
            initial_state["compact_summary"] = memory_context.get("compact_summary")
            initial_state["total_turn_count"] = session_memory.get_total_turn_count()

        # 세션 ID를 state에 포함 (L4 캐시 키로 사용)
        initial_state["session_id"] = session_id

        config = cast(
            Any,
            {
                "configurable": {"thread_id": session_id},
                "recursion_limit": GRAPH_RECURSION_LIMIT,
            },
        )

        # === PR-6: L1 Supervisor Response Cache Check ===
        from app.supervisor.cache import SupervisorResponseCache

        cached_response = SupervisorResponseCache.get(body.message, session_id)
        if cached_response:
            logger.info(
                f"[L1 Cache HIT] Returning cached response for: {body.message[:30]}..."
            )
            # 캐시에서 복원한 응답을 사용
            final_state = {
                "final_answer": cached_response.get("final_answer", ""),
                "mode": cached_response.get("mode"),
                "query_analysis": cached_response.get("query_analysis", {}),
                "citations": cached_response.get("citations", []),
                "sources": [],
                "retrieval": {},
                "_cache_hit": True,
            }
        else:
            # === PR-6 끝 ===
            # MAS graph includes async nodes; prefer the async API when available.
            GRAPH_TIMEOUT_SECONDS = getattr(get_config(), "graph_timeout_seconds", 120)
            logger.info(
                f"[chat] Starting graph execution for session={session_id[:8]}..."
            )
            try:
                if hasattr(graph, "ainvoke"):
                    final_state = await asyncio.wait_for(
                        graph.ainvoke(initial_state, config),
                        timeout=GRAPH_TIMEOUT_SECONDS,
                    )
                else:
                    final_state = await asyncio.wait_for(
                        asyncio.to_thread(graph.invoke, initial_state, config),
                        timeout=GRAPH_TIMEOUT_SECONDS,
                    )
            except asyncio.TimeoutError:
                logger.error(
                    f"[chat] Graph execution timed out after {GRAPH_TIMEOUT_SECONDS}s for session={session_id[:8]}"
                )
                raise HTTPException(
                    status_code=504,
                    detail="요청 처리 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.",
                )
            logger.info(
                f"[chat] Graph execution completed for session={session_id[:8]}"
            )

            # === PR-6: L1 Cache Save ===
            if final_state.get("final_answer") and not final_state.get(
                "guardrail_blocked"
            ):
                SupervisorResponseCache.set(
                    body.message,
                    {
                        "final_answer": final_state.get("final_answer"),
                        "mode": final_state.get("mode"),
                        "query_analysis": final_state.get("query_analysis", {}),
                        "citations": final_state.get("citations", []),
                    },
                    session_id,
                )
                logger.debug(
                    f"[L1 Cache SAVE] Cached response for: {body.message[:30]}..."
                )
            # === PR-6 끝 ===

        # 로깅용 retrieval 정보
        retrieval = final_state.get("retrieval") or {}
        rag_logger.log_structured_retrieval(
            entry=log_entry,
            agency_info=retrieval.get("agency", {}),
            disputes=retrieval.get("disputes", []),
            counsels=retrieval.get("counsels", []),
            laws=retrieval.get("laws", []),
            criteria=retrieval.get("criteria", []),
        )

        answer = final_state.get("final_answer") or ""

        # 어시스턴트 응답을 메모리에 추가
        if session_memory:
            await session_memory.add_turn(role="assistant", content=answer)

        node_timings = final_state.get("_node_timings", {})
        if node_timings:
            rag_logger.log_node_timings(log_entry, node_timings)

        # 에이전트 트레이스 로깅
        pipeline_summary = None
        trace_entries = final_state.get("_agent_trace_entries", [])
        if trace_entries:
            from app.supervisor.graph import build_pipeline_summary

            pipeline_summary = build_pipeline_summary(
                trace_entries,
                total_duration_ms=log_entry.total_time_ms or 0,
            )
            rag_logger.log_pipeline_trace(log_entry, pipeline_summary)

        # 공통 응답 빌더로 응답 데이터 구성
        response_data = build_chat_response_data(session_id, final_state)

        rag_logger.log_response(
            entry=log_entry,
            answer=answer,
            chunks_used=len(response_data["sources"]),
            sources_count=len(response_data["sources"]),
            status="success",
        )
        rag_logger.finalize(log_entry, start_time)
        rag_logger.save(log_entry)

        # M3-3: best-effort workflow run 저장 (A 경로). run_id는 S3 로그와 공유.
        from app.observability import save_workflow_run

        await save_workflow_run(
            run_id=log_entry.request_id,
            variant="A",
            query=body.message,
            status="success",
            session_id=session_id,
            chat_type=body.chat_type,
            total_time_ms=log_entry.total_time_ms,
            clarified=not response_data.get("has_sufficient_evidence", True),
            blocked=bool(final_state.get("guardrail_blocked")),
        )

        # M3-4: best-effort workflow step 저장 (A node sequence + latency).
        if pipeline_summary:
            from app.observability.workflow_steps import (
                build_a_steps,
                save_workflow_steps,
            )

            await save_workflow_steps(
                log_entry.request_id,
                build_a_steps(pipeline_summary.get("per_node", []), node_timings),
            )

        # debug 모드일 때 타이밍 정보 변환
        timing_response = None
        if body.debug and node_timings:
            timing_response = [
                NodeTiming(
                    node_name=name,
                    duration_ms=info.get("duration_ms", 0),
                    start_time=info.get("start_time", ""),
                    end_time=info.get("end_time", ""),
                )
                for name, info in node_timings.items()
            ]

        return ChatResponse(
            **response_data,
            chunks_used=len(response_data["sources"]),
            model="gpt-4o-mini",
            node_timings=timing_response if body.debug else None,
            request_id=log_entry.request_id if body.debug else None,
            total_time_ms=log_entry.total_time_ms if body.debug else None,
        )

    except Exception as e:
        logger.exception("[chat] Unhandled error")
        rag_logger.log_response(
            entry=log_entry,
            answer="",
            chunks_used=0,
            sources_count=0,
            status="error",
            error_message=str(e),
        )
        rag_logger.finalize(log_entry, start_time)
        rag_logger.save(log_entry)

        # M3-3: best-effort workflow run 저장 (A 경로, 에러). final_state 부재 가능.
        from app.observability import save_workflow_run

        await save_workflow_run(
            run_id=log_entry.request_id,
            variant="A",
            query=body.message,
            status="error",
            session_id=session_id,
            chat_type=body.chat_type,
            error_message=str(e),
            total_time_ms=log_entry.total_time_ms,
        )

        raise HTTPException(
            status_code=500,
            detail="답변 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        )


async def _stream_with_heartbeat(async_iterable, heartbeat_interval: int = 15):
    """astream_events에 heartbeat를 인터리브하는 래퍼.

    이벤트 간 간격이 heartbeat_interval을 초과하면 heartbeat를 yield합니다.
    generation_node_v2 같은 blocking LLM 호출 중에도 heartbeat를 전송하여
    프론트엔드 SSE 타임아웃을 방지합니다.
    """
    aiter = async_iterable.__aiter__()
    while True:
        try:
            event = await asyncio.wait_for(
                aiter.__anext__(), timeout=heartbeat_interval
            )
            yield ("event", event)
        except asyncio.TimeoutError:
            yield ("heartbeat", None)
        except StopAsyncIteration:
            break


@router.post("/chat/stream")
@limiter.limit(RateLimits.CHAT_GUEST)
async def chat_stream_sse(
    request: Request,
    body: ChatRequest,
    current_user: Optional[User] = Depends(get_current_user_optional),
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
        log_entry = rag_logger.create_entry(query=body.message)
        rag_logger.log_input(
            entry=log_entry,
            message=body.message,
            session_id=body.session_id,
            chat_type=body.chat_type,
            onboarding=body.onboarding,
            top_k=body.top_k or 5,
            chunk_types=body.chunk_types,
            agencies=body.agencies,
        )

        session_id = body.session_id or str(uuid.uuid4())
        final_state = None

        # 즉시 연결 확인 이벤트 전송 (클라이언트에 연결 성공 알림)
        yield f"data: {json.dumps({'type': 'status', 'data': {'node': 'init', 'status': '연결됨', 'progress': 0}}, ensure_ascii=False)}\n\n"

        # Get user_id from JWT token
        user_id = current_user.user_id if current_user else None

        try:
            graph = get_graph_for_chat_type(body.chat_type)
            GRAPH_RECURSION_LIMIT = 50

            # Create memory with DB persistence
            config = get_config()
            use_db = config.memory.backend == "db"

            logger.info(
                f"[chat_stream] Memory backend: {config.memory.backend}, use_db: {use_db}, user_id: {user_id}"
            )

            session_memory = None
            memory_context = {}
            if should_use_memory(body.chat_type):
                session_memory = ConversationMemory(
                    chat_type=body.chat_type,
                    session_id=session_id,
                    user_id=user_id,
                    use_db=use_db,
                )
                logger.info(
                    f"[chat_stream] ConversationMemory created: session={session_id[:8]}, use_db={use_db}, chat_type={body.chat_type}"
                )
                await session_memory.add_turn(role="user", content=body.message)
                memory_context = session_memory.get_context_for_llm()

            # 초기 상태 생성
            initial_state = create_initial_state(
                user_query=body.message,
                chat_type=body.chat_type,
                onboarding=cast(Any, body.onboarding),
            )

            # 온보딩 데이터 영속화
            if body.onboarding and session_memory:
                session_memory.save_metadata("onboarding", dict(body.onboarding))
            elif session_memory:
                saved_onboarding = session_memory.get_metadata("onboarding")
                if saved_onboarding:
                    initial_state["onboarding"] = saved_onboarding

            # 메모리 컨텍스트 병합
            if memory_context and session_memory:
                initial_state["conversation_history"] = memory_context.get(
                    "conversation_history", []
                )
                initial_state["compact_summary"] = memory_context.get("compact_summary")
                initial_state["total_turn_count"] = (
                    session_memory.get_total_turn_count()
                )

            # 세션 ID를 state에 포함 (L4 캐시 키로 사용)
            initial_state["session_id"] = session_id

            runnable_config = cast(
                Any,
                {
                    "configurable": {"thread_id": session_id},
                    "recursion_limit": GRAPH_RECURSION_LIMIT,
                },
            )

            logger.info(
                f"[chat_stream] Starting graph streaming for session={session_id[:8]}..."
            )

            # LangGraph astream_events로 실시간 토큰 스트리밍 + 노드 진행 상황
            # on_custom_event: 토큰, fallback 이벤트 (generation_node가 발생)
            # on_chain_start/end: 노드 시작/종료
            full_answer = ""
            final_state = {}
            SSE_HEARTBEAT_INTERVAL = 15  # 초

            async for item_type, item in _stream_with_heartbeat(
                graph.astream_events(initial_state, runnable_config, version="v2"),
                heartbeat_interval=SSE_HEARTBEAT_INTERVAL,
            ):
                if item_type == "heartbeat":
                    yield ": heartbeat\n\n"
                    continue

                event = item
                event_type = event.get("event")

                # 1. Custom Events (token, fallback, error)
                if event_type == "on_custom_event":
                    custom_event_name = event.get("name")
                    custom_data = event.get("data", {})

                    if custom_event_name == "generation_token":
                        # Token from LLM streaming
                        full_answer += custom_data.get("content", "")
                        sse_event = {
                            "type": "token",
                            "data": {
                                "content": custom_data.get("content"),
                                "model": custom_data.get("model", "unknown"),
                            },
                        }
                        yield f"data: {json.dumps(sse_event, ensure_ascii=False)}\n\n"

                    elif custom_event_name == "generation_fallback":
                        # Fallback model switch
                        fallback_event = {
                            "type": "fallback",
                            "data": {
                                "model": custom_data.get("model", "unknown"),
                                "message": custom_data.get(
                                    "message", "Fallback triggered"
                                ),
                            },
                        }
                        yield f"data: {json.dumps(fallback_event, ensure_ascii=False)}\n\n"

                    elif custom_event_name == "generation_error":
                        # Error during generation
                        error_event = {
                            "type": "error",
                            "data": {"message": "답변 생성 중 오류가 발생했습니다."},
                        }
                        yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

                # 2. Node Start Events (status updates)
                elif event_type == "on_chain_start":
                    node_name = event.get("name", "")
                    if node_name in NODE_LABELS:
                        label, progress = NODE_LABELS[node_name]
                        status_event = {
                            "type": "status",
                            "data": {
                                "node": node_name,
                                "status": label,
                                "progress": progress,
                            },
                        }
                        yield f"data: {json.dumps(status_event, ensure_ascii=False)}\n\n"

                # 3. Node End Events (capture final state)
                elif event_type == "on_chain_end":
                    chain_name = event.get("name", "")
                    node_output = event.get("data", {}).get("output", {})

                    # DEBUG: output_guardrail 노드의 출력 확인
                    if chain_name == "output_guardrail" and isinstance(
                        node_output, dict
                    ):
                        og_answer = node_output.get("final_answer", "")
                        logger.info(
                            f"[SSE DEBUG] output_guardrail returned final_answer length: {len(og_answer) if og_answer else 'None/Empty'}"
                        )
                        if og_answer and "[출처]" in og_answer:
                            source_idx = og_answer.find("[출처]")
                            logger.info(
                                f"[SSE DEBUG] output_guardrail source: {og_answer[source_idx : source_idx + 150]}..."
                            )

                    if (
                        isinstance(node_output, dict)
                        and chain_name in KNOWN_GRAPH_NODES
                    ):
                        existing_answer = final_state.get("final_answer", "")
                        final_state.update(node_output)

                        # final_answer가 유효한 값에서 빈 값으로 덮어쓰여진 경우 복원
                        new_answer = final_state.get("final_answer", "")
                        if existing_answer and not new_answer:
                            final_state["final_answer"] = existing_answer
                            logger.warning(
                                f"[SSE] Restored final_answer overwritten by node={chain_name}"
                            )

            # 최종 결과 전송
            if final_state:
                answer = final_state.get("final_answer", "")

                # DEBUG: SSE 전송 전 final_answer 확인
                logger.info(f"[SSE DEBUG] final_state keys: {list(final_state.keys())}")
                logger.info(
                    f"[SSE DEBUG] final_answer length: {len(answer) if answer else 'None/Empty'}"
                )
                if answer and "[출처]" in answer:
                    source_idx = answer.find("[출처]")
                    logger.info(
                        f"[SSE DEBUG] Source section: {answer[source_idx : source_idx + 200]}..."
                    )

                # DEBUG: full_answer 상태 확인
                logger.info(
                    f"[SSE DEBUG] full_answer (streamed) length: {len(full_answer)}"
                )

                # Fallback: final_answer가 비어있을 때 토큰 누적 답변 사용
                if not answer and full_answer:
                    logger.warning(
                        "[SSE DEBUG] final_answer is empty, using full_answer fallback"
                    )
                    review_executed = bool(final_state.get("review"))
                    if review_executed:
                        review_answer = (final_state.get("review", {}) or {}).get(
                            "final_answer", ""
                        )
                        if review_answer:
                            answer = review_answer
                            logger.warning(
                                "[SSE] Using review.final_answer as fallback"
                            )
                        else:
                            answer = full_answer
                            logger.error(
                                "[SSE] final_answer is empty after review execution. "
                                "Falling back to pre-review full_answer as last resort."
                            )
                    else:
                        answer = full_answer
                        logger.warning(
                            "[SSE] Using streamed full_answer as fallback "
                            "(final_state.final_answer was empty, no review executed)"
                        )

                # 공통 응답 빌더로 응답 데이터 구성
                response_data = build_chat_response_data(session_id, final_state)
                # 스트리밍에서 누적한 answer가 더 정확할 수 있으므로 덮어쓰기
                response_data["answer"] = answer

                # 어시스턴트 응답을 메모리에 추가
                if session_memory:
                    await session_memory.add_turn(role="assistant", content=answer)
                    logger.info(
                        f"[chat_stream] Memory save status: "
                        f"conversation_id={session_memory.conversation_id}, "
                        f"use_db={session_memory.use_db}, "
                        f"turns={session_memory.get_turn_count()}, "
                        f"session={session_id[:8]}"
                    )

                complete_event = {"type": "complete", "data": response_data}

                # DEBUG: 최종 SSE 전송 데이터 확인
                sent_answer = response_data.get("answer", "")
                logger.info(f"[SSE DEBUG] Sending answer length: {len(sent_answer)}")
                if "[출처]" in sent_answer:
                    source_idx = sent_answer.find("[출처]")
                    logger.info(
                        f"[SSE DEBUG] Sent source section: {sent_answer[source_idx : source_idx + 200]}..."
                    )
                else:
                    logger.warning("[SSE DEBUG] No [출처] section in sent answer!")
                    logger.info(
                        f"[SSE DEBUG] Full answer preview: {sent_answer[:300]}..."
                    )

                yield f"data: {json.dumps(complete_event, ensure_ascii=False)}\n\n"

                # 에이전트 트레이스 로깅
                trace_entries = (
                    final_state.get("_agent_trace_entries", []) if final_state else []
                )
                if trace_entries:
                    from app.supervisor.graph import build_pipeline_summary

                    pipeline_summary = build_pipeline_summary(
                        trace_entries,
                        total_duration_ms=(time.time() - start_time) * 1000,
                    )
                    rag_logger.log_pipeline_trace(log_entry, pipeline_summary)

                # RAG 로깅
                retrieval = final_state.get("retrieval") or {}
                rag_logger.log_structured_retrieval(
                    entry=log_entry,
                    agency_info=retrieval.get("agency", {}),
                    disputes=retrieval.get("disputes", []),
                    counsels=retrieval.get("counsels", []),
                    laws=retrieval.get("laws", []),
                    criteria=retrieval.get("criteria", []),
                )
                rag_logger.log_response(
                    entry=log_entry,
                    answer=answer,
                    chunks_used=len(response_data["sources"]),
                    sources_count=len(response_data["sources"]),
                    status="success",
                )
                rag_logger.finalize(log_entry, start_time)
                rag_logger.save(log_entry)

        except asyncio.CancelledError:
            logger.info(
                f"[chat_stream] Client disconnected during streaming, session={session_id[:8]}"
            )
            # BUG-6 fix: 부분 응답이 있으면 assistant turn으로 저장
            if full_answer and session_memory:
                try:
                    await session_memory.add_turn(role="assistant", content=full_answer)
                    logger.info(
                        f"[chat_stream] Saved partial answer ({len(full_answer)} chars) on cancel"
                    )
                except Exception as save_err:
                    logger.error(
                        f"[chat_stream] Failed to save partial answer: {save_err}"
                    )
            rag_logger.log_response(
                entry=log_entry,
                answer=full_answer or "",
                chunks_used=0,
                sources_count=0,
                status="cancelled",
                error_message="Client disconnected",
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
                error_message=str(e),
            )
            rag_logger.finalize(log_entry, start_time)
            rag_logger.save(log_entry)
            error_event = {
                "type": "error",
                "data": {
                    "message": "답변 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
                },
            }
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Nginx buffering 비활성화
        },
    )


# ============================================================
# 대화 세션 관리 API
# ============================================================


@router.get("/chat/sessions")
@limiter.limit(RateLimits.AUTH)
async def get_user_sessions(
    request: Request,
    current_user: User = Depends(get_current_user_optional),
    limit: int = 20,
    offset: int = 0,
):
    """
    로그인한 사용자의 대화 세션 목록을 조회합니다.

    Args:
        current_user: 현재 인증된 사용자 (필수)
        limit: 최대 개수 (기본값: 20)
        offset: 건너뛸 개수 (기본값: 0)

    Returns:
        대화 세션 목록 (최신순)

    Raises:
        HTTPException 401: 인증되지 않은 사용자
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")

    try:
        from app.supervisor.persistence.db import ConversationDB

        db = ConversationDB()
        conversations = await db.get_user_conversations(
            user_id=current_user.user_id,
            limit=limit,
            offset=offset,
            include_inactive=False,
        )

        # 응답 형식 변환
        sessions = []
        for conv in conversations:
            sessions.append(
                {
                    "id": str(conv["session_id"]),
                    "type": conv["chat_type"],
                    "title": f"{conv['chat_type']} 상담",  # TODO: 첫 메시지에서 제목 생성
                    "createdAt": conv["created_at"].isoformat(),
                    "lastMessageAt": conv["updated_at"].isoformat(),
                    "turnCount": conv["turn_count"],
                }
            )

        logger.info(
            f"[get_user_sessions] user={current_user.user_id}, count={len(sessions)}"
        )
        return {"sessions": sessions}

    except Exception as e:
        logger.error(f"[get_user_sessions] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="세션 목록 조회 실패")


@router.get("/chat/sessions/{session_id}/history")
@limiter.limit(RateLimits.AUTH)
async def get_session_history(
    request: Request,
    session_id: str,
    current_user: User = Depends(get_current_user_optional),
    limit: int = 50,
):
    """
    특정 세션의 대화 내역을 조회합니다.

    Args:
        session_id: 세션 ID
        current_user: 현재 인증된 사용자 (필수)
        limit: 최대 턴 수 (기본값: 50)

    Returns:
        대화 내역 (시간순)

    Raises:
        HTTPException 401: 인증되지 않은 사용자
        HTTPException 403: 다른 사용자의 세션
        HTTPException 404: 세션을 찾을 수 없음
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")

    try:
        from app.supervisor.persistence.db import ConversationDB

        db = ConversationDB()

        # 세션 정보 조회 (권한 확인)
        conv = await db.get_conversation_by_session(session_id)
        if not conv:
            raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

        # 권한 확인: 자신의 세션만 조회 가능
        if conv["user_id"] != current_user.user_id:
            raise HTTPException(status_code=403, detail="접근 권한이 없습니다")

        # 대화 내역 조회
        history = await db.get_conversation_history(
            conversation_id=conv["conversation_id"], limit=limit
        )

        # 응답 형식 변환
        messages = []
        for turn in history:
            messages.append(
                {
                    "id": turn["turn_number"],
                    "type": "user" if turn["role"] == "user" else "ai",
                    "content": turn["content"],
                    "timestamp": turn["created_at"].isoformat(),
                }
            )

        logger.info(
            f"[get_session_history] session={session_id[:8]}, messages={len(messages)}"
        )
        return {"messages": messages}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[get_session_history] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="대화 내역 조회 실패")


@router.delete("/chat/sessions/{session_id}")
@limiter.limit(RateLimits.AUTH)
async def delete_session(
    request: Request,
    session_id: str,
    current_user: User = Depends(get_current_user_optional),
):
    """
    특정 세션을 삭제(비활성화)합니다.

    Args:
        session_id: 세션 ID
        current_user: 현재 인증된 사용자 (필수)

    Returns:
        성공 메시지

    Raises:
        HTTPException 401: 인증되지 않은 사용자
        HTTPException 403: 다른 사용자의 세션
        HTTPException 404: 세션을 찾을 수 없음
    """
    if not current_user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")

    try:
        from app.supervisor.persistence.db import ConversationDB

        db = ConversationDB()

        # 세션 정보 조회 (권한 확인)
        conv = await db.get_conversation_by_session(session_id)
        if not conv:
            raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

        # 권한 확인: 자신의 세션만 삭제 가능
        if conv["user_id"] != current_user.user_id:
            raise HTTPException(status_code=403, detail="접근 권한이 없습니다")

        # 세션 비활성화
        await db.deactivate_conversation(conv["conversation_id"])

        logger.info(
            f"[delete_session] session={session_id[:8]}, user={current_user.user_id}"
        )
        return {"success": True, "message": "세션이 삭제되었습니다"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[delete_session] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="세션 삭제 실패")


@router.post("/chat/sessions/claim")
@limiter.limit(RateLimits.AUTH)
async def claim_guest_sessions(
    request: Request,
    body: dict,
    current_user: User = Depends(get_current_user),
):
    """
    게스트 세션을 로그인한 사용자 계정으로 이전합니다.
    로그인 시 한 번 호출됩니다.

    Note: get_current_user 사용 (인증 필수, 미인증 시 자동 401)
    """
    session_ids = body.get("session_ids", [])
    if not session_ids or not isinstance(session_ids, list):
        raise HTTPException(
            status_code=422, detail="session_ids는 비어있지 않은 리스트여야 합니다"
        )
    if len(session_ids) > 50:
        raise HTTPException(
            status_code=422, detail="session_ids는 최대 50개까지 허용됩니다"
        )
    if not all(isinstance(sid, str) and 0 < len(sid) <= 100 for sid in session_ids):
        raise HTTPException(
            status_code=422,
            detail="session_ids의 모든 항목은 1~100자의 문자열이어야 합니다",
        )

    from app.supervisor.persistence.db import ConversationDB

    db = ConversationDB()
    claimed_ids = await db.claim_sessions_for_user(
        session_ids=session_ids,
        user_id=current_user.user_id,
    )
    return {
        "claimed_count": len(claimed_ids),
        "claimed_session_ids": claimed_ids,
    }


__all__ = ["router"]
