"""
똑소리 프로젝트 - 로거 호환성 모듈

[주의]
이 파일은 하위 호환성을 위해 유지됩니다.
새 코드에서는 app.common.logging 모듈을 직접 사용하세요.

권장 사용법:
    from app.common.logging import get_logger, get_rag_logger

기존 코드 호환:
    from app.common.logger import get_rag_logger  # 계속 동작함
"""

# 새 로깅 모듈에서 모든 것을 re-export
from app.common.logging import (
    # 표준 로거
    get_logger,
    setup_logging,

    # RAG 로거
    RAGLogger,
    get_rag_logger,
    RAGLogEntry,

    # 데이터 클래스
    ChunkLog,
    RetrievalLog,
    LLMLog,
    ResponseSummary,
    StructuredRetrievalLog,
    NodeTimingLog,
    InputLog,
)

# 기존에 직접 정의되어 있던 클래스들도 호환성을 위해 export
# (이미 logging 모듈에서 import한 것과 동일)
from app.common.logging.rag_logger import (
    DomainLog,
    DisputeLog,
    CounselLog,
    LawLog,
    CriteriaLog,
)

__all__ = [
    # 표준 로거
    "get_logger",
    "setup_logging",

    # RAG 로거
    "RAGLogger",
    "get_rag_logger",
    "RAGLogEntry",

    # 검색 관련 데이터 클래스
    "ChunkLog",
    "RetrievalLog",

    # LLM 관련 데이터 클래스
    "LLMLog",
    "ResponseSummary",

    # 4섹션 구조화 검색 데이터 클래스
    "DomainLog",
    "DisputeLog",
    "CounselLog",
    "LawLog",
    "CriteriaLog",
    "StructuredRetrievalLog",

    # 노드 타이밍
    "NodeTimingLog",
    "InputLog",
]
