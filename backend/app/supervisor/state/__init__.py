"""
똑소리 프로젝트 - LangGraph 상태 스키마 통합 모듈

이 모듈은 분리된 상태 정의를 통합하여 ChatState를 제공합니다.
하위 호환성을 유지하면서 구조화된 상태 관리를 지원합니다.

모듈 구조:
- session.py: 세션 메타데이터 (OnboardingInfo, SessionState)
- agent_results.py: 에이전트 결과 (QueryAnalysisResult, RetrievalResult, ReviewResult)
- output.py: 최종 출력 (ClaimEvidenceMapping, OutputState)
- control.py: 제어 플래그 (RoutingMode, ControlState)
- supervisor.py: MAS Supervisor 상태 (SupervisorState, AgentMessage)
- memory.py: 메모리 관리 (MemoryState)

사용법:
    # 통합 ChatState 사용 (권장)
    from app.supervisor.state import ChatState, create_initial_state

    # 개별 상태 타입 사용
    from app.supervisor.state import QueryAnalysisResult, RetrievalResult

    # SupervisorState 사용
    from app.supervisor.state import SupervisorState, AgentMessage
"""

import operator
from typing import Annotated, Any, Dict, List, Literal, Optional

from langgraph.graph import MessagesState
from typing_extensions import TypedDict

from .agent_results import (  # v2 타입
    AgentResultsState,
    CitedCase,
    IndividualRetrievalResult,
    QueryAnalysisResult,
    RetrievalResult,
    RetryContext,
    ReviewResult,
    ViolationV2,
)
from .control import (
    ControlState,
    RoutingMode,
    TraceEntry,
)
from .output import (
    ClaimEvidenceMapping,
    OutputState,
    ResponseDepth,
)

# === 개별 모듈에서 타입 import ===
from .session import (
    ChatType,
    OnboardingInfo,
    SessionState,
)


# =============================================================================
# [DEPRECATED] ReAct 패턴 - MAS Supervisor로 대체됨 (Phase 7)
# 하위 호환성을 위해 stub 정의만 유지. 실제 구현은 _archive/로 이동됨.
# =============================================================================
class ReActStep(TypedDict):
    """[DEPRECATED] ReAct pattern removed in Phase 7. Use MAS Supervisor instead."""

    thought: str
    action: str
    action_input: Dict[str, Any]
    observation: str


class ReActState(TypedDict, total=False):
    """[DEPRECATED] ReAct pattern removed in Phase 7. Use SupervisorState instead."""

    react_steps: List[ReActStep]
    current_iteration: int
    max_iterations: int
    should_continue: bool
    last_thought: Optional[str]
    last_action: Optional[str]
    last_observation: Optional[str]


from .memory import (
    CompactSummary,
    ConversationTurn,
    MemoryState,
    RAGConversationMemory,
    RAGTurn,
)
from .supervisor import (
    AgentMessage,
    SupervisorState,
)


def _merge_dicts(existing: Optional[Dict], new: Optional[Dict]) -> Dict:
    """Dict-merge reducer for _node_timings (병렬 노드 타이밍 병합)."""
    if existing is None:
        return new or {}
    if new is None:
        return existing
    return {**existing, **new}


