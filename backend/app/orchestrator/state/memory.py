"""
똑소리 프로젝트 - 메모리 관리 상태 스키마

장기 대화를 위한 메모리 관리 상태를 정의합니다.
대화 히스토리 압축 및 요약 기능을 지원합니다.
"""

from typing import List, Dict, Optional, Any
from typing_extensions import TypedDict


class ConversationTurn(TypedDict, total=False):
    """
    대화 턴 기록

    단일 대화 턴(사용자 입력 + 시스템 응답)을 기록합니다.

    Attributes:
        role: 발화자 역할
            - 'user': 사용자 메시지
            - 'assistant': 시스템 응답

        content: 메시지 내용

        turn: 턴 번호 (1-based)
            - Compact 요약 후에도 유지

        timestamp: 메시지 시간 (ISO 8601)
            - 선택적, 로깅용

    Example:
        >>> turn: ConversationTurn = {
        ...     'role': 'user',
        ...     'content': '헬스장 환불 규정이 어떻게 되나요?',
        ...     'turn': 1
        ... }
    """
    role: str
    content: str
    turn: int
    timestamp: Optional[str]


class CompactSummary(TypedDict, total=False):
    """
    대화 압축 요약

    긴 대화를 요약하여 토큰 사용량을 줄입니다.
    압축된 턴 수와 핵심 내용을 보존합니다.

    Attributes:
        summary: 요약된 대화 내용
            - 핵심 정보만 추출
            - 다음 응답 생성에 컨텍스트로 사용

        turns_compacted: 압축된 턴 수
            - 예: 10턴이 요약되면 10

        created_at: 요약 생성 시간 (ISO 8601)

        key_facts: 추출된 핵심 사실 목록
            - 구매 정보, 분쟁 내용 등
            - 선택적, 구조화된 정보 보존용

    Example:
        >>> summary: CompactSummary = {
        ...     'summary': '사용자는 헬스장 3개월 회원권 환불 문의...',
        ...     'turns_compacted': 5,
        ...     'key_facts': ['품목: 헬스장 회원권', '금액: 50만원']
        ... }
    """
    summary: str
    turns_compacted: int
    created_at: Optional[str]
    key_facts: Optional[List[str]]


class MemoryState(TypedDict, total=False):
    """
    메모리 관리 상태

    장기 대화를 위한 히스토리 관리 상태입니다.

    Attributes:
        conversation_history: 대화 히스토리
            - 최근 N턴의 전체 대화 기록
            - 각 항목은 {role, content, turn} 형태

        compact_summary: Compact 요약 데이터
            - 오래된 턴이 압축된 요약
            - None이면 압축된 내용 없음

        total_turn_count: 전체 대화 턴 수
            - Compact로 압축된 턴 포함
            - 실제 히스토리 길이보다 클 수 있음

    Note:
        메모리 관리 정책:
        - 기본: 최근 10턴 유지
        - 초과 시: 오래된 턴 compact_summary로 압축
        - LLM 컨텍스트: compact_summary + 최근 턴

    Example:
        >>> state: MemoryState = {
        ...     'conversation_history': [
        ...         {'role': 'user', 'content': '...', 'turn': 6},
        ...         {'role': 'assistant', 'content': '...', 'turn': 6}
        ...     ],
        ...     'compact_summary': {
        ...         'summary': '이전 5턴 요약...',
        ...         'turns_compacted': 5
        ...     },
        ...     'total_turn_count': 6
        ... }
    """
    conversation_history: List[Dict[str, Any]]
    compact_summary: Optional[Dict[str, Any]]
    total_turn_count: int


__all__ = [
    'ConversationTurn',
    'CompactSummary',
    'MemoryState',
]
