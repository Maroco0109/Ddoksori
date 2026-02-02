"""
S2-PR5: AgentMetrics 테스트
"""

import time

import pytest

from app.common.metrics import AgentMetrics, MetricRecord


class TestMeasureContextManager:
    def setup_method(self):
        AgentMetrics.clear()

    def test_measure_records_successful_execution(self):
        with AgentMetrics.measure("test_agent", "test_op"):
            time.sleep(0.01)

        stats = AgentMetrics.get_stats("test_agent")

        assert stats["count"] == 1
        assert stats["success_rate"] == 100.0
        assert stats["avg_duration_ms"] >= 10

    def test_measure_records_failed_execution(self):
        with pytest.raises(ValueError):
            with AgentMetrics.measure("test_agent", "test_op"):
                raise ValueError("Test error")

        stats = AgentMetrics.get_stats("test_agent")

        assert stats["count"] == 1
        assert stats["success_rate"] == 0.0

    def test_measure_with_metadata(self):
        with AgentMetrics.measure("test_agent", "test_op", metadata={"key": "value"}):
            pass

        records = AgentMetrics.get_recent_records("test_agent", limit=1)

        assert records[0]["metadata"] == {"key": "value"}


class TestRecordManual:
    def setup_method(self):
        AgentMetrics.clear()

    def test_record_manual_stores_metric(self):
        AgentMetrics.record_manual(
            agent_name="test_agent",
            operation="manual_op",
            duration_ms=50.0,
            success=True,
        )

        stats = AgentMetrics.get_stats("test_agent")

        assert stats["count"] == 1
        assert stats["avg_duration_ms"] == 50.0


class TestGetStats:
    def setup_method(self):
        AgentMetrics.clear()

    def test_get_stats_empty(self):
        stats = AgentMetrics.get_stats("nonexistent")

        assert stats["count"] == 0
        assert stats["success_rate"] == 0.0

    def test_get_stats_multiple_records(self):
        for i in range(10):
            AgentMetrics.record_manual("test_agent", "op", float(i * 10), success=True)

        stats = AgentMetrics.get_stats("test_agent")

        assert stats["count"] == 10
        assert stats["success_rate"] == 100.0
        assert stats["min_duration_ms"] == 0.0
        assert stats["max_duration_ms"] == 90.0

    def test_get_stats_all_agents(self):
        AgentMetrics.record_manual("agent1", "op", 10.0)
        AgentMetrics.record_manual("agent2", "op", 20.0)

        stats = AgentMetrics.get_stats()

        assert stats["count"] == 2

    def test_get_stats_percentiles(self):
        for i in range(100):
            AgentMetrics.record_manual("test_agent", "op", float(i))

        stats = AgentMetrics.get_stats("test_agent")

        assert stats["p50_duration_ms"] == 50.0
        assert stats["p95_duration_ms"] == 95.0
        assert stats["p99_duration_ms"] == 99.0


class TestGetStatsByOperation:
    def setup_method(self):
        AgentMetrics.clear()

    def test_stats_by_operation(self):
        AgentMetrics.record_manual("test_agent", "op1", 10.0)
        AgentMetrics.record_manual("test_agent", "op1", 20.0)
        AgentMetrics.record_manual("test_agent", "op2", 50.0)

        stats = AgentMetrics.get_stats_by_operation("test_agent")

        assert "op1" in stats
        assert "op2" in stats
        assert stats["op1"]["count"] == 2
        assert stats["op2"]["count"] == 1
        assert stats["op1"]["avg_duration_ms"] == 15.0


class TestGetAllAgents:
    def setup_method(self):
        AgentMetrics.clear()

    def test_get_all_agents_empty(self):
        agents = AgentMetrics.get_all_agents()

        assert agents == []

    def test_get_all_agents_multiple(self):
        AgentMetrics.record_manual("agent1", "op", 10.0)
        AgentMetrics.record_manual("agent2", "op", 20.0)
        AgentMetrics.record_manual("agent3", "op", 30.0)

        agents = AgentMetrics.get_all_agents()

        assert set(agents) == {"agent1", "agent2", "agent3"}


class TestGetRecentRecords:
    def setup_method(self):
        AgentMetrics.clear()

    def test_get_recent_records_ordering(self):
        AgentMetrics.record_manual("test_agent", "op1", 10.0)
        time.sleep(0.01)
        AgentMetrics.record_manual("test_agent", "op2", 20.0)

        records = AgentMetrics.get_recent_records("test_agent", limit=2)

        assert records[0]["operation"] == "op2"
        assert records[1]["operation"] == "op1"

    def test_get_recent_records_limit(self):
        for i in range(10):
            AgentMetrics.record_manual("test_agent", f"op{i}", float(i))

        records = AgentMetrics.get_recent_records("test_agent", limit=5)

        assert len(records) == 5


class TestClear:
    def setup_method(self):
        AgentMetrics.clear()

    def test_clear_specific_agent(self):
        AgentMetrics.record_manual("agent1", "op", 10.0)
        AgentMetrics.record_manual("agent2", "op", 20.0)

        count = AgentMetrics.clear("agent1")

        assert count == 1
        assert AgentMetrics.get_stats("agent1")["count"] == 0
        assert AgentMetrics.get_stats("agent2")["count"] == 1

    def test_clear_all(self):
        AgentMetrics.record_manual("agent1", "op", 10.0)
        AgentMetrics.record_manual("agent2", "op", 20.0)

        count = AgentMetrics.clear()

        assert count == 2
        assert AgentMetrics.get_all_agents() == []


class TestMaxRecordsLimit:
    def setup_method(self):
        AgentMetrics.clear()

    def test_max_records_per_agent(self):
        original_max = AgentMetrics._max_records_per_agent
        AgentMetrics._max_records_per_agent = 5

        try:
            for i in range(10):
                AgentMetrics.record_manual("test_agent", f"op{i}", float(i))

            stats = AgentMetrics.get_stats("test_agent")

            assert stats["count"] == 5
        finally:
            AgentMetrics._max_records_per_agent = original_max


class TestGetSummary:
    def setup_method(self):
        AgentMetrics.clear()

    def test_get_summary(self):
        AgentMetrics.record_manual("agent1", "op", 10.0)
        AgentMetrics.record_manual("agent1", "op", 20.0)
        AgentMetrics.record_manual("agent2", "op", 30.0)

        summary = AgentMetrics.get_summary()

        assert summary["total_agents"] == 2
        assert summary["total_records"] == 3
        assert "agent1" in summary["agents"]
        assert "agent2" in summary["agents"]
        assert summary["agents"]["agent1"]["count"] == 2
        assert summary["agents"]["agent2"]["count"] == 1
