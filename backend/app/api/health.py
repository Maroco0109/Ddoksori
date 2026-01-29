"""
똑소리 프로젝트 - 헬스체크 라우터

서버 상태 확인 및 기본 정보 제공 엔드포인트입니다.
"""

import os
import httpx
from fastapi import APIRouter

from app.agents.retrieval.tools.retriever import RAGRetriever
from app.agents.retrieval.tools.hybrid_retriever import HybridRetriever
from app.common.config import get_config
from .dependencies import get_db_config, get_embed_api_url, get_retrieval_mode


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
            "Hybrid RAG 검색 (Dense + Lexical + RRF)" if retrieval_mode == 'hybrid' else "RAG 검색",
            "LLM 답변 생성"
        ]
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
    embed_api_url = get_embed_api_url()
    retrieval_mode = get_retrieval_mode()

    try:
        if retrieval_mode == 'hybrid':
            checker = HybridRetriever(db_config, embed_api_url)
        else:
            checker = RAGRetriever(db_config, embed_api_url)

        checker.connect()
        checker.close()
        return {"status": "healthy", "database": "connected"}

    except Exception as e:
        # Windows CP949/EUC-KR 로케일 이슈를 위한 안전한 문자열 변환
        try:
            error_msg = str(e)
        except UnicodeDecodeError:
            error_msg = repr(e)
        return {"status": "unhealthy", "error": error_msg}


@router.get("/health/llm/supervisor")
async def check_supervisor_llm():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"status": "unhealthy", "error": "OPENAI_API_KEY not found"}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=5.0
            )
            if response.status_code == 200:
                model_name = get_config().models.supervisor
                return {"status": "healthy", "model": f"{model_name} (OpenAI API)"}
            else:
                return {"status": "unhealthy", "error": f"OpenAI API returned {response.status_code}"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@router.get("/health/llm/exaone")
async def check_exaone_llm():
    base_url = os.getenv("MODEL_EXAONE_BASE_URL") or os.getenv("EXAONE_RUNPOD_URL")
    if not base_url:
        return {"status": "unhealthy", "error": "EXAONE URL not configured"}
    
    if not base_url.endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{base_url}/models", timeout=5.0)
            if response.status_code == 200:
                return {"status": "healthy", "url": base_url}
            else:
                return {"status": "unhealthy", "error": f"vLLM returned {response.status_code}"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@router.get("/health/embedding")
async def check_embedding():
    use_openai = os.getenv("USE_OPENAI_EMBEDDING", "false").lower() == "true"
    
    if use_openai:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return {"status": "unhealthy", "error": "OPENAI_API_KEY not found"}
        return {"status": "healthy", "type": "OpenAI Embedding"}
    else:
        embed_url = get_embed_api_url()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(embed_url, timeout=5.0)
                if response.status_code in [200, 404, 405]:
                    return {"status": "healthy", "url": embed_url}
                else:
                    return {"status": "unhealthy", "error": f"Embedding server returned {response.status_code}"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}



__all__ = ['router']
