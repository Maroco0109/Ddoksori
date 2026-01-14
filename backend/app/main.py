import os
import time
import asyncio
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any, Generator
from dotenv import load_dotenv
# from fastmcp import FastMCP

from rag import RAGRetriever, HybridRetriever, RAGGenerator, SearchResult
from rag.specialized_retrievers import StructuredRetriever
from rag.logger import get_rag_logger
from utils.embedding_connection import get_embedding_api_url

# 환경 변수 로드
load_dotenv()

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
    top_k: Optional[int] = Field(default=5, ge=1, le=100, description="검색 결과 수")
    chunk_types: Optional[List[str]] = None
    agencies: Optional[List[str]] = None

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


class ChatResponse(BaseModel):
    answer: str
    chunks_used: int
    model: str
    sources: List[dict]
    # S1-1 Safety Guardrails
    has_sufficient_evidence: bool = True
    clarifying_questions: List[str] = []
    # 4섹션 구조화 응답
    domain: Optional[AgencyRecommendation] = None
    similar_cases: Optional[SimilarCases] = None
    related_laws: Optional[List[LawReference]] = None
    related_criteria: Optional[List[CriteriaReference]] = None


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
async def chat(
    request: ChatRequest,
    retriever=Depends(get_retriever)
):
    """
    RAG 기반 챗봇 응답 생성 (4섹션 구조화 응답)

    응답 구조:
    1. 추천 기관 (domain): KCA/ECMC/KCDRC
    2. 유사 사례 (similar_cases): disputes + counsels
    3. 관련 법령 (related_laws): 2단계 검색
    4. 관련 기준 (related_criteria): 2단계 검색
    """
    start_time = time.time()
    log_entry = rag_logger.create_entry(query=request.message)

    try:
        # StructuredRetriever를 사용하여 4개 섹션 일괄 검색
        structured_retriever = StructuredRetriever(db_config, embed_api_url)
        structured_retriever.connect()

        try:
            # 4개 섹션 데이터 일괄 검색
            search_results = structured_retriever.search_all_sections(
                query=request.message,
                dispute_k=3,
                counsel_k=3,
                law_k=3,
                criteria_k=3
            )
        finally:
            structured_retriever.close()

        # 기관 추천
        agency_info = search_results['agency']

        # 검색 결과 추출
        disputes = search_results['disputes']
        counsels = search_results['counsels']
        laws = search_results['laws']
        criteria = search_results['criteria']

        # 로깅: 4섹션 구조화 검색 결과
        total_chunks = len(disputes) + len(counsels) + len(laws) + len(criteria)
        rag_logger.log_structured_retrieval(
            entry=log_entry,
            agency_info=agency_info,
            disputes=disputes,
            counsels=counsels,
            laws=laws,
            criteria=criteria
        )

        if total_chunks == 0:
            rag_logger.log_response(
                entry=log_entry,
                answer="",
                chunks_used=0,
                sources_count=0,
                status="no_results"
            )
            rag_logger.finalize(log_entry, start_time)
            rag_logger.save(log_entry)

            return ChatResponse(
                answer="죄송합니다. 관련된 분쟁조정 사례를 찾을 수 없습니다. 다른 질문을 해주시겠어요?",
                chunks_used=0,
                model=generator.model,
                sources=[],
                domain=AgencyRecommendation(**agency_info)
            )

        # LLM으로 구조화된 답변 생성
        result = generator.generate_structured_answer(
            query=request.message,
            agency_info=agency_info,
            disputes=disputes,
            counsels=counsels,
            laws=laws,
            criteria=criteria
        )

        rag_logger.log_llm(
            entry=log_entry,
            model=result['model'],
            system_prompt=result.get('system_prompt', ''),
            user_prompt=result.get('user_prompt', ''),
            response_time_ms=result.get('response_time_ms', 0),
            prompt_tokens=result.get('prompt_tokens', 0),
            completion_tokens=result.get('completion_tokens', 0),
            has_sufficient_evidence=result.get('has_sufficient_evidence', True),
            clarifying_questions=result.get('clarifying_questions', [])
        )

        # 기존 sources 형식으로도 제공 (하위 호환성)
        sources = []
        for d in disputes:
            sources.append({
                'doc_id': d.get('doc_id'),
                'chunk_id': d.get('chunk_id'),
                'chunk_type': d.get('chunk_type'),
                'source_org': d.get('source_org'),
                'url': d.get('url'),
                'decision_date': d.get('decision_date'),
                'doc_title': d.get('doc_title'),
                'similarity': d.get('similarity', 0)
            })

        # 4섹션 구조화 응답 변환
        domain_response = AgencyRecommendation(**agency_info)

        similar_cases_response = SimilarCases(
            disputes=[CaseReference(**d) for d in disputes],
            counsels=[CaseReference(**c) for c in counsels]
        )

        laws_response = [LawReference(**l) for l in laws]
        criteria_response = [CriteriaReference(**c) for c in criteria]

        # Log response
        rag_logger.log_response(
            entry=log_entry,
            answer=result['answer'],
            chunks_used=result['chunks_used'],
            sources_count=len(sources),
            status="success"
        )

        rag_logger.finalize(log_entry, start_time)
        rag_logger.save(log_entry)

        return ChatResponse(
            answer=result['answer'],
            chunks_used=result['chunks_used'],
            model=result['model'],
            sources=sources,
            has_sufficient_evidence=result.get('has_sufficient_evidence', True),
            clarifying_questions=result.get('clarifying_questions', []),
            # 4섹션 구조화 응답
            domain=domain_response,
            similar_cases=similar_cases_response,
            related_laws=laws_response,
            related_criteria=criteria_response
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