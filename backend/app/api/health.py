"""
똑소리 프로젝트 - 헬스체크 라우터

서버 상태 확인 및 기본 정보 제공 엔드포인트입니다.
"""

import os
from fastapi import APIRouter

from app.agents.retrieval.tools.retriever import RAGRetriever
from app.agents.retrieval.tools.hybrid_retriever import HybridRetriever
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


__all__ = ['router']