# === 통합 ChatState ===
class ChatState(MessagesState):
    """
    LangGraph 오케스트레이터 통합 상태 스키마

    MessagesState를 상속하여 messages 필드에 add_messages reducer 자동 적용.
    thread_id(=session_id)별로 상태가 checkpointer에 저장됨.

    이 클래스는 다음 상태들을 통합합니다:
    - SessionState: 세션 메타데이터
    - AgentResultsState: 에이전트 실행 결과
    - OutputState: 최종 출력
    - ControlState: 제어 플래그
    - ReActState: ReAct 패턴
    - MemoryState: 메모리 관리

    상태 흐름:
    1. 초기화: user_query, chat_type, onboarding 설정
    2. query_analysis 노드: query_analysis 결과 저장
    3. retrieval 노드: retrieval 결과 + sources 저장
    4. generation 노드: draft_answer 저장
    5. review 노드: review 결과 저장, final_answer 확정

    Attributes:
        # 세션 메타데이터 (SessionState)
        messages: 멀티턴 대화 히스토리 (add_messages reducer)
        chat_type: 상담 유형 ('dispute' | 'general')
        onboarding: 온보딩 폼 데이터 (분쟁 상담용)
        user_query: 현재 턴의 사용자 질문

        # 에이전트 결과 (AgentResultsState)
        query_analysis: 질의분석 결과
        retrieval: 4섹션 검색 결과
        draft_answer: LLM 생성 초안
        review: 검토 결과

        # 최종 출력 (OutputState)
        final_answer: 최종 확정 답변
        sources: 인용 출처 목록 (operator.add로 누적)
        has_sufficient_evidence: 근거 충분 여부
        claim_evidence_map: 주장-근거 매핑

        # 제어 플래그 (ControlState)
        retry_count: 재생성 횟수 (무한 루프 방지, max=2)
        low_similarity_mode: 저유사도 모드 여부
        mode: 라우팅 모드 (NO_RETRIEVAL, NEED_RAG, NEED_CLARIFICATION)
        guardrail_blocked: 가드레일 차단 여부
        guardrail_type: 차단 유형

        # ReAct 패턴 (ReActState)
        react_steps: ReAct 히스토리 (누적)
        current_iteration: 현재 ReAct 반복 횟수 (0-based)
        max_iterations: 최대 반복 횟수
        should_continue: ReAct 루프 계속 여부
        last_thought: 마지막 추론 내용
        last_action: 마지막 선택 액션
        last_observation: 마지막 관찰 결과

        # 메모리 관리 (MemoryState)
        conversation_history: 대화 히스토리
        compact_summary: Compact 요약 데이터
        total_turn_count: 전체 대화 턴 수

        # 노드 타이밍
        _node_timings: 노드별 실행 시간 기록
    """

    # === 세션 메타데이터 ===
    chat_type: Literal["dispute", "general"]
    onboarding: Optional[OnboardingInfo]
    user_query: str
    session_id: Optional[str]  # 세션 ID (캐시 키로 사용)

    # === 에이전트 결과 ===
    query_analysis: Optional[QueryAnalysisResult]
    retrieval: Optional[RetrievalResult]
    draft_answer: Optional[str]
    review: Optional[ReviewResult]

    # === 최종 출력 ===
    final_answer: Optional[str]
    sources: Annotated[List[Dict], operator.add]
    has_sufficient_evidence: bool
    retrieval_confidence: float  # 검색 결과 충분성 점수 (0.0~1.0)
    claim_evidence_map: List[ClaimEvidenceMapping]
    response_depth: ResponseDepth  # Progressive Disclosure 응답 깊이
    available_details: Optional[Dict]  # 아직 제공하지 않은 상세 정보 메타데이터

    # === 제어 플래그 ===
    retry_count: int
    low_similarity_mode: bool
    mode: RoutingMode
    guardrail_blocked: bool
    guardrail_type: Optional[str]
    # 슈퍼바이저 라우팅 방식: "deterministic"(A, 기본) | "llm"(A-hub, M8 측정)
    routing_mode: str

    # === ReAct 패턴 ===
    react_steps: Annotated[List[ReActStep], operator.add]
    current_iteration: int
    max_iterations: int
    should_continue: bool
    last_thought: Optional[str]
    last_action: Optional[str]
    last_observation: Optional[str]

    # === Supervisor (Phase 5: MAS) ===
    supervisor: Optional[SupervisorState]

    # === 개별 Retrieval 결과 (Phase 5: MAS) ===
    # 4개 Retrieval Agent가 병렬로 실행되어 각각의 결과를 저장
    # operator.add로 누적되어 retrieval_merge_node에서 병합됨
    individual_retrieval_results: Annotated[
        List[IndividualRetrievalResult], operator.add
    ]

    # === MAS v2 추가 필드 ===
    retry_context: Optional[RetryContext]  # 재생성 컨텍스트
    cited_cases: List[CitedCase]  # 인용된 사례 정보
    expanded_queries: List[str]  # LLM 기반 확장 쿼리 리스트

    # === 노드 타이밍 ===
    _node_timings: Annotated[Dict[str, Dict], _merge_dicts]

    # === 에이전트 트레이스 (append-only, 병렬 fan-out 호환) ===
    _agent_trace_entries: Annotated[List[TraceEntry], operator.add]

    # === 메모리 관리 ===
    conversation_history: List[Dict[str, Any]]
    compact_summary: Optional[Dict[str, Any]]
    total_turn_count: int

    # === RAG 대화 메모리 (PR-B: 선별 히스토리) ===
    rag_conversation_memory: Optional[List[Dict[str, Any]]]

    # === Phase D: 이전 턴 컨텍스트 (FOLLOWUP_WITH_CONTEXT용) ===
    _last_turn_context: Optional[Dict[str, Any]]

    # === 후속 질문 ===
    followup_questions: List[str]

    # === 분쟁 슬롯 (온보딩 영속화용) ===
    dispute_slots: Dict[str, Optional[str]]
    conversation_phase: str


