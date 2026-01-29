"""
똑소리 프로젝트 - 에이전트 결과 상태 스키마

각 에이전트(질의분석, 검색, 생성, 검토)의 실행 결과를 저장합니다.
노드 간 데이터 전달의 중심 역할을 합니다.
"""

from typing import List, Dict, Optional, Literal
from typing_extensions import TypedDict


class QueryAnalysisResult(TypedDict, total=False):
    """
    질의분석 에이전트 결과

    사용자 질문을 분석하여 의도, 키워드, 검색 쿼리 등을 추출합니다.

    Attributes:
        query_type: 질의 유형 분류
            - 'dispute': 분쟁 관련 (환불, 교환, 피해 등)
            - 'general': 일반 질문 (인사, 정의 질문 등)
            - 'law': 법령 관련 질문
            - 'criteria': 분쟁해결기준 관련
            - 'procedure': 분쟁조정 신청 절차 안내
            - 'restricted': 전문기관 도메인 (금융, 의료, 개인정보, 부동산, 건설)
            - 'system_meta': 시스템 관련 (기능 문의 등)
            - 'ambiguous': 의도 불명확

        keywords: 추출된 핵심 키워드 리스트
        agency_hint: 추천 기관 힌트 ('KCA', 'ECMC', None)
        needs_clarification: 추가 정보 필요 여부
        missing_fields: 누락된 필수 정보 목록
        extracted_info: 추출된 구조화 정보 (품목, 금액 등)
        missing_fields_description: 누락 정보에 대한 설명
        rewritten_query: 정규화 + 확장된 최종 검색 쿼리
        search_queries: Multi-Query 검색용 쿼리 리스트 (최대 4개)
        expansion_applied: 적용된 확장 규칙 설명
        retriever_types: 활성화할 Retrieval Agent 리스트
        restricted_domain: 전문기관 도메인 (finance, medical, privacy, realestate, construction)
        restricted_agency_info: 전문기관 정보 (name, organization, url, phone)

    Example:
        >>> result: QueryAnalysisResult = {
        ...     'query_type': 'dispute',
        ...     'keywords': ['헬스장', '환불', '회원권'],
        ...     'rewritten_query': '헬스장 회원권 중도해지 환불',
        ...     'search_queries': ['헬스장 환불', '피트니스 중도해지']
        ... }
    """
    query_type: Literal['dispute', 'general', 'law', 'criteria', 'procedure', 'restricted', 'system_meta', 'ambiguous']
    keywords: List[str]
    agency_hint: Optional[str]
    needs_clarification: bool
    missing_fields: List[str]
    extracted_info: Dict[str, str]
    missing_fields_description: str
    rewritten_query: str
    search_queries: List[str]
    expansion_applied: str

    # === PR-2: Selective Retrieval 시작 ===
    retriever_types: List[str]  # ["law", "criteria", "case", "counsel"] 중 선택
    # === PR-2: Selective Retrieval 끝 ===

    # === Phase 9: Restricted Domain 정보 ===
    restricted_domain: Optional[str]  # finance, medical, privacy, realestate, construction
    restricted_agency_info: Optional[Dict[str, str]]  # {name, organization, url, phone}


class RetrievalResult(TypedDict, total=False):
    """
    정보검색 에이전트 결과 (4섹션 구조)

    벡터 검색 + FTS 하이브리드 검색 결과를 4가지 섹션으로 구조화합니다.

    Attributes:
        agency: 추천 기관 정보 (기관명, 연락처, 역할)
        disputes: 분쟁조정 사례 리스트
        counsels: 상담 사례 리스트
        laws: 관련 법령 조항 리스트
        criteria: 분쟁해결기준 리스트
        max_similarity: 가장 높은 유사도 점수 (0.0~1.0)
        avg_similarity: 평균 유사도 점수

    Example:
        >>> result: RetrievalResult = {
        ...     'disputes': [{'title': '...', 'similarity': 0.85}],
        ...     'laws': [{'article': '제17조', 'content': '...'}],
        ...     'max_similarity': 0.85,
        ...     'avg_similarity': 0.72
        ... }
    """
    agency: Dict
    disputes: List[Dict]
    counsels: List[Dict]
    laws: List[Dict]
    criteria: List[Dict]
    max_similarity: float
    avg_similarity: float


