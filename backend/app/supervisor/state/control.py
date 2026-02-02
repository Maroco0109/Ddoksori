"""
똑소리 프로젝트 - 제어 상태 스키마

그래프 실행 흐름을 제어하는 플래그와 라우팅 정보를 관리합니다.
"""

from typing import Any, Dict, Literal, Optional

from typing_extensions import TypedDict

# 라우팅 모드 타입 정의
# - NO_RETRIEVAL: 검색 불필요 (인사, 시스템 질문 등)
# - NEED_RAG: RAG 파이프라인 필요 → Full Pipeline
# - CACHED_RAG: 후속 턴 → 캐시된 Retrieval 사용
# - RESTRICTED_DOMAIN: 전문기관 도메인 (금융, 의료, 개인정보, 부동산, 건설)
RoutingMode = Literal[
    "NO_RETRIEVAL",
    "NEED_RAG",
    "CACHED_RAG",
    "RESTRICTED_DOMAIN",
    "META_CONVERSATIONAL",
    "FOLLOWUP_WITH_CONTEXT",
]


class TraceEntry(TypedDict):
    """
    단일 노드 실행 트레이스 엔트리.

    MAS 파이프라인의 각 노드 실행 시 생성되며,
    _agent_trace_entries 리스트에 append-only로 축적됩니다.
    순서는 timestamp 기준으로 summary 빌드 시 결정됩니다.

    Attributes:
        node_name: 그래프 노드 이름 (예: 'supervisor', 'retrieval_law')
        timestamp: Unix epoch 시작 시각
        duration_ms: 실행 시간 (밀리초)
        protocol_summary: 노드별 축약된 프로토콜 요약 (선택)
        metadata: 추가 컨텍스트 (예: error, cache_hit 등, 선택)
    """

    node_name: str
    timestamp: float
    duration_ms: float
    protocol_summary: Optional[Dict[str, Any]]
    metadata: Optional[Dict[str, Any]]


class ControlState(TypedDict, total=False):
    """
    제어 플래그 상태

    그래프 실행 흐름과 조건부 라우팅을 제어합니다.

    Attributes:
        retry_count: 재생성 횟수
            - 검토 실패 시 답변 재생성 카운트
            - max=2 (무한 루프 방지)

        low_similarity_mode: 저유사도 모드
            - True: 검색 결과 유사도가 threshold 미만
            - 규칙 기반 폴백 활성화

        mode: 라우팅 모드
            - 질의분석 후 결정되는 처리 경로
            - NO_RETRIEVAL: Fast Path (검색 생략)
            - NEED_RAG: 일반 RAG 파이프라인

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

        query_complexity: Adaptive RAG 복잡도 분류
            - 'simple': 단순 키워드 질문
            - 'moderate': 일반적 분쟁 상담
            - 'complex': 복잡한 상황 설명

    Example:
        >>> state: ControlState = {
        ...     'retry_count': 0,
        ...     'mode': 'NEED_RAG',
        ...     'guardrail_blocked': False
        ... }
    """

    retry_count: int
    low_similarity_mode: bool
    mode: RoutingMode
    guardrail_blocked: bool
    guardrail_type: Optional[str]
    _node_timings: Dict[str, Dict]
    query_complexity: Optional[str]


__all__ = [
    "RoutingMode",
    "TraceEntry",
    "ControlState",
]
