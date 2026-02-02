"""
똑소리 프로젝트 - 에이전트 프로토콜 정의 (문서화/참조용)

작성일: 2026-01-28
최종 수정: 2026-02-01

[역할 및 책임]
이 파일은 MAS 아키텍처의 에이전트 간 인터페이스를 TypedDict로 문서화합니다.
실제 런타임 구현은 supervisor/state/에 있으며, 이 파일은 참조 문서 역할을 합니다.

[실제 상태 구조]
- supervisor/state/agent_results.py: QueryAnalysisResult, IndividualRetrievalResult, RetrievalResult 등
- supervisor/state/__init__.py: ChatState 통합 상태
- supervisor/state/session.py: OnboardingInfo, SessionState
- supervisor/nodes/retrieval_merge.py: 병합된 검색 결과 로직

[주의사항]
- 이 파일의 TypedDict는 0개의 런타임 import를 가지는 문서화 파일입니다.
- Protocol 클래스는 제거되었습니다 (실제로 사용되지 않음).
- 실제 구현을 참고할 때는 위 경로의 파일들을 확인하세요.
"""

from typing import List, Dict, Optional, Literal, Any
from typing_extensions import TypedDict


# ============================================================
# 공통 타입 정의
# ============================================================

class OnboardingInfo(TypedDict, total=False):
    """
    온보딩 폼 데이터 (분쟁 상담용).

    프론트엔드 DisputeFormData는 다음과 같이 매핑됩니다:
    - Frontend fields: purchaseDate, purchasePlace, platform, purchaseItem, purchaseAmount, disputeDetails
    - Backend mapping (in convertDisputeFormToOnboarding):
        - purchaseDate → purchase_date
        - purchasePlace → purchase_place
        - platform → purchase_platform
        - purchaseItem → purchase_item
        - purchaseAmount → purchase_amount
        - disputeDetails → dispute_details

    Attributes:
        purchase_date: 구매일자 (예: "2026-01-15")
        purchase_place: 구매처 (판매자 상호/브랜드)
        purchase_platform: 구매 플랫폼 (온라인/오프라인)
        purchase_item: 구매 품목 (예: "헬스장 회원권")
        purchase_amount: 구매 금액 (예: "500000")
        dispute_details: 분쟁 상세 내용
        days_since_purchase: 구매 후 경과 일수 (자동 계산)
        product_category: 품목 카테고리 (전자제품, 의류 등)

    Example:
        >>> onboarding: OnboardingInfo = {
        ...     'purchase_item': '헬스장 회원권',
        ...     'purchase_amount': '500000',
        ...     'dispute_details': '환불 거부당함'
        ... }
    """
    purchase_date: Optional[str]
    purchase_place: Optional[str]
    purchase_platform: Optional[str]
    purchase_item: Optional[str]
    purchase_amount: Optional[str]
    dispute_details: Optional[str]
    days_since_purchase: Optional[int]     # 구매 후 경과 일수 (자동 계산)
    product_category: Optional[str]        # 품목 카테고리 (전자제품, 의류 등)


# 의도 타입
IntentType = Literal['general', 'information_search']

# 라우팅 모드 타입
RoutingMode = Literal[
    'NO_RETRIEVAL',              # 단순 인사/시스템 → Fast Path
    'NEED_RAG',                  # 정보 검색 필요 → Full Pipeline
    'CACHED_RAG',                # 후속 턴 → 캐시된 Retrieval 사용
    'RESTRICTED_DOMAIN',         # 전문기관 도메인
    'META_CONVERSATIONAL',       # 메타 대화 (시스템 질문 등)
    'FOLLOWUP_WITH_CONTEXT',     # 이전 컨텍스트 기반 후속 질문
]

# 검색 에이전트 타입 (4개)
RetrieverType = Literal['law', 'criteria', 'case', 'counsel']

# 채팅 타입
ChatType = Literal['dispute', 'general']

# 위반 유형
ViolationType = Literal['hallucination', 'legal_judgment', 'prohibited_expression', 'query_mismatch']

