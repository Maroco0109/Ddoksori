"""
똑소리 프로젝트 - RAG 파이프라인 로거

작성일: 2026-01-24
최종 수정: 2026-01-24

[역할 및 책임]
RAG 파이프라인 실행 과정을 상세하게 기록하는 구조화된 JSON 로거입니다.
각 채팅 요청에 대해 다음 정보를 JSON 파일로 저장합니다:
- 입력 쿼리 정보
- 검색된 청크와 유사도 점수
- LLM 프롬프트 및 토큰 사용량
- 응답 시간 측정

[사용 예시]
    logger = RAGLogger()
    entry = logger.create_entry(query="환불 가능한가요?")

    # 파이프라인 실행 중 log_retrieval(), log_llm() 등 호출

    logger.finalize(entry, start_time)
    logger.save(entry)

[출력 형식]
logs/rag/YYYY-MM-DD/HHMMSS_{request_id}.json
"""

import hashlib
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .config import RAG_LOG_DIR, is_rag_logging_enabled

# SEC-12: 프로덕션에서 시스템 프롬프트 해싱
HASH_SYSTEM_PROMPT = os.getenv("HASH_SYSTEM_PROMPT_IN_LOGS", "true").lower() == "true"
APP_ENV = os.getenv("APP_ENV", "development")

logger = logging.getLogger(__name__)


# ============================================================
# 데이터 클래스 정의 - 검색 관련
# ============================================================


@dataclass
class ChunkLog:
    """
    검색된 청크 로그.

    벡터 검색 결과로 반환된 개별 청크의 정보를 기록합니다.
    """

    chunk_id: str  # 청크 고유 ID
    doc_id: str  # 문서 ID
    doc_title: str  # 문서 제목
    doc_type: str  # 문서 유형 (law, counsel_case, etc.)
    chunk_type: str  # 청크 유형
    source_org: str  # 출처 기관
    similarity: float  # 코사인 유사도 점수
    content_preview: str  # 내용 미리보기 (첫 200자)


@dataclass
class RetrievalLog:
    """
    검색 단계 로그.

    벡터 검색 과정의 설정과 결과를 기록합니다.
    """

    mode: str  # 검색 모드 ("dense" | "hybrid")
    top_k: int  # 검색 결과 개수
    embedding_time_ms: float = 0.0  # 임베딩 생성 시간 (밀리초)
    search_time_ms: float = 0.0  # 검색 실행 시간 (밀리초)
    dense_candidates: int = 0  # Dense 검색 후보 수
    lexical_candidates: int = 0  # Lexical 검색 후보 수
    chunks: List[ChunkLog] = field(default_factory=list)


# ============================================================
# 데이터 클래스 정의 - LLM 관련
# ============================================================


@dataclass
class LLMLog:
    """
    LLM 호출 로그.

    LLM API 호출에 사용된 프롬프트와 응답 정보를 기록합니다.
    """

    model: str = ""  # 사용된 모델명
    system_prompt: str = ""  # 시스템 프롬프트
    user_prompt: str = ""  # 사용자 프롬프트
    prompt_tokens: int = 0  # 입력 토큰 수
    completion_tokens: int = 0  # 출력 토큰 수
    response_time_ms: float = 0.0  # 응답 시간 (밀리초)
    has_sufficient_evidence: bool = True  # 충분한 증거 존재 여부
    clarifying_questions: List[str] = field(default_factory=list)  # 명확화 질문


@dataclass
class ResponseSummary:
    """
    응답 요약.

    최종 응답의 통계 정보를 기록합니다.
    """

    answer_length: int = 0  # 답변 길이 (문자 수)
    chunks_used: int = 0  # 사용된 청크 수
    sources_count: int = 0  # 출처 수
    status: str = "success"  # 상태 ("success" | "no_results" | "error")
    error_message: Optional[str] = None  # 에러 메시지 (있는 경우)


# ============================================================
# 데이터 클래스 정의 - 4섹션 구조화 검색
# ============================================================


@dataclass
class DomainLog:
    """
    기관 추천 로그.

    분쟁 유형에 따른 담당 기관 추천 정보를 기록합니다.
    """

    agency: str  # 추천 기관 (KCA, ECMC, KCDRC)
    dispute_type: str  # 분쟁 유형 (1:N, 1:1, contents)
    reason: str  # 추천 사유
    confidence: float  # 신뢰도 점수
    matched_keywords: List[str] = field(default_factory=list)  # 매칭된 키워드


