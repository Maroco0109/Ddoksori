"""
똑소리 프로젝트 - 에이전트 프로토콜 정의

작성일: 2026-01-24
최종 수정: 2026-01-24

[역할 및 책임]
각 에이전트가 준수해야 하는 입출력 인터페이스를 Protocol로 정의합니다.
LangGraph 노드로 등록되기 전에 타입 검증을 수행할 수 있습니다.

[에이전트 목록]
1. QueryAnalysisAgent: 사용자 쿼리 분석 및 의도 파악
2. RetrievalAgent: 벡터 DB에서 관련 문서 검색
3. AnswerGenerationAgent: LLM을 활용한 답변 생성
4. LegalReviewAgent: 생성된 답변의 법률적 검토

[사용 예시]
    from app.agents.protocols import QueryAnalysisProtocol

    class MyQueryAnalyzer(QueryAnalysisProtocol):
        def analyze(self, input: QueryAnalysisInput) -> QueryAnalysisOutput:
            # 구현...
            pass

[주의사항]
- Protocol은 구조적 서브타이핑을 사용합니다 (duck typing)
- 명시적 상속 없이도 메서드 시그니처가 일치하면 프로토콜을 만족합니다
"""

from typing import Protocol, List, Dict, Optional, Literal, Any, runtime_checkable
from typing_extensions import TypedDict


# ============================================================
# 공통 타입 정의
# ============================================================

class OnboardingInfo(TypedDict, total=False):
    """
    온보딩 폼 데이터.

    분쟁 상담 시 프론트엔드에서 수집한 사용자 정보입니다.

    Attributes:
        purchase_date: 구매일자 (YYYY-MM-DD)
        purchase_place: 구매처 (판매자 상호/브랜드)
        purchase_platform: 구매 플랫폼 (온라인/오프라인)
        purchase_item: 구매 품목
        purchase_amount: 구매 금액
        dispute_details: 분쟁 상세 내용
    """
    purchase_date: Optional[str]
    purchase_place: Optional[str]
    purchase_platform: Optional[str]
    purchase_item: Optional[str]
    purchase_amount: Optional[str]
    dispute_details: Optional[str]


# 라우팅 모드 타입
RoutingMode = Literal['NO_RETRIEVAL', 'NEED_RAG', 'NEED_USER_CLARIFICATION', 'NEED_CLARIFICATION']

# 쿼리 타입
QueryType = Literal['dispute', 'general', 'law', 'criteria', 'system_meta', 'ambiguous']

# 채팅 타입
ChatType = Literal['dispute', 'general']


# ============================================================
# 질의분석 에이전트 (Query Analysis Agent)
# ============================================================

class QueryAnalysisInput(TypedDict):
    """
    질의분석 노드 입력.

    사용자의 원본 쿼리와 컨텍스트 정보를 포함합니다.

    Attributes:
        user_query: 사용자가 입력한 원본 질문
        chat_type: 채팅 유형 ('dispute' | 'general')
        onboarding: 온보딩 폼 데이터 (분쟁 상담 시)
    """
    user_query: str
    chat_type: ChatType
    onboarding: Optional[OnboardingInfo]


class QueryAnalysisResult(TypedDict, total=False):
    """
    질의분석 결과 상세.

    쿼리 분석 후 추출된 정보와 재작성된 쿼리를 포함합니다.

    Attributes:
        query_type: 쿼리 유형 (dispute, general, law, criteria, system_meta, ambiguous)
        keywords: 추출된 키워드 목록
        agency_hint: 담당 기관 힌트 (KCA, ECMC, KCDRC)
        needs_clarification: 추가 정보 필요 여부
        missing_fields: 누락된 필드 목록
        missing_fields_description: 누락 필드 설명 (사용자 안내용)
        extracted_info: 추출된 정보 (품목, 금액 등)
        rewritten_query: 정규화/확장된 검색 쿼리
        search_queries: 다중 쿼리 검색용 쿼리 리스트
        expansion_applied: 적용된 확장 규칙 설명
    """
    query_type: QueryType
    keywords: List[str]
    agency_hint: Optional[str]
    needs_clarification: bool
    missing_fields: List[str]
    missing_fields_description: str
    extracted_info: Dict[str, str]
    rewritten_query: str
    search_queries: List[str]
    expansion_applied: str


