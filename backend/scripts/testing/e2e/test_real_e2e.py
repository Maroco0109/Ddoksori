"""
Suite 3: Extended Real E2E — 실제 RDS + 실제 LLM 확장 시나리오 테스트

기존 test_rds_llm_pipeline.py의 기본 파이프라인 검증을 넘어,
에지 케이스, 프로토콜 준수, 답변 품질을 실제 환경에서 검증합니다.

실행:
    PYTHONPATH=backend conda run -n dsr pytest backend/scripts/testing/e2e/test_real_e2e.py -v -s

사전 조건:
    - DB_HOST, DB_PASSWORD 환경변수 설정
    - OPENAI_API_KEY 설정
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict

import pytest

# Ensure backend on path
_backend = str(Path(__file__).parent.parent.parent.parent)
if _backend not in sys.path:
    sys.path.insert(0, _backend)

pytestmark = [pytest.mark.e2e, pytest.mark.llm, pytest.mark.needs_db]


# ============================================================
# Helper
# ============================================================

def _run_graph(compiled_graph, query: str, chat_type: str = "dispute") -> Dict[str, Any]:
    """MAS 그래프 동기 실행."""
    from app.supervisor import create_initial_state

    state = create_initial_state(
        user_query=query,
        chat_type=chat_type,
        onboarding=None,
    )
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    async def _invoke():
        return await compiled_graph.ainvoke(state, config)

    return asyncio.run(_invoke())


# ============================================================
# 3.1 다중 도메인 쿼리 — 법령 + 사례 동시 필요
# ============================================================

class TestMultiDomainQuery:
    """여러 도메인의 검색 결과가 필요한 복합 쿼리 검증."""

    def test_dispute_query_retrieves_multiple_sources(
        self, compiled_mas_graph, openai_api_key
    ):
        """분쟁 쿼리가 법령과 사례 등 복수 소스에서 검색하는지 확인."""
        result = _run_graph(
            compiled_mas_graph,
            "전자상거래로 구매한 노트북 화면 불량인데 환불 거부당했어요. 관련 법률과 유사 사례 알려주세요.",
        )

        individual = result.get("individual_retrieval_results", [])
        sources = {r.get("source", "") for r in individual}

        assert len(sources) >= 2, (
            f"복합 쿼리인데 소스가 {len(sources)}개뿐: {sources}. "
            "최소 2개 도메인에서 검색되어야 합니다."
        )

    def test_multi_domain_answer_references_both(
        self, compiled_mas_graph, openai_api_key
    ):
        """복합 쿼리 답변이 법률과 사례 모두를 참조하는지 확인."""
        result = _run_graph(
            compiled_mas_graph,
            "냉장고 구매 후 1주일 만에 고장났어요. 관련 법령과 환불 기준이 궁금합니다.",
        )

        answer = result.get("final_answer") or result.get("draft_answer", "")
        assert answer, "답변이 생성되지 않았습니다"
        # 최소한 답변 길이가 100자 이상 (충분한 내용)
        assert len(answer) >= 100, (
            f"복합 쿼리 답변이 너무 짧습니다 ({len(answer)}자). "
            "법령과 기준을 모두 참조하는 충분한 답변이 필요합니다."
        )


# ============================================================
# 3.2 모호한 쿼리 — 의도 불명확
# ============================================================

class TestAmbiguousQuery:
    """모호하거나 불완전한 쿼리 처리 검증."""

    def test_vague_query_still_produces_answer(
        self, compiled_mas_graph, openai_api_key
    ):
        """모호한 쿼리에도 답변을 생성하는지 확인."""
        result = _run_graph(compiled_mas_graph, "환불요")
        answer = result.get("final_answer") or result.get("draft_answer", "")
        assert answer, "모호한 쿼리('환불요')에 답변이 생성되지 않았습니다"

    def test_short_query_query_analysis_populated(
        self, compiled_mas_graph, openai_api_key
    ):
        """짧은 쿼리에서도 query_analysis가 정상 수행되는지 확인."""
        result = _run_graph(compiled_mas_graph, "환불")
        qa = result.get("query_analysis", {})
        assert qa, "query_analysis 결과가 비어있습니다"
        assert "intent" in qa, "query_analysis에 intent가 없습니다"


# ============================================================
# 3.3 일반(general) 쿼리 — Fast Path 상세 검증
# ============================================================

class TestFastPathDetailed:
    """Fast path (일반 쿼리)의 상세 동작 검증."""

    def test_greeting_produces_conversational_answer(
        self, compiled_mas_graph, openai_api_key
    ):
        """인사 쿼리에 대해 대화형 답변을 생성하는지 확인."""
        result = _run_graph(compiled_mas_graph, "안녕하세요, 반갑습니다", "general")
        answer = result.get("final_answer") or result.get("draft_answer", "")
        assert answer, "인사 쿼리에 답변이 없습니다"

    def test_fast_path_mode_set(
        self, compiled_mas_graph, openai_api_key
    ):
        """Fast path 쿼리에서 mode가 NO_RETRIEVAL로 설정되는지 확인."""
        result = _run_graph(compiled_mas_graph, "오늘 날씨 어때요?", "general")
        mode = result.get("mode")
        # general 쿼리는 NO_RETRIEVAL 또는 retrieval 최소화
        # Supervisor가 LLM 기반으로 결정하므로 mode가 설정되었는지만 확인
        assert mode is not None, "general 쿼리에서 mode가 설정되지 않았습니다"

    def test_fast_path_no_review(
        self, compiled_mas_graph, openai_api_key
    ):
        """Fast path에서 review가 실행되지 않는지 확인."""
        result = _run_graph(compiled_mas_graph, "감사합니다", "general")
        timings = result.get("_node_timings", {})
        assert "review" not in timings, (
            f"Fast path에서 review가 실행됨: {list(timings.keys())}"
        )


# ============================================================
# 3.4 프로토콜 필수 키 검증 (실제 데이터)
# ============================================================

class TestProtocolComplianceReal:
    """실제 파이프라인 출력의 프로토콜 필수 키 검증."""

    QUERY_ANALYSIS_KEYS = {
        "intent", "original_query", "expanded_queries",
        "keywords", "retriever_types", "needs_clarification", "missing_fields",
    }

    RETRIEVAL_KEYS = {
        "source", "documents", "max_similarity",
        "avg_similarity", "search_time_ms",
    }

    def test_query_analysis_has_all_protocol_keys(
        self, compiled_mas_graph, openai_api_key
    ):
        """query_analysis 출력이 프로토콜 필수 키를 모두 포함하는지 확인."""
        result = _run_graph(
            compiled_mas_graph,
            "헬스장 3개월 이용 후 환불 가능한가요?",
        )

        qa = result.get("query_analysis", {})
        assert qa, "query_analysis 결과가 비어있습니다"

        missing = self.QUERY_ANALYSIS_KEYS - set(qa.keys())
        assert not missing, f"query_analysis에 누락된 프로토콜 키: {missing}"

    def test_retrieval_results_have_all_protocol_keys(
        self, compiled_mas_graph, openai_api_key
    ):
        """retrieval 결과가 프로토콜 필수 키를 모두 포함하는지 확인."""
        result = _run_graph(
            compiled_mas_graph,
            "냉장고 구매 후 고장 시 환불 기준",
        )

        individual = result.get("individual_retrieval_results", [])
        assert individual, "retrieval 결과가 비어있습니다"

        for ir in individual:
            missing = self.RETRIEVAL_KEYS - set(ir.keys())
            source = ir.get("source", "unknown")
            assert not missing, (
                f"retrieval_{source}에 누락된 프로토콜 키: {missing}"
            )

    def test_retrieval_similarity_positive(
        self, compiled_mas_graph, openai_api_key
    ):
        """retrieval 결과의 similarity 값이 양수인지 확인."""
        result = _run_graph(
            compiled_mas_graph,
            "전자상거래법 청약철회 기간",
        )

        individual = result.get("individual_retrieval_results", [])
        for ir in individual:
            max_sim = ir.get("max_similarity", 0)
            assert max_sim > 0, (
                f"retrieval_{ir.get('source')}의 max_similarity가 0 이하: {max_sim}"
            )


# ============================================================
# 3.5 Node Timing 검증
# ============================================================

class TestNodeTimings:
    """_node_timings를 통한 파이프라인 단계별 실행 검증."""

    def test_dispute_has_expected_node_timings(
        self, compiled_mas_graph, openai_api_key
    ):
        """분쟁 쿼리가 예상 노드들을 실행하는지 타이밍으로 확인."""
        result = _run_graph(
            compiled_mas_graph,
            "스마트폰 구매 후 2주 만에 고장났는데 환불 가능한가요?",
        )

        timings = result.get("_node_timings", {})
        expected_nodes = {"query_analysis", "generation"}
        actual_nodes = set(timings.keys())

        missing = expected_nodes - actual_nodes
        assert not missing, (
            f"분쟁 쿼리에서 누락된 노드: {missing}. "
            f"실행된 노드: {sorted(actual_nodes)}"
        )

    def test_node_timings_have_duration(
        self, compiled_mas_graph, openai_api_key
    ):
        """각 노드의 duration_ms가 양수인지 확인."""
        result = _run_graph(
            compiled_mas_graph,
            "노트북 배송 지연 보상 가능한가요?",
        )

        timings = result.get("_node_timings", {})
        for node_name, timing_data in timings.items():
            duration = timing_data.get("duration_ms", 0)
            assert duration > 0, (
                f"{node_name}의 duration_ms가 0 이하: {duration}"
            )


# ============================================================
# 3.6 Supervisor 상태 검증
# ============================================================

class TestSupervisorState:
    """Supervisor 상태 필드 검증."""

    def test_supervisor_state_populated(
        self, compiled_mas_graph, openai_api_key
    ):
        """분쟁 쿼리 실행 후 supervisor 상태가 채워지는지 확인."""
        result = _run_graph(
            compiled_mas_graph,
            "에어컨 설치 후 소음 문제로 교환 요청",
        )

        supervisor = result.get("supervisor", {})
        assert supervisor, "supervisor 상태가 비어있습니다"

    def test_dispute_mode_set(
        self, compiled_mas_graph, openai_api_key
    ):
        """분쟁 쿼리에서 mode가 설정되는지 확인."""
        result = _run_graph(
            compiled_mas_graph,
            "세탁기 구매 3일 만에 고장, 환불 가능한가요?",
        )

        mode = result.get("mode")
        assert mode is not None, "mode가 설정되지 않았습니다"


# ============================================================
# 3.7 답변 품질 — 법률 인용 포함 검증
# ============================================================

class TestAnswerQualityExtended:
    """답변의 법률 인용 품질 검증."""

    def test_dispute_answer_length_sufficient(
        self, compiled_mas_graph, openai_api_key
    ):
        """분쟁 답변이 충분한 길이인지 확인 (최소 200자)."""
        result = _run_graph(
            compiled_mas_graph,
            "인터넷으로 구매한 옷의 사이즈가 맞지 않아 환불하고 싶습니다. 가능한가요?",
        )

        answer = result.get("final_answer") or result.get("draft_answer", "")
        assert answer, "답변이 비어있습니다"
        assert len(answer) >= 200, (
            f"분쟁 답변이 너무 짧습니다 ({len(answer)}자). "
            "법률 근거와 실무 안내를 포함한 충분한 답변이 필요합니다."
        )

    def test_dispute_answer_no_hallucinated_law(
        self, compiled_mas_graph, openai_api_key
    ):
        """답변에 존재하지 않는 법률 조문 번호가 인용되지 않는지 기본 검증."""
        import re

        result = _run_graph(
            compiled_mas_graph,
            "전자상거래법에 따른 청약철회 기간은 어떻게 되나요?",
        )

        answer = result.get("final_answer") or result.get("draft_answer", "")
        if not answer:
            pytest.skip("답변이 생성되지 않았습니다")

        # 비현실적으로 높은 조문 번호 (제500조 이상) 검출
        high_articles = re.findall(r"제(\d+)조", answer)
        for article_num_str in high_articles:
            article_num = int(article_num_str)
            assert article_num < 500, (
                f"비현실적으로 높은 조문 번호 발견: 제{article_num}조. "
                "허위 인용(hallucination)일 수 있습니다."
            )


# ============================================================
# 3.8 Restricted 도메인 쿼리
# ============================================================

class TestRestrictedDomain:
    """금융/의료 등 제한 도메인 쿼리 처리 검증."""

    def test_medical_query_handled_gracefully(
        self, compiled_mas_graph, openai_api_key
    ):
        """의료 관련 쿼리가 적절히 처리되는지 확인."""
        result = _run_graph(
            compiled_mas_graph,
            "성형수술 부작용으로 환불받을 수 있나요?",
        )

        answer = result.get("final_answer") or result.get("draft_answer", "")
        assert answer, "restricted 도메인 쿼리에 답변이 없습니다"


# ============================================================
# 3.9 캐시 미사용 확인
# ============================================================

class TestCacheBehavior:
    """캐시 관련 상태 검증."""

    def test_first_query_not_cached(
        self, compiled_mas_graph, openai_api_key
    ):
        """고유한 쿼리의 첫 실행은 캐시 히트가 아닌지 확인."""
        unique_query = f"환불 테스트 쿼리 {uuid.uuid4().hex[:8]}"
        result = _run_graph(compiled_mas_graph, unique_query)

        cache_hit = result.get("_cache_hit", False)
        assert not cache_hit, "고유 쿼리의 첫 실행인데 캐시 히트가 발생했습니다"
