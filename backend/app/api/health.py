"""
똑소리 프로젝트 - 헬스체크 라우터

서버 상태 확인 및 기본 정보 제공 엔드포인트입니다.
"""

import os

import httpx
from fastapi import APIRouter

from app.agents.retrieval.tools.hybrid_retriever import HybridRetriever
from app.agents.retrieval.tools.retriever import RAGRetriever

from .dependencies import get_db_config, get_retrieval_mode

router = APIRouter(tags=["Health"])


@router.get("/")
async def root():
    """
    루트 엔드포인트

    API 서버 기본 정보를 반환합니다.
    """
    retrieval_mode = get_retrieval_mode()

    return {
        "message": "똑소리 API 서버가 정상적으로 실행 중입니다.",
        "version": "0.4.1",
        "retrieval_mode": retrieval_mode,
        "features": [
            (
                "Hybrid RAG 검색 (Dense + Lexical + RRF)"
                if retrieval_mode == "hybrid"
                else "RAG 검색"
            ),
            "LLM 답변 생성",
        ],
    }


@router.get("/health")
async def health_check():
    """
    서버 상태 확인

    데이터베이스 연결 상태를 확인하고 결과를 반환합니다.

    Returns:
        status: 'healthy' 또는 'unhealthy'
        database: 연결 상태 ('connected')
        error: 오류 메시지 (unhealthy인 경우)
    """
    db_config = get_db_config()
    retrieval_mode = get_retrieval_mode()

    try:
        if retrieval_mode == "hybrid":
            checker = HybridRetriever(db_config)
        else:
            checker = RAGRetriever(db_config)

        checker.connect()
        checker.close()
        return {"status": "healthy", "database": "connected"}

    except Exception:
        # [SEC-06] 보안: 상세 에러 메시지 노출 제거
        return {"status": "unhealthy", "error": "Database connection failed"}


@router.get("/health/llm/supervisor")
async def check_supervisor_llm():
    """
    Supervisor LLM 상태 확인

    [SEC-06] 보안: 모델명, 내부 URL, 상세 에러 메시지 노출 제거
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"status": "unhealthy", "error": "API key not configured"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=5.0,
            )
            if response.status_code == 200:
                return {"status": "healthy"}
            else:
                return {"status": "unhealthy", "error": "Service unavailable"}
    except Exception:
        return {"status": "unhealthy", "error": "Service unavailable"}


@router.get("/health/llm/exaone")
async def check_exaone_llm():
    """
    EXAONE LLM 상태 확인

    [SEC-06] 보안: 내부 URL, 상세 에러 메시지 노출 제거
    """
    base_url = os.getenv("MODEL_EXAONE_BASE_URL") or os.getenv("EXAONE_RUNPOD_URL")
    if not base_url:
        return {"status": "unhealthy", "error": "Service not configured"}

    if not base_url.endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{base_url}/models", timeout=5.0)
            if response.status_code == 200:
                return {"status": "healthy"}
            else:
                return {"status": "unhealthy", "error": "Service unavailable"}
    except Exception:
        return {"status": "unhealthy", "error": "Service unavailable"}


@router.get("/health/embedding")
async def check_embedding():
    """
    임베딩 API 상태 확인

    [SEC-06] 보안: 모델명 노출 제거
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"status": "unhealthy", "error": "API key not configured"}
    return {"status": "healthy"}


__all__ = ["router"]
