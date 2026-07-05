"""
똑소리 프로젝트 - 헬스체크 라우터

서버 상태 확인 및 기본 정보 제공 엔드포인트입니다.
"""

import logging
import os
import time

import httpx
from fastapi import APIRouter

from app.agents.retrieval.tools.hybrid_retriever import HybridRetriever
from app.agents.retrieval.tools.retriever import RAGRetriever
from app.common.config import get_config

from .dependencies import get_db_config, get_retrieval_mode

logger = logging.getLogger(__name__)

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

    except Exception as e:
        logger.error(f"[Health] DB 연결 실패: {e}")
        return {"status": "unhealthy", "error": "서비스 연결 실패"}


@router.get("/health/llm/supervisor")
async def check_supervisor_llm():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"status": "unhealthy", "error": "LLM 서비스 설정 오류"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=5.0,
            )
            if response.status_code == 200:
                model_name = get_config().models.supervisor
                return {"status": "healthy", "model": f"{model_name} (OpenAI API)"}
            else:
                logger.error(f"[Health] OpenAI API 응답 오류: {response.status_code}")
                return {
                    "status": "unhealthy",
                    "error": "LLM 서비스 응답 오류",
                }
    except Exception as e:
        logger.error(f"[Health] OpenAI API 연결 실패: {e}")
        return {"status": "unhealthy", "error": "LLM 서비스 연결 실패"}


@router.get("/health/llm/exaone")
async def check_exaone_llm():
    # M2-1 canonical: 활성 ExaoneLLMClient 경로가 EXAONE_RUNPOD_URL을 사용하므로 우선한다.
    # MODEL_EXAONE_BASE_URL(MAS/candidate)은 fallback으로만 둔다.
    base_url = os.getenv("EXAONE_RUNPOD_URL") or os.getenv("MODEL_EXAONE_BASE_URL")
    if not base_url:
        return {
            "status": "unhealthy",
            "provider": "runpod_vllm",
            "error_type": "not_configured",
            "error": "LLM 서비스 설정 오류",
        }

    if not base_url.endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"

    try:
        async with httpx.AsyncClient() as client:
            start = time.perf_counter()
            response = await client.get(f"{base_url}/models", timeout=5.0)
            latency_ms = round((time.perf_counter() - start) * 1000, 1)
            if response.status_code == 200:
                model = None
                try:
                    data = response.json().get("data", [])
                    if data:
                        model = data[0].get("id")
                except ValueError:
                    pass
                return {
                    "status": "healthy",
                    "provider": "runpod_vllm",
                    "url": base_url,
                    "model": model,
                    "latency_ms": latency_ms,
                    "http_status": response.status_code,
                }
            else:
                logger.error(f"[Health] vLLM 응답 오류: {response.status_code}")
                return {
                    "status": "unhealthy",
                    "provider": "runpod_vllm",
                    "url": base_url,
                    "http_status": response.status_code,
                    "latency_ms": latency_ms,
                    "error_type": "bad_response",
                    "error": "LLM 서비스 응답 오류",
                }
    except httpx.TimeoutException as e:
        logger.error(f"[Health] vLLM 타임아웃: {e}")
        return {
            "status": "unhealthy",
            "provider": "runpod_vllm",
            "url": base_url,
            "error_type": "timeout",
            "error": "LLM 서비스 연결 실패",
        }
    except Exception as e:
        logger.error(f"[Health] vLLM 연결 실패: {e}")
        return {
            "status": "unhealthy",
            "provider": "runpod_vllm",
            "url": base_url,
            "error_type": "connection_error",
            "error": "LLM 서비스 연결 실패",
        }


@router.get("/health/embedding")
async def check_embedding():
    """OpenAI 임베딩 API 상태 확인"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"status": "unhealthy", "error": "LLM 서비스 설정 오류"}
    return {
        "status": "healthy",
        "type": "OpenAI Embedding",
        "model": "text-embedding-3-large",
    }


__all__ = ["router"]
