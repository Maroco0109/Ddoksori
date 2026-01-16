"""
똑소리 프로젝트 - LangGraph 상태 스키마
작성일: 2026-01-14
S2-3: 멀티턴 대화를 위한 상태 정의

LangGraph StateGraph에서 사용하는 TypedDict 기반 상태 스키마.
MessagesState를 상속하여 add_messages reducer를 자동 적용.
"""

from typing import TypedDict, List, Dict, Optional, Annotated, Literal
import operator

# LangGraph imports
from langgraph.graph import MessagesState


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
    """
    query_type: Literal['dispute', 'general', 'law', 'criteria']
    keywords: List[str]
    agency_hint: Optional[str]
    needs_clarification: bool
    missing_fields: List[str]
    extracted_info: Dict[str, str]
    missing_fields_description: str


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
    sources: Annotated[List[Dict], operator.add]  # 출처 누적
    has_sufficient_evidence: bool
    clarifying_questions: List[str]
    
    # 제어 플래그
    retry_count: int
    awaiting_user_choice: bool
    low_similarity_mode: bool
    
    # 노드 타이밍 정보
    _node_timings: Optional[Dict[str, Dict]]


def create_initial_state(
    user_query: str,
    chat_type: Literal['dispute', 'general'] = 'general',
    onboarding: Optional[OnboardingInfo] = None,
) -> ChatState:
    """
    초기 ChatState 생성 헬퍼 함수
    
    Args:
        user_query: 사용자 질문
        chat_type: 상담 유형
        onboarding: 온보딩 데이터 (분쟁 상담용)
        
    Returns:
        초기화된 ChatState
        
    Example:
        >>> state = create_initial_state(
        ...     user_query="헬스장 환불 규정 알려줘",
        ...     chat_type='dispute',
        ...     onboarding={'purchase_item': '헬스장 회원권'}
        ... )
    """
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
        retry_count=0,
        awaiting_user_choice=False,
        low_similarity_mode=False,
        _node_timings={},
    )
