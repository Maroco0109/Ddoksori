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


@dataclass
class RAGLogEntry:
    """RAG 파이프라인 전체 로그 엔트리"""
    request_id: str
    timestamp: str
    query: str
    retrieval: RetrievalLog = field(default_factory=lambda: RetrievalLog(mode="", top_k=0))
    llm: LLMLog = field(default_factory=LLMLog)
    response: ResponseSummary = field(default_factory=ResponseSummary)
    total_time_ms: float = 0.0


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

    def __init__(self, log_dir: str = None):
        """
        Initialize RAG Logger.

        Args:
            log_dir: Directory for log files. Defaults to 'logs/rag' relative to backend/
        """
        if log_dir is None:
            log_dir = os.getenv('RAG_LOG_DIR', 'logs/rag')

        # Make path relative to backend directory
        backend_dir = Path(__file__).parent.parent
        self.log_dir = backend_dir / log_dir
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
        """Log retrieval results."""
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
        clarifying_questions: List[str] = None
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