# 심각도
SeverityLevel = Literal['critical', 'warning']

# 사례 카테고리
CaseCategory = Literal['조정', '해결', '상담']

# 근거 소스
EvidenceSource = Literal['law', 'criteria', 'case', 'counsel']


# ============================================================
# 질의분석 에이전트 (Query Analysis Agent)
# ============================================================
# Used in: supervisor/nodes/supervisor.py, agents/query_analysis/agent.py

class QueryAnalysisInput(TypedDict):
    """
    질의분석 노드 입력.

    Attributes:
        user_query: 사용자가 입력한 원본 질문
        chat_type: 채팅 유형 ('dispute' | 'general')
        onboarding: 온보딩 폼 데이터 (분쟁 상담 시)
    """
    user_query: str
    chat_type: ChatType
    onboarding: Optional[OnboardingInfo]


class QueryAnalysisOutput(TypedDict):
    """
    질의분석 노드 출력.

    LLM 기반 다중 쿼리 확장이 적용된 출력입니다.

    Attributes:
        intent: 의도 분류 ('general' | 'information_search')
        original_query: 원본 질문
        expanded_queries: 다중 확장 쿼리 리스트 (최대 5개)
        keywords: 핵심 키워드 목록
        retriever_types: 추천 검색 에이전트 타입 목록
    """
    intent: IntentType
    original_query: str
    expanded_queries: List[str]
    keywords: List[str]
    retriever_types: List[RetrieverType]


# ============================================================
# 메타데이터 필터 (Retrieval용)
# ============================================================

class MetadataFilter(TypedDict, total=False):
    """
    검색 메타데이터 필터.

    Attributes:
        dataset_type: 데이터셋 타입 ('law_guide' 등)
        document_types: 문서 타입 목록 (['법률', '시행령'] or ['행정규칙', '별표'])
        categories: 카테고리 목록 (['조정', '해결'] or ['상담'])
    """
    dataset_type: Optional[str]
    document_types: Optional[List[str]]
    categories: Optional[List[str]]


# ============================================================
# Supervisor 관련 타입
# ============================================================

class SupervisorPhase(TypedDict):
    """Supervisor 현재 단계."""
    current_phase: Literal['analyzing', 'retrieving', 'drafting', 'reviewing', 'done']


class SupervisorState(TypedDict):
    """
    Supervisor 상태.

    Attributes:
        current_phase: 현재 실행 단계
        selected_retrievers: 선택된 검색 에이전트 목록
        agent_keywords: 에이전트별 키워드 매핑
        iteration_count: 반복 횟수
        reasoning: 의사결정 근거
    """
    current_phase: Literal['analyzing', 'retrieving', 'drafting', 'reviewing', 'done']
    selected_retrievers: List[RetrieverType]
    agent_keywords: Dict[str, List[str]]
    iteration_count: int
    reasoning: str


# ============================================================
# 정보검색 에이전트 (Retrieval Agent)
# ============================================================

class RetrievalTaskInput(TypedDict):
    """
    Supervisor → Retrieval Agent 입력.

    Attributes:
        expanded_queries: 확장 쿼리 리스트
        agent_keywords: 해당 에이전트용 추출 키워드
        metadata_filter: 메타데이터 필터
        top_k: 반환 문서 수
        ignore_threshold: 임계치 무시 여부
    """
    expanded_queries: List[str]
    agent_keywords: List[str]
    metadata_filter: MetadataFilter
    top_k: int
    ignore_threshold: bool


class DocumentMetadata(TypedDict, total=False):
    """
    검색된 문서 메타데이터.

    Attributes:
        doc_id: 문서 ID
        title: 문서 제목
        dataset_type: 데이터셋 타입
        document_type: 문서 타입 ('법률', '시행령', '행정규칙', '별표')
        category: 카테고리 ('조정', '해결', '상담')
        article: 법령 조문 번호
        source_url: 출처 URL
    """
    doc_id: str
    title: str
    dataset_type: str
    document_type: str
    category: str
    article: Optional[str]
    source_url: Optional[str]


