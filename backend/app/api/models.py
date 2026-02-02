"""
똑소리 프로젝트 - API 요청/응답 모델

FastAPI 엔드포인트에서 사용하는 Pydantic 스키마를 정의합니다.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Literal


# === 요청 모델 ===

class ChatRequest(BaseModel):
    """채팅 요청 모델"""
    message: str = Field(..., min_length=1, description="사용자 질문")
    session_id: Optional[str] = Field(default=None, description="멀티턴 세션 ID (없으면 새 세션 생성)")
    chat_type: Literal['dispute', 'general'] = Field(default='dispute', description="상담 유형")
    onboarding: Optional[Dict[str, str]] = Field(default=None, description="온보딩 폼 데이터")
    top_k: Optional[int] = Field(default=5, ge=1, le=100, description="검색 결과 수")
    chunk_types: Optional[List[str]] = None
    agencies: Optional[List[str]] = None
    debug: bool = Field(default=False, description="디버그 모드 (타이밍 정보 포함)")

    @field_validator('message')
    @classmethod
    def message_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('메시지는 빈 문자열일 수 없습니다')
        return v.strip()


class SearchRequest(BaseModel):
    """검색 요청 모델"""
    query: str = Field(..., min_length=1, description="검색 쿼리")
    top_k: Optional[int] = Field(default=5, ge=1, le=100, description="검색 결과 수")
    chunk_types: Optional[List[str]] = None
    agencies: Optional[List[str]] = None

    @field_validator('query')
    @classmethod
    def query_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('쿼리는 빈 문자열일 수 없습니다')
        return v.strip()


# === 응답 모델 - 참조 정보 ===

class AgencyRecommendation(BaseModel):
    """추천 기관 정보"""
    agency: str = ''  # KCA, ECMC, KCDRC
    agency_info: Dict[str, str] = {}
    dispute_type: str = ''  # 1:N, 1:1, contents
    reason: str = ''
    confidence: float = 0.7
    # 프론트엔드 호환 필드
    is_restricted: bool = False
    full_name: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    agency_code: Optional[str] = None
    restriction_reason: Optional[str] = None


class CaseReference(BaseModel):
    """
    사례 참조 정보

    분쟁조정사례 및 상담사례의 메타데이터를 포함합니다.
    """
    chunk_id: Optional[str] = None
    doc_id: Optional[str] = None
    doc_title: Optional[str] = None
    source_org: Optional[str] = None
    decision_date: Optional[str] = None
    similarity: float = 0.0
    content: Optional[str] = None
    url: Optional[str] = None
    # 실시간 LLM 추출 메타데이터
    product_item: Optional[str] = None        # 품목 (예: "키보드", "헬스회원권")
    dispute_amount: Optional[str] = None      # 금액 (예: "120,000원")
    transaction_date: Optional[str] = None    # 거래/구매 일자
    mediation_result: Optional[str] = None    # 조정결과 (예: "인용", "기각", "조정성립")


class LawReference(BaseModel):
    """법령 참조 정보"""
    unit_id: Optional[str] = None
    law_name: Optional[str] = None
    full_path: Optional[str] = None  # "제14조 제1항"
    text: Optional[str] = None
    similarity: float = 0.0


class CriteriaReference(BaseModel):
    """분쟁해결기준 참조 정보"""
    unit_id: Optional[str] = None
    source_label: Optional[str] = None
    category: Optional[str] = None
    industry: Optional[str] = None
    item_group: Optional[str] = None
    item: Optional[str] = None
    unit_text: Optional[str] = None
    similarity: float = 0.0


class SimilarCases(BaseModel):
    """유사 사례 모음"""
    disputes: List[CaseReference] = []
    counsels: List[CaseReference] = []


# === 응답 모델 - 디버그 ===

class NodeTiming(BaseModel):
    """에이전트 노드 실행 시간 (debug 모드용)"""
    node_name: str
    duration_ms: float
    start_time: str
    end_time: str


# === 응답 모델 - 메인 ===

class ChatResponse(BaseModel):
    """채팅 응답 모델"""
    session_id: str = Field(..., description="세션 ID (멀티턴 대화용)")
    answer: str
    chunks_used: int
    model: str
    sources: List[dict]
    has_sufficient_evidence: bool = True
    clarifying_questions: List[str] = []
    followup_questions: List[str] = Field(
        default=[],
        description="후속 질문 제안 목록 (Track 2)"
    )
    domain: Optional[AgencyRecommendation] = None
    similar_cases: Optional[SimilarCases] = None
    related_laws: Optional[List[LawReference]] = None
    related_criteria: Optional[List[CriteriaReference]] = None
    # debug 모드 필드
    node_timings: Optional[List[NodeTiming]] = None
    request_id: Optional[str] = None
    total_time_ms: Optional[float] = None


class HealthResponse(BaseModel):
    """헬스체크 응답"""
    status: str
    database: Optional[str] = None
    error: Optional[str] = None


class SearchResponse(BaseModel):
    """검색 응답 모델"""
    query: str
    results_count: int
    results: List[dict]


__all__ = [
    # 요청
    'ChatRequest',
    'SearchRequest',
    # 참조 정보
    'AgencyRecommendation',
    'CaseReference',
    'LawReference',
    'CriteriaReference',
    'SimilarCases',
    # 디버그
    'NodeTiming',
    # 응답
    'ChatResponse',
    'HealthResponse',
    'SearchResponse',
]
