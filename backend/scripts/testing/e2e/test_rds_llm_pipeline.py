"""
Suite 2: RDS + LLM 전체 파이프라인 테스트

실제 RDS DB와 OpenAI API를 사용하여 전체 E2E 파이프라인을 검증합니다.

전제 조건:
    - DB_HOST 설정
    - OPENAI_API_KEY 설정

실행:
    PYTHONPATH=backend conda run -n dsr pytest backend/scripts/testing/e2e/test_rds_llm_pipeline.py -v
"""

import asyncio
import inspect
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict

import pytest

# Ensure backend is on sys.path
_backend_root = str(Path(__file__).parent.parent.parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from app.common.config import get_config

# ============================================================
# Helper: MAS 그래프 실행 (동기 래퍼)
# ============================================================


def _run_mas_graph(
    compiled_graph, user_query: str, chat_type: str = "dispute"
) -> Dict[str, Any]:
    """MAS Supervisor 그래프를 invoke하고 최종 state를 반환합니다 (동기)."""
    from app.supervisor import create_initial_state

    initial_state = create_initial_state(
        user_query=user_query,
        chat_type=chat_type,
        onboarding=None,
    )

    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async def _invoke():
        return await compiled_graph.ainvoke(initial_state, config)

    return asyncio.run(_invoke())


# ============================================================
# Test 2.1: Retrieval — Law 도메인 검색
# ============================================================


@pytest.mark.e2e
@pytest.mark.needs_db
class TestLawRetrieval:
    def test_law_retrieval_returns_results(self, hybrid_retriever):
        """법령 에이전트가 vector_chunks에서 결과를 반환하는지 확인"""
        results = hybrid_retriever.search(
            query="전자상거래법 청약철회 조항",
            top_k=5,
            dataset_type_filter="law_guide",
        )
        assert len(results) > 0, "법령 검색 결과가 0건입니다"

    def test_law_retrieval_positive_similarity(self, hybrid_retriever):
        """법령 검색 결과의 similarity가 양수인지 확인"""
        results = hybrid_retriever.search(
            query="소비자보호법 청약철회 기간",
            top_k=5,
            dataset_type_filter="law_guide",
        )
        if results:
            for r in results:
                assert r.similarity > 0, f"similarity가 0 이하: {r.similarity}"


# ============================================================
# Test 2.2: Retrieval — Criteria 도메인 검색
# ============================================================


@pytest.mark.e2e
@pytest.mark.needs_db
class TestCriteriaRetrieval:
    def test_criteria_retrieval_returns_results(self, hybrid_retriever):
        """분쟁해결기준 에이전트가 결과를 반환하는지 확인"""
        results = hybrid_retriever.search(
            query="냉장고 환불 기준",
            top_k=5,
            dataset_type_filter="law_guide",
            chunk_type_filter=["별표1_품목매핑", "별표3_품질보증", "별표4_내용연수"],
        )
        assert len(results) > 0, "분쟁해결기준 검색 결과가 0건입니다"

    def test_criteria_no_duplicate_chunk_ids(self, hybrid_retriever):
        """분쟁해결기준 검색 결과에 중복 chunk_id가 없는지 확인"""
        results = hybrid_retriever.search(
            query="냉장고 환불 기준",
            top_k=10,
            dataset_type_filter="law_guide",
            chunk_type_filter=["별표1_품목매핑", "별표3_품질보증", "별표4_내용연수"],
        )
        if results:
            chunk_ids = [r.chunk_id for r in results]
            assert len(chunk_ids) == len(set(chunk_ids)), (
                f"중복 chunk_id 발견: {[c for c in chunk_ids if chunk_ids.count(c) > 1]}"
            )


# ============================================================
# Test 2.3: Retrieval — Case 도메인 검색
# ============================================================


@pytest.mark.e2e
@pytest.mark.needs_db
class TestCaseRetrieval:
    def test_case_retrieval_returns_results(self, hybrid_retriever):
        """분쟁사례 에이전트가 결과를 반환하는지 확인"""
        results = hybrid_retriever.search(
            query="전자제품 반품 거부",
            top_k=5,
            category_filter=["조정", "해결", "상담"],
        )
        assert len(results) > 0, "분쟁사례 검색 결과가 0건입니다"


# ============================================================
# Test 2.4: Retrieval — Hybrid RRF Fusion
# ============================================================


@pytest.mark.e2e
@pytest.mark.needs_db
class TestHybridRRFFusion:
    def test_hybrid_rrf_returns_results(self, hybrid_retriever):
        """Dense + Lexical RRF 결과가 정상 병합되는지 확인"""
        results = hybrid_retriever.search(query="환불", top_k=5)
        assert len(results) > 0, "Hybrid RRF 검색 결과가 0건입니다"

    def test_rrf_scores_in_valid_range(self, hybrid_retriever):
        """RRF 점수가 유효한 범위(> 0)인지 확인"""
        results = hybrid_retriever.search(query="환불", top_k=5)
        if results:
            for r in results:
                assert r.similarity > 0, f"RRF score가 0 이하: {r.similarity}"


# ============================================================
# Test 2.5: Dispute 전체 파이프라인
# ============================================================


@pytest.mark.e2e
@pytest.mark.llm
@pytest.mark.needs_db
class TestDisputeFullPipeline:
    def test_dispute_pipeline_produces_answer(self, compiled_mas_graph, openai_api_key):
        """분쟁 쿼리의 전체 파이프라인이 답변을 생성하는지 확인"""
        result = _run_mas_graph(
            compiled_mas_graph,
            user_query="노트북 구매 후 화면 불량인데 환불 가능한가요?",
            chat_type="dispute",
        )

        final_answer = result.get("final_answer", "")
        assert final_answer, "final_answer가 비어있습니다"

    def test_dispute_pipeline_has_retrieval(self, compiled_mas_graph, openai_api_key):
        """분쟁 파이프라인에서 retrieval 결과가 존재하는지 확인"""
        result = _run_mas_graph(
            compiled_mas_graph,
            user_query="노트북 구매 후 화면 불량인데 환불 가능한가요?",
            chat_type="dispute",
        )

        individual = result.get("individual_retrieval_results", [])
        retrieval = result.get("retrieval", {})

        has_results = bool(individual) or bool(retrieval)
        assert has_results, "retrieval 결과가 존재하지 않습니다"

    def test_dispute_no_prohibited_expressions(
        self, compiled_mas_graph, openai_api_key
    ):
        """분쟁 답변에 금지 표현이 없는지 확인"""
        from app.agents.legal_review.agent import _check_prohibited_expressions

        result = _run_mas_graph(
            compiled_mas_graph,
            user_query="노트북 구매 후 화면 불량인데 환불 가능한가요?",
            chat_type="dispute",
        )

        final_answer = result.get("final_answer", "")
        if final_answer:
            violations = _check_prohibited_expressions(final_answer)
            assert len(violations) == 0, f"금지 표현 발견: {violations}"


# ============================================================
# Test 2.6: Law Query Pipeline
# ============================================================


@pytest.mark.e2e
@pytest.mark.llm
@pytest.mark.needs_db
class TestLawQueryPipeline:
    def test_law_pipeline_produces_answer(self, compiled_mas_graph, openai_api_key):
        """법령 쿼리의 전체 파이프라인이 답변을 생성하는지 확인"""
        result = _run_mas_graph(
            compiled_mas_graph,
            user_query="소비자보호법에서 청약철회 기간은?",
            chat_type="dispute",
        )

        final_answer = result.get("final_answer", "")
        assert final_answer, "final_answer가 비어있습니다"


# ============================================================
# Test 2.7: Criteria Query Pipeline
# ============================================================


@pytest.mark.e2e
@pytest.mark.llm
@pytest.mark.needs_db
class TestCriteriaQueryPipeline:
    def test_criteria_pipeline_produces_answer(
        self, compiled_mas_graph, openai_api_key
    ):
        """분쟁해결기준 쿼리의 전체 파이프라인이 답변을 생성하는지 확인"""
        result = _run_mas_graph(
            compiled_mas_graph,
            user_query="냉장고 품질보증기간이 어떻게 되나요?",
            chat_type="dispute",
        )

        final_answer = result.get("final_answer", "")
        assert final_answer, "final_answer가 비어있습니다"


# ============================================================
# Test 2.8: General Query Fast Path
# ============================================================


@pytest.mark.e2e
@pytest.mark.llm
class TestGeneralQueryFastPath:
    def test_general_query_produces_answer(self, compiled_mas_graph, openai_api_key):
        """일반 질문이 답변을 생성하는지 확인"""
        result = _run_mas_graph(
            compiled_mas_graph,
            user_query="안녕하세요",
            chat_type="general",
        )

        final_answer = result.get("final_answer", "")
        assert final_answer, "general 쿼리의 final_answer가 비어있습니다"

    def test_general_query_no_retrieval(self, compiled_mas_graph, openai_api_key):
        """일반 질문은 retrieval이 생략되는지 확인"""
        result = _run_mas_graph(
            compiled_mas_graph,
            user_query="안녕하세요",
            chat_type="general",
        )

        individual = result.get("individual_retrieval_results", [])
        if individual:
            total_docs = sum(len(ir.get("documents", [])) for ir in individual)
            assert total_docs == 0, (
                f"general 쿼리인데 retrieval 결과가 {total_docs}건 존재합니다"
            )


# ============================================================
# Test 2.9: LLM 답변 품질 검증 — 금지 표현
# ============================================================


@pytest.mark.e2e
@pytest.mark.llm
@pytest.mark.needs_db
class TestAnswerQuality:
    def test_multiple_dispute_queries_no_prohibited(
        self, compiled_mas_graph, openai_api_key
    ):
        """여러 dispute 쿼리에 금지 표현이 없는지 확인"""
        from app.agents.legal_review.agent import _check_prohibited_expressions

        queries = [
            "전자상거래 환불 규정이 어떻게 되나요?",
            "배송지연으로 인한 손해배상 받을 수 있나요?",
        ]

        for query in queries:
            result = _run_mas_graph(
                compiled_mas_graph,
                user_query=query,
                chat_type="dispute",
            )

            final_answer = result.get("final_answer", "")
            if final_answer:
                violations = _check_prohibited_expressions(final_answer)
                assert len(violations) == 0, (
                    f"쿼리 '{query[:20]}...'의 답변에 금지 표현 발견: {violations}"
                )


# ============================================================
# Test 2.10: LLM 답변 출처 인용 검증
# ============================================================


@pytest.mark.e2e
@pytest.mark.llm
@pytest.mark.needs_db
class TestAnswerCitations:
    def test_dispute_answer_has_sources(self, compiled_mas_graph, openai_api_key):
        """dispute 답변에 출처 정보가 포함되는지 확인"""
        result = _run_mas_graph(
            compiled_mas_graph,
            user_query="환불 거부당했는데 어떻게 해야 하나요?",
            chat_type="dispute",
        )

        sources = result.get("sources", [])
        citations = result.get("citations", [])

        has_source_info = bool(sources) or bool(citations)
        if not has_source_info:
            from app.agents.legal_review.agent import CITATION_PATTERNS

            final_answer = result.get("final_answer", "")
            has_citation_in_text = any(
                re.search(p, final_answer) for p in CITATION_PATTERNS
            )
            assert has_citation_in_text, (
                "dispute 답변에 sources도 없고, 텍스트 내 인용 패턴도 없습니다"
            )


# ============================================================
# Test 2.11: Similarity Threshold 도메인별 적용 검증
# ============================================================


@pytest.mark.e2e
@pytest.mark.unit
class TestDomainThresholdFiltering:
    def test_threshold_code_defaults(self):
        """각 도메인별 threshold 코드 기본값 확인"""
        from app.common.config import AgentSettings

        fields = AgentSettings.model_fields
        assert fields["similarity_threshold_law"].default == 0.60
        assert fields["similarity_threshold_criteria"].default == 0.50
        assert fields["similarity_threshold_dispute"].default == 0.55

    def test_base_agent_process_computes_similarity(self):
        """BaseRetrievalAgent.process()에 유사도 계산 로직이 있는지 확인"""
        from app.agents.retrieval.base_retrieval_agent import BaseRetrievalAgent

        source = inspect.getsource(BaseRetrievalAgent.process)

        # 현재 아키텍처: BaseRetrievalAgent.process()는 max_similarity/avg_similarity를 계산
        assert "max_sim" in source, (
            "BaseRetrievalAgent.process()에 max_sim 계산 로직이 없습니다"
        )
        assert "avg_sim" in source, (
            "BaseRetrievalAgent.process()에 avg_sim 계산 로직이 없습니다"
        )
        assert "_execute_search" in source, (
            "BaseRetrievalAgent.process()에 _execute_search 호출이 없습니다"
        )