class RetrievedDocument(TypedDict, total=False):
    """
    검색된 단일 문서.

    Attributes:
        chunk_id: 청크 ID
        content: 청크 텍스트
        metadata: 문서 메타데이터
        similarity: 유사도 점수
        product_relevance: 온보딩 품목 관련성 (0.0~1.0)
    """
    chunk_id: str
    content: str
    metadata: DocumentMetadata
    similarity: float
    product_relevance: Optional[float]     # 온보딩 품목 관련성 (0.0~1.0)


# Used in: supervisor/state/agent_results.py
class IndividualRetrievalResult(TypedDict, total=False):
    """
    개별 Retrieval Agent 결과 (Phase 5: MAS Supervisor).

    4개의 독립된 Retrieval Agent(Law, Criteria, Case, Counsel)가
    각각 반환하는 검색 결과입니다. state['individual_retrieval_results']에
    operator.add로 누적됩니다.

    Attributes:
        source: 검색 소스 ('law', 'criteria', 'case', 'counsel')
        documents: 검색된 문서 목록
        max_similarity: 최대 유사도
        avg_similarity: 평균 유사도
        search_time_ms: 검색 소요 시간 (ms)
        error: 오류 메시지 (실패 시)

    Example:
        >>> result: IndividualRetrievalResult = {
        ...     'source': 'law',
        ...     'documents': [{'article': '제17조', 'content': '...'}],
        ...     'max_similarity': 0.92,
        ...     'search_time_ms': 150
        ... }
    """
    source: str
    documents: List[Dict]
    max_similarity: float
    avg_similarity: float
    search_time_ms: float
    error: Optional[str]


# Used in: supervisor/nodes/retrieval_merge.py
class MergedRetrievalResult(TypedDict, total=False):
    """
    retrieval_merge 노드 결과 — state['retrieval']에 저장됨.

    4개 Retrieval Agent의 individual_retrieval_results를 병합하여
    4섹션 구조로 통합한 최종 검색 결과입니다.

    Attributes:
        agency: 추천 기관 정보 (기관명, 연락처, 역할)
        disputes: 분쟁조정 사례 리스트
        counsels: 상담 사례 리스트
        laws: 관련 법령 조항 리스트
        criteria: 분쟁해결기준 리스트
        max_similarity: 가장 높은 유사도 점수 (0.0~1.0)
        avg_similarity: 평균 유사도 점수

    Example:
        >>> result: MergedRetrievalResult = {
        ...     'disputes': [{'title': '...', 'similarity': 0.85}],
        ...     'laws': [{'article': '제17조', 'content': '...'}],
        ...     'max_similarity': 0.85,
        ...     'avg_similarity': 0.72
        ... }
    """
    agency: Dict[str, Any]
    disputes: List[Dict[str, Any]]
    counsels: List[Dict[str, Any]]
    laws: List[Dict[str, Any]]
    criteria: List[Dict[str, Any]]
    max_similarity: float
    avg_similarity: float


# ============================================================
# 답변생성 에이전트 (Answer Generation Agent)
# ============================================================

class RetryContext(TypedDict):
    """
    재생성 컨텍스트.

    검토 실패 시 AnswerDrafter에게 전달되는 정보입니다.

    Attributes:
        violations: 이전 답변의 위반 사항 목록
        previous_draft: 이전 답변
        retry_count: 재시도 횟수 (max 1)
    """
    violations: List[str]
    previous_draft: str
    retry_count: int


class GenerationInput(TypedDict):
    """
    답변생성 노드 입력.

    Attributes:
        user_query: 원본 사용자 쿼리
        expanded_queries: 확장 쿼리 리스트 (컨텍스트 제공용)
        retrieval_results: 모든 검색 결과
        retry_context: 재생성 시 위반사항 정보
    """
    user_query: str
    expanded_queries: List[str]
    retrieval_results: List[IndividualRetrievalResult]
    retry_context: Optional[RetryContext]


