"""
똑소리 프로젝트 - 로깅 핸들러 모듈

작성일: 2026-01-24
최종 수정: 2026-01-24

[역할 및 책임]
커스텀 로그 핸들러들을 정의합니다.
콘솔, 파일, JSON 등 다양한 출력 형식을 지원합니다.

[핸들러 종류]
- ConsoleHandler: 컬러 콘솔 출력
- FileHandler: 일별 로테이션 파일 출력
- JSONHandler: 구조화된 JSON 파일 출력
"""

import logging
import sys
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

from .config import (
    CONSOLE_LOG_FORMAT,
    DEFAULT_DATE_FORMAT,
    DEFAULT_LOG_FORMAT,
    get_log_level,
)

# ============================================================
# 컬러 포맷터 (콘솔 출력용)
# ============================================================


class ColoredFormatter(logging.Formatter):
    """
    로그 레벨에 따라 색상을 적용하는 포맷터입니다.

    콘솔 출력 시 가독성을 높이기 위해 사용됩니다.
    """

    # ANSI 컬러 코드
    COLORS = {
        "DEBUG": "\033[36m",  # 시안 (Cyan)
        "INFO": "\033[32m",  # 초록 (Green)
        "WARNING": "\033[33m",  # 노랑 (Yellow)
        "ERROR": "\033[31m",  # 빨강 (Red)
        "CRITICAL": "\033[35m",  # 마젠타 (Magenta)
    }
    RESET = "\033[0m"

    def __init__(self, fmt: Optional[str] = None, datefmt: Optional[str] = None):
        """
        컬러 포맷터를 초기화합니다.

        Args:
            fmt: 로그 포맷 문자열
            datefmt: 날짜 포맷 문자열
        """
        super().__init__(fmt or CONSOLE_LOG_FORMAT, datefmt or DEFAULT_DATE_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        """
        로그 레코드를 포맷팅하고 색상을 적용합니다.

        Args:
            record: 로그 레코드

        Returns:
            색상이 적용된 로그 메시지
        """
        # 원본 레벨명 저장
        original_levelname = record.levelname

        # 색상 적용
        color = self.COLORS.get(record.levelname, "")
        if color:
            record.levelname = f"{color}{record.levelname}{self.RESET}"

        # 포맷팅
        result = super().format(record)

        # 원본 레벨명 복원 (다른 핸들러에 영향 없도록)
        record.levelname = original_levelname

        return result


# ============================================================
# 핸들러 생성 함수
# ============================================================


def create_console_handler(
    level: Optional[str] = None, use_color: bool = True
) -> logging.StreamHandler:
    """
    콘솔 출력 핸들러를 생성합니다.

    Args:
        level: 로그 레벨 (None이면 기본 레벨 사용)
        use_color: 컬러 출력 사용 여부

    Returns:
        설정된 StreamHandler 인스턴스
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(getattr(logging, level or get_log_level()))

    if use_color:
        handler.setFormatter(ColoredFormatter())
    else:
        handler.setFormatter(logging.Formatter(CONSOLE_LOG_FORMAT, DEFAULT_DATE_FORMAT))

    return handler


def create_file_handler(
    log_dir: str,
    filename: str = "app.log",
    level: Optional[str] = None,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> RotatingFileHandler:
    """
    파일 출력 핸들러를 생성합니다 (크기 기반 로테이션).

    Args:
        log_dir: 로그 파일 저장 디렉토리
        filename: 로그 파일명
        level: 로그 레벨
        max_bytes: 최대 파일 크기 (바이트)
        backup_count: 백업 파일 개수

    Returns:
        설정된 RotatingFileHandler 인스턴스
    """
    # 디렉토리 생성
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    filepath = log_path / filename

    handler = RotatingFileHandler(
        filepath, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    handler.setLevel(getattr(logging, level or get_log_level()))
    handler.setFormatter(logging.Formatter(DEFAULT_LOG_FORMAT, DEFAULT_DATE_FORMAT))

    return handler


def create_daily_file_handler(
    log_dir: str,
    filename: str = "app.log",
    level: Optional[str] = None,
    backup_count: int = 30,  # 30일 보관
) -> TimedRotatingFileHandler:
    """
    일별 로테이션 파일 핸들러를 생성합니다.

    Args:
        log_dir: 로그 파일 저장 디렉토리
        filename: 로그 파일명
        level: 로그 레벨
        backup_count: 보관할 백업 파일 개수 (일 단위)

    Returns:
        설정된 TimedRotatingFileHandler 인스턴스
    """
    # 디렉토리 생성
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    filepath = log_path / filename

    handler = TimedRotatingFileHandler(
        filepath,
        when="midnight",
        interval=1,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(getattr(logging, level or get_log_level()))
    handler.setFormatter(logging.Formatter(DEFAULT_LOG_FORMAT, DEFAULT_DATE_FORMAT))

    return handler