class IndividualRetrievalResult(TypedDict, total=False):
    """
    개별 Retrieval Agent 결과 (Phase 5: MAS Supervisor)

    4개의 독립된 Retrieval Agent(Law, Criteria, Case, Counsel)가
    각각 반환하는 검색 결과입니다.

    Attributes:
        source: 검색 소스 ('law', 'criteria', 'case', 'counsel')
        documents: 검색된 문서 리스트 (최대 5개)
        max_similarity: 최고 유사도 점수
        avg_similarity: 평균 유사도 점수
        search_time_ms: 검색 소요 시간 (밀리초)
        error: 검색 실패 시 에러 메시지

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


class HallucinationCheckResult(TypedDict, total=False):
    """
    Hallucination 검사 결과

    Attributes:
        passed: 검사 통과 여부
        cited_refs: 답변에서 발견된 인용 리스트
        verified_refs: 검색 결과에서 확인된 인용 리스트
        unverified_refs: 확인되지 않은 인용 (Hallucination 의심)
        accuracy: 인용 정확도 (0.0 ~ 1.0)
    """
    passed: bool
    cited_refs: List[str]
    verified_refs: List[str]
    unverified_refs: List[str]
    accuracy: float


class RelevanceCheckResult(TypedDict, total=False):
    """
    관련성 검사 결과

    Attributes:
        passed: 검사 통과 여부
        query_answer_score: Query-Answer 관련성 점수
        query_retrieval_score: Query-Retrieval 관련성 점수
        answer_source_score: Answer-Source 관련성 점수
        message: 실패 시 상세 메시지
    """
    passed: bool
    query_answer_score: float
    query_retrieval_score: float
    answer_source_score: float
    message: Optional[str]


class LegalJudgmentCheckResult(TypedDict, total=False):
    """
    법적 판단 검사 결과

    Attributes:
        passed: 검사 통과 여부 (법적 판단 없음 = True)
        detected_judgments: 탐지된 법적 판단 표현 리스트
        severity: 심각도 ('low', 'medium', 'high')
        llm_verified: LLM 2차 검증 수행 여부
    """
    passed: bool
    detected_judgments: List[str]
    severity: Literal['low', 'medium', 'high']
    llm_verified: bool


class ReviewResult(TypedDict, total=False):
    """
    검토 에이전트 결과

    생성된 답변의 품질과 안전성을 검토합니다.

    Attributes:
        passed: 검토 통과 여부
            - True: 답변 그대로 사용 가능
            - False: 수정 필요 또는 재생성 필요

        violations: 발견된 위반 사항 리스트
            - 금지 표현 (단정적 표현, 법적 보장 등)
            - 출처 누락 (인용 없는 주장)
            - 환각 의심 (근거 없는 내용)

        filtered_answer: 위반 사항 수정 후 답변
            - passed=False인 경우에만 설정
            - 금지 표현 제거/완화된 버전

        hallucination_check: Hallucination 검사 결과
            - 인용 정확성 검증 결과

        relevance_check: 관련성 검사 결과
            - Query-Answer, Query-Retrieval, Answer-Source 관련성

        legal_judgment_check: 법적 판단 검사 결과
            - 변호사법 위반 가능성 검증

        confidence_score: 종합 신뢰도 점수 (0.0 ~ 1.0)
            - 출처 커버리지, 관련성, 인용 정확도 종합

    Example:
        >>> result: ReviewResult = {
        ...     'passed': False,
        ...     'violations': ['단정적 표현: "반드시 승소합니다"'],
        ...     'filtered_answer': '환불 가능성이 있습니다...',
        ...     'confidence_score': 0.75
        ... }
    """
    passed: bool
    violations: List[str]
    filtered_answer: Optional[str]
    hallucination_check: Optional[HallucinationCheckResult]
    relevance_check: Optional[RelevanceCheckResult]
    legal_judgment_check: Optional[LegalJudgmentCheckResult]
    confidence_score: Optional[float]


class AgentResultsState(TypedDict, total=False):
    """
    에이전트 실행 결과 상태

    각 노드가 실행 후 업데이트하는 결과 데이터입니다.
    파이프라인 순서대로 채워집니다:
    query_analysis → retrieval → draft_answer → review

    Attributes:
        query_analysis: 질의분석 결과
        retrieval: 검색 결과 (4섹션)
        draft_answer: LLM 생성 초안
        review: 검토 결과
    """
    query_analysis: Optional[QueryAnalysisResult]
    retrieval: Optional[RetrievalResult]
    draft_answer: Optional[str]
    review: Optional[ReviewResult]


# =============================================================================
# MAS v2 타입 정의
# =============================================================================

class CitedCase(TypedDict):
    """
    인용된 사례 정보 (v2)

    AnswerDrafter가 검색 결과에서 추출한 사례 인용 정보입니다.

    Attributes:
        case_id: 사례 고유 ID (chunk_id)
        category: 사례 카테고리 ('조정', '해결', '상담')
        title: 사례 제목
        summary: 사례 요약
        relevance: 사용자 질문과의 관련성 설명
    """
    case_id: str
    category: Literal['조정', '해결', '상담']
    title: str
    summary: str
    relevance: str


class ViolationV2(TypedDict, total=False):
    """
    위반 사항 상세 정보 (v2)

    LegalReviewer가 탐지한 위반 사항의 상세 정보입니다.

    Attributes:
        type: 위반 유형
            - 'hallucination': 근거 없는 인용
            - 'legal_judgment': 법적 판단 표현
            - 'prohibited_expression': 금지 표현
            - 'query_mismatch': 질의-답변 불일치
        description: 위반 설명
        location: 위반 발생 위치 (문장 또는 단락)
        severity: 심각도 ('critical', 'warning')
        suggestion: 수정 제안 (optional)
    """
    type: Literal['hallucination', 'legal_judgment', 'prohibited_expression', 'query_mismatch']
    description: str
    location: str
    severity: Literal['critical', 'warning']
    suggestion: Optional[str]


class RetryContext(TypedDict):
    """
    재생성 컨텍스트 (v2)

    LegalReviewer가 검토 실패 시 AnswerDrafter에게 전달하는 재시도 정보입니다.

    Attributes:
        violations: 이전 위반 사항 리스트 (문자열)
        previous_draft: 이전 생성 답변
        retry_count: 현재 재시도 횟수 (max 1)
    """
    violations: List[str]
    previous_draft: str
    retry_count: int


__all__ = [
    'QueryAnalysisResult',
    'RetrievalResult',
    'IndividualRetrievalResult',
    'HallucinationCheckResult',
    'RelevanceCheckResult',
    'LegalJudgmentCheckResult',
    'ReviewResult',
    'AgentResultsState',
    # v2 타입
    'CitedCase',
    'ViolationV2',
    'RetryContext',
]
