"""
S2-PR5: Agent Performance Metrics Collection
"""

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Generator

logger = logging.getLogger(__name__)


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
        metadata: Optional[Dict[str, Any]] = None
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
            cls._metrics[agent_name] = cls._metrics[agent_name][-cls._max_records_per_agent:]
    
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
    
    @classmethod
    def get_stats(cls, agent_name: Optional[str] = None) -> Dict[str, Any]:
        if agent_name:
            records = cls._metrics.get(agent_name, [])
        else:
            records = [r for agent_records in cls._metrics.values() for r in agent_records]
        
        if not records:
            return {
                'count': 0,
                'success_rate': 0.0,
                'avg_duration_ms': 0.0,
                'max_duration_ms': 0.0,
                'min_duration_ms': 0.0,
                'p50_duration_ms': None,
                'p95_duration_ms': None,
                'p99_duration_ms': None,
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
            'count': n,
            'success_rate': round(len(successes) / n * 100, 2),
            'avg_duration_ms': round(sum(durations) / n, 2),
            'max_duration_ms': round(max(durations), 2),
            'min_duration_ms': round(min(durations), 2),
            'p50_duration_ms': percentile(0.50),
            'p95_duration_ms': percentile(0.95),
            'p99_duration_ms': percentile(0.99),
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
                'count': n,
                'success_rate': round(len(successes) / n * 100, 2),
                'avg_duration_ms': round(sum(durations) / n, 2),
            }
        
        return result
    
    @classmethod
    def get_all_agents(cls) -> List[str]:
        return list(cls._metrics.keys())
    
    @classmethod
    def get_recent_records(
        cls, 
        agent_name: Optional[str] = None, 
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        if agent_name:
            records = cls._metrics.get(agent_name, [])
        else:
            records = [r for agent_records in cls._metrics.values() for r in agent_records]
        
        records = sorted(records, key=lambda r: r.timestamp, reverse=True)[:limit]
        
        return [
            {
                'agent': r.agent,
                'operation': r.operation,
                'duration_ms': round(r.duration_ms, 2),
                'success': r.success,
                'error': r.error,
                'timestamp': r.timestamp,
                'metadata': r.metadata,
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
            'total_agents': len(agents),
            'total_records': sum(len(cls._metrics.get(a, [])) for a in agents),
            'agents': {},
        }
        
        for agent in agents:
            summary['agents'][agent] = cls.get_stats(agent)
        
        return summary
