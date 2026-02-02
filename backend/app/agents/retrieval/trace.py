"""
RetrievalTrace - Trace/logging schema for retrieval operations
Sprint 3 - s3-5: Retrieval observability
"""

import logging
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ENABLE_RETRIEVAL_TRACE = os.getenv("ENABLE_RETRIEVAL_TRACE", "false").lower() == "true"


@dataclass
class RetrieverStep:
    retriever_type: str
    query: str
    top_k: int
    result_count: int
    elapsed_ms: float
    filters: Dict[str, Any] = field(default_factory=dict)
    top_similarities: List[float] = field(default_factory=list)


@dataclass
class RetrievalTrace:
    session_id: str
    query: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    steps: List[RetrieverStep] = field(default_factory=list)
    total_elapsed_ms: float = 0.0
    final_result_count: int = 0

    search_plan: Optional[Dict[str, Any]] = None
    fusion_method: Optional[str] = None

    def add_step(
        self,
        retriever_type: str,
        query: str,
        top_k: int,
        results: List[Any],
        elapsed_ms: float,
        filters: Optional[Dict[str, Any]] = None,
    ):
        top_sims = []
        for r in results[:5]:
            if hasattr(r, "similarity"):
                top_sims.append(float(r.similarity))
            elif isinstance(r, dict) and "similarity" in r:
                top_sims.append(float(r["similarity"]))

        step = RetrieverStep(
            retriever_type=retriever_type,
            query=query,
            top_k=top_k,
            result_count=len(results),
            elapsed_ms=elapsed_ms,
            filters=filters or {},
            top_similarities=top_sims,
        )
        self.steps.append(step)

    def finalize(self, final_count: int):
        self.final_result_count = final_count
        self.total_elapsed_ms = sum(s.elapsed_ms for s in self.steps)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "query": self.query,
            "timestamp": self.timestamp,
            "steps": [asdict(s) for s in self.steps],
            "total_elapsed_ms": self.total_elapsed_ms,
            "final_result_count": self.final_result_count,
            "search_plan": self.search_plan,
            "fusion_method": self.fusion_method,
        }


class TraceContext:
    _current: Optional[RetrievalTrace] = None

    @classmethod
    def start(cls, session_id: str, query: str) -> Optional[RetrievalTrace]:
        if not ENABLE_RETRIEVAL_TRACE:
            return None

        cls._current = RetrievalTrace(session_id=session_id, query=query)
        return cls._current

    @classmethod
    def current(cls) -> Optional[RetrievalTrace]:
        return cls._current

    @classmethod
    def end(cls) -> Optional[RetrievalTrace]:
        trace = cls._current
        cls._current = None

        if trace and ENABLE_RETRIEVAL_TRACE:
            logger.info(
                f"[RetrievalTrace] session={trace.session_id} "
                f"steps={len(trace.steps)} "
                f"total_ms={trace.total_elapsed_ms:.1f} "
                f"final_count={trace.final_result_count}"
            )

        return trace


def trace_retriever(retriever_type: str):
    def decorator(func):
        def wrapper(self, query: str, top_k: int = 10, **kwargs):
            trace = TraceContext.current()

            start = time.time()
            results = func(self, query, top_k, **kwargs)
            elapsed = (time.time() - start) * 1000

            if trace:
                filters = {k: v for k, v in kwargs.items() if v is not None}
                trace.add_step(
                    retriever_type=retriever_type,
                    query=query,
                    top_k=top_k,
                    results=results,
                    elapsed_ms=elapsed,
                    filters=filters,
                )

            return results

        return wrapper

    return decorator
