"""
똑소리 프로젝트 - 에이전트 프로토콜 정의

작성일: 2026-01-28
최종 수정: 2026-01-29

[역할 및 책임]
MAS 아키텍처의 에이전트 간 인터페이스를 정의합니다.
각 에이전트가 준수해야 하는 입출력 인터페이스를 TypedDict로 정의합니다.

[주요 기능]
1. QueryAnalyst: LLM 기반 다중 쿼리 확장
2. Supervisor: 하이브리드 에이전트 선택
3. Retrieval Agents: 메타데이터 필터 기반 검색 최적화
4. AnswerDrafter: 사례 인용 기능 강화
5. LegalReviewer: 재생성 루프 (max 1회)

[에이전트 흐름]
QueryAnalyst → Supervisor → Retrieval Agents → AnswerDrafter → LegalReviewer → Final Answer
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
    """
    purchase_date: Optional[str]
    purchase_place: Optional[str]
    purchase_platform: Optional[str]
    purchase_item: Optional[str]
    purchase_amount: Optional[str]
    dispute_details: Optional[str]


# 의도 타입
IntentType = Literal['general', 'information_search']

# 라우팅 모드 타입
RoutingMode = Literal['NO_RETRIEVAL', 'NEED_RAG', 'NEED_USER_CLARIFICATION', 'NEED_CLARIFICATION']

# 검색 에이전트 타입
RetrieverType = Literal['law', 'criteria', 'case']

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
# 질의분석 에이전트 (Query Analysis Agent) - v2
# ============================================================

class QueryAnalysisInput(TypedDict):
    """
    질의분석 노드 입력 (v2).

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
    질의분석 노드 출력 (v2).

    LLM 기반 다중 쿼리 확장이 적용된 출력입니다.

    Attributes:
        intent: 의도 분류 ('general' | 'information_search')
        original_query: 원본 질문
        expanded_queries: 다중 확장 쿼리 리스트 (최대 5개)
        keywords: 핵심 키워드 목록
        retriever_types: 추천 검색 에이전트 타입 목록
        needs_clarification: 추가 정보 필요 여부
        missing_fields: 누락된 필드 목록
    """
    intent: IntentType
    original_query: str
    expanded_queries: List[str]
    keywords: List[str]
    retriever_types: List[RetrieverType]
    needs_clarification: bool
    missing_fields: List[str]


@runtime_checkable
class QueryAnalysisProtocol(Protocol):
    """질의분석 에이전트 프로토콜 (v2)."""

    async def analyze(self, input_data: QueryAnalysisInput) -> QueryAnalysisOutput:
        """사용자 쿼리를 분석하고 확장합니다."""
        ...


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
    Supervisor 상태 (v2).

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
# 정보검색 에이전트 (Retrieval Agent) - v2
# ============================================================

class RetrievalTaskInput(TypedDict):
    """
    Supervisor → Retrieval Agent 입력 (v2).

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
    검색된 문서 메타데이터 (v2).

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


class RetrievedDocument(TypedDict):
    """
    검색된 단일 문서 (v2).

    Attributes:
        chunk_id: 청크 ID
        content: 청크 텍스트
        metadata: 문서 메타데이터
        similarity: 유사도 점수
    """
    chunk_id: str
    content: str
    metadata: DocumentMetadata
    similarity: float


class RetrievalResult(TypedDict):
    """
    Retrieval Agent → Supervisor 출력 (v2).

    Attributes:
        source: 검색 소스 ('law' | 'criteria' | 'case')
        documents: 검색된 문서 목록
        max_similarity: 최대 유사도
        avg_similarity: 평균 유사도
        search_time_ms: 검색 소요 시간 (ms)
        error: 오류 메시지 (실패 시)
    """
    source: RetrieverType
    documents: List[RetrievedDocument]
    max_similarity: float
    avg_similarity: float
    search_time_ms: float
    error: Optional[str]


@runtime_checkable
class RetrievalProtocol(Protocol):
    """정보검색 에이전트 프로토콜 (v2)."""

    async def retrieve(self, input_data: RetrievalTaskInput) -> RetrievalResult:
        """관련 문서를 검색합니다."""
        ...


# ============================================================
# 답변생성 에이전트 (Answer Generation Agent) - v2
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
    답변생성 노드 입력 (v2).

    Attributes:
        user_query: 원본 사용자 쿼리
        expanded_queries: 확장 쿼리 리스트 (컨텍스트 제공용)
        retrieval_results: 모든 검색 결과
        retry_context: 재생성 시 위반사항 정보
    """
    user_query: str
    expanded_queries: List[str]
    retrieval_results: List[RetrievalResult]
    retry_context: Optional[RetryContext]


