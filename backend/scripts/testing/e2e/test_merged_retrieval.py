"""
E2E tests for merged retrieval features (Branch 36 + counsel_agent).
Tests agent structure, protocol compliance, and import integrity.

실행:
    PYTHONPATH=backend conda run -n dsr pytest backend/scripts/testing/e2e/test_merged_retrieval.py -v
"""

import sys
from pathlib import Path

import pytest

# Ensure backend is on sys.path
_backend = str(Path(__file__).parent.parent.parent.parent)
if _backend not in sys.path:
    sys.path.insert(0, _backend)


# ============================================================
# Test 1: Retrieval Agent 임포트 검증
# ============================================================


@pytest.mark.e2e
@pytest.mark.unit
class TestRetrievalAgentImports:
    """4개 Retrieval Agent가 올바르게 임포트 가능한지 검증합니다."""

    def test_law_agent_importable(self):
        """LawRetrievalAgent 임포트 검증"""
        from app.agents.retrieval.law_agent import (
            LawRetrievalAgent,
            law_retrieval_agent,
        )

        assert LawRetrievalAgent is not None
        assert law_retrieval_agent is not None
        assert isinstance(law_retrieval_agent, LawRetrievalAgent)

    def test_criteria_agent_importable(self):
        """CriteriaRetrievalAgent 임포트 검증"""
        from app.agents.retrieval.criteria_agent import (
            CriteriaRetrievalAgent,
            criteria_retrieval_agent,
        )

        assert CriteriaRetrievalAgent is not None
        assert criteria_retrieval_agent is not None
        assert isinstance(criteria_retrieval_agent, CriteriaRetrievalAgent)

    def test_case_agent_importable(self):
        """CaseRetrievalAgent 임포트 검증"""
        from app.agents.retrieval.case_agent import (
            CaseRetrievalAgent,
            case_retrieval_agent,
        )

        assert CaseRetrievalAgent is not None
        assert case_retrieval_agent is not None
        assert isinstance(case_retrieval_agent, CaseRetrievalAgent)

    def test_counsel_agent_importable(self):
        """CounselRetrievalAgent 임포트 검증"""
        from app.agents.retrieval.counsel_agent import (
            CounselRetrievalAgent,
            counsel_retrieval_agent,
        )

        assert CounselRetrievalAgent is not None
        assert counsel_retrieval_agent is not None
        assert isinstance(counsel_retrieval_agent, CounselRetrievalAgent)


# ============================================================
# Test 2: Retrieval Agent 구조 검증
# ============================================================


@pytest.mark.e2e
@pytest.mark.unit
class TestRetrievalAgentStructure:
    """4개 Retrieval Agent의 구조와 속성을 검증합니다."""

    @pytest.fixture
    def all_agents(self):
        """4개 에이전트 인스턴스 반환"""
        from app.agents.retrieval.case_agent import case_retrieval_agent
        from app.agents.retrieval.counsel_agent import counsel_retrieval_agent
        from app.agents.retrieval.criteria_agent import criteria_retrieval_agent
        from app.agents.retrieval.law_agent import law_retrieval_agent

        return [
            law_retrieval_agent,
            criteria_retrieval_agent,
            case_retrieval_agent,
            counsel_retrieval_agent,
        ]

    def test_all_agents_have_required_attributes(self, all_agents):
        """모든 에이전트가 필수 속성을 가지고 있는지 확인"""
        required_attrs = ["agent_name", "agent_description"]

        for agent in all_agents:
            for attr in required_attrs:
                assert hasattr(agent, attr), (
                    f"{agent.__class__.__name__} missing attribute: {attr}"
                )
                value = getattr(agent, attr)
                assert value is not None, f"{agent.__class__.__name__}.{attr} is None"
                assert value != "", f"{agent.__class__.__name__}.{attr} is empty"

        # domain_key는 case와 counsel agent만 정의함
        from app.agents.retrieval.case_agent import case_retrieval_agent
        from app.agents.retrieval.counsel_agent import counsel_retrieval_agent

        assert hasattr(case_retrieval_agent, "domain_key")
        assert hasattr(counsel_retrieval_agent, "domain_key")

    def test_agent_names_are_unique(self, all_agents):
        """모든 에이전트의 agent_name이 고유한지 확인"""
        agent_names = [agent.agent_name for agent in all_agents]
        assert len(agent_names) == len(set(agent_names)), (
            f"Duplicate agent_name found: {agent_names}"
        )

    def test_domain_keys_are_correct(self, all_agents):
        """case와 counsel 에이전트의 domain_key가 올바른지 확인"""
        from app.agents.retrieval.case_agent import case_retrieval_agent
        from app.agents.retrieval.counsel_agent import counsel_retrieval_agent

        # domain_key는 case와 counsel agent만 정의함 (law, criteria는 사용하지 않음)
        assert case_retrieval_agent.domain_key == "case"
        assert counsel_retrieval_agent.domain_key == "counsel"

    def test_agents_inherit_base(self, all_agents):
        """모든 에이전트가 BaseRetrievalAgent를 상속하는지 확인"""
        from app.agents.retrieval.base_retrieval_agent import BaseRetrievalAgent

        for agent in all_agents:
            assert isinstance(agent, BaseRetrievalAgent), (
                f"{agent.__class__.__name__} does not inherit from BaseRetrievalAgent"
            )


