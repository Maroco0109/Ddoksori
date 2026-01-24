"""
똑소리 프로젝트 - 메트릭스 라우터

에이전트 성능 메트릭을 조회하는 엔드포인트입니다.
"""

from typing import Optional
from fastapi import APIRouter


router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.get("/agents")
async def get_agent_metrics(agent_name: Optional[str] = None):
    """
    에이전트 성능 메트릭스 조회

    Args:
        agent_name: 특정 에이전트 이름 (없으면 전체)

    Returns:
        성능 통계 (count, success_rate, avg/min/max/p95 duration)
    """
    from app.common.metrics import AgentMetrics
    return AgentMetrics.get_stats(agent_name)


@router.get("/agents/summary")
async def get_agent_metrics_summary():
    """
    전체 에이전트 성능 요약

    Returns:
        모든 에이전트의 성능 요약 정보
    """
    from app.common.metrics import AgentMetrics
    return AgentMetrics.get_summary()


@router.get("/agents/recent")
async def get_recent_metrics(agent_name: Optional[str] = None, limit: int = 100):
    """
    최근 메트릭 레코드 조회

    Args:
        agent_name: 특정 에이전트 이름 (없으면 전체)
        limit: 조회할 레코드 수 (기본 100)

    Returns:
        최근 메트릭 레코드 리스트
    """
    from app.common.metrics import AgentMetrics
    return AgentMetrics.get_recent_records(agent_name, limit)


__all__ = ['router']
