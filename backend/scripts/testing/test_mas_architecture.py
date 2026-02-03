"""
MAS 아키텍처 테스트 (ralph-loop)

테스트 항목:
1. 모듈 Import 테스트
2. 그래프 생성 테스트
3. Retrieval Agent metadata_filter 테스트 (RDS 필요)
4. 쿼리 확장 테스트
5. CitedCase 추출 테스트
6. Violation 상세 생성 테스트
"""

import asyncio

import pytest

# pytest-asyncio 설정
pytestmark = pytest.mark.asyncio


class TestV2ModuleImports:
    """v2 모듈 Import 테스트"""

    def test_protocols_import(self):
        """protocols.py import 테스트"""
        from app.agents.protocols import (
            CitedCase,
            MetadataFilter,
            QueryAnalysisOutput,
            Violation,
        )

        assert QueryAnalysisOutput is not None
        assert MetadataFilter is not None
        assert CitedCase is not None
        assert Violation is not None

    def test_retrieval_agents_import(self):
        """Retrieval Agent import 테스트"""
        from app.agents.retrieval.case_agent import CaseRetrievalAgent
        from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent
        from app.agents.retrieval.law_agent import LawRetrievalAgent

        assert LawRetrievalAgent is not None
        assert CriteriaRetrievalAgent is not None
        assert CaseRetrievalAgent is not None

    def test_v2_nodes_import(self):
        """v2 노드 import 테스트"""
        from app.agents.answer_generation.agent import generation_node_v2
        from app.agents.legal_review.agent import review_node_v2
        from app.agents.query_analysis.agent import query_analysis_node_v2

        assert query_analysis_node_v2 is not None
        assert generation_node_v2 is not None
        assert review_node_v2 is not None

    def test_graph_v2_import(self):
        """v2 그래프 import 테스트"""
        from app.supervisor.graph_mas import create_mas_supervisor_graph

        assert create_mas_supervisor_graph is not None


class TestV2GraphCreation:
    """v2 그래프 생성 테스트"""

    def test_create_graph_v2(self):
        """v2 그래프 생성 테스트"""
        from app.supervisor.graph_mas import create_mas_supervisor_graph

        graph = create_mas_supervisor_graph()

        # 노드 수 확인 (14개: cache_check, cache_response, input/output_guardrail,
        # supervisor, query_analysis, generation, review,
        # retrieval_law/criteria/case, retrieval_merge, memory_save, inject_cached_retrieval)
        assert len(graph.nodes) == 14, (
            f"Expected 14 nodes, got {len(graph.nodes)}: {sorted(graph.nodes.keys())}"
        )

        # 필수 노드 확인
        required_nodes = [
            "cache_check",
            "cache_response",
            "input_guardrail",
            "output_guardrail",
            "supervisor",
            "query_analysis",
            "generation",
            "review",
            "retrieval_law",
            "retrieval_criteria",
            "retrieval_case",
            "retrieval_merge",
            "memory_save",
            "inject_cached_retrieval",
        ]
        for node in required_nodes:
            assert node in graph.nodes, f"Missing node: {node}"


@pytest.mark.llm
class TestQueryAnalysisV2:
    """쿼리 분석 v2 테스트 (LLM 호출 필요: expand_query_with_llm_v2)"""

    def test_query_analysis_node_v2_dispute(self):
        """분쟁 쿼리 분석 테스트"""
        from app.agents.query_analysis.agent import query_analysis_node_v2

        state = {
            "user_query": "노트북 환불 받고 싶은데 어떻게 해야 하나요?",
            "chat_type": "dispute",
            "onboarding": None,
        }

        result = asyncio.run(query_analysis_node_v2(state))

        assert "query_analysis" in result
        qa = result["query_analysis"]

        # v2 필드 확인
        assert "intent" in qa
        assert "expanded_queries" in qa
        assert "retriever_types" in qa

        # 의도 분류 확인
        assert qa["intent"] == "information_search"

        # 확장 쿼리 확인
        assert len(qa["expanded_queries"]) >= 1

        # retriever_types 확인
        assert "law" in qa["retriever_types"] or "criteria" in qa["retriever_types"]

    def test_query_analysis_node_v2_general(self):
        """일반 쿼리 분석 테스트"""
        from app.agents.query_analysis.agent import query_analysis_node_v2

        state = {
            "user_query": "안녕하세요",
            "chat_type": "general",
            "onboarding": None,
        }

        result = asyncio.run(query_analysis_node_v2(state))

        qa = result["query_analysis"]
        assert qa["intent"] == "general"
        assert result["mode"] == "NO_RETRIEVAL"


