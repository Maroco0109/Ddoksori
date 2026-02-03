"""
Agent Registry - 에이전트 중앙 등록 및 관리

Supervisor와 에이전트 간의 결합도를 낮추기 위한 레지스트리 패턴.
모든 에이전트는 이 레지스트리에 등록되며, Supervisor는 레지스트리를 통해
에이전트에 접근합니다.

Usage:
    from app.agents.registry import AgentRegistry, get_agent_registry

    # 에이전트 등록
    registry = get_agent_registry()
    registry.register(
        name="query_analyst",
        description="질문 분석 및 의도 파악",
        handler=query_analyst_handler,
        category="analysis"
    )

    # 에이전트 조회
    agent = registry.get("query_analyst")
    agents = registry.get_by_category("retrieval")
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class AgentHandler(Protocol):
    """에이전트 핸들러 프로토콜."""

    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """에이전트 요청 처리."""
        ...


@dataclass
class AgentInfo:
    """에이전트 메타데이터."""

    name: str
    """에이전트 고유 이름."""

    description: str
    """에이전트 설명 (Supervisor 프롬프트에 사용)."""

    handler: Optional[AgentHandler] = None
    """에이전트 핸들러 인스턴스."""

    category: str = "general"
    """에이전트 카테고리 (analysis, retrieval, generation, review)."""

    required_inputs: List[str] = field(default_factory=list)
    """필수 입력 필드 목록."""

    provided_outputs: List[str] = field(default_factory=list)
    """제공 출력 필드 목록."""

    priority: int = 0
    """실행 우선순위 (높을수록 먼저 실행)."""

    enabled: bool = True
    """에이전트 활성화 여부."""

    def to_prompt_str(self) -> str:
        """Supervisor 프롬프트용 문자열 반환."""
        return f"{self.name}: {self.description}"


class AgentRegistry:
    """
    에이전트 중앙 레지스트리.

    모든 에이전트는 이 레지스트리에 등록되며,
    Supervisor는 레지스트리를 통해 에이전트에 접근합니다.
    """

    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}
        self._by_category: Dict[str, List[str]] = {}
        logger.debug("[AgentRegistry] Initialized")

    def register(
        self,
        name: str,
        description: str,
        handler: Optional[AgentHandler] = None,
        category: str = "general",
        required_inputs: Optional[List[str]] = None,
        provided_outputs: Optional[List[str]] = None,
        priority: int = 0,
        enabled: bool = True,
    ) -> None:
        """
        에이전트를 레지스트리에 등록합니다.

        Args:
            name: 에이전트 고유 이름
            description: 에이전트 설명
            handler: 에이전트 핸들러 인스턴스
            category: 에이전트 카테고리
            required_inputs: 필수 입력 필드 목록
            provided_outputs: 제공 출력 필드 목록
            priority: 실행 우선순위
            enabled: 활성화 여부
        """
        if name in self._agents:
            logger.warning(f"[AgentRegistry] Overwriting existing agent: {name}")

        info = AgentInfo(
            name=name,
            description=description,
            handler=handler,
            category=category,
            required_inputs=required_inputs or [],
            provided_outputs=provided_outputs or [],
            priority=priority,
            enabled=enabled,
        )

        self._agents[name] = info

        # 카테고리별 인덱스 업데이트
        if category not in self._by_category:
            self._by_category[category] = []
        if name not in self._by_category[category]:
            self._by_category[category].append(name)

        logger.info(f"[AgentRegistry] Registered: {name} (category={category})")

    def unregister(self, name: str) -> bool:
        """
        에이전트를 레지스트리에서 제거합니다.

        Args:
            name: 에이전트 이름

        Returns:
            제거 성공 여부
        """
        if name not in self._agents:
            return False

        info = self._agents.pop(name)
        if info.category in self._by_category:
            self._by_category[info.category] = [
                n for n in self._by_category[info.category] if n != name
            ]

        logger.info(f"[AgentRegistry] Unregistered: {name}")
        return True

    def get(self, name: str) -> Optional[AgentInfo]:
        """
        에이전트 정보를 조회합니다.

        Args:
            name: 에이전트 이름

        Returns:
            AgentInfo 또는 None
        """
        return self._agents.get(name)

    def get_handler(self, name: str) -> Optional[AgentHandler]:
        """
        에이전트 핸들러를 조회합니다.

        Args:
            name: 에이전트 이름

        Returns:
            AgentHandler 또는 None
        """
        info = self._agents.get(name)
        return info.handler if info else None

    def get_by_category(self, category: str) -> List[AgentInfo]:
        """
        카테고리별 에이전트 목록을 조회합니다.

        Args:
            category: 에이전트 카테고리

        Returns:
            해당 카테고리의 AgentInfo 리스트
        """
        names = self._by_category.get(category, [])
        return [self._agents[n] for n in names if n in self._agents]

    def get_all(self, enabled_only: bool = True) -> List[AgentInfo]:
        """
        모든 에이전트 목록을 조회합니다.

        Args:
            enabled_only: True면 활성화된 에이전트만 반환

        Returns:
            AgentInfo 리스트
        """
        agents = list(self._agents.values())
        if enabled_only:
            agents = [a for a in agents if a.enabled]
        return sorted(agents, key=lambda a: -a.priority)

    def get_for_prompt(self, enabled_only: bool = True) -> Dict[str, str]:
        """
        Supervisor 프롬프트용 에이전트 목록을 반환합니다.

        Args:
            enabled_only: True면 활성화된 에이전트만 반환

        Returns:
            {name: description} 딕셔너리
        """
        return {a.name: a.description for a in self.get_all(enabled_only)}

    def list_names(self, enabled_only: bool = True) -> List[str]:
        """
        에이전트 이름 목록을 반환합니다.

        Args:
            enabled_only: True면 활성화된 에이전트만 반환

        Returns:
            에이전트 이름 리스트
        """
        return [a.name for a in self.get_all(enabled_only)]

    def enable(self, name: str) -> bool:
        """에이전트를 활성화합니다."""
        if name in self._agents:
            self._agents[name].enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        """에이전트를 비활성화합니다."""
        if name in self._agents:
            self._agents[name].enabled = False
            return True
        return False

    def clear(self) -> None:
        """모든 에이전트를 제거합니다 (테스트용)."""
        self._agents.clear()
        self._by_category.clear()


# 싱글톤 인스턴스
_registry: Optional[AgentRegistry] = None


def get_agent_registry() -> AgentRegistry:
    """AgentRegistry 싱글톤 인스턴스를 반환합니다."""
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
        _register_default_agents(_registry)
    return _registry


def reset_agent_registry() -> None:
    """레지스트리를 리셋합니다 (테스트용)."""
    global _registry
    _registry = None


def _register_default_agents(registry: AgentRegistry) -> None:
    """기본 에이전트들을 등록합니다."""
    # Analysis Agents
    registry.register(
        name="query_analyst",
        description="질문 분석 및 의도 파악",
        category="analysis",
        required_inputs=["user_query"],
        provided_outputs=["query_type", "domain", "keywords", "retriever_types"],
        priority=100,
    )

    # Retrieval Agents (Fan-out 그룹)
    registry.register(
        name="retrieval_team",
        description="법령, 분쟁조정기준, 분쟁사례, 상담사례 검색 (병렬)",
        category="retrieval",
        required_inputs=["user_query", "query_analysis"],
        provided_outputs=["retrieval_results"],
        priority=80,
    )

    registry.register(
        name="retrieval_law",
        description="관련 법령 조항 검색",
        category="retrieval",
        required_inputs=["user_query"],
        provided_outputs=["law_results"],
        priority=75,
    )

    registry.register(
        name="retrieval_criteria",
        description="분쟁해결기준 검색",
        category="retrieval",
        required_inputs=["user_query"],
        provided_outputs=["criteria_results"],
        priority=75,
    )

    registry.register(
        name="retrieval_case",
        description="분쟁조정사례 검색",
        category="retrieval",
        required_inputs=["user_query"],
        provided_outputs=["case_results"],
        priority=75,
    )

    registry.register(
        name="retrieval_counsel",
        description="상담사례 검색",
        category="retrieval",
        required_inputs=["user_query"],
        provided_outputs=["counsel_results"],
        priority=75,
    )

    # Generation Agents
    registry.register(
        name="answer_drafter",
        description="답변 초안 작성",
        category="generation",
        required_inputs=["user_query", "retrieval_results"],
        provided_outputs=["draft_answer", "citations"],
        priority=60,
    )

    # Review Agents
    registry.register(
        name="legal_reviewer",
        description="법적 정확성 검토",
        category="review",
        required_inputs=["draft_answer"],
        provided_outputs=["review_result", "corrections"],
        priority=40,
    )

    logger.info(
        f"[AgentRegistry] Registered {len(registry.list_names())} default agents"
    )
