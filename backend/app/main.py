import os
import time
import asyncio
import uuid
import logging
import json
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any, Generator, Literal, cast
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

if os.getenv('LANGCHAIN_TRACING_V2', 'false').lower() == 'true':
    logger.info(f"[Langsmith] Tracing enabled - Project: {os.getenv('LANGCHAIN_PROJECT', 'default')}")

from app.agents.retrieval.tools.retriever import RAGRetriever, SearchResult
from app.agents.retrieval.tools.hybrid_retriever import HybridRetriever
from app.agents.answer_generation.tools.generator import RAGGenerator

from app.common.logger import get_rag_logger
from utils.embedding_connection import get_embedding_api_url
from app.orchestrator import get_graph, get_graph_for_chat_type, create_initial_state
from app.orchestrator.memory import ConversationMemory, should_use_memory

# PR-3: 세션별 대화 메모리 저장소 (in-memory, 프로덕션에서는 Redis 등 사용 권장)
_session_memories: Dict[str, ConversationMemory] = {}

# PR-5: SSE 실시간 상태 표시용 노드 라벨 및 진행률
# (노드 이름, 한글 라벨, 진행률 %)
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

from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI(
    title="똑소리 API",
    version="0.4.1",  # Refactored for concurrency safety
    description="한국 소비자 분쟁 조정 RAG 챗봇 API"
)

# S3-PR5: Prometheus Monitoring
Instrumentator().instrument(app).expose(app)

# CORS 설정
cors_origins = [origin.strip() for origin in os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(',')]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# DB 설정
db_config = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'ddoksori'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres'),
    'client_encoding': 'UTF8'  # Ensure UTF-8 encoding for Korean text
}

# RAG 컴포넌트 설정
# Adaptive Embedding Strategy: Determine best URL (Remote -> Local Running -> Start Local)
embed_api_url = get_embedding_api_url()
# Update env var for other components that might check it
os.environ['EMBED_API_URL'] = embed_api_url
retrieval_mode = os.getenv('RETRIEVAL_MODE', 'dense')  # 'hybrid', 'dense'

generator = RAGGenerator()
rag_logger = get_rag_logger()


# Dependency for Retriever
def get_retriever() -> Generator[Any, None, None]:
    """
    Retriever 인스턴스를 생성하고 연결을 관리하는 Dependency
    요청마다 독립적인 DB 연결을 보장함
    """
    if retrieval_mode == 'hybrid':
        retriever_instance = HybridRetriever(db_config, embed_api_url)
    else:
        retriever_instance = RAGRetriever(db_config, embed_api_url)
    
    try:
        retriever_instance.connect()
        yield retriever_instance
    finally:
        retriever_instance.close()


def _serialize_search_result(chunk: SearchResult) -> Dict[str, Any]:
    """SearchResult 객체를 dict로 변환 (S1-1 citation metadata)"""
    return {
        'chunk_id': chunk.chunk_id,
        'doc_id': chunk.doc_id,
        'chunk_type': chunk.chunk_type,
        'content': chunk.content,
        'doc_title': chunk.doc_title,
        'doc_type': chunk.doc_type,
        'category_path': chunk.category_path,
        'similarity': chunk.similarity,
        # S1-1 Citation Metadata
        'source_org': chunk.source_org,
        'url': chunk.url,
        'decision_date': chunk.decision_date,
        'collected_at': chunk.collected_at
    }


# Request/Response 모델
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="사용자 질문")
    session_id: Optional[str] = Field(default=None, description="멀티턴 세션 ID (없으면 새 세션 생성)")
    chat_type: Literal['dispute', 'general'] = Field(default='dispute', description="상담 유형")
    onboarding: Optional[Dict[str, str]] = Field(default=None, description="온보딩 폼 데이터")
    top_k: Optional[int] = Field(default=5, ge=1, le=100, description="검색 결과 수")
    chunk_types: Optional[List[str]] = None
    agencies: Optional[List[str]] = None
    debug: bool = Field(default=False, description="디버그 모드 (타이밍 정보 포함)")

    @field_validator('message')
    @classmethod
    def message_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('메시지는 빈 문자열일 수 없습니다')
        return v.strip()


class AgencyRecommendation(BaseModel):
    """추천 기관 정보"""
    agency: str  # KCA, ECMC, KCDRC
    agency_info: Dict[str, str]
    dispute_type: str  # 1:N, 1:1, contents
    reason: str
    confidence: float = 0.7


