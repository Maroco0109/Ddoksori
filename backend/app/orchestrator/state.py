"""
똑소리 프로젝트 - LangGraph 상태 스키마
작성일: 2026-01-14
S2-3: 멀티턴 대화를 위한 상태 정의
S2-7: ReAct 패턴 지원 필드 추가
PR-3: 메모리 관리 필드 추가 (conversation_history, compact_summary)

LangGraph StateGraph에서 사용하는 TypedDict 기반 상태 스키마.
MessagesState를 상속하여 add_messages reducer를 자동 적용.
"""

from typing import List, Dict, Optional, Annotated, Literal, Any
from typing_extensions import TypedDict
import operator

from langgraph.graph import MessagesState


# PR-4: NEED_CLARIFICATION 추가 (통합 그래프용, NEED_USER_CLARIFICATION과 동일 의미)
RoutingMode = Literal['NO_RETRIEVAL', 'NEED_RAG', 'NEED_USER_CLARIFICATION', 'NEED_CLARIFICATION']


class SlotStatus(TypedDict):
    slot_name: str
    status: Literal['filled', 'partial', 'missing']
    evidence_chunk_ids: List[str]
    confidence: float


class ClaimEvidenceMapping(TypedDict):
    claim: str
    evidence_chunk_ids: List[str]
    evidence_texts: List[str]
    grounded: bool


class OnboardingInfo(TypedDict, total=False):
    """
    온보딩 폼 데이터 (분쟁 상담용)

    프론트엔드 DisputeFormData와 매핑:
    - purchase_date: 구매일자
    - purchase_place: 구매처 (판매자 상호/브랜드)
    - purchase_platform: 구매 플랫폼 (온라인/오프라인)
    - purchase_item: 구매 품목
    - purchase_amount: 구매 금액
    - dispute_details: 분쟁 상세 내용
    """
    purchase_date: Optional[str]
    purchase_place: Optional[str]
    purchase_platform: Optional[str]
    purchase_item: Optional[str]
    purchase_amount: Optional[str]
    dispute_details: Optional[str]


class QueryAnalysisResult(TypedDict, total=False):
    """
    질의분석 에이전트 결과

    S2-5 확장: 쿼리 재생성(Query Rewriting) 필드 추가
    - rewritten_query: 정규화 + 확장된 최종 검색 쿼리
    - search_queries: Multi-Query 검색용 쿼리 리스트
    - expansion_applied: 적용된 확장 규칙 설명
    """
    query_type: Literal['dispute', 'general', 'law', 'criteria', 'system_meta', 'ambiguous']
    keywords: List[str]
    agency_hint: Optional[str]
    needs_clarification: bool
    missing_fields: List[str]
    extracted_info: Dict[str, str]
    missing_fields_description: str
    rewritten_query: str
    search_queries: List[str]
    expansion_applied: str


class RetrievalResult(TypedDict, total=False):
    """
    정보검색 에이전트 결과 (4섹션 구조)
    """
    agency: Dict
    disputes: List[Dict]
    counsels: List[Dict]
    laws: List[Dict]
    criteria: List[Dict]
    max_similarity: float
    avg_similarity: float


class ReviewResult(TypedDict, total=False):
    """
    검토 에이전트 결과

    S2-2 규칙 기반 검토 결과:
    - passed: 검토 통과 여부
    - violations: 발견된 위반 사항 (금지 표현, 출처 누락 등)
    - filtered_answer: 위반 사항 수정 후 답변 (passed=False인 경우)
    """
    passed: bool
    violations: List[str]
    filtered_answer: Optional[str]


class ReActStep(TypedDict):
    """
    ReAct 단일 스텝 기록 (S2-7)

    ReAct 패턴의 Thought-Action-Observation 사이클 단위 기록.
    react_steps 필드에 operator.add로 누적되어 전체 추론 과정을 추적.

    Attributes:
        thought: 현재 상황 분석 및 다음 행동에 대한 추론
        action: 선택된 액션 (search_all, search_criteria, ask_clarification 등)
        action_input: 액션에 전달되는 입력값
        observation: 액션 실행 결과 요약
    """
    thought: str
    action: str
    action_input: Dict[str, Any]
    observation: str