class ClaimEvidence(TypedDict):
    """
    주장-근거 매핑.

    Attributes:
        claim: 답변 내 주장
        evidence_chunk_ids: 근거가 되는 청크 ID 목록
        evidence_texts: 근거 텍스트 목록
        evidence_source: 근거 소스 ('law' | 'criteria' | 'case' | 'counsel')
        grounded: 근거 있음 여부
    """
    claim: str
    evidence_chunk_ids: List[str]
    evidence_texts: List[str]
    evidence_source: EvidenceSource
    grounded: bool


class CitedCase(TypedDict):
    """
    인용된 사례 정보.

    Attributes:
        case_id: 사례 ID
        category: 카테고리 ('조정' | '해결' | '상담')
        title: 사례 제목
        summary: 사례 요약 (답변에 포함된 내용)
        relevance: 현재 질의와의 관련성 설명
    """
    case_id: str
    category: CaseCategory
    title: str
    summary: str
    relevance: str


# Used in: agents/answer_generation/agent.py
class GenerationOutput(TypedDict):
    """
    답변생성 노드 출력.

    Attributes:
        draft_answer: 생성된 답변 초안
        claim_evidence_map: 주장-근거 매핑 목록
        cited_cases: 인용된 사례 정보 목록
        has_sufficient_evidence: 근거 충분 여부
        generation_time_ms: 생성 소요 시간 (ms)
        response_depth: "summary" | "detail" | "full"
        available_details: 미표시 상세 정보 메타
        followup_questions: 제안 후속 질문
    """
    draft_answer: str
    claim_evidence_map: List[ClaimEvidence]
    cited_cases: List[CitedCase]
    has_sufficient_evidence: bool
    generation_time_ms: float
    response_depth: Optional[str]          # "summary" | "detail" | "full"
    available_details: Optional[Dict]      # 미표시 상세 정보 메타
    followup_questions: Optional[List[str]]  # 제안 후속 질문


# ============================================================
# 법률검토 에이전트 (Legal Review Agent)
# ============================================================

class ReviewInput(TypedDict):
    """
    법률검토 노드 입력.

    Attributes:
        user_query: 원본 질문
        draft_answer: 검토할 답변
        claim_evidence_map: 주장-근거 매핑
        cited_cases: 인용된 사례 목록
        retrieval_results: 원본 검색 결과 (검증용)
        retry_count: 현재 재시도 횟수
    """
    user_query: str
    draft_answer: str
    claim_evidence_map: List[ClaimEvidence]
    cited_cases: List[CitedCase]
    retrieval_results: List[IndividualRetrievalResult]
    retry_count: int


class Violation(TypedDict):
    """
    위반 사항 상세.

    Attributes:
        type: 위반 유형 ('hallucination' | 'legal_judgment' | 'prohibited_expression' | 'query_mismatch')
        description: 위반 내용 상세
        location: 위반 위치 (문장 또는 단락)
        severity: 심각도 ('critical' | 'warning')
        suggestion: 수정 제안
    """
    type: ViolationType
    description: str
    location: str
    severity: SeverityLevel
    suggestion: Optional[str]


# Used in: agents/legal_review/agent.py
# Note: actual review output is stored in state['review'] dict
class ReviewOutput(TypedDict):
    """
    법률검토 노드 출력.

    실제 그래프에서는 state['review']에 저장됩니다.

    Attributes:
        passed: 검토 통과 여부
        violations: 위반 사항 목록 (passed=False일 때)
        final_answer: 수정된 최종 답변 (passed=True일 때)
        review_time_ms: 검토 소요 시간 (ms)
    """
    passed: bool
    violations: List[Violation]
    final_answer: Optional[str]
    review_time_ms: float


# ============================================================
# 통합 ChatState (참조용 - 실제는 supervisor/state/__init__.py)
# ============================================================