class CaseReference(BaseModel):
    """사례 참조 정보 (Phase 2: 메타데이터 포함)"""
    chunk_id: Optional[str] = None
    doc_id: Optional[str] = None
    doc_title: Optional[str] = None
    source_org: Optional[str] = None
    decision_date: Optional[str] = None
    similarity: float = 0.0
    content: Optional[str] = None
    url: Optional[str] = None
    # Phase 2: 실시간 LLM 추출 메타데이터
    product_item: Optional[str] = None        # 품목 (예: "키보드", "헬스회원권")
    dispute_amount: Optional[str] = None      # 금액 (예: "120,000원")
    transaction_date: Optional[str] = None    # 거래/구매 일자
    mediation_result: Optional[str] = None    # 조정결과 (예: "인용", "기각", "조정성립")


class LawReference(BaseModel):
    """법령 참조 정보"""
    unit_id: Optional[str] = None
    law_name: Optional[str] = None
    full_path: Optional[str] = None  # "제14조 제1항"
    text: Optional[str] = None
    similarity: float = 0.0


class CriteriaReference(BaseModel):
    """기준 참조 정보"""
    unit_id: Optional[str] = None
    source_label: Optional[str] = None
    category: Optional[str] = None
    industry: Optional[str] = None
    item_group: Optional[str] = None
    item: Optional[str] = None
    unit_text: Optional[str] = None
    similarity: float = 0.0


class SimilarCases(BaseModel):
    """유사 사례 모음"""
    disputes: List[CaseReference] = []
    counsels: List[CaseReference] = []


class NodeTiming(BaseModel):
    """에이전트 노드 실행 시간 (debug 모드용)"""
    node_name: str
    duration_ms: float
    start_time: str
    end_time: str


class ChatResponse(BaseModel):
    session_id: str = Field(..., description="세션 ID (멀티턴 대화용)")
    answer: str
    chunks_used: int
    model: str
    sources: List[dict]
    has_sufficient_evidence: bool = True
    clarifying_questions: List[str] = []
    domain: Optional[AgencyRecommendation] = None
    similar_cases: Optional[SimilarCases] = None
    related_laws: Optional[List[LawReference]] = None
    related_criteria: Optional[List[CriteriaReference]] = None
    # debug 모드 필드
    node_timings: Optional[List[NodeTiming]] = None
    request_id: Optional[str] = None
    total_time_ms: Optional[float] = None


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="검색 쿼리")
    top_k: Optional[int] = Field(default=5, ge=1, le=100, description="검색 결과 수")
    chunk_types: Optional[List[str]] = None
    agencies: Optional[List[str]] = None

    @field_validator('query')
    @classmethod
    def query_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('쿼리는 빈 문자열일 수 없습니다')
        return v.strip()


# API 엔드포인트
@app.get("/")
async def root():
    return {
        "message": "똑소리 API 서버가 정상적으로 실행 중입니다.",
        "version": "0.4.1",
        "retrieval_mode": retrieval_mode,
        "features": [
            "Hybrid RAG 검색 (Dense + Lexical + RRF)" if retrieval_mode == 'hybrid' else "RAG 검색",
            "LLM 답변 생성"
        ]
    }


@app.get("/health")
async def health_check():
    """서버 상태 확인"""
    # Note: Dedicated connection for health check
    try:
        if retrieval_mode == 'hybrid':
            checker = HybridRetriever(db_config, embed_api_url)
        else:
            checker = RAGRetriever(db_config, embed_api_url)
        
        checker.connect()
        checker.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        # Safe string conversion for Windows CP949/EUC-KR locale issues
        try:
            error_msg = str(e)
        except UnicodeDecodeError:
            error_msg = repr(e)
        return {"status": "unhealthy", "error": error_msg}