class ChatState(MessagesState):
    """
    LangGraph 오케스트레이터 상태 스키마

    MessagesState를 상속하여 messages 필드에 add_messages reducer 자동 적용.
    thread_id(=session_id)별로 상태가 checkpointer에 저장됨.

    상태 흐름:
    1. 초기화: user_query, chat_type, onboarding 설정
    2. query_analysis 노드: query_analysis 결과 저장
    3. retrieval 노드: retrieval 결과 + sources 저장
    4. generation 노드: draft_answer 저장
    5. review 노드: review 결과 저장, final_answer 확정

    Attributes:
        messages: 멀티턴 대화 히스토리 (add_messages reducer)
        chat_type: 상담 유형 ('dispute' | 'general')
        onboarding: 온보딩 폼 데이터 (분쟁 상담용)
        user_query: 현재 턴의 사용자 질문
        query_analysis: 질의분석 결과
        retrieval: 4섹션 검색 결과
        draft_answer: LLM 생성 초안
        review: 검토 결과
        final_answer: 최종 확정 답변
        sources: 인용 출처 목록 (operator.add로 누적)
        has_sufficient_evidence: 근거 충분 여부
        clarifying_questions: 추가 질문 목록 (되묻기용)
        retry_count: 재생성 횟수 (무한 루프 방지, max=2)
    """
    # 세션 메타데이터
    chat_type: Literal['dispute', 'general']
    onboarding: Optional[OnboardingInfo]

    # 현재 턴 데이터
    user_query: str

    # 에이전트 결과 (각 노드가 업데이트)
    query_analysis: Optional[QueryAnalysisResult]
    retrieval: Optional[RetrievalResult]
    draft_answer: Optional[str]
    review: Optional[ReviewResult]

    # 최종 출력
    final_answer: Optional[str]
    sources: Annotated[List[Dict], operator.add]
    has_sufficient_evidence: bool
    clarifying_questions: List[str]
    claim_evidence_map: List[ClaimEvidenceMapping]

    # 제어 플래그
    retry_count: int
    awaiting_user_choice: bool
    low_similarity_mode: bool

    # === 라우팅 및 가드레일 필드 (PR-2 통합) ===
    mode: RoutingMode
    guardrail_blocked: bool
    guardrail_type: Optional[str]

    # === ReAct 패턴 필드 (S2-7) ===
    react_steps: Annotated[List[ReActStep], operator.add]  # ReAct 히스토리 (누적)
    current_iteration: int          # 현재 ReAct 반복 횟수 (0-based)
    max_iterations: int             # 최대 반복 횟수 (기본값: 2)
    should_continue: bool           # ReAct 루프 계속 여부
    last_thought: Optional[str]     # 마지막 추론 내용
    last_action: Optional[str]      # 마지막 선택 액션
    last_observation: Optional[str] # 마지막 관찰 결과

    # 노드 타이밍 정보
    _node_timings: Optional[Dict[str, Dict]]

    # === 메모리 관리 필드 (PR-3) ===
    conversation_history: List[Dict[str, Any]]  # 대화 히스토리 [{role, content, turn}]
    compact_summary: Optional[Dict[str, Any]]   # Compact 요약 데이터
    total_turn_count: int                       # 전체 대화 턴 수 (Compact 포함)


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
        chat_type: 상담 유형
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
        messages=[],
        chat_type=chat_type,
        onboarding=onboarding,
        user_query=user_query,
        query_analysis=None,
        retrieval=None,
        draft_answer=None,
        review=None,
        final_answer=None,
        sources=[],
        has_sufficient_evidence=True,
        clarifying_questions=[],
        claim_evidence_map=[],
        retry_count=0,
        awaiting_user_choice=False,
        low_similarity_mode=False,
        mode='NEED_RAG',
        guardrail_blocked=False,
        guardrail_type=None,
        react_steps=[],
        current_iteration=0,
        max_iterations=max_iterations,
        should_continue=True,
        last_thought=None,
        last_action=None,
        last_observation=None,
        _node_timings={},
        # PR-3: 메모리 필드 초기화
        conversation_history=[],
        compact_summary=None,
        total_turn_count=0,
    )


# PR-2: 통합 상태 스키마 (ChatState 재사용)
UnifiedState = ChatState


__all__ = [
    'RoutingMode',
    'SlotStatus',
    'ClaimEvidenceMapping',
    'OnboardingInfo',
    'QueryAnalysisResult',
    'RetrievalResult',
    'ReviewResult',
    'ReActStep',
    'ChatState',
    'UnifiedState',
    'create_initial_state',
]
