import os
import time
import asyncio
import uuid
import logging
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
from app.orchestrator import get_graph, get_graph_for_chat_type, create_initial_state, create_simple_state

app = FastAPI(
    title="똑소리 API",
    version="0.4.1",  # Refactored for concurrency safety
    description="한국 소비자 분쟁 조정 RAG 챗봇 API"
)

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
    """사례 참조 정보"""
    chunk_id: Optional[str] = None
    doc_id: Optional[str] = None
    doc_title: Optional[str] = None
    source_org: Optional[str] = None
    decision_date: Optional[str] = None
    similarity: float = 0.0
    content: Optional[str] = None
    url: Optional[str] = None


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
        
        if request.chat_type == 'general':
            initial_state = create_simple_state(user_query=request.message)
            final_state = await asyncio.to_thread(graph.invoke, initial_state)
        else:
            initial_state = create_initial_state(
                user_query=request.message,
                chat_type=request.chat_type,
                onboarding=cast(Any, request.onboarding),
            )
            config = cast(Any, {"configurable": {"thread_id": session_id}})
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
async def chat_stream(
    request: ChatRequest,
    retriever=Depends(get_retriever)
):
    """
    RAG 기반 스트리밍 챗봇 응답 생성
    """
    try:
        # chunk_types 필터 처리 (리스트의 첫 번째 값 사용)
        chunk_type_filter = request.chunk_types[0] if request.chunk_types else None

        # 유사 청크 검색
        if hasattr(retriever, 'search') and retrieval_mode == 'hybrid':
            chunks = retriever.search(
                query=request.message,
                top_k=request.top_k,
                chunk_type_filter=chunk_type_filter
            )
        else:
            chunks = retriever.vector_search(
                query=request.message,
                top_k=request.top_k,
                chunk_type_filter=chunk_type_filter
            )

        if not chunks:
            async def no_results():
                yield "죄송합니다. 관련된 분쟁조정 사례를 찾을 수 없습니다."
            return StreamingResponse(no_results(), media_type="text/plain")

        # SearchResult를 dict로 변환
        chunks_dict = [_serialize_search_result(chunk) for chunk in chunks]

        # 스트리밍 답변 생성 (동기 함수를 비동기로 실행)
        async def stream_response():
            result = await asyncio.to_thread(
                generator.generate_answer, request.message, chunks_dict
            )
            yield result['answer']

        return StreamingResponse(
            stream_response(),
            media_type="text/plain"
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"답변 생성 중 오류 발생: {str(e)}")


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


# mcp = FastMCP.from_fastapi(app)

# if __name__ == "__main__":
#     mcp.run()