class ClaimEvidence(TypedDict):
    """
    주장-근거 매핑 (v2).

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


class GenerationOutput(TypedDict):
    """
    답변생성 노드 출력 (v2).

    Attributes:
        draft_answer: 생성된 답변 초안
        claim_evidence_map: 주장-근거 매핑 목록
        cited_cases: 인용된 사례 정보 목록
        has_sufficient_evidence: 근거 충분 여부
        generation_time_ms: 생성 소요 시간 (ms)
    """
    draft_answer: str
    claim_evidence_map: List[ClaimEvidence]
    cited_cases: List[CitedCase]
    has_sufficient_evidence: bool
    generation_time_ms: float


@runtime_checkable
class GenerationProtocol(Protocol):
    """답변생성 에이전트 프로토콜 (v2)."""

    async def generate(self, input_data: GenerationInput) -> GenerationOutput:
        """답변을 생성합니다."""
        ...


# ============================================================
# 법률검토 에이전트 (Legal Review Agent) - v2
# ============================================================

class ReviewInput(TypedDict):
    """
    법률검토 노드 입력 (v2).

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
    retrieval_results: List[RetrievalResult]
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


class ReviewOutput(TypedDict):
    """
    법률검토 노드 출력 (v2).

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


@runtime_checkable
class ReviewProtocol(Protocol):
    """법률검토 에이전트 프로토콜 (v2)."""

    async def review(self, input_data: ReviewInput) -> ReviewOutput:
        """답변을 검토합니다."""
        ...


# ============================================================
# 통합 ChatState # ============================================================

class ProtocolChatState(TypedDict, total=False):
    """
    통합 채팅 상태 (v2).

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
    retrieval_results: List[RetrievalResult]

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
    """질의분석 출력(v2)이 프로토콜을 만족하는지 검증합니다."""
    required_keys = {'intent', 'original_query', 'expanded_queries', 'keywords', 'retriever_types'}
    return required_keys.issubset(output.keys())


def validate_retrieval_result(output: Dict[str, Any]) -> bool:
    """검색 결과(v2)가 프로토콜을 만족하는지 검증합니다."""
    required_keys = {'source', 'documents', 'max_similarity', 'avg_similarity', 'search_time_ms'}
    return required_keys.issubset(output.keys())


def validate_generation_output(output: Dict[str, Any]) -> bool:
    """답변생성 출력(v2)이 프로토콜을 만족하는지 검증합니다."""
    required_keys = {'draft_answer', 'claim_evidence_map', 'cited_cases', 'has_sufficient_evidence'}
    return required_keys.issubset(output.keys())


def validate_review_output(output: Dict[str, Any]) -> bool:
    """검토 출력(v2)이 프로토콜을 만족하는지 검증합니다."""
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

    # 질의분석 에이전트     'QueryAnalysisInput',
    'QueryAnalysisOutput',
    'QueryAnalysisProtocol',

    # 정보검색 에이전트     'RetrievalTaskInput',
    'DocumentMetadata',
    'RetrievedDocument',
    'RetrievalResult',
    'RetrievalProtocol',

    # 답변생성 에이전트     'RetryContext',
    'GenerationInput',
    'ClaimEvidence',
    'CitedCase',
    'GenerationOutput',
    'GenerationProtocol',

    # 법률검토 에이전트     'ReviewInput',
    'Violation',
    'ReviewOutput',
    'ReviewProtocol',

    # 통합 상태
    'ProtocolChatState',

    # 검증 유틸리티
    'validate_query_analysis_output',
    'validate_retrieval_result',
    'validate_generation_output',
    'validate_review_output',
]
