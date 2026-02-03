"""
똑소리 프로젝트 - API 의존성

FastAPI Dependency Injection을 위한 공통 의존성을 정의합니다.
"""

import os
from typing import Any, Dict, Generator

from app.agents.retrieval.tools.hybrid_retriever import HybridRetriever
from app.agents.retrieval.tools.retriever import RAGRetriever


def get_db_config() -> Dict[str, Any]:
    """
    데이터베이스 연결 설정 반환

    환경변수에서 DB 연결 정보를 로드합니다.
    """
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "database": os.getenv("DB_NAME", "ddoksori"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "postgres"),
        "client_encoding": "UTF8",  # 한국어 텍스트를 위한 UTF-8 인코딩
    }


def get_retrieval_mode() -> str:
    """검색 모드 반환 ('hybrid' 또는 'dense')"""
    return os.getenv("RETRIEVAL_MODE", "dense")


def get_retriever() -> Generator[Any, None, None]:
    """
    Retriever 인스턴스를 생성하고 연결을 관리하는 Dependency

    요청마다 독립적인 DB 연결을 보장합니다.
    요청 완료 후 연결이 자동으로 닫힙니다.

    Yields:
        HybridRetriever 또는 RAGRetriever 인스턴스
    """
    db_config = get_db_config()
    retrieval_mode = get_retrieval_mode()

    if retrieval_mode == "hybrid":
        retriever_instance = HybridRetriever(db_config)
    else:
        retriever_instance = RAGRetriever(db_config)

    try:
        retriever_instance.connect()
        yield retriever_instance
    finally:
        retriever_instance.close()


__all__ = [
    "get_db_config",
    "get_retrieval_mode",
    "get_retriever",
]