class QueryAnalysisOutput(TypedDict):
    """
    질의분석 노드 출력.

    분석 결과와 다음 노드 라우팅 정보를 포함합니다.

    Attributes:
        query_analysis: 분석 결과 상세
        mode: 라우팅 모드 (NO_RETRIEVAL, NEED_RAG, NEED_USER_CLARIFICATION 등)
    """
    query_analysis: QueryAnalysisResult
    mode: RoutingMode


@runtime_checkable
class QueryAnalysisProtocol(Protocol):
    """
    질의분석 에이전트 프로토콜.

    사용자 쿼리를 분석하여 의도, 키워드, 필요한 정보를 추출합니다.
    """

    def analyze(self, input_data: QueryAnalysisInput) -> QueryAnalysisOutput:
        """
        사용자 쿼리를 분석합니다.

        Args:
            input_data: 분석할 입력 데이터

        Returns:
            분석 결과 및 라우팅 정보
        """
        ...


# ============================================================
# 정보검색 에이전트 (Retrieval Agent)
# ============================================================

class RetrievalInput(TypedDict):
    """
    정보검색 노드 입력.

    검색에 필요한 쿼리와 분석 결과를 포함합니다.

    Attributes:
        user_query: 원본 사용자 쿼리
        query_analysis: 질의분석 결과
        onboarding: 온보딩 폼 데이터
        top_k: 검색 결과 개수 (기본값: 5)
    """
    user_query: str
    query_analysis: QueryAnalysisResult
    onboarding: Optional[OnboardingInfo]
    top_k: int


class AgencyInfo(TypedDict, total=False):
    """
    기관 추천 정보.

    분쟁 유형에 따른 담당 기관 정보입니다.

    Attributes:
        agency: 추천 기관 (KCA, ECMC, KCDRC)
        dispute_type: 분쟁 유형 (1:N, 1:1, contents)
        reason: 추천 사유
        confidence: 신뢰도 점수 (0.0~1.0)
        matched_keywords: 매칭된 키워드
    """
    agency: str
    dispute_type: str
    reason: str
    confidence: float
    matched_keywords: List[str]


class RetrievalResult(TypedDict, total=False):
    """
    검색 결과 상세.

    4섹션(기관, 분쟁조정, 상담, 법령, 기준) 검색 결과입니다.

    Attributes:
        agency: 기관 추천 정보
        disputes: 분쟁조정 사례 목록
        counsels: 상담 사례 목록
        laws: 관련 법령 목록
        criteria: 분쟁해결기준 목록
        max_similarity: 최대 유사도 점수
        avg_similarity: 평균 유사도 점수
    """
    agency: AgencyInfo
    disputes: List[Dict[str, Any]]
    counsels: List[Dict[str, Any]]
    laws: List[Dict[str, Any]]
    criteria: List[Dict[str, Any]]
    max_similarity: float
    avg_similarity: float


class RetrievalOutput(TypedDict):
    """
    정보검색 노드 출력.

    검색 결과와 출처 목록을 포함합니다.

    Attributes:
        retrieval: 4섹션 검색 결과
        sources: 인용 출처 목록 (프론트엔드 표시용)
    """
    retrieval: RetrievalResult
    sources: List[Dict[str, Any]]


@runtime_checkable
class RetrievalProtocol(Protocol):
    """
    정보검색 에이전트 프로토콜.

    벡터 DB에서 관련 문서를 검색하여 4섹션 구조로 반환합니다.
    """

    def retrieve(self, input_data: RetrievalInput) -> RetrievalOutput:
        """
        관련 문서를 검색합니다.

        Args:
            input_data: 검색 입력 데이터

        Returns:
            검색 결과 및 출처 목록
        """
        ...


# ============================================================
# 답변생성 에이전트 (Answer Generation Agent)
# ============================================================

class GenerationInput(TypedDict):
    """
    답변생성 노드 입력.

    답변 생성에 필요한 쿼리, 검색 결과, 분석 결과를 포함합니다.

    Attributes:
        user_query: 원본 사용자 쿼리
        retrieval: 검색 결과
        query_analysis: 질의분석 결과
        onboarding: 온보딩 폼 데이터
        chat_type: 채팅 유형
    """
    user_query: str
    retrieval: RetrievalResult
    query_analysis: QueryAnalysisResult
    onboarding: Optional[OnboardingInfo]
    chat_type: ChatType


