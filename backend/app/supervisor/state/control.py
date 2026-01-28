"""
똑소리 프로젝트 - 제어 상태 스키마

그래프 실행 흐름을 제어하는 플래그와 라우팅 정보를 관리합니다.
"""

from typing import Optional, Literal, Dict
from typing_extensions import TypedDict


# 라우팅 모드 타입 정의
# - NO_RETRIEVAL: 검색 불필요 (인사, 시스템 질문 등)
# - NEED_RAG: RAG 파이프라인 필요
# - NEED_USER_CLARIFICATION: 사용자 추가 정보 필요
# - NEED_CLARIFICATION: NEED_USER_CLARIFICATION과 동일 (통합 그래프용)
# - RESTRICTED_DOMAIN: 전문기관 도메인 (금융, 의료, 개인정보, 부동산, 건설)
RoutingMode = Literal[
    'NO_RETRIEVAL',
    'NEED_RAG',
    'NEED_USER_CLARIFICATION',
    'NEED_CLARIFICATION',
    'RESTRICTED_DOMAIN',
]


class ControlState(TypedDict, total=False):
    """
    제어 플래그 상태

    그래프 실행 흐름과 조건부 라우팅을 제어합니다.

    Attributes:
        retry_count: 재생성 횟수
            - 검토 실패 시 답변 재생성 카운트
            - max=2 (무한 루프 방지)

        awaiting_user_choice: 사용자 선택 대기 중
            - True: 사용자 입력 필요 (되묻기 상태)
            - 다음 입력 시 선택으로 처리

        low_similarity_mode: 저유사도 모드
            - True: 검색 결과 유사도가 threshold 미만
            - 규칙 기반 폴백 또는 되묻기 활성화

        mode: 라우팅 모드
            - 질의분석 후 결정되는 처리 경로
            - NO_RETRIEVAL: Fast Path (검색 생략)
            - NEED_RAG: 일반 RAG 파이프라인
            - NEED_CLARIFICATION: 되묻기 필요

        guardrail_blocked: 가드레일 차단 여부
            - True: 모더레이션에서 차단됨
            - 안전 메시지로 대체 응답

        guardrail_type: 차단 유형
            - 'profanity': 욕설/비속어
            - 'harmful': 유해 콘텐츠
            - 'off_topic': 주제 이탈
            - None: 차단 없음

        _node_timings: 노드별 실행 시간 기록
            - 디버깅 및 성능 모니터링용
            - 키: 노드명, 값: {start, end, duration_ms}

    Example:
        >>> state: ControlState = {
        ...     'retry_count': 0,
        ...     'mode': 'NEED_RAG',
        ...     'guardrail_blocked': False
        ... }
    """
    retry_count: int
    awaiting_user_choice: bool
    low_similarity_mode: bool
    mode: RoutingMode
    guardrail_blocked: bool
    guardrail_type: Optional[str]
    _node_timings: Optional[Dict[str, Dict]]


__all__ = [
    'RoutingMode',
    'ControlState',
]
