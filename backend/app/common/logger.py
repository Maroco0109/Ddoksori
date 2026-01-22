"""
RAG Pipeline Logger

Captures detailed JSON logs for debugging and analysis.
Each chat request generates a JSON file with:
- Query info
- Retrieved chunks with similarity scores
- LLM prompts and token usage
- Response timing
"""

import os
import json
import uuid
import time
from datetime import datetime
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional
from pathlib import Path


@dataclass
class ChunkLog:
    """검색된 청크 로그"""
    chunk_id: str
    doc_id: str
    doc_title: str
    doc_type: str
    chunk_type: str
    source_org: str
    similarity: float
    content_preview: str  # First 200 chars


@dataclass
class RetrievalLog:
    """검색 단계 로그"""
    mode: str  # "dense" | "hybrid"
    top_k: int
    embedding_time_ms: float = 0.0
    search_time_ms: float = 0.0
    dense_candidates: int = 0
    lexical_candidates: int = 0
    chunks: List[ChunkLog] = field(default_factory=list)


@dataclass
class LLMLog:
    """LLM 호출 로그"""
    model: str = ""
    system_prompt: str = ""
    user_prompt: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    response_time_ms: float = 0.0
    has_sufficient_evidence: bool = True
    clarifying_questions: List[str] = field(default_factory=list)


@dataclass
class ResponseSummary:
    """응답 요약"""
    answer_length: int = 0
    chunks_used: int = 0
    sources_count: int = 0
    status: str = "success"  # "success" | "no_results" | "error"
    error_message: Optional[str] = None


# ============================================================
# 4-Section Structured Retrieval Logs (for /chat endpoint)
# ============================================================

@dataclass
class DomainLog:
    """기관 추천 로그"""
    agency: str  # KCA, ECMC, KCDRC
    dispute_type: str  # 1:N, 1:1, contents
    reason: str  # Why this agency was chosen
    confidence: float
    matched_keywords: List[str] = field(default_factory=list)


@dataclass
class DisputeLog:
    """분쟁조정 사례 로그 (메타데이터 포함)"""
    chunk_id: str
    doc_id: str
    doc_title: str
    source_org: str
    decision_date: Optional[str]
    similarity: float
    content_preview: str  # 200 chars
    # Phase 2: 실시간 LLM 추출 메타데이터
    product_item: Optional[str] = None        # 품목 (예: "키보드", "헬스회원권")
    dispute_amount: Optional[str] = None      # 금액 (예: "120,000원")
    transaction_date: Optional[str] = None    # 거래/구매 일자
    mediation_result: Optional[str] = None    # 조정결과 (예: "인용", "기각", "조정성립")


@dataclass
class CounselLog:
    """상담 사례 로그"""
    chunk_id: str
    doc_id: str
    doc_title: str
    source_org: str
    similarity: float
    content_preview: str  # 200 chars


@dataclass
class LawLog:
    """법령 로그"""
    unit_id: str
    law_name: str
    full_path: str  # 제14조 제1항
    similarity: float
    text_preview: str  # 200 chars


@dataclass
class CriteriaLog:
    """기준 로그"""
    unit_id: str
    source_label: str
    category: str
    industry: str
    item_group: str
    item: str
    similarity: float
    text_preview: str  # 200 chars


@dataclass
class StructuredRetrievalLog:
    """4섹션 구조화 검색 로그"""
    domain: Optional[DomainLog] = None
    disputes: List[DisputeLog] = field(default_factory=list)
    counsels: List[CounselLog] = field(default_factory=list)
    laws: List[LawLog] = field(default_factory=list)
    criteria: List[CriteriaLog] = field(default_factory=list)


@dataclass
class NodeTimingLog:
    """노드 실행 시간 로그 (I/O 추적 포함)"""
    node_name: str
    duration_ms: float
    start_time: str
    end_time: str
    # I/O 추적 필드 (Phase 1 개선)
    input_snapshot: Optional[Dict] = None      # 노드 입력 상태 스냅샷
    output_snapshot: Optional[Dict] = None     # 노드 출력 상태 스냅샷
    state_changes: List[str] = field(default_factory=list)  # 변경된 필드 목록


