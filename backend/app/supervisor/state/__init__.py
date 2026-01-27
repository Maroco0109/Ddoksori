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

from typing import List, Dict, Optional, Annotated, Literal, Any
from typing_extensions import TypedDict
import operator

from langgraph.graph import MessagesState

# === 개별 모듈에서 타입 import ===
from .session import (
    OnboardingInfo,
    ChatType,
    SessionState,
)
from .agent_results import (
    QueryAnalysisResult,
    RetrievalResult,
    IndividualRetrievalResult,
    ReviewResult,
    AgentResultsState,
)
from .output import (
    ClaimEvidenceMapping,
    OutputState,
)
from .control import (
    RoutingMode,
    ControlState,
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
    ConversationTurn,
    CompactSummary,
    MemoryState,
)
from .supervisor import (
    AgentMessage,
    SupervisorState,
)


# === SlotStatus (분쟁 슬롯 채움 상태) ===
class SlotStatus(TypedDict):
    """
    분쟁 슬롯 채움 상태

    분쟁 상담에서 필수 정보 수집 상태를 추적합니다.

    Attributes:
        slot_name: 슬롯 이름 (예: 'purchase_date', 'purchase_item')
        status: 채움 상태
            - 'filled': 완전히 채워짐
            - 'partial': 부분적으로 채워짐
            - 'missing': 누락됨
        evidence_chunk_ids: 근거 문서 ID 목록
        confidence: 추출 신뢰도 (0.0~1.0)
    """
    slot_name: str
    status: Literal['filled', 'partial', 'missing']
    evidence_chunk_ids: List[str]
    confidence: float


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
        clarifying_questions: 추가 질문 목록 (되묻기용)
        claim_evidence_map: 주장-근거 매핑

        # 제어 플래그 (ControlState)
        retry_count: 재생성 횟수 (무한 루프 방지, max=2)
        awaiting_user_choice: 사용자 선택 대기 여부
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
    chat_type: Literal['dispute', 'general']
    onboarding: Optional[OnboardingInfo]
    user_query: str

    # === 에이전트 결과 ===
    query_analysis: Optional[QueryAnalysisResult]
    retrieval: Optional[RetrievalResult]
    draft_answer: Optional[str]
    review: Optional[ReviewResult]

    # === 최종 출력 ===
    final_answer: Optional[str]
    sources: Annotated[List[Dict], operator.add]
    has_sufficient_evidence: bool
    clarifying_questions: List[str]
    claim_evidence_map: List[ClaimEvidenceMapping]

    # === 제어 플래그 ===
    retry_count: int
    awaiting_user_choice: bool
    low_similarity_mode: bool
    mode: RoutingMode
    guardrail_blocked: bool
    guardrail_type: Optional[str]

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
    individual_retrieval_results: Annotated[List[IndividualRetrievalResult], operator.add]

    # === 노드 타이밍 ===
    _node_timings: Optional[Dict[str, Dict]]

    # === 메모리 관리 ===
    conversation_history: List[Dict[str, Any]]
    compact_summary: Optional[Dict[str, Any]]
    total_turn_count: int


def create_initial_state(
    user_query: str,
    chat_type: Literal['dispute', 'general'] = 'general',
    onboarding: Optional[OnboardingInfo] = None,
    max_iterations: Optional[int] = None,
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
        max_iterations = 1 if chat_type == 'general' else 2

    return ChatState(
        # 세션 메타데이터
        messages=[],
        chat_type=chat_type,
        onboarding=onboarding,
        user_query=user_query,

        # 에이전트 결과
        query_analysis=None,
        retrieval=None,
        draft_answer=None,
        review=None,

        # 최종 출력
        final_answer=None,
        sources=[],
        has_sufficient_evidence=True,
        clarifying_questions=[],
        claim_evidence_map=[],

        # 제어 플래그
        retry_count=0,
        awaiting_user_choice=False,
        low_similarity_mode=False,
        mode='NEED_RAG',
        guardrail_blocked=False,
        guardrail_type=None,

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

        # 노드 타이밍
        _node_timings={},

        # 메모리 관리
        conversation_history=[],
        compact_summary=None,
        total_turn_count=0,
    )


# 통합 상태 스키마 (ChatState 별칭)
UnifiedState = ChatState


# === 모든 public 심볼 export ===
__all__ = [
    # 세션
    'OnboardingInfo',
    'ChatType',
    'SessionState',

    # 에이전트 결과
    'QueryAnalysisResult',
    'RetrievalResult',
    'IndividualRetrievalResult',
    'ReviewResult',
    'AgentResultsState',

    # 출력
    'ClaimEvidenceMapping',
    'OutputState',

    # 제어
    'RoutingMode',
    'ControlState',

    # ReAct
    'ReActStep',
    'ReActState',

    # 메모리
    'ConversationTurn',
    'CompactSummary',
    'MemoryState',

    # 슈퍼바이저
    'AgentMessage',
    'SupervisorState',

    # 기타
    'SlotStatus',

    # 통합 상태
    'ChatState',
    'UnifiedState',
    'create_initial_state',
]
