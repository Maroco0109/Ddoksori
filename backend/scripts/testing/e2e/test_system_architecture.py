"""
Suite 1: 시스템 아키텍처 검증 테스트

리팩토링(PR 1-6) 후 시스템 구조 무결성을 검증합니다.
DB/API 연결 없이 실행 가능합니다.

실행:
    PYTHONPATH=backend conda run -n dsr pytest backend/scripts/testing/e2e/test_system_architecture.py -v
"""

import inspect
import re
import sys
from pathlib import Path

import pytest

# Ensure backend is on sys.path
_backend_root = str(Path(__file__).parent.parent.parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)


# ============================================================
# Test 1.1: MAS 그래프 구조 검증
# ============================================================


@pytest.mark.e2e
@pytest.mark.unit
class TestMASGraphStructure:
    """MAS Supervisor 그래프의 노드와 엣지가 올바른지 검증합니다."""

    def test_mas_graph_nodes_exist(self):
        """MAS 그래프에 필수 노드가 모두 존재하는지 확인"""
        from app.supervisor import reset_graph
        from app.supervisor.graph_mas import create_mas_supervisor_graph

        reset_graph()
        graph = create_mas_supervisor_graph()

        node_names = set(graph.nodes.keys())

        expected_nodes = {
            "cache_check",
            "cache_response",
            "input_guardrail",
            "supervisor",
            "query_analysis",
            "retrieval_law",
            "retrieval_criteria",
            "retrieval_case",
            "retrieval_merge",
            "generation",
            "review",
            "output_guardrail",
            "ask_clarification",
        }

        missing = expected_nodes - node_names
        assert not missing, f"Missing nodes: {missing}"

    def test_mas_graph_no_counsel_node(self):
        """counsel 노드가 제거되었는지 확인 (Phase 10: 3개 Agent 정규화)"""
        from app.supervisor import reset_graph
        from app.supervisor.graph_mas import create_mas_supervisor_graph

        reset_graph()
        graph = create_mas_supervisor_graph()
        node_names = set(graph.nodes.keys())

        assert (
            "retrieval_counsel" not in node_names
        ), "retrieval_counsel 노드가 여전히 존재합니다 (Phase 10에서 제거 필요)"


# ============================================================
# Test 1.2: Agent Registry 검증
# ============================================================


@pytest.mark.e2e
@pytest.mark.unit
class TestAgentRegistry:
    """등록된 에이전트가 protocols.py 정의와 일치하는지 확인합니다."""

    def test_retrieval_agents_registered(self):
        """3개 Retrieval Agent가 올바르게 등록되었는지 확인"""
        from app.agents.retrieval import (
            CaseRetrievalAgent,
            CriteriaRetrievalAgent,
            LawRetrievalAgent,
        )

        agents = {
            "law": LawRetrievalAgent,
            "criteria": CriteriaRetrievalAgent,
            "case": CaseRetrievalAgent,
        }

        for key, agent_cls in agents.items():
            assert hasattr(
                agent_cls, "domain_key"
            ), f"{agent_cls.__name__} missing domain_key"
            assert hasattr(
                agent_cls, "required_inputs"
            ), f"{agent_cls.__name__} missing required_inputs"
            assert hasattr(
                agent_cls, "provided_outputs"
            ), f"{agent_cls.__name__} missing provided_outputs"

    def test_agent_domain_keys(self):
        """각 Agent의 domain_key가 올바르게 설정되었는지 확인"""
        from app.agents.retrieval import (
            CaseRetrievalAgent,
            CriteriaRetrievalAgent,
            LawRetrievalAgent,
        )

        assert LawRetrievalAgent.domain_key == "law"
        assert CriteriaRetrievalAgent.domain_key == "criteria"
        assert CaseRetrievalAgent.domain_key == "case"

    def test_retrieval_agents_inherit_base(self):
        """모든 Retrieval Agent가 BaseRetrievalAgent를 상속하는지 확인"""
        from app.agents.retrieval import (
            BaseRetrievalAgent,
            CaseRetrievalAgent,
            CriteriaRetrievalAgent,
            LawRetrievalAgent,
        )

        for agent_cls in [
            LawRetrievalAgent,
            CriteriaRetrievalAgent,
            CaseRetrievalAgent,
        ]:
            assert issubclass(
                agent_cls, BaseRetrievalAgent
            ), f"{agent_cls.__name__} does not inherit BaseRetrievalAgent"


# ============================================================
# Test 1.3: Config 중앙화 검증
# ============================================================


