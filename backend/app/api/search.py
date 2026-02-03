"""
똑소리 프로젝트 - 검색 라우터

Vector DB 검색 엔드포인트입니다.
LLM 답변 생성 없이 검색만 수행합니다.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from app.agents.retrieval.tools.retriever import SearchResult
from app.middleware.rate_limiter import RateLimits, limiter

from .dependencies import get_retrieval_mode, get_retriever
from .models import SearchRequest

router = APIRouter(tags=["Search"])


def _serialize_search_result(chunk: SearchResult) -> Dict[str, Any]:
    """
    SearchResult 객체를 dict로 변환

    S1-1 citation metadata를 포함합니다.
    """
    return {
        "chunk_id": chunk.chunk_id,
        "doc_id": chunk.doc_id,
        "chunk_type": chunk.chunk_type,
        "content": chunk.content,
        "doc_title": chunk.doc_title,
        "doc_type": chunk.doc_type,
        "category_path": chunk.category_path,
        "similarity": chunk.similarity,
        # S1-1 Citation Metadata
        "source_org": chunk.source_org,
        "url": chunk.url,
        "decision_date": chunk.decision_date,
        "collected_at": chunk.collected_at,
    }


@router.post("/search")
@limiter.limit(RateLimits.SEARCH)
async def search(
    http_request: Request, request: SearchRequest, retriever=Depends(get_retriever)
):
    """
    Vector DB에서 유사한 사례 검색

    LLM 답변 생성 없이 검색만 수행합니다.
    Hybrid 모드에서는 RRF 기반 fusion 검색을 사용합니다.

    Args:
        request: 검색 요청 (쿼리, top_k 등)
        retriever: Retriever 인스턴스 (DI)

    Returns:
        query: 검색 쿼리
        results_count: 결과 개수
        results: 검색 결과 리스트
    """
    retrieval_mode = get_retrieval_mode()

    try:
        # chunk_types 필터 처리 (리스트의 첫 번째 값 사용)
        chunk_type_filter = request.chunk_types[0] if request.chunk_types else None

        # Hybrid search (RRF fusion) or vector-only
        if hasattr(retriever, "search") and retrieval_mode == "hybrid":
            chunks = retriever.search(
                query=request.query,
                top_k=request.top_k,
                chunk_type_filter=chunk_type_filter,
            )
        else:
            chunks = retriever.vector_search(
                query=request.query,
                top_k=request.top_k,
                chunk_type_filter=chunk_type_filter,
            )

        # SearchResult 객체를 dict로 변환
        results = [_serialize_search_result(chunk) for chunk in chunks]

        return {
            "query": request.query,
            "results_count": len(results),
            "results": results,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 중 오류 발생: {str(e)}")


__all__ = ["router"]
