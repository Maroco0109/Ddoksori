"""
S2-PR5: Agent Performance Metrics Collection
"""

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional

from prometheus_client import REGISTRY, Counter, Histogram

logger = logging.getLogger(__name__)

# S3-PR5: Prometheus Metrics Definition
# Initialize metrics eagerly to ensure they appear in the registry
PROM_AGENT_LATENCY = Histogram(
    "agent_execution_seconds", "Time spent in agent execution", ["agent_name"]
)
PROM_AGENT_REQUESTS = Counter(
    "agent_requests_total", "Total number of agent requests", ["agent_name", "status"]
)
PROM_LLM_TOKENS = Counter(
    "llm_tokens_total", "Total LLM tokens used", ["model", "type"]
)
PROM_TOOL_USAGE = Counter(
    "agent_tool_usage_total", "Total tool usage by mode", ["tool_name", "mode"]
)

# S3-PR5: Cache Metrics
PROM_CACHE_HITS = Counter("cache_hits_total", "Total cache hits")
PROM_CACHE_MISSES = Counter("cache_misses_total", "Total cache misses")
PROM_CACHE_ERRORS = Counter("cache_errors_total", "Total cache errors")

# S3-PR5: Cost Metrics
PROM_LLM_COST = Counter("llm_cost_usd_total", "Total LLM API cost in USD", ["model"])
PROM_EMBEDDING_COST = Counter(
    "embedding_cost_usd_total", "Total embedding API cost in USD"
)


@dataclass
class MetricRecord:
    agent: str
    operation: str
    duration_ms: float
    success: bool
    error: Optional[str]
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentMetrics:
    _metrics: Dict[str, List[MetricRecord]] = {}
    _max_records_per_agent: int = 1000

    @classmethod
    @contextmanager
    def measure(
        cls,
        agent_name: str,
        operation: str = "execute",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Generator[None, None, None]:
        start = time.perf_counter()
        error = None

        try:
            yield
        except Exception as e:
            error = e
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000

            record = MetricRecord(
                agent=agent_name,
                operation=operation,
                duration_ms=duration_ms,
                success=error is None,
                error=str(error) if error else None,
                timestamp=time.time(),
                metadata=metadata or {},
            )

            cls._record(agent_name, record)

            # S3-PR5: Prometheus observation
            PROM_AGENT_LATENCY.labels(agent_name=agent_name).observe(
                duration_ms / 1000.0
            )
            status = "success" if error is None else "error"
            PROM_AGENT_REQUESTS.labels(agent_name=agent_name, status=status).inc()

            log_msg = f"[metrics] {agent_name}.{operation}: {duration_ms:.2f}ms"
            if error:
                log_msg += f" (ERROR: {error})"
            logger.debug(log_msg)

    @classmethod
    def _record(cls, agent_name: str, record: MetricRecord) -> None:
        if agent_name not in cls._metrics:
            cls._metrics[agent_name] = []

        cls._metrics[agent_name].append(record)

        if len(cls._metrics[agent_name]) > cls._max_records_per_agent:
            cls._metrics[agent_name] = cls._metrics[agent_name][
                -cls._max_records_per_agent :
            ]

    @classmethod
    def record_manual(
        cls,
        agent_name: str,
        operation: str,
        duration_ms: float,
        success: bool = True,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        record = MetricRecord(
            agent=agent_name,
            operation=operation,
            duration_ms=duration_ms,
            success=success,
            error=error,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        cls._record(agent_name, record)

        # S3-PR5: Prometheus observation (Manual)
        PROM_AGENT_LATENCY.labels(agent_name=agent_name).observe(duration_ms / 1000.0)
        status = "success" if success else "error"
        PROM_AGENT_REQUESTS.labels(agent_name=agent_name, status=status).inc()

    @classmethod
    def get_stats(cls, agent_name: Optional[str] = None) -> Dict[str, Any]:
        if agent_name:
            records = cls._metrics.get(agent_name, [])
        else:
            records = [
                r for agent_records in cls._metrics.values() for r in agent_records
            ]

        if not records:
            return {
                "count": 0,
                "success_rate": 0.0,
                "avg_duration_ms": 0.0,
                "max_duration_ms": 0.0,
                "min_duration_ms": 0.0,
                "p50_duration_ms": None,
                "p95_duration_ms": None,
                "p99_duration_ms": None,
            }

        durations = [r.duration_ms for r in records]
        successes = [r for r in records if r.success]
        sorted_durations = sorted(durations)
        n = len(durations)

        def percentile(p: float) -> Optional[float]:
            if n < 5:
                return None
            idx = int(n * p)
            return sorted_durations[min(idx, n - 1)]

        return {
            "count": n,
            "success_rate": round(len(successes) / n * 100, 2),
            "avg_duration_ms": round(sum(durations) / n, 2),
            "max_duration_ms": round(max(durations), 2),
            "min_duration_ms": round(min(durations), 2),
            "p50_duration_ms": percentile(0.50),
            "p95_duration_ms": percentile(0.95),
            "p99_duration_ms": percentile(0.99),
        }

    @classmethod
    def get_stats_by_operation(cls, agent_name: str) -> Dict[str, Dict[str, Any]]:
        records = cls._metrics.get(agent_name, [])
        if not records:
            return {}

        by_operation: Dict[str, List[MetricRecord]] = {}
        for r in records:
            if r.operation not in by_operation:
                by_operation[r.operation] = []
            by_operation[r.operation].append(r)

        result = {}
        for op, op_records in by_operation.items():
            durations = [r.duration_ms for r in op_records]
            successes = [r for r in op_records if r.success]
            n = len(durations)

            result[op] = {
                "count": n,
                "success_rate": round(len(successes) / n * 100, 2),
                "avg_duration_ms": round(sum(durations) / n, 2),
            }

        return result

    @classmethod
    def get_all_agents(cls) -> List[str]:
        return list(cls._metrics.keys())

    @classmethod
    def get_recent_records(
        cls, agent_name: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        if agent_name:
            records = cls._metrics.get(agent_name, [])
        else:
            records = [
                r for agent_records in cls._metrics.values() for r in agent_records
            ]

        records = sorted(records, key=lambda r: r.timestamp, reverse=True)[:limit]

        return [
            {
                "agent": r.agent,
                "operation": r.operation,
                "duration_ms": round(r.duration_ms, 2),
                "success": r.success,
                "error": r.error,
                "timestamp": r.timestamp,
                "metadata": r.metadata,
            }
            for r in records
        ]

    @classmethod
    def clear(cls, agent_name: Optional[str] = None) -> int:
        if agent_name:
            count = len(cls._metrics.get(agent_name, []))
            cls._metrics[agent_name] = []
            return count
        else:
            count = sum(len(records) for records in cls._metrics.values())
            cls._metrics = {}
            return count

    @classmethod
    def get_summary(cls) -> Dict[str, Any]:
        agents = cls.get_all_agents()

        summary = {
            "total_agents": len(agents),
            "total_records": sum(len(cls._metrics.get(a, [])) for a in agents),
            "agents": {},
        }

        for agent in agents:
            summary["agents"][agent] = cls.get_stats(agent)

        return summary