class ProtocolChatState(TypedDict, total=False):
    """
    통합 채팅 상태 (참조용).

    실제 구현은 supervisor/state/__init__.py의 ChatState입니다.
    모든 에이전트 간 데이터가 저장되는 중앙 상태입니다.
    """
    # === 세션 정보 ===
    user_query: str
    chat_type: ChatType
    onboarding: Optional[OnboardingInfo]

    # === QueryAnalyst 결과 ===
    query_analysis: QueryAnalysisOutput

    # === Supervisor 상태 ===
    supervisor: SupervisorState

    # === Retrieval 결과 ===
    # 개별 Agent 결과 (operator.add로 누적)
    individual_retrieval_results: List[IndividualRetrievalResult]
    # 병합된 최종 결과 (retrieval_merge 노드가 생성)
    retrieval: MergedRetrievalResult

    # === Generation 결과 ===
    draft_answer: str
    claim_evidence_map: List[ClaimEvidence]
    cited_cases: List[CitedCase]

    # === Review 결과 ===
    review: ReviewOutput
    retry_count: int

    # === 최종 출력 ===
    final_answer: str
    sources: List[Dict[str, Any]]


# ============================================================
# 타입 검증 유틸리티
# ============================================================

def validate_query_analysis_output(output: Dict[str, Any]) -> bool:
    """질의분석 출력이 프로토콜을 만족하는지 검증합니다."""
    required_keys = {'intent', 'original_query', 'expanded_queries', 'keywords', 'retriever_types'}
    return required_keys.issubset(output.keys())


def validate_individual_retrieval_result(output: Dict[str, Any]) -> bool:
    """개별 검색 결과가 프로토콜을 만족하는지 검증합니다."""
    required_keys = {'source', 'documents', 'max_similarity', 'avg_similarity', 'search_time_ms'}
    return required_keys.issubset(output.keys())


def validate_merged_retrieval_result(output: Dict[str, Any]) -> bool:
    """병합된 검색 결과가 프로토콜을 만족하는지 검증합니다."""
    required_keys = {'agency', 'disputes', 'counsels', 'laws', 'criteria', 'max_similarity', 'avg_similarity'}
    return required_keys.issubset(output.keys())


def validate_generation_output(output: Dict[str, Any]) -> bool:
    """답변생성 출력이 프로토콜을 만족하는지 검증합니다."""
    required_keys = {'draft_answer', 'claim_evidence_map', 'cited_cases', 'has_sufficient_evidence'}
    return required_keys.issubset(output.keys())


def validate_review_output(output: Dict[str, Any]) -> bool:
    """검토 출력이 프로토콜을 만족하는지 검증합니다."""
    required_keys = {'passed', 'violations', 'final_answer', 'review_time_ms'}
    return required_keys.issubset(output.keys())


# ============================================================
# 모듈 공개 API
# ============================================================

__all__ = [
    # 공통 타입
    'OnboardingInfo',
    'IntentType',
    'RoutingMode',
    'RetrieverType',
    'ChatType',
    'ViolationType',
    'SeverityLevel',
    'CaseCategory',
    'EvidenceSource',

    # 메타데이터 필터
    'MetadataFilter',

    # Supervisor
    'SupervisorPhase',
    'SupervisorState',

    # 질의분석 에이전트
    'QueryAnalysisInput',
    'QueryAnalysisOutput',

    # 정보검색 에이전트
    'RetrievalTaskInput',
    'DocumentMetadata',
    'RetrievedDocument',
    'IndividualRetrievalResult',
    'MergedRetrievalResult',

    # 답변생성 에이전트
    'RetryContext',
    'GenerationInput',
    'ClaimEvidence',
    'CitedCase',
    'GenerationOutput',

    # 법률검토 에이전트
    'ReviewInput',
    'Violation',
    'ReviewOutput',

    # 통합 상태
    'ProtocolChatState',

    # 검증 유틸리티
    'validate_query_analysis_output',
    'validate_individual_retrieval_result',
    'validate_merged_retrieval_result',
    'validate_generation_output',
    'validate_review_output',
]
