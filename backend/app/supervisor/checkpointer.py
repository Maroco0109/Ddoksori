"""
똑소리 프로젝트 - LangGraph Checkpointer 팩토리
작성일: 2026-01-14
S2-3: 세션 상태 저장을 위한 Checkpointer 관리

Checkpointer는 LangGraph에서 thread_id별 상태를 저장/복원하는 역할.
- InMemory: 개발/테스트용 (서버 재시작 시 상태 소실)
- Postgres: 프로덕션용 (PR3에서 구현 예정)

환경변수:
    CHECKPOINTER_MODE: 'memory' (기본) | 'postgres'
"""

import os
from typing import Literal, Optional

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

# 지원하는 Checkpointer 모드
CheckpointerMode = Literal["memory", "postgres"]

# 기본 모드
DEFAULT_MODE: CheckpointerMode = "memory"


def get_checkpointer_mode() -> CheckpointerMode:
    """
    환경변수에서 Checkpointer 모드 읽기

    Returns:
        'memory' 또는 'postgres'

    Raises:
        ValueError: 지원하지 않는 모드인 경우
    """
    mode = os.getenv("CHECKPOINTER_MODE", DEFAULT_MODE).lower()

    if mode not in ("memory", "postgres"):
        raise ValueError(
            f"지원하지 않는 CHECKPOINTER_MODE: '{mode}'. "
            f"'memory' 또는 'postgres'를 사용하세요."
        )

    return mode  # type: ignore


def get_checkpointer(mode: Optional[CheckpointerMode] = None) -> BaseCheckpointSaver:
    """
    Checkpointer 인스턴스 생성 팩토리

    Args:
        mode: 'memory' | 'postgres' | None (환경변수에서 읽음)

    Returns:
        BaseCheckpointSaver 구현체
        - 'memory': MemorySaver (인메모리, 재시작 시 소실)
        - 'postgres': PostgresSaver (PR3에서 구현 예정)

    Raises:
        NotImplementedError: 'postgres' 모드는 PR3에서 구현 예정
        ValueError: 지원하지 않는 모드인 경우

    Example:
        >>> # 환경변수 기반
        >>> checkpointer = get_checkpointer()

        >>> # 명시적 지정
        >>> checkpointer = get_checkpointer('memory')

        >>> # 그래프 컴파일에 사용
        >>> graph = builder.compile(checkpointer=checkpointer)

    Note:
        - InMemory는 서버 재시작 시 모든 세션 상태가 소실됨
        - 프로덕션 배포 전 반드시 Postgres로 전환 필요 (PR3)
        - LangGraph는 thread_id를 키로 상태를 저장/조회함
    """
    if mode is None:
        mode = get_checkpointer_mode()

    if mode == "memory":
        return _create_memory_checkpointer()

    if mode == "postgres":
        return _create_postgres_checkpointer()

    # 타입 체크를 위한 방어 코드 (실행되지 않아야 함)
    raise ValueError(f"지원하지 않는 모드: {mode}")


def _create_memory_checkpointer() -> MemorySaver:
    """
    InMemory Checkpointer 생성

    개발/테스트용. 서버 재시작 시 상태 소실.

    Returns:
        MemorySaver 인스턴스
    """
    return MemorySaver()


def _create_postgres_checkpointer() -> BaseCheckpointSaver:
    """
    PostgreSQL Checkpointer 생성 (PR3에서 구현 예정)

    프로덕션용. 영구 저장.

    Required packages (PR3):
        pip install langgraph-checkpoint-postgres psycopg[pool]

    환경변수 (PR3):
        DATABASE_URL: PostgreSQL 연결 문자열
        또는 DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

    Raises:
        NotImplementedError: PR3에서 구현 예정

    Note:
        PR3 구현 시 다음 사항 반영:
        - AsyncPostgresSaver 사용 (FastAPI async 호환)
        - ConnectionPool 사용 (프로덕션 권장)
        - autocommit=True, row_factory=dict_row 필수
        - checkpointer.setup() 호출 (테이블 자동 생성)
    """
    raise NotImplementedError(
        "PostgreSQL Checkpointer는 PR3에서 구현 예정입니다.\n"
        "현재는 CHECKPOINTER_MODE=memory를 사용하세요.\n\n"
        "PR3 구현 시 필요 패키지:\n"
        "  pip install langgraph-checkpoint-postgres psycopg[pool]\n\n"
        "참고: https://github.com/langchain-ai/langgraph/tree/main/libs/checkpoint-postgres"
    )
