import pytest
from httpx import ASGITransport, AsyncClient
from prometheus_client import REGISTRY

from app.common.metrics import PROM_AGENT_LATENCY, PROM_AGENT_REQUESTS, AgentMetrics
from app.main import app


@pytest.mark.asyncio
async def test_metrics_endpoint():
    """Verify /metrics endpoint is exposed and returns Prometheus format"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Trigger a metric recording to ensure it shows up (lazy init sometimes hides metrics)
        AgentMetrics.record_manual("init_check", "test", 0.1)

        response = await ac.get("/metrics")
        assert response.status_code == 200
        assert "agent_execution_seconds_bucket" in response.text
        assert "agent_requests_total" in response.text
        # Verify FastAPI instrumentator metrics are also present
        assert "http_requests_total" in response.text


@pytest.mark.asyncio
async def test_agent_metrics_recording():
    """Verify AgentMetrics correctly updates Prometheus counters"""
    # Reset specific metrics for testing
    agent_name = "test_agent"

    # Run a measured block
    with AgentMetrics.measure(agent_name, "test_op"):
        pass  # instantaneous

    # Check if Prometheus metric was updated
    # Note: Accessing REGISTRY directly to verify values is complex in integration tests
    # So we verify via the endpoint or by checking the metric object logic

    # Verify via custom endpoint for stats (in-memory)
    stats = AgentMetrics.get_stats(agent_name)
    assert stats["count"] >= 1

    # Verify Prometheus sample value directly if possible,
    # or rely on the endpoint test which confirms exposure.

    # Simple check on the python object wrapper
    before = PROM_AGENT_REQUESTS.labels(
        agent_name=agent_name, status="success"
    )._value.get()

    with AgentMetrics.measure(agent_name, "test_op_2"):
        pass

    after = PROM_AGENT_REQUESTS.labels(
        agent_name=agent_name, status="success"
    )._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_tool_usage_tracking():
    """Verify Tool Usage counters are defined"""
    from app.common.metrics import PROM_TOOL_USAGE

    tool_name = "test_tool"
    mode = "rule"

    before = PROM_TOOL_USAGE.labels(tool_name=tool_name, mode=mode)._value.get()
    PROM_TOOL_USAGE.labels(tool_name=tool_name, mode=mode).inc()
    after = PROM_TOOL_USAGE.labels(tool_name=tool_name, mode=mode)._value.get()

    assert after == before + 1
