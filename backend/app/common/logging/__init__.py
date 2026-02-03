"""
똑소리 프로젝트 - 통합 로깅 모듈

작성일: 2026-01-24
최종 수정: 2026-01-24

[역할 및 책임]
애플리케이션 전역에서 사용되는 로깅 시스템을 통합 관리합니다.
표준 Python 로거와 RAG 구조화 로거를 모두 제공합니다.

[사용 예시]
    # 표준 로거 사용
    from app.common.logging import get_logger

    logger = get_logger(__name__)
    logger.info("작업을 시작합니다")
    logger.error("오류가 발생했습니다", exc_info=True)

    # RAG 구조화 로거 사용
    from app.common.logging import get_rag_logger

    rag_logger = get_rag_logger()
    entry = rag_logger.create_entry(query="환불 문의")
    # ... 파이프라인 실행 ...
    rag_logger.save(entry)

[모듈 구성]
- config.py: 로깅 설정 (레벨, 포맷)
- handlers.py: 핸들러 (콘솔, 파일)
- rag_logger.py: RAG 파이프라인 전용 구조화 로거
"""

import logging
from typing import Optional

from .config import (
    DEFAULT_DATE_FORMAT,  # noqa: F401 - re-exported
    DEFAULT_LOG_FORMAT,  # noqa: F401 - re-exported
    LOGGER_LEVELS,
    LogLevel,
    get_log_level,
    get_rag_log_dir,  # noqa: F401 - re-exported
    is_rag_logging_enabled,
)
from .handlers import (
    ColoredFormatter,
    create_console_handler,
    create_daily_file_handler,
    create_file_handler,
)
from .rag_logger import (
    ChunkLog,
    InputLog,
    LLMLog,
    NodeTimingLog,
    RAGLogEntry,
    RAGLogger,
    ResponseSummary,
    RetrievalLog,
    StructuredRetrievalLog,
    get_rag_logger,
)

# ============================================================
# 로깅 시스템 초기화 상태
# ============================================================

_logging_initialized: bool = False


def setup_logging(
    level: Optional[str] = None,
    use_color: bool = True,
    log_to_file: bool = False,
    log_dir: Optional[str] = None,
) -> None:
    """
    로깅 시스템을 초기화합니다.

    애플리케이션 시작 시 한 번 호출해야 합니다.
    이미 초기화된 경우 다시 초기화하지 않습니다.

    Args:
        level: 로그 레벨 (None이면 환경변수 또는 기본값 사용)
        use_color: 콘솔 출력에 컬러 사용 여부
        log_to_file: 파일 출력 활성화 여부
        log_dir: 로그 파일 저장 디렉토리

    Example:
        # 기본 설정으로 초기화
        setup_logging()

        # 디버그 레벨로 파일 출력 포함하여 초기화
        setup_logging(level="DEBUG", log_to_file=True, log_dir="logs")
    """
    global _logging_initialized

    if _logging_initialized:
        return

    # 루트 로거 설정
    root_logger = logging.getLogger()
    log_level = level or get_log_level()
    root_logger.setLevel(getattr(logging, log_level))

    # 기존 핸들러 제거 (중복 방지)
    root_logger.handlers.clear()

    # 콘솔 핸들러 추가
    console_handler = create_console_handler(level=log_level, use_color=use_color)
    root_logger.addHandler(console_handler)

    # 파일 핸들러 추가 (옵션)
    if log_to_file and log_dir:
        file_handler = create_daily_file_handler(log_dir=log_dir, level=log_level)
        root_logger.addHandler(file_handler)

    # 특정 로거 레벨 오버라이드
    for logger_name, logger_level in LOGGER_LEVELS.items():
        logging.getLogger(logger_name).setLevel(getattr(logging, logger_level))

    _logging_initialized = True


def get_logger(name: str) -> logging.Logger:
    """
    명명된 로거를 반환합니다.

    로깅 시스템이 초기화되지 않은 경우 기본 설정으로 자동 초기화됩니다.

    Args:
        name: 로거 이름 (일반적으로 __name__ 사용)

    Returns:
        설정된 Logger 인스턴스

    Example:
        from app.common.logging import get_logger

        logger = get_logger(__name__)
        logger.info("처리를 시작합니다")
        logger.debug("상세 정보: %s", data)
        logger.error("오류 발생", exc_info=True)
    """
    # 자동 초기화 (아직 초기화되지 않은 경우)
    if not _logging_initialized:
        setup_logging()

    return logging.getLogger(name)


# ============================================================
# 편의 함수
# ============================================================


def log_debug(message: str, *args, **kwargs) -> None:
    """디버그 레벨 로그를 기록합니다."""
    get_logger("app").debug(message, *args, **kwargs)


def log_info(message: str, *args, **kwargs) -> None:
    """정보 레벨 로그를 기록합니다."""
    get_logger("app").info(message, *args, **kwargs)


def log_warning(message: str, *args, **kwargs) -> None:
    """경고 레벨 로그를 기록합니다."""
    get_logger("app").warning(message, *args, **kwargs)


def log_error(message: str, *args, **kwargs) -> None:
    """오류 레벨 로그를 기록합니다."""
    get_logger("app").error(message, *args, **kwargs)


def log_critical(message: str, *args, **kwargs) -> None:
    """치명적 오류 레벨 로그를 기록합니다."""
    get_logger("app").critical(message, *args, **kwargs)


# ============================================================
# 공개 API
# ============================================================

__all__ = [
    # 로거 생성
    "get_logger",
    "get_rag_logger",
    "setup_logging",
    # 설정
    "LogLevel",
    "get_log_level",
    "is_rag_logging_enabled",
    # 핸들러
    "create_console_handler",
    "create_file_handler",
    "create_daily_file_handler",
    "ColoredFormatter",
    # RAG 로거 클래스
    "RAGLogger",
    "RAGLogEntry",
    "ChunkLog",
    "RetrievalLog",
    "LLMLog",
    "ResponseSummary",
    "StructuredRetrievalLog",
    "NodeTimingLog",
    "InputLog",
    # 편의 함수
    "log_debug",
    "log_info",
    "log_warning",
    "log_error",
    "log_critical",
]