@app.post("/search")
async def search(
    request: SearchRequest,
    retriever=Depends(get_retriever)
):
    """
    Vector DB에서 유사한 사례 검색 (LLM 답변 생성 없이 검색만)
    """
    try:
        # chunk_types 필터 처리 (리스트의 첫 번째 값 사용)
        chunk_type_filter = request.chunk_types[0] if request.chunk_types else None

        # Hybrid search (RRF fusion) or vector-only
        if hasattr(retriever, 'search') and retrieval_mode == 'hybrid':
            chunks = retriever.search(
                query=request.query,
                top_k=request.top_k,
                chunk_type_filter=chunk_type_filter
            )
        else:
            chunks = retriever.vector_search(
                query=request.query,
                top_k=request.top_k,
                chunk_type_filter=chunk_type_filter
            )

        # SearchResult 객체를 dict로 변환
        results = [_serialize_search_result(chunk) for chunk in chunks]

        return {
            "query": request.query,
            "results_count": len(results),
            "results": results
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 중 오류 발생: {str(e)}")


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    LangGraph 기반 멀티턴 챗봇 응답 생성
    
    워크플로우: query_analysis → retrieval → generation → review → END
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

        # Phase 5: Recursion limit 증가 (기본 25 → 50)
        # V2 그래프의 sufficiency 및 review 루프로 인해 기본값이 부족할 수 있음
        GRAPH_RECURSION_LIMIT = 50

        # PR-3: 세션 메모리 가져오기/생성
        memory_context = {}
        if should_use_memory(request.chat_type):
            if session_id not in _session_memories:
                _session_memories[session_id] = ConversationMemory(chat_type=request.chat_type)
            session_memory = _session_memories[session_id]

            # 사용자 메시지를 메모리에 추가
            session_memory.add_turn(role='user', content=request.message)

            # 메모리 컨텍스트 가져오기
            memory_context = session_memory.get_context_for_llm()

        # PR-2: 통합 상태 초기화 (chat_type에 따라 max_iterations 자동 설정)
        initial_state = create_initial_state(
            user_query=request.message,
            chat_type=request.chat_type,
            onboarding=cast(Any, request.onboarding),
            # max_iterations는 create_initial_state에서 chat_type 기반으로 자동 설정
            # general: 1, dispute: 2
        )

        # PR-3: 메모리 컨텍스트를 초기 상태에 병합
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

        # PR-3: 어시스턴트 응답을 메모리에 추가
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
            # debug 모드 필드
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


@app.post("/chat/stream")
async def chat_stream_sse(request: ChatRequest):
    """
    PR-5: LangGraph astream 기반 SSE 스트리밍 챗봇 응답 생성

    SSE 이벤트 타입:
    - status: 노드별 진행 상태 (node, status, progress)
    - complete: 최종 결과 (session_id, answer, sources)
    - error: 오류 발생 시

    Example SSE events:
        data: {"type": "status", "data": {"node": "query_analysis", "status": "질의 분석중...", "progress": 15}}
        data: {"type": "status", "data": {"node": "react_act", "status": "정보 검색중...", "progress": 50}}
        data: {"type": "complete", "data": {"session_id": "...", "answer": "...", "sources": [...]}}
    """
    async def event_generator():
        session_id = request.session_id or str(uuid.uuid4())
        final_state = None

        try:
            graph = get_graph_for_chat_type(request.chat_type)
            GRAPH_RECURSION_LIMIT = 50

            # PR-3: 세션 메모리 가져오기/생성
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

            # PR-3: 메모리 컨텍스트 병합
            if memory_context:
                initial_state['conversation_history'] = memory_context.get('conversation_history', [])
                initial_state['compact_summary'] = memory_context.get('compact_summary')
                initial_state['total_turn_count'] = _session_memories[session_id].get_total_turn_count()

            config = cast(Any, {
                "configurable": {"thread_id": session_id},
                "recursion_limit": GRAPH_RECURSION_LIMIT
            })

            # PR-5: LangGraph astream으로 노드별 진행 상황 스트리밍
            async for event in graph.astream(initial_state, config):
                # event는 {노드이름: 노드출력상태} 형태의 dict
                if event:
                    node_name = list(event.keys())[0]
                    final_state = event[node_name]  # 최신 상태 저장

                    # 노드 라벨 및 진행률 가져오기
                    label, progress = NODE_LABELS.get(node_name, ('처리중...', 0))

                    # SSE status 이벤트 전송
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

                # PR-3: 어시스턴트 응답을 메모리에 추가
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


@app.get("/case/{case_uid}")
async def get_case(
    case_uid: str,
    retriever=Depends(get_retriever)
):
    """
    특정 사례의 전체 정보 조회
    """
    try:
        chunks = retriever.get_case_chunks(case_uid)
        
        if not chunks:
            raise HTTPException(status_code=404, detail="사례를 찾을 수 없습니다.")
        
        return {
            "case_uid": case_uid,
            "chunks_count": len(chunks),
            "chunks": chunks
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"사례 조회 중 오류 발생: {str(e)}")


@app.get("/metrics/agents")
async def get_agent_metrics(agent_name: Optional[str] = None):
    """
    S2-PR5: 에이전트 성능 메트릭스 조회
    
    Args:
        agent_name: 특정 에이전트 이름 (없으면 전체)
    
    Returns:
        성능 통계 (count, success_rate, avg/min/max/p95 duration)
    """
    from app.common.metrics import AgentMetrics
    return AgentMetrics.get_stats(agent_name)


@app.get("/metrics/agents/summary")
async def get_agent_metrics_summary():
    """
    S2-PR5: 전체 에이전트 성능 요약
    """
    from app.common.metrics import AgentMetrics
    return AgentMetrics.get_summary()


@app.get("/metrics/agents/recent")
async def get_recent_metrics(agent_name: Optional[str] = None, limit: int = 100):
    """
    S2-PR5: 최근 메트릭 레코드 조회
    """
    from app.common.metrics import AgentMetrics
    return AgentMetrics.get_recent_records(agent_name, limit)


# mcp = FastMCP.from_fastapi(app)

# if __name__ == "__main__":
#     mcp.run()