@pytest.mark.e2e
@pytest.mark.unit
class TestConfigCentralized:
    """get_config() 설정값이 코드에서 사용되는 기본값과 일치하는지 확인합니다."""

    def test_model_config_code_defaults(self):
        """ModelConfig 코드 레벨 기본값 확인 (.env 오버라이드 무관)"""
        from app.common.config import ModelConfig

        # Field.default 값 검증 (환경변수 영향 없음)
        fields = ModelConfig.model_fields
        assert fields["supervisor"].default == "gpt-4o"
        assert fields["draft_agent"].default == "gpt-4o"
        assert fields["review_agent"].default == "gpt-4o"

    def test_similarity_threshold_code_defaults(self):
        """AgentSettings 코드 레벨 기본값 확인 (.env 오버라이드 무관)"""
        from app.common.config import AgentSettings

        fields = AgentSettings.model_fields
        assert fields["similarity_threshold_law"].default == 0.60
        assert fields["similarity_threshold_criteria"].default == 0.50
        assert fields["similarity_threshold_dispute"].default == 0.55  # case 매핑
        assert fields["similarity_threshold_general"].default == 0.45
        assert fields["similarity_threshold"].default == 0.55

    def test_similarity_threshold_case_maps_to_dispute(self):
        """get_similarity_threshold('case')가 dispute 임계값을 반환하는지 확인"""
        from app.common.config import AgentSettings

        # AgentSettings 소스에서 case → dispute 매핑 확인
        source = inspect.getsource(AgentSettings.get_similarity_threshold)
        assert (
            '"case"' in source and "dispute" in source
        ), "get_similarity_threshold()에 case → dispute 매핑이 없습니다"

    def test_no_orchestrator_mode_field(self):
        """config.py에 ORCHESTRATOR_MODE 필드가 없는지 확인 (레거시 제거)"""
        from app.common import config as config_module

        source = inspect.getsource(config_module)
        # AppConfig, AgentSettings 등 모든 Settings 클래스에서 orchestrator_mode 필드 없음
        assert (
            "orchestrator_mode" not in source
        ), "config.py에 레거시 orchestrator_mode 필드가 남아있습니다"


# ============================================================
# Test 1.4: Legacy 코드 제거 검증
# ============================================================


@pytest.mark.e2e
@pytest.mark.unit
class TestNoLegacyImports:
    """삭제된 legacy 모듈의 import가 active 코드에 없는지 확인합니다."""

    @pytest.fixture
    def active_source_files(self):
        """backend/app/ 하위의 .py 파일 목록 (archive 제외)"""
        app_dir = Path(_backend_root) / "app"
        files = []
        for py_file in app_dir.rglob("*.py"):
            # _archive, __pycache__ 제외
            if "_archive" in str(py_file) or "__pycache__" in str(py_file):
                continue
            files.append(py_file)
        return files

    def test_no_specialized_retrievers_import(self, active_source_files):
        """specialized_retrievers 모듈 참조가 없는지 확인"""
        for py_file in active_source_files:
            content = py_file.read_text(errors="ignore")
            assert (
                "specialized_retriever" not in content
            ), f"{py_file.relative_to(_backend_root)} references deleted specialized_retrievers"

    def test_no_rdb_retriever_import(self, active_source_files):
        """rdb_retriever 모듈 참조가 없는지 확인"""
        for py_file in active_source_files:
            content = py_file.read_text(errors="ignore")
            assert (
                "rdb_retriever" not in content
            ), f"{py_file.relative_to(_backend_root)} references deleted rdb_retriever"

    def test_no_splade_retriever_import(self, active_source_files):
        """splade_retriever 모듈 참조가 없는지 확인"""
        for py_file in active_source_files:
            content = py_file.read_text(errors="ignore")
            assert (
                "splade_retriever" not in content
            ), f"{py_file.relative_to(_backend_root)} references deleted splade_retriever"

    def test_no_orchestrator_mode_env_var(self, active_source_files):
        """ORCHESTRATOR_MODE 환경변수 참조가 config.py 내에 없는지 확인"""
        config_path = Path(_backend_root) / "app" / "common" / "config.py"
        content = config_path.read_text(errors="ignore")
        assert (
            "ORCHESTRATOR_MODE" not in content
        ), "config.py에 ORCHESTRATOR_MODE 환경변수 참조가 남아있습니다"


# ============================================================
# Test 1.5: Retrieval Agent DB 쿼리 검증
# ============================================================


@pytest.mark.e2e
@pytest.mark.unit
class TestRetrieverUsesVectorChunks:
    """RAGRetriever/HybridRetriever SQL이 vector_chunks만 참조하는지 확인합니다."""

    def test_hybrid_retriever_uses_vector_chunks(self):
        """hybrid_retriever.py 소스에서 vector_chunks 참조 확인"""
        retriever_path = (
            Path(_backend_root)
            / "app"
            / "agents"
            / "retrieval"
            / "tools"
            / "hybrid_retriever.py"
        )
        source = retriever_path.read_text()

        assert (
            "vector_chunks" in source
        ), "hybrid_retriever.py에 vector_chunks 참조가 없습니다"

    def test_no_legacy_join_pattern(self):
        """hybrid_retriever.py에 레거시 documents JOIN chunks 패턴이 없는지 확인"""
        retriever_path = (
            Path(_backend_root)
            / "app"
            / "agents"
            / "retrieval"
            / "tools"
            / "hybrid_retriever.py"
        )
        source = retriever_path.read_text()

        # documents JOIN chunks 패턴 검사 (대소문자 무관)
        assert not re.search(
            r"documents\s+JOIN\s+chunks", source, re.IGNORECASE
        ), "hybrid_retriever.py에 레거시 'documents JOIN chunks' 패턴이 남아있습니다"

    def test_no_mv_searchable_chunks_reference(self):
        """hybrid_retriever.py에 mv_searchable_chunks 참조가 없는지 확인"""
        retriever_path = (
            Path(_backend_root)
            / "app"
            / "agents"
            / "retrieval"
            / "tools"
            / "hybrid_retriever.py"
        )
        source = retriever_path.read_text()

        assert (
            "mv_searchable_chunks" not in source
        ), "hybrid_retriever.py에 레거시 mv_searchable_chunks 참조가 남아있습니다"