class ClaimEvidenceMapping(TypedDict):
    """
    주장-근거 매핑.

    생성된 답변의 각 주장에 대한 근거 정보입니다.

    Attributes:
        claim: 답변에 포함된 주장
        evidence_chunk_ids: 근거 청크 ID 목록
        evidence_texts: 근거 텍스트 목록
        grounded: 근거 충분 여부
    """
    claim: str
    evidence_chunk_ids: List[str]
    evidence_texts: List[str]
    grounded: bool


class GenerationOutput(TypedDict):
    """
    답변생성 노드 출력.

    생성된 답변과 관련 메타데이터를 포함합니다.

    Attributes:
        draft_answer: LLM이 생성한 초안 답변
        has_sufficient_evidence: 근거 충분 여부
        clarifying_questions: 추가 질문 목록 (근거 부족 시)
        claim_evidence_map: 주장-근거 매핑 목록
    """
    draft_answer: str
    has_sufficient_evidence: bool
    clarifying_questions: List[str]
    claim_evidence_map: List[ClaimEvidenceMapping]


@runtime_checkable
class GenerationProtocol(Protocol):
    """
    답변생성 에이전트 프로토콜.

    검색 결과를 기반으로 LLM을 활용하여 답변을 생성합니다.
    """

    def generate(self, input_data: GenerationInput) -> GenerationOutput:
        """
        답변을 생성합니다.

        Args:
            input_data: 생성 입력 데이터

        Returns:
            생성된 답변 및 메타데이터
        """
        ...


# ============================================================
# 법률검토 에이전트 (Legal Review Agent)
# ============================================================

class ReviewInput(TypedDict):
    """
    법률검토 노드 입력.

    검토할 답변과 관련 정보를 포함합니다.

    Attributes:
        draft_answer: 검토할 초안 답변
        retrieval: 검색 결과 (출처 검증용)
        sources: 인용 출처 목록
        claim_evidence_map: 주장-근거 매핑 (할루시네이션 검증용)
    """
    draft_answer: str
    retrieval: RetrievalResult
    sources: List[Dict[str, Any]]
    claim_evidence_map: List[ClaimEvidenceMapping]


class ReviewResult(TypedDict, total=False):
    """
    검토 결과 상세.

    검토 통과 여부와 발견된 위반 사항을 포함합니다.

    Attributes:
        passed: 검토 통과 여부
        violations: 발견된 위반 사항 목록
        filtered_answer: 위반 사항 수정 후 답변 (passed=False 시)
    """
    passed: bool
    violations: List[str]
    filtered_answer: Optional[str]


class ReviewOutput(TypedDict):
    """
    법률검토 노드 출력.

    검토 결과와 최종 답변을 포함합니다.

    Attributes:
        review: 검토 결과 상세
        final_answer: 최종 확정 답변 (검토 통과 또는 수정 완료)
        retry_count: 재검토 횟수 (무한 루프 방지)
    """
    review: ReviewResult
    final_answer: Optional[str]
    retry_count: int


@runtime_checkable
class ReviewProtocol(Protocol):
    """
    법률검토 에이전트 프로토콜.

    생성된 답변의 법률적 정확성과 금지 표현을 검토합니다.
    """

    def review(self, input_data: ReviewInput) -> ReviewOutput:
        """
        답변을 검토합니다.

        Args:
            input_data: 검토 입력 데이터

        Returns:
            검토 결과 및 최종 답변
        """
        ...


# ============================================================
# ReAct 패턴 관련 타입
# ============================================================

class ReActStep(TypedDict):
    """
    ReAct 단일 스텝 기록.

    Thought-Action-Observation 사이클의 단위 기록입니다.

    Attributes:
        thought: 현재 상황 분석 및 추론
        action: 선택된 액션 (search_all, search_criteria, ask_clarification 등)
        action_input: 액션에 전달되는 입력값
        observation: 액션 실행 결과 요약
    """
    thought: str
    action: str
    action_input: Dict[str, Any]
    observation: str


class ReActInput(TypedDict):
    """
    ReAct 노드 입력.

    ReAct 패턴 실행에 필요한 상태 정보를 포함합니다.

    Attributes:
        user_query: 사용자 쿼리
        query_analysis: 질의분석 결과
        retrieval: 현재까지의 검색 결과 (있는 경우)
        react_steps: 이전 ReAct 스텝 기록
        current_iteration: 현재 반복 횟수
        max_iterations: 최대 반복 횟수
    """
    user_query: str
    query_analysis: QueryAnalysisResult
    retrieval: Optional[RetrievalResult]
    react_steps: List[ReActStep]
    current_iteration: int
    max_iterations: int