@dataclass
class DisputeLog:
    """
    분쟁조정 사례 로그.

    검색된 분쟁조정 사례의 메타데이터를 기록합니다.
    """

    chunk_id: str  # 청크 ID
    doc_id: str  # 문서 ID
    doc_title: str  # 문서 제목
    source_org: str  # 출처 기관
    decision_date: Optional[str]  # 결정일
    similarity: float  # 유사도 점수
    content_preview: str  # 내용 미리보기 (200자)
    # LLM 추출 메타데이터
    product_item: Optional[str] = None  # 품목 (예: "키보드", "헬스회원권")
    dispute_amount: Optional[str] = None  # 분쟁 금액 (예: "120,000원")
    transaction_date: Optional[str] = None  # 거래/구매 일자
    mediation_result: Optional[str] = None  # 조정결과 (예: "인용", "기각")


@dataclass
class CounselLog:
    """
    상담 사례 로그.

    검색된 상담 사례 정보를 기록합니다.
    """

    chunk_id: str  # 청크 ID
    doc_id: str  # 문서 ID
    doc_title: str  # 문서 제목
    source_org: str  # 출처 기관
    similarity: float  # 유사도 점수
    content_preview: str  # 내용 미리보기 (200자)


@dataclass
class LawLog:
    """
    법령 로그.

    검색된 법령 조항 정보를 기록합니다.
    """

    unit_id: str  # 단위 ID
    law_name: str  # 법률명
    full_path: str  # 전체 경로 (예: 제14조 제1항)
    similarity: float  # 유사도 점수
    text_preview: str  # 내용 미리보기 (200자)


@dataclass
class CriteriaLog:
    """
    분쟁해결기준 로그.

    검색된 분쟁해결기준 정보를 기록합니다.
    """

    unit_id: str  # 단위 ID
    source_label: str  # 출처 레이블
    category: str  # 카테고리
    industry: str  # 업종
    item_group: str  # 품목군
    item: str  # 품목
    similarity: float  # 유사도 점수
    text_preview: str  # 내용 미리보기 (200자)


@dataclass
class StructuredRetrievalLog:
    """
    4섹션 구조화 검색 로그.

    분쟁조정, 상담, 법령, 기준의 4섹션 검색 결과를 통합합니다.
    """

    domain: Optional[DomainLog] = None
    disputes: List[DisputeLog] = field(default_factory=list)
    counsels: List[CounselLog] = field(default_factory=list)
    laws: List[LawLog] = field(default_factory=list)
    criteria: List[CriteriaLog] = field(default_factory=list)


# ============================================================
# 데이터 클래스 정의 - 노드 타이밍
# ============================================================


@dataclass
class NodeTimingLog:
    """
    노드 실행 시간 로그.

    LangGraph 노드별 실행 시간과 I/O 추적 정보를 기록합니다.
    """

    node_name: str  # 노드 이름
    duration_ms: float  # 실행 시간 (밀리초)
    start_time: str  # 시작 시간 (ISO 형식)
    end_time: str  # 종료 시간 (ISO 형식)
    input_snapshot: Optional[Dict] = None  # 입력 상태 스냅샷
    output_snapshot: Optional[Dict] = None  # 출력 상태 스냅샷
    state_changes: List[str] = field(default_factory=list)  # 변경된 필드 목록


@dataclass
class InputLog:
    """
    입력 로그.

    프론트엔드에서 전달된 요청 데이터를 기록합니다.
    """

    message: str  # 사용자 메시지
    session_id: Optional[str] = None  # 세션 ID
    chat_type: str = "dispute"  # 채팅 유형 (dispute | general)
    onboarding: Optional[Dict] = None  # 온보딩 정보
    top_k: int = 5  # 검색 결과 개수
    chunk_types: Optional[List[str]] = None  # 청크 유형 필터
    agencies: Optional[List[str]] = None  # 기관 필터


# ============================================================
# 메인 로그 엔트리
# ============================================================