# ============================================================
# Test 1.6: Docker Config 동기화 검증
# ============================================================


@pytest.mark.e2e
@pytest.mark.unit
class TestDockerConfigSync:
    """docker-compose.prod.yml 환경변수가 config.py 기본값과 일치하는지 확인합니다."""

    @pytest.fixture
    def docker_compose_content(self):
        compose_path = Path(_backend_root).parent / "docker-compose.prod.yml"
        if not compose_path.exists():
            pytest.skip("docker-compose.prod.yml not found")
        return compose_path.read_text()

    def test_model_supervisor_default(self, docker_compose_content):
        """MODEL_SUPERVISOR 기본값이 gpt-4o인지 확인"""
        assert (
            "MODEL_SUPERVISOR:-gpt-4o" in docker_compose_content
            or "MODEL_SUPERVISOR=${MODEL_SUPERVISOR:-gpt-4o}" in docker_compose_content
        )

    def test_similarity_threshold_default(self, docker_compose_content):
        """SIMILARITY_THRESHOLD 기본값이 0.55인지 확인"""
        assert (
            "SIMILARITY_THRESHOLD:-0.55" in docker_compose_content
            or "SIMILARITY_THRESHOLD=${SIMILARITY_THRESHOLD:-0.55}"
            in docker_compose_content
        )

    def test_embedding_model_default(self, docker_compose_content):
        """EMBEDDING_MODEL 기본값이 text-embedding-3-large인지 확인"""
        assert "text-embedding-3-large" in docker_compose_content

    def test_no_removed_env_vars(self, docker_compose_content):
        """제거된 환경변수가 docker-compose.prod.yml에 없는지 확인"""
        removed_vars = [
            "MAS_SUPERVISOR_ENABLED",
            "MODEL_QUERY_ANALYST",
            "MAX_RETRY_COUNT",
        ]
        for var in removed_vars:
            assert (
                var not in docker_compose_content
            ), f"docker-compose.prod.yml에 제거된 환경변수 {var}가 남아있습니다"


# ============================================================
# Test 1.7: Fallback Chain 보존 검증
# ============================================================


@pytest.mark.e2e
@pytest.mark.unit
class TestFallbackChainsPreserved:
    """리팩토링에서 보존해야 할 fallback chain이 코드에 존재하는지 확인합니다."""

    def test_answer_generation_fallback_models(self):
        """Answer Generation에 fallback 모델 체인이 존재하는지 확인"""
        gen_path = (
            Path(_backend_root) / "app" / "agents" / "answer_generation" / "agent.py"
        )
        source = gen_path.read_text()

        # gpt-4o-mini 또는 다른 fallback 모델 언급 확인
        # 또는 rule_based / safe_fallback 로직 존재 확인
        has_fallback = (
            "fallback" in source.lower()
            or "rule_based" in source
            or "safe_fallback" in source
            or "gpt-4o-mini" in source
        )
        assert has_fallback, "answer_generation/agent.py에 fallback 체인이 없습니다"

    def test_legal_review_prohibited_patterns_exist(self):
        """legal_review/agent.py에 PROHIBITED_PATTERNS가 정의되어 있는지 확인"""
        review_path = (
            Path(_backend_root) / "app" / "agents" / "legal_review" / "agent.py"
        )
        source = review_path.read_text()

        assert (
            "PROHIBITED_PATTERNS" in source
        ), "legal_review/agent.py에 PROHIBITED_PATTERNS가 정의되어 있지 않습니다"
        assert (
            "CITATION_PATTERNS" in source
        ), "legal_review/agent.py에 CITATION_PATTERNS가 정의되어 있지 않습니다"

    def test_query_analysis_intent_classifier_exists(self):
        """query_analysis에 의도 분류 로직이 존재하는지 확인"""
        qa_path = Path(_backend_root) / "app" / "agents" / "query_analysis" / "agent.py"
        source = qa_path.read_text()

        has_intent = (
            "intent" in source.lower()
            or "query_type" in source
            or "IntentClassifier" in source
            or "classify" in source.lower()
        )
        assert has_intent, "query_analysis/agent.py에 의도 분류 로직이 없습니다"
