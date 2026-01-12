import os
import time
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Generator
from dotenv import load_dotenv
# from fastmcp import FastMCP

from rag import RAGRetriever, HybridRetriever, RAGGenerator, SearchResult
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
cors_origins = os.getenv('CORS_ORIGINS', 'http://localhost:5173').split(',')
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
    'password': os.getenv('DB_PASSWORD', 'postgres')
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
    message: str
    top_k: Optional[int] = 5
    chunk_types: Optional[List[str]] = None
    agencies: Optional[List[str]] = None


class ChatResponse(BaseModel):
    answer: str
    chunks_used: int
    model: str
    sources: List[dict]
    # S1-1 Safety Guardrails
    has_sufficient_evidence: bool = True
    clarifying_questions: List[str] = []


class SearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = 5
    chunk_types: Optional[List[str]] = None
    agencies: Optional[List[str]] = None


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
        return {"status": "unhealthy", "error": str(e)}


@app.post("/search")
async def search(
    request: SearchRequest,
    retriever=Depends(get_retriever)
):
    """
    Vector DB에서 유사한 사례 검색 (LLM 답변 생성 없이 검색만)
    """
    try:
        # Hybrid search (RRF fusion) or vector-only
        if hasattr(retriever, 'search') and retrieval_mode == 'hybrid':
            chunks = retriever.search(
                query=request.query,
                top_k=request.top_k
            )
        else:
            chunks = retriever.vector_search(
                query=request.query,
                top_k=request.top_k
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
    RAG 기반 챗봇 응답 생성
    """
    start_time = time.time()
    log_entry = rag_logger.create_entry(query=request.message)

    try:
        # 1. 유사 청크 검색 (instrumented)
        if retrieval_mode == 'hybrid' and hasattr(retriever, 'search_instrumented'):
            search_result = retriever.search_instrumented(
                query=request.message,
                top_k=request.top_k
            )
            chunks = search_result['results']
            chunks_dict = [_serialize_search_result(c) for c in chunks]

            rag_logger.log_retrieval(
                entry=log_entry,
                mode='hybrid',
                top_k=request.top_k,
                embedding_time_ms=search_result['embedding_time_ms'],
                search_time_ms=search_result['search_time_ms'],
                chunks=chunks_dict,
                dense_candidates=search_result.get('dense_candidates', 0),
                lexical_candidates=search_result.get('lexical_candidates', 0)
            )
        elif hasattr(retriever, 'vector_search_instrumented'):
            search_result = retriever.vector_search_instrumented(
                query=request.message,
                top_k=request.top_k
            )
            chunks = search_result['results']
            chunks_dict = [_serialize_search_result(c) for c in chunks]

            rag_logger.log_retrieval(
                entry=log_entry,
                mode='dense',
                top_k=request.top_k,
                embedding_time_ms=search_result['embedding_time_ms'],
                search_time_ms=search_result['search_time_ms'],
                chunks=chunks_dict
            )
        else:
            # Fallback to non-instrumented
            if hasattr(retriever, 'search') and retrieval_mode == 'hybrid':
                chunks = retriever.search(
                    query=request.message,
                    top_k=request.top_k
                )
            else:
                chunks = retriever.vector_search(
                    query=request.message,
                    top_k=request.top_k
                )
            chunks_dict = [_serialize_search_result(c) for c in chunks]
            rag_logger.log_retrieval(
                entry=log_entry,
                mode=retrieval_mode,
                top_k=request.top_k,
                embedding_time_ms=0,
                search_time_ms=0,
                chunks=chunks_dict
            )

        if not chunks:
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
                sources=[]
            )

        # 2. LLM으로 답변 생성 (instrumented)
        if hasattr(generator, 'generate_answer_instrumented'):
            result = generator.generate_answer_instrumented(
                query=request.message,
                chunks=chunks_dict
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
        else:
            result = generator.generate_answer(
                query=request.message,
                chunks=chunks_dict
            )
            rag_logger.log_llm(
                entry=log_entry,
                model=result['model'],
                system_prompt='',
                user_prompt='',
                response_time_ms=0
            )

        # 3. 응답 포맷팅 (S1-1 correct field mapping)
        sources = [
            {
                'doc_id': chunk.doc_id,
                'chunk_id': chunk.chunk_id,
                'chunk_type': chunk.chunk_type,
                'source_org': chunk.source_org,
                'url': chunk.url,
                'decision_date': chunk.decision_date,
                'collected_at': chunk.collected_at,
                'doc_title': chunk.doc_title,
                'similarity': chunk.similarity
            }
            for chunk in chunks
        ]

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
            clarifying_questions=result.get('clarifying_questions', [])
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
        # 유사 청크 검색
        if hasattr(retriever, 'search') and retrieval_mode == 'hybrid':
            chunks = retriever.search(
                query=request.message,
                top_k=request.top_k
            )
        else:
            chunks = retriever.vector_search(
                query=request.message,
                top_k=request.top_k
            )

        if not chunks:
            async def no_results():
                yield "죄송합니다. 관련된 분쟁조정 사례를 찾을 수 없습니다."
            return StreamingResponse(no_results(), media_type="text/plain")

        # SearchResult를 dict로 변환
        chunks_dict = [_serialize_search_result(chunk) for chunk in chunks]

        # 스트리밍 답변 생성
        async def stream_response():
            result = generator.generate_answer(request.message, chunks_dict)
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