@pytest.mark.integration
class TestRetrievalAgentsV2:
    """Retrieval Agent v2 테스트 (Docker DB 필요)"""

    def test_law_agent_with_metadata_filter(self):
        """법령 검색 에이전트 metadata_filter 테스트"""
        from app.agents.retrieval.law_agent import law_retrieval_agent

        request = {
            "context": {
                "user_query": "청약철회 기간",
                "query_analysis": {},
                "expanded_queries": ["청약철회 기간 전자상거래"],
                "agent_keywords": ["청약철회", "기간"],
            },
            "params": {
                "top_k": 3,
                "metadata_filter": {
                    "dataset_type": "law_guide",
                    "document_types": ["법률", "시행령"],
                },
                "ignore_threshold": False,
            },
        }

        result = asyncio.run(law_retrieval_agent.process(request))

        assert result["status"] in ("success", "failure")
        if result["status"] == "success":
            assert "result" in result
            assert "results" in result["result"]
            print(f"Law agent returned {len(result['result']['results'])} results")

    def test_criteria_agent_with_metadata_filter(self):
        """기준 검색 에이전트 metadata_filter 테스트"""
        from app.agents.retrieval.criteria_agent import criteria_retrieval_agent

        request = {
            "context": {
                "user_query": "노트북 환불 기준",
                "query_analysis": {},
                "expanded_queries": ["노트북 분쟁해결기준 환불"],
                "agent_keywords": ["노트북", "환불"],
            },
            "params": {
                "top_k": 3,
                "metadata_filter": {
                    "dataset_type": "law_guide",
                },
                "ignore_threshold": False,
            },
        }

        result = asyncio.run(criteria_retrieval_agent.process(request))

        assert result["status"] in ("success", "failure")
        if result["status"] == "success":
            assert "result" in result
            print(f"Criteria agent returned {len(result['result']['results'])} results")

    def test_case_agent_with_category_filter(self):
        """사례 검색 에이전트 카테고리 필터 테스트"""
        from app.agents.retrieval.case_agent import case_retrieval_agent

        request = {
            "context": {
                "user_query": "스마트폰 불량 환불 사례",
                "query_analysis": {},
                "expanded_queries": ["스마트폰 불량 환불 분쟁조정"],
                "agent_keywords": ["스마트폰", "불량", "환불"],
            },
            "params": {
                "top_k": 5,
                "metadata_filter": {
                    "categories": ["조정", "해결", "상담"],
                },
                "ignore_threshold": False,
            },
        }

        result = asyncio.run(case_retrieval_agent.process(request))

        assert result["status"] in ("success", "failure")
        if result["status"] == "success":
            assert "result" in result
            print(f"Case agent returned {len(result['result']['results'])} results")