@dataclass
class InputLog:
    """입력 로그 (프론트엔드에서 전달된 전체 데이터)"""
    message: str
    session_id: Optional[str] = None
    chat_type: str = "dispute"
    onboarding: Optional[Dict] = None
    top_k: int = 5
    chunk_types: Optional[List[str]] = None
    agencies: Optional[List[str]] = None


@dataclass
class RAGLogEntry:
    """RAG 파이프라인 전체 로그 엔트리"""
    request_id: str
    timestamp: str
    query: str
    input_data: Optional[InputLog] = None
    retrieval: RetrievalLog = field(default_factory=lambda: RetrievalLog(mode="", top_k=0))
    structured_retrieval: Optional[StructuredRetrievalLog] = None
    llm: LLMLog = field(default_factory=LLMLog)
    response: ResponseSummary = field(default_factory=ResponseSummary)
    total_time_ms: float = 0.0
    node_timings: List[NodeTimingLog] = field(default_factory=list)


class RAGLogger:
    """
    RAG 파이프라인 로거

    Usage:
        logger = RAGLogger()
        entry = logger.create_entry(query="환불 가능한가요?")

        # ... pipeline execution with log_retrieval(), log_llm() calls ...

        logger.finalize(entry, start_time)
        logger.save(entry)
    """

    def __init__(self, log_dir: Optional[str] = None):
        resolved_dir = log_dir if log_dir else os.getenv('RAG_LOG_DIR', 'logs/rag')
        backend_dir = Path(__file__).parent.parent
        self.log_dir = backend_dir / resolved_dir
        self.enabled = os.getenv('RAG_LOG_ENABLED', 'true').lower() == 'true'

        if self.enabled:
            self.log_dir.mkdir(parents=True, exist_ok=True)

    def create_entry(self, query: str, request_id: Optional[str] = None) -> RAGLogEntry:
        """Create a new log entry for a request."""
        return RAGLogEntry(
            request_id=request_id or str(uuid.uuid4()),
            timestamp=datetime.now().isoformat(),
            query=query
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
        agencies: Optional[List[str]] = None
    ) -> None:
        entry.input_data = InputLog(
            message=message,
            session_id=session_id,
            chat_type=chat_type,
            onboarding=onboarding,
            top_k=top_k,
            chunk_types=chunk_types,
            agencies=agencies
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
        lexical_candidates: int = 0
    ) -> None:
        chunk_logs = [
            ChunkLog(
                chunk_id=c.get('chunk_id', ''),
                doc_id=c.get('doc_id', ''),
                doc_title=c.get('doc_title', ''),
                doc_type=c.get('doc_type', ''),
                chunk_type=c.get('chunk_type', ''),
                source_org=c.get('source_org', ''),
                similarity=c.get('similarity', 0.0),
                content_preview=c.get('content', '')[:200] if c.get('content') else ''
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
            chunks=chunk_logs
        )

    def log_structured_retrieval(
        self,
        entry: RAGLogEntry,
        agency_info: Dict,
        disputes: List[Dict],
        counsels: List[Dict],
        laws: List[Dict],
        criteria: List[Dict]
    ) -> None:
        """Log 4-section structured retrieval results."""
        domain_log = DomainLog(
            agency=agency_info.get('agency', ''),
            dispute_type=agency_info.get('dispute_type', ''),
            reason=agency_info.get('reason', ''),
            confidence=agency_info.get('confidence', 0.0),
            matched_keywords=agency_info.get('matched_keywords', [])
        )

        dispute_logs = [
            DisputeLog(
                chunk_id=d.get('chunk_id', ''),
                doc_id=d.get('doc_id', ''),
                doc_title=d.get('doc_title', ''),
                source_org=d.get('source_org', ''),
                decision_date=d.get('decision_date'),
                similarity=d.get('similarity', 0.0),
                content_preview=(d.get('content') or '')[:200],
                # Phase 2: 메타데이터 필드
                product_item=d.get('product_item'),
                dispute_amount=d.get('dispute_amount'),
                transaction_date=d.get('transaction_date'),
                mediation_result=d.get('mediation_result'),
            ) for d in disputes
        ]

        counsel_logs = [
            CounselLog(
                chunk_id=c.get('chunk_id', ''),
                doc_id=c.get('doc_id', ''),
                doc_title=c.get('doc_title', ''),
                source_org=c.get('source_org', ''),
                similarity=c.get('similarity', 0.0),
                content_preview=(c.get('content') or '')[:200]
            ) for c in counsels
        ]

        law_logs = [
            LawLog(
                unit_id=l.get('unit_id', ''),
                law_name=l.get('law_name', ''),
                full_path=l.get('full_path', ''),
                similarity=l.get('similarity', 0.0),
                text_preview=(l.get('text') or '')[:200]
            ) for l in laws
        ]

        criteria_logs = [
            CriteriaLog(
                unit_id=cr.get('unit_id', ''),
                source_label=cr.get('source_label', ''),
                category=cr.get('category', ''),
                industry=cr.get('industry', ''),
                item_group=cr.get('item_group', ''),
                item=cr.get('item', ''),
                similarity=cr.get('similarity', 0.0),
                text_preview=(cr.get('unit_text') or '')[:200]
            ) for cr in criteria
        ]

        entry.structured_retrieval = StructuredRetrievalLog(
            domain=domain_log,
            disputes=dispute_logs,
            counsels=counsel_logs,
            laws=law_logs,
            criteria=criteria_logs
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
        clarifying_questions: Optional[List[str]] = None
    ) -> None:
        """Log LLM interaction details."""
        entry.llm = LLMLog(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            response_time_ms=response_time_ms,
            has_sufficient_evidence=has_sufficient_evidence,
            clarifying_questions=clarifying_questions or []
        )

    def log_response(
        self,
        entry: RAGLogEntry,
        answer: str,
        chunks_used: int,
        sources_count: int,
        status: str = "success",
        error_message: Optional[str] = None
    ) -> None:
        """Log response summary."""
        entry.response = ResponseSummary(
            answer_length=len(answer) if answer else 0,
            chunks_used=chunks_used,
            sources_count=sources_count,
            status=status,
            error_message=error_message
        )

    def log_node_timings(
        self,
        entry: RAGLogEntry,
        node_timings: Dict[str, Dict]
    ) -> None:
        """Log node execution timings from LangGraph state (with I/O snapshots)."""
        timing_logs = []
        for node_name, timing in node_timings.items():
            start_ts = timing.get('start', 0)
            end_ts = timing.get('end', 0)
            timing_logs.append(NodeTimingLog(
                node_name=node_name,
                duration_ms=timing.get('duration_ms', 0.0),
                start_time=datetime.fromtimestamp(start_ts).isoformat() if start_ts else '',
                end_time=datetime.fromtimestamp(end_ts).isoformat() if end_ts else '',
                input_snapshot=timing.get('input_snapshot'),
                output_snapshot=timing.get('output_snapshot'),
                state_changes=timing.get('state_changes', [])
            ))
        entry.node_timings = timing_logs

    def finalize(self, entry: RAGLogEntry, start_time: float) -> None:
        """Finalize the log entry with total time."""
        entry.total_time_ms = (time.time() - start_time) * 1000

    def save(self, entry: RAGLogEntry) -> Optional[str]:
        """
        Save log entry to JSON file.

        Returns:
            filepath if saved, None if logging disabled
        """
        if not self.enabled:
            return None

        # Organize by date subdirectory
        dt = datetime.fromisoformat(entry.timestamp)
        date_dir = self.log_dir / dt.strftime('%Y-%m-%d')
        date_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{dt.strftime('%H%M%S')}_{entry.request_id[:8]}.json"
        filepath = date_dir / filename

        log_dict = asdict(entry)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(log_dict, f, ensure_ascii=False, indent=2)

        return str(filepath)


# Singleton instance
_logger_instance: Optional[RAGLogger] = None


def get_rag_logger() -> RAGLogger:
    """Get or create the singleton RAG logger instance."""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = RAGLogger()
    return _logger_instance
