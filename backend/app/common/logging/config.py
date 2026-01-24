"""
똑소리 프로젝트 - 로깅 설정 모듈

작성일: 2026-01-24
최종 수정: 2026-01-24

[역할 및 책임]
애플리케이션 전역에서 사용되는 로깅 설정을 정의합니다.
로그 레벨, 포맷, 핸들러 설정 등을 중앙에서 관리합니다.

[설정 항목]
- LOG_LEVEL: 로그 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- LOG_FORMAT: 로그 메시지 포맷
- LOG_DATE_FORMAT: 타임스탬프 포맷
- RAG_LOG_ENABLED: RAG 구조화 로그 활성화 여부
- RAG_LOG_DIR: RAG 로그 저장 디렉토리
"""

import os
from enum import Enum
from typing import Optional


class LogLevel(str, Enum):
    """로그 레벨 열거형"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# ============================================================
# 기본 로깅 설정
# ============================================================

# 로그 레벨 (환경변수로 오버라이드 가능)
DEFAULT_LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# 기본 로그 포맷 (한국어 시간대 고려)
DEFAULT_LOG_FORMAT: str = (
    "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
)

# 간결한 로그 포맷 (콘솔용)
CONSOLE_LOG_FORMAT: str = (
    "%(asctime)s | %(levelname)-8s | %(message)s"
)

# JSON 로그 포맷 (구조화된 로그용)
JSON_LOG_FORMAT: str = (
    '{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
    '"logger": "%(name)s", "line": %(lineno)d, "message": "%(message)s"}'
)

# 날짜 포맷
DEFAULT_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"


# ============================================================
# RAG 로깅 설정
# ============================================================

# RAG 구조화 로그 활성화 여부
RAG_LOG_ENABLED: bool = os.getenv("RAG_LOG_ENABLED", "true").lower() == "true"

# RAG 로그 저장 디렉토리 (backend/app 기준 상대경로)
RAG_LOG_DIR: str = os.getenv("RAG_LOG_DIR", "logs/rag")


# ============================================================
# 로거별 설정
# ============================================================

# 특정 로거의 로그 레벨 오버라이드
LOGGER_LEVELS: dict[str, str] = {
    # 외부 라이브러리 로그 레벨 조정
    "httpx": "WARNING",
    "httpcore": "WARNING",
    "openai": "WARNING",
    "anthropic": "WARNING",
    "urllib3": "WARNING",
    # LangGraph/LangChain 로그 레벨
    "langchain": "WARNING",
    "langgraph": "INFO",
}


def get_log_level() -> str:
    """
    현재 로그 레벨을 반환합니다.

    환경변수 LOG_LEVEL이 설정되어 있으면 해당 값을 사용하고,
    그렇지 않으면 기본값 INFO를 반환합니다.

    Returns:
        로그 레벨 문자열 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    return os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL)


def is_rag_logging_enabled() -> bool:
    """
    RAG 구조화 로깅이 활성화되어 있는지 확인합니다.

    Returns:
        RAG 로깅 활성화 여부
    """
    return RAG_LOG_ENABLED


def get_rag_log_dir() -> str:
    """
    RAG 로그 저장 디렉토리 경로를 반환합니다.

    Returns:
        RAG 로그 디렉토리 경로
    """
    return RAG_LOG_DIR