class ReActOutput(TypedDict):
    """
    ReAct 노드 출력.

    ReAct 실행 결과와 다음 단계 정보를 포함합니다.

    Attributes:
        react_steps: 업데이트된 ReAct 스텝 기록
        should_continue: 추가 반복 필요 여부
        current_iteration: 현재 반복 횟수
        last_thought: 마지막 추론 내용
        last_action: 마지막 실행 액션
        last_observation: 마지막 관찰 결과
        retrieval: 업데이트된 검색 결과 (검색 액션 실행 시)
    """
    react_steps: List[ReActStep]
    should_continue: bool
    current_iteration: int
    last_thought: Optional[str]
    last_action: Optional[str]
    last_observation: Optional[str]
    retrieval: Optional[RetrievalResult]


@runtime_checkable
class ReActProtocol(Protocol):
    """
    ReAct 에이전트 프로토콜.

    Thought-Action-Observation 패턴으로 반복적 추론을 수행합니다.
    """

    def think(self, input_data: ReActInput) -> Dict[str, Any]:
        """
        현재 상태를 분석하고 다음 액션을 결정합니다.

        Args:
            input_data: ReAct 입력 데이터

        Returns:
            추론 결과 (thought, action, action_input)
        """
        ...

    def act(self, action: str, action_input: Dict[str, Any]) -> str:
        """
        선택된 액션을 실행하고 결과를 반환합니다.

        Args:
            action: 실행할 액션 이름
            action_input: 액션 입력값

        Returns:
            액션 실행 결과 (observation)
        """
        ...


# ============================================================
# 타입 검증 유틸리티
# ============================================================

def validate_query_analysis_output(output: Dict[str, Any]) -> bool:
    """
    질의분석 출력이 프로토콜을 만족하는지 검증합니다.

    Args:
        output: 검증할 출력 딕셔너리

    Returns:
        유효성 검증 결과
    """
    required_keys = {'query_analysis', 'mode'}
    return required_keys.issubset(output.keys())


def validate_retrieval_output(output: Dict[str, Any]) -> bool:
    """
    검색 출력이 프로토콜을 만족하는지 검증합니다.

    Args:
        output: 검증할 출력 딕셔너리

    Returns:
        유효성 검증 결과
    """
    required_keys = {'retrieval', 'sources'}
    return required_keys.issubset(output.keys())


def validate_generation_output(output: Dict[str, Any]) -> bool:
    """
    답변생성 출력이 프로토콜을 만족하는지 검증합니다.

    Args:
        output: 검증할 출력 딕셔너리

    Returns:
        유효성 검증 결과
    """
    required_keys = {'draft_answer', 'has_sufficient_evidence', 'clarifying_questions', 'claim_evidence_map'}
    return required_keys.issubset(output.keys())


def validate_review_output(output: Dict[str, Any]) -> bool:
    """
    검토 출력이 프로토콜을 만족하는지 검증합니다.

    Args:
        output: 검증할 출력 딕셔너리

    Returns:
        유효성 검증 결과
    """
    required_keys = {'review', 'final_answer', 'retry_count'}
    return required_keys.issubset(output.keys())


# ============================================================
# 모듈 공개 API
# ============================================================

__all__ = [
    # 공통 타입
    'OnboardingInfo',
    'RoutingMode',
    'QueryType',
    'ChatType',

    # 질의분석 에이전트
    'QueryAnalysisInput',
    'QueryAnalysisResult',
    'QueryAnalysisOutput',
    'QueryAnalysisProtocol',

    # 정보검색 에이전트
    'RetrievalInput',
    'AgencyInfo',
    'RetrievalResult',
    'RetrievalOutput',
    'RetrievalProtocol',

    # 답변생성 에이전트
    'GenerationInput',
    'ClaimEvidenceMapping',
    'GenerationOutput',
    'GenerationProtocol',

    # 법률검토 에이전트
    'ReviewInput',
    'ReviewResult',
    'ReviewOutput',
    'ReviewProtocol',

    # ReAct 패턴
    'ReActStep',
    'ReActInput',
    'ReActOutput',
    'ReActProtocol',

    # 검증 유틸리티
    'validate_query_analysis_output',
    'validate_retrieval_output',
    'validate_generation_output',
    'validate_review_output',
]