# ============================================================
# Test 3: Retrieval Agent 프로토콜 검증
# ============================================================


@pytest.mark.e2e
@pytest.mark.unit
class TestRetrievalAgentProtocol:
    """4개 Retrieval Agent가 BaseRetrievalAgent 프로토콜을 준수하는지 검증합니다."""

    @pytest.fixture
    def all_agent_classes(self):
        """4개 에이전트 클래스 반환"""
        from app.agents.retrieval.case_agent import CaseRetrievalAgent
        from app.agents.retrieval.counsel_agent import CounselRetrievalAgent
        from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent
        from app.agents.retrieval.law_agent import LawRetrievalAgent

        return [
            LawRetrievalAgent,
            CriteriaRetrievalAgent,
            CaseRetrievalAgent,
            CounselRetrievalAgent,
        ]

    def test_agents_have_execute_search(self, all_agent_classes):
        """모든 에이전트가 _execute_search 메서드를 가지고 있는지 확인"""
        for agent_cls in all_agent_classes:
            assert hasattr(agent_cls, "_execute_search"), (
                f"{agent_cls.__name__} missing _execute_search method"
            )

            # 메서드가 호출 가능한지 확인
            method = getattr(agent_cls, "_execute_search")
            assert callable(method), (
                f"{agent_cls.__name__}._execute_search is not callable"
            )

    def test_agents_have_format_results(self, all_agent_classes):
        """모든 에이전트가 _format_results 메서드를 가지고 있는지 확인"""
        for agent_cls in all_agent_classes:
            assert hasattr(agent_cls, "_format_results"), (
                f"{agent_cls.__name__} missing _format_results method"
            )

            method = getattr(agent_cls, "_format_results")
            assert callable(method), (
                f"{agent_cls.__name__}._format_results is not callable"
            )

    def test_agents_have_build_sources(self, all_agent_classes):
        """모든 에이전트가 _build_sources 메서드를 가지고 있는지 확인"""
        for agent_cls in all_agent_classes:
            assert hasattr(agent_cls, "_build_sources"), (
                f"{agent_cls.__name__} missing _build_sources method"
            )

            method = getattr(agent_cls, "_build_sources")
            assert callable(method), (
                f"{agent_cls.__name__}._build_sources is not callable"
            )

    def test_agents_have_get_search_filters(self, all_agent_classes):
        """모든 에이전트가 _get_search_filters 메서드를 가지고 있는지 확인"""
        for agent_cls in all_agent_classes:
            assert hasattr(agent_cls, "_get_search_filters"), (
                f"{agent_cls.__name__} missing _get_search_filters method"
            )

            method = getattr(agent_cls, "_get_search_filters")
            assert callable(method), (
                f"{agent_cls.__name__}._get_search_filters is not callable"
            )


# ============================================================
# Test 4: CounselAgent 특화 검증
# ============================================================