class TestGenerationV2:
    """답변 생성 v2 테스트"""

    def test_extract_cited_cases(self):
        """CitedCase 추출 테스트"""
        from app.agents.answer_generation.agent import _extract_cited_cases

        retrieval = {
            "cases": [
                {
                    "chunk_id": "case_001",
                    "doc_id": "doc_001",
                    "doc_title": "스마트폰 환불 분쟁조정 사례",
                    "category": "조정",
                    "content": "스마트폰 구입 후 7일 이내 환불 요청...",
                },
                {
                    "chunk_id": "case_002",
                    "doc_id": "doc_002",
                    "doc_title": "노트북 불량 해결 사례",
                    "category": "해결",
                    "content": "노트북 배터리 불량으로 교환 요청...",
                },
            ]
        }

        cited_cases = _extract_cited_cases(retrieval)

        assert len(cited_cases) == 2
        assert cited_cases[0]["case_id"] == "case_001"
        assert cited_cases[0]["category"] == "조정"
        assert cited_cases[1]["category"] == "해결"

    def test_build_retry_prompt_supplement(self):
        """재생성 프롬프트 보충 테스트"""
        from app.agents.answer_generation.agent import _build_retry_prompt_supplement

        retry_context = {
            "violations": [
                "[prohibited_expression] 금지 표현 발견: 반드시 ~합니다",
                "[hallucination] 검색 결과에서 확인되지 않은 인용",
            ],
            "previous_draft": "이전 답변...",
            "retry_count": 0,
        }

        supplement = _build_retry_prompt_supplement(retry_context)

        assert "이전 답변 검토 결과" in supplement
        assert "금지 표현" in supplement
        assert "hallucination" in supplement


class TestReviewV2:
    """법률 검토 v2 테스트"""

    def test_build_violation_details(self):
        """Violation 상세 생성 테스트"""
        from app.agents.legal_review.agent import (
            CitationVerifyResult,
            _build_violation_details,
        )

        prohibited_violations = [
            ("반드시 ~합니다", "반드시 환불받을 수 있습니다"),
        ]
        has_citation = False
        has_evidence = True
        citation_verify = CitationVerifyResult(
            passed=False,
            cited_refs=["제17조"],
            verified_refs=[],
            unverified_refs=["제17조"],
            accuracy=0.0,
        )

        violations = _build_violation_details(
            prohibited_violations, has_citation, has_evidence, citation_verify
        )

        # 위반 사항 확인
        assert len(violations) >= 2  # 금지표현 + hallucination

        # 구조 확인
        for v in violations:
            assert "type" in v
            assert "description" in v
            assert "severity" in v
            assert v["type"] in (
                "prohibited_expression",
                "hallucination",
                "query_mismatch",
                "legal_judgment",
            )

    def test_build_retry_context(self):
        """retry_context 생성 테스트"""
        from app.agents.legal_review.agent import _build_retry_context

        violations = [
            {
                "type": "prohibited_expression",
                "description": "금지 표현 발견",
                "severity": "critical",
            },
        ]
        draft_answer = "이전 답변"
        retry_count = 0

        retry_ctx = _build_retry_context(violations, draft_answer, retry_count)

        assert "violations" in retry_ctx
        assert "previous_draft" in retry_ctx
        assert "retry_count" in retry_ctx
        assert retry_ctx["retry_count"] == 0


@pytest.mark.integration
@pytest.mark.e2e
class TestE2EV2:
    """E2E 테스트 (Docker DB 필요)"""

    def test_full_pipeline_dispute_query(self):
        """분쟁 쿼리 전체 파이프라인 테스트"""
        from app.supervisor.graph_mas import get_mas_supervisor_graph

        graph = get_mas_supervisor_graph()

        initial_state = {
            "messages": [],
            "user_query": "노트북 구입 후 일주일만에 고장났는데 환불 받을 수 있나요?",
            "chat_type": "dispute",
            "session_id": "test_session_v2",
        }

        config = {"configurable": {"thread_id": "test_v2_e2e"}}

        # 그래프 실행
        result = asyncio.run(graph.ainvoke(initial_state, config))

        # 결과 확인
        assert result is not None
        print("\n[E2E Result]")
        print(f"  mode: {result.get('mode')}")
        print(f"  final_answer length: {len(result.get('final_answer', '') or '')}")

        if result.get("query_analysis"):
            qa = result["query_analysis"]
            print(f"  intent: {qa.get('intent')}")
            print(f"  expanded_queries: {len(qa.get('expanded_queries', []))}")
            print(f"  retriever_types: {qa.get('retriever_types')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s", "--tb=short"])