def create_initial_state(
    user_query: str,
    chat_type: Literal["dispute", "general"] = "general",
    onboarding: Optional[OnboardingInfo] = None,
    max_iterations: Optional[int] = None,
    routing_mode: str = "deterministic",
) -> ChatState:
    """
    초기 ChatState 생성 헬퍼 함수

    Args:
        user_query: 사용자 질문
        chat_type: 상담 유형 ('dispute' | 'general')
        onboarding: 온보딩 데이터 (분쟁 상담용)
        max_iterations: ReAct 최대 반복 횟수 (None이면 chat_type에 따라 자동 설정)

    Returns:
        초기화된 ChatState

    Example:
        >>> state = create_initial_state(
        ...     user_query="헬스장 환불 규정 알려줘",
        ...     chat_type='dispute',
        ...     onboarding={'purchase_item': '헬스장 회원권'}
        ... )
    """
    # chat_type에 따른 max_iterations 기본값 설정
    if max_iterations is None:
        max_iterations = 1 if chat_type == "general" else 2

    return ChatState(
        # 세션 메타데이터
        messages=[],
        chat_type=chat_type,
        onboarding=onboarding,
        user_query=user_query,
        session_id=None,
        # 에이전트 결과
        query_analysis=None,
        retrieval=None,
        draft_answer=None,
        review=None,
        # 최종 출력
        final_answer=None,
        sources=[],
        has_sufficient_evidence=True,
        retrieval_confidence=0.0,
        claim_evidence_map=[],
        response_depth="full",
        available_details=None,
        # 제어 플래그
        retry_count=0,
        low_similarity_mode=False,
        mode="NEED_RAG",
        guardrail_blocked=False,
        guardrail_type=None,
        routing_mode=routing_mode,
        # ReAct 패턴
        react_steps=[],
        current_iteration=0,
        max_iterations=max_iterations,
        should_continue=True,
        last_thought=None,
        last_action=None,
        last_observation=None,
        # === Supervisor (Phase 5: MAS) ===
        supervisor=None,
        # === 개별 Retrieval 결과 (Phase 5: MAS) ===
        individual_retrieval_results=[],
        # === MAS v2 추가 필드 ===
        retry_context=None,
        cited_cases=[],
        expanded_queries=[],
        # 노드 타이밍
        _node_timings={},
        # 에이전트 트레이스
        _agent_trace_entries=[],
        # 메모리 관리
        conversation_history=[],
        compact_summary=None,
        total_turn_count=0,
        # RAG 대화 메모리
        rag_conversation_memory=[],
        # Phase D: 이전 턴 컨텍스트
        _last_turn_context=None,
        # 후속 질문
        followup_questions=[],
        # 분쟁 슬롯
        dispute_slots={},
        conversation_phase="initial",
    )


# 통합 상태 스키마 (ChatState 별칭)
UnifiedState = ChatState


# === 모든 public 심볼 export ===
__all__ = [
    # 세션
    "OnboardingInfo",
    "ChatType",
    "SessionState",
    # 에이전트 결과
    "QueryAnalysisResult",
    "RetrievalResult",
    "IndividualRetrievalResult",
    "ReviewResult",
    "AgentResultsState",
    # v2 타입
    "CitedCase",
    "ViolationV2",
    "RetryContext",
    # 출력
    "ClaimEvidenceMapping",
    "ResponseDepth",
    "OutputState",
    # 제어
    "RoutingMode",
    "TraceEntry",
    "ControlState",
    # ReAct
    "ReActStep",
    "ReActState",
    # 메모리
    "ConversationTurn",
    "CompactSummary",
    "MemoryState",
    "RAGConversationMemory",
    "RAGTurn",
    # 슈퍼바이저
    "AgentMessage",
    "SupervisorState",
    # 통합 상태
    "ChatState",
    "UnifiedState",
    "create_initial_state",
]