@pytest.mark.e2e
@pytest.mark.unit
class TestCounselAgentSpecific:
    """CounselRetrievalAgent의 특화된 기능을 검증합니다."""

    def test_counsel_agent_domain_key(self):
        """counsel_agent의 domain_key가 'counsel'인지 확인"""
        from app.agents.retrieval.counsel_agent import counsel_retrieval_agent

        assert counsel_retrieval_agent.domain_key == "counsel"

    def test_counsel_agent_name(self):
        """counsel_agent의 agent_name이 'retrieval_counsel'인지 확인"""
        from app.agents.retrieval.counsel_agent import counsel_retrieval_agent

        assert counsel_retrieval_agent.agent_name == "retrieval_counsel"

    def test_counsel_filters_include_category(self):
        """counsel_agent의 _get_search_filters()가 category_filter를 포함하는지 확인"""
        from app.agents.retrieval.counsel_agent import counsel_retrieval_agent

        filters = counsel_retrieval_agent._get_search_filters()

        assert isinstance(filters, dict), "filters must be a dictionary"
        assert "category_filter" in filters, (
            "counsel_agent filters must include 'category_filter'"
        )
        assert filters["category_filter"] == "상담", (
            "counsel_agent category_filter must be '상담'"
        )

    def test_counsel_dataset_filter_is_case(self):
        """counsel_agent의 dataset_filter가 'case'인지 확인"""
        from app.agents.retrieval.counsel_agent import counsel_retrieval_agent

        filters = counsel_retrieval_agent._get_search_filters()

        assert "dataset_filter" in filters, (
            "counsel_agent filters must include 'dataset_filter'"
        )
        assert filters["dataset_filter"] == "case", (
            "counsel_agent dataset_filter must be 'case'"
        )


# ============================================================
# Test 5: ClassVar 속성 검증
# ============================================================


@pytest.mark.e2e
@pytest.mark.unit
class TestClassVarAttributes:
    """각 에이전트의 ClassVar 속성이 올바르게 정의되었는지 검증합니다."""

    def test_required_inputs_defined(self):
        """모든 에이전트가 required_inputs ClassVar를 가지고 있는지 확인"""
        from app.agents.retrieval.case_agent import CaseRetrievalAgent
        from app.agents.retrieval.counsel_agent import CounselRetrievalAgent
        from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent
        from app.agents.retrieval.law_agent import LawRetrievalAgent

        agent_classes = [
            LawRetrievalAgent,
            CriteriaRetrievalAgent,
            CaseRetrievalAgent,
            CounselRetrievalAgent,
        ]

        for agent_cls in agent_classes:
            assert hasattr(agent_cls, "required_inputs"), (
                f"{agent_cls.__name__} missing required_inputs"
            )
            assert isinstance(agent_cls.required_inputs, list), (
                f"{agent_cls.__name__}.required_inputs must be a list"
            )
            assert "user_query" in agent_cls.required_inputs, (
                f"{agent_cls.__name__}.required_inputs must include 'user_query'"
            )

    def test_provided_outputs_defined(self):
        """모든 에이전트가 provided_outputs ClassVar를 가지고 있는지 확인"""
        from app.agents.retrieval.case_agent import CaseRetrievalAgent
        from app.agents.retrieval.counsel_agent import CounselRetrievalAgent
        from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent
        from app.agents.retrieval.law_agent import LawRetrievalAgent

        agent_classes = [
            LawRetrievalAgent,
            CriteriaRetrievalAgent,
            CaseRetrievalAgent,
            CounselRetrievalAgent,
        ]
        expected_outputs = ["results", "sources", "max_similarity", "avg_similarity"]

        for agent_cls in agent_classes:
            assert hasattr(agent_cls, "provided_outputs"), (
                f"{agent_cls.__name__} missing provided_outputs"
            )
            assert isinstance(agent_cls.provided_outputs, list), (
                f"{agent_cls.__name__}.provided_outputs must be a list"
            )
            for output in expected_outputs:
                assert output in agent_cls.provided_outputs, (
                    f"{agent_cls.__name__}.provided_outputs must include '{output}'"
                )