@dataclass
class RAGLogEntry:
    """
    RAG 파이프라인 전체 로그 엔트리.

    하나의 채팅 요청에 대한 전체 파이프라인 실행 정보를 담습니다.
    """

    request_id: str  # 요청 고유 ID
    timestamp: str  # 타임스탬프 (ISO 형식)
    query: str  # 사용자 쿼리
    input_data: Optional[InputLog] = None  # 입력 데이터
    retrieval: RetrievalLog = field(
        default_factory=lambda: RetrievalLog(mode="", top_k=0)
    )
    structured_retrieval: Optional[StructuredRetrievalLog] = None
    llm: LLMLog = field(default_factory=LLMLog)
    response: ResponseSummary = field(default_factory=ResponseSummary)
    total_time_ms: float = 0.0  # 전체 실행 시간 (밀리초)
    node_timings: List[NodeTimingLog] = field(default_factory=list)
    pipeline_trace: Optional[Dict] = None


# ============================================================
# RAG 로거 클래스
# ============================================================


class RAGLogger:
    """
    RAG 파이프라인 로거.

    RAG 파이프라인의 각 단계를 JSON 형식으로 기록합니다.
    로그 파일은 날짜별 디렉토리에 저장됩니다.

    사용 예시:
        logger = RAGLogger()
        entry = logger.create_entry(query="환불 가능한가요?")

        # ... 파이프라인 실행 ...

        logger.finalize(entry, start_time)
        logger.save(entry)

    Attributes:
        log_dir: 로그 파일 저장 디렉토리
        enabled: 로깅 활성화 여부
    """

    def __init__(self, log_dir: Optional[str] = None):
        """
        RAG 로거를 초기화합니다.

        Args:
            log_dir: 로그 저장 디렉토리 (None이면 기본값 사용)
        """
        resolved_dir = log_dir if log_dir else RAG_LOG_DIR
        backend_dir = Path(__file__).parent.parent.parent
        self.log_dir = backend_dir / resolved_dir
        self.enabled = is_rag_logging_enabled()

        if self.enabled:
            self.log_dir.mkdir(parents=True, exist_ok=True)

    def create_entry(self, query: str, request_id: Optional[str] = None) -> RAGLogEntry:
        """
        새 로그 엔트리를 생성합니다.

        Args:
            query: 사용자 쿼리
            request_id: 요청 ID (None이면 자동 생성)

        Returns:
            초기화된 RAGLogEntry 인스턴스
        """
        return RAGLogEntry(
            request_id=request_id or str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            query=query,
        )

    def log_input(
        self,
        entry: RAGLogEntry,
        message: str,
        session_id: Optional[str] = None,
        chat_type: str = "dispute",
        onboarding: Optional[Dict] = None,
        top_k: int = 5,
        chunk_types: Optional[List[str]] = None,
        agencies: Optional[List[str]] = None,
    ) -> None:
        """
        입력 데이터를 기록합니다.

        Args:
            entry: 로그 엔트리
            message: 사용자 메시지
            session_id: 세션 ID
            chat_type: 채팅 유형
            onboarding: 온보딩 정보
            top_k: 검색 결과 개수
            chunk_types: 청크 유형 필터
            agencies: 기관 필터
        """
        entry.input_data = InputLog(
            message=message,
            session_id=session_id,
            chat_type=chat_type,
            onboarding=onboarding,
            top_k=top_k,
            chunk_types=chunk_types,
            agencies=agencies,
        )

    def log_retrieval(
        self,
        entry: RAGLogEntry,
        mode: str,
        top_k: int,
        embedding_time_ms: float,
        search_time_ms: float,
        chunks: List[Dict],
        dense_candidates: int = 0,
        lexical_candidates: int = 0,
    ) -> None:
        """
        검색 결과를 기록합니다.

        Args:
            entry: 로그 엔트리
            mode: 검색 모드
            top_k: 검색 결과 개수
            embedding_time_ms: 임베딩 생성 시간
            search_time_ms: 검색 실행 시간
            chunks: 검색된 청크 목록
            dense_candidates: Dense 검색 후보 수
            lexical_candidates: Lexical 검색 후보 수
        """
        chunk_logs = [
            ChunkLog(
                chunk_id=c.get("chunk_id", ""),
                doc_id=c.get("doc_id", ""),
                doc_title=c.get("doc_title", ""),
                doc_type=c.get("doc_type", ""),
                chunk_type=c.get("chunk_type", ""),
                source_org=c.get("source_org", ""),
                similarity=c.get("similarity", 0.0),
                content_preview=c.get("content", "")[:200] if c.get("content") else "",
            )
            for c in chunks
        ]

        entry.retrieval = RetrievalLog(
            mode=mode,
            top_k=top_k,
            embedding_time_ms=embedding_time_ms,
            search_time_ms=search_time_ms,
            dense_candidates=dense_candidates,
            lexical_candidates=lexical_candidates,
            chunks=chunk_logs,
        )

    def log_structured_retrieval(
        self,
        entry: RAGLogEntry,
        agency_info: Dict,
        disputes: List[Dict],
        counsels: List[Dict],
        laws: List[Dict],
        criteria: List[Dict],
    ) -> None:
        """
        4섹션 구조화 검색 결과를 기록합니다.

        Args:
            entry: 로그 엔트리
            agency_info: 기관 추천 정보
            disputes: 분쟁조정 사례 목록
            counsels: 상담 사례 목록
            laws: 법령 목록
            criteria: 분쟁해결기준 목록
        """
        domain_log = DomainLog(
            agency=agency_info.get("agency", ""),
            dispute_type=agency_info.get("dispute_type", ""),
            reason=agency_info.get("reason", ""),
            confidence=agency_info.get("confidence", 0.0),
            matched_keywords=agency_info.get("matched_keywords", []),
        )

        dispute_logs = [
            DisputeLog(
                chunk_id=d.get("chunk_id", ""),
                doc_id=d.get("doc_id", ""),
                doc_title=d.get("doc_title", ""),
                source_org=d.get("source_org", ""),
                decision_date=d.get("decision_date"),
                similarity=d.get("similarity", 0.0),
                content_preview=(d.get("content") or "")[:200],
                product_item=d.get("product_item"),
                dispute_amount=d.get("dispute_amount"),
                transaction_date=d.get("transaction_date"),
                mediation_result=d.get("mediation_result"),
            )
            for d in disputes
        ]

        counsel_logs = [
            CounselLog(
                chunk_id=c.get("chunk_id", ""),
                doc_id=c.get("doc_id", ""),
                doc_title=c.get("doc_title", ""),
                source_org=c.get("source_org", ""),
                similarity=c.get("similarity", 0.0),
                content_preview=(c.get("content") or "")[:200],
            )
            for c in counsels
        ]

        law_logs = [
            LawLog(
                unit_id=law.get("unit_id", ""),
                law_name=law.get("law_name", ""),
                full_path=law.get("full_path", ""),
                similarity=law.get("similarity", 0.0),
                text_preview=(law.get("text") or "")[:200],
            )
            for law in laws
        ]

        criteria_logs = [
            CriteriaLog(
                unit_id=cr.get("unit_id", ""),
                source_label=cr.get("source_label", ""),
                category=cr.get("category", ""),
                industry=cr.get("industry", ""),
                item_group=cr.get("item_group", ""),
                item=cr.get("item", ""),
                similarity=cr.get("similarity", 0.0),
                text_preview=(cr.get("unit_text") or "")[:200],
            )
            for cr in criteria
        ]

        entry.structured_retrieval = StructuredRetrievalLog(
            domain=domain_log,
            disputes=dispute_logs,
            counsels=counsel_logs,
            laws=law_logs,
            criteria=criteria_logs,
        )

    def log_llm(
        self,
        entry: RAGLogEntry,
        model: str,
        system_prompt: str,
        user_prompt: str,
        response_time_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        has_sufficient_evidence: bool = True,
        clarifying_questions: Optional[List[str]] = None,
    ) -> None:
        """
        LLM 호출 정보를 기록합니다.

        [SEC-12] 프로덕션 환경에서는 시스템 프롬프트를 해시로 대체하여
        로그를 통한 프롬프트 유출을 방지합니다.

        Args:
            entry: 로그 엔트리
            model: 사용된 모델명
            system_prompt: 시스템 프롬프트
            user_prompt: 사용자 프롬프트
            response_time_ms: 응답 시간
            prompt_tokens: 입력 토큰 수
            completion_tokens: 출력 토큰 수
            has_sufficient_evidence: 충분한 증거 존재 여부
            clarifying_questions: 명확화 질문 목록
        """
        # SEC-12: 프로덕션에서 시스템 프롬프트 해싱
        logged_system_prompt = system_prompt
        if HASH_SYSTEM_PROMPT and APP_ENV == "production" and system_prompt:
            prompt_hash = hashlib.sha256(system_prompt.encode()).hexdigest()[:16]
            logged_system_prompt = f"[HASH:{prompt_hash}]"
            logger.debug("[SEC-12] System prompt hashed for production logging")

        entry.llm = LLMLog(
            model=model,
            system_prompt=logged_system_prompt,
            user_prompt=user_prompt,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            response_time_ms=response_time_ms,
            has_sufficient_evidence=has_sufficient_evidence,
            clarifying_questions=clarifying_questions or [],
        )

    def log_response(
        self,
        entry: RAGLogEntry,
        answer: str,
        chunks_used: int,
        sources_count: int,
        status: str = "success",
        error_message: Optional[str] = None,
    ) -> None:
        """
        응답 요약을 기록합니다.

        Args:
            entry: 로그 엔트리
            answer: 생성된 답변
            chunks_used: 사용된 청크 수
            sources_count: 출처 수
            status: 응답 상태
            error_message: 에러 메시지
        """
        entry.response = ResponseSummary(
            answer_length=len(answer) if answer else 0,
            chunks_used=chunks_used,
            sources_count=sources_count,
            status=status,
            error_message=error_message,
        )

    def log_node_timings(
        self, entry: RAGLogEntry, node_timings: Dict[str, Dict]
    ) -> None:
        """
        노드 실행 시간을 기록합니다.

        Args:
            entry: 로그 엔트리
            node_timings: 노드별 타이밍 정보 딕셔너리
        """
        timing_logs = []
        for node_name, timing in node_timings.items():
            start_ts = timing.get("start", 0)
            end_ts = timing.get("end", 0)
            timing_logs.append(
                NodeTimingLog(
                    node_name=node_name,
                    duration_ms=timing.get("duration_ms", 0.0),
                    start_time=(
                        datetime.fromtimestamp(start_ts).isoformat() if start_ts else ""
                    ),
                    end_time=(
                        datetime.fromtimestamp(end_ts).isoformat() if end_ts else ""
                    ),
                    input_snapshot=timing.get("input_snapshot"),
                    output_snapshot=timing.get("output_snapshot"),
                    state_changes=timing.get("state_changes", []),
                )
            )
        entry.node_timings = timing_logs

    def log_pipeline_trace(
        self,
        entry: RAGLogEntry,
        pipeline_summary: Dict,
    ) -> None:
        """
        에이전트 파이프라인 트레이스를 기록합니다.

        Args:
            entry: 로그 엔트리
            pipeline_summary: build_pipeline_summary()의 반환값
        """
        entry.pipeline_trace = pipeline_summary
        logger.info(
            f"[PIPELINE TRACE] request={entry.request_id[:8]} "
            f"nodes={pipeline_summary.get('node_count', 0)} "
            f"total={pipeline_summary.get('total_duration_ms', 0):.0f}ms | "
            f"path: {' > '.join(pipeline_summary.get('node_sequence', []))}"
        )

    def finalize(self, entry: RAGLogEntry, start_time: float) -> None:
        """
        로그 엔트리를 마무리합니다.

        Args:
            entry: 로그 엔트리
            start_time: 시작 시간 (time.time() 값)
        """
        entry.total_time_ms = (time.time() - start_time) * 1000

    def save(self, entry: RAGLogEntry) -> Optional[str]:
        """
        로그 엔트리를 JSON 파일로 저장합니다.

        Args:
            entry: 로그 엔트리

        Returns:
            저장된 파일 경로 (로깅 비활성화 시 None)
        """
        if not self.enabled:
            return None

        # 날짜별 서브디렉토리 생성
        dt = datetime.fromisoformat(entry.timestamp)
        date_dir = self.log_dir / dt.strftime("%Y-%m-%d")
        date_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{dt.strftime('%H%M%S')}_{entry.request_id[:8]}.json"
        filepath = date_dir / filename

        log_dict = asdict(entry)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(log_dict, f, ensure_ascii=False, indent=2)

        return str(filepath)


# ============================================================
# 싱글톤 인스턴스 관리
# ============================================================

_logger_instance: Optional[RAGLogger] = None


def get_rag_logger() -> RAGLogger:
    """
    RAG 로거 싱글톤 인스턴스를 반환합니다.

    Returns:
        RAGLogger 인스턴스
    """
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = RAGLogger()
    return _logger_instance
