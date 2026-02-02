"""
Agent Registry 모듈.

Supervisor와 에이전트 간의 결합도를 낮추기 위한 레지스트리 패턴.

Usage:
    from app.agents.registry import get_agent_registry

    registry = get_agent_registry()
    agents = registry.get_for_prompt()  # Supervisor 프롬프트용
"""

from app.agents.registry.agent_registry import (
    AgentHandler,
    AgentInfo,
    AgentRegistry,
    get_agent_registry,
    reset_agent_registry,
)

__all__ = [
    "AgentHandler",
    "AgentInfo",
    "AgentRegistry",
    "get_agent_registry",
    "reset_agent_registry",
]
