"""
Retrieval Agents 테스트 - LawRetrievalAgent, CriteriaRetrievalAgent,
CaseRetrievalAgent, CounselRetrievalAgent, BaseRetrievalAgent
작성일: 2026-02-08

테스트 대상:
- 각 에이전트의 agent_name, agent_description
- BaseRetrievalAgent.process() 흐름 (validate → search → format → report)
- BaseRetrievalAgent.validate_request()
- LawRetrievalAgent._format_results, _build_sources
- CriteriaRetrievalAgent._format_results, _build_sources
- CaseRetrievalAgent._get_search_filters, _format_results, _build_sources
- CounselRetrievalAgent._get_search_filters, _format_results, _build_sources
- LawRetrievalAgent article pattern matching regex
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

backend_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_path))

import pytest

pytestmark = pytest.mark.unit


# ============================================================================
# Mock result objects matching actual DB result shapes
# ============================================================================


def _make_similar_chunk_result(**kwargs):
    """SimilarChunkResult-like object for law/criteria agents."""
    defaults = {
        "chunk_id": "test_chunk_1",
        "text": "테스트 법률 내용",
        "similarity": 0.85,
        "rrf_score": 0.5,
        "law_name": "소비자기본법",
        "document_type": "법률",
        "dataset_type": "law_guide",
        "category": None,
        "chunk_type": None,
        "source_url": None,
        "source_file": None,
        "printed_page": None,
        "source_year": None,
        "metadata": {"hierarchy_path": "소비자기본법 > 제1장", "조문번호": "제1조"},
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_search_result(**kwargs):
    """SearchResult-like object for case/counsel agents."""
    defaults = {
        "chunk_id": "case_chunk_1",
        "doc_id": "doc_1",
        "chunk_type": "본문",
        "content": "분쟁 사례 내용",
        "doc_title": "노트북 환불 분쟁",
        "source_org": "한국소비자원",
        "url": "https://example.com",
        "source_file": "case_001.pdf",
        "printed_page": 1,
        "decision_date": "2025-01-15",
        "similarity": 0.78,
        "metadata": {"category": "전자제품"},
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ============================================================================
# LawRetrievalAgent tests
# ============================================================================


class TestLawRetrievalAgentMeta:
    """LawRetrievalAgent 메타데이터 테스트"""

    def test_agent_name(self):
        from app.agents.retrieval.law_agent import LawRetrievalAgent

        agent = LawRetrievalAgent()
        assert agent.agent_name == "retrieval_law"

    def test_agent_description_not_empty(self):
        from app.agents.retrieval.law_agent import LawRetrievalAgent

        agent = LawRetrievalAgent()
        assert len(agent.agent_description) > 0

    def test_required_inputs(self):
        from app.agents.retrieval.law_agent import LawRetrievalAgent

        agent = LawRetrievalAgent()
        assert "user_query" in agent.required_inputs


class TestLawRetrievalAgentFormatting:
    """LawRetrievalAgent 결과 포맷팅 테스트"""

    def test_format_results(self):
        from app.agents.retrieval.law_agent import LawRetrievalAgent

        agent = LawRetrievalAgent()
        results = [
            _make_similar_chunk_result(
                chunk_id="law_1",
                text="제1조 내용",
                similarity=0.9,
                law_name="소비자기본법",
            ),
        ]
        formatted = agent._format_results(results)
        assert len(formatted) == 1
        assert formatted[0]["chunk_id"] == "law_1"
        assert formatted[0]["content"] == "제1조 내용"
        assert formatted[0]["similarity"] == 0.9
        assert formatted[0]["metadata"]["law_name"] == "소비자기본법"

    def test_build_sources(self):
        from app.agents.retrieval.law_agent import LawRetrievalAgent

        agent = LawRetrievalAgent()
        results = [
            _make_similar_chunk_result(
                chunk_id="law_1",
                law_name="전자상거래법",
                similarity=0.85,
            ),
        ]
        sources = agent._build_sources(results)
        assert len(sources) == 1
        assert sources[0]["type"] == "law"
        assert sources[0]["index"] == 1
        assert sources[0]["chunk_id"] == "law_1"
        assert sources[0]["law_name"] == "전자상거래법"

    def test_format_results_empty(self):
        from app.agents.retrieval.law_agent import LawRetrievalAgent

        agent = LawRetrievalAgent()
        formatted = agent._format_results([])
        assert formatted == []


class TestLawArticlePatternMatching:
    """법령 조문 패턴 매칭 테스트"""

    def test_article_pattern_basic(self):
        """기본 조문 패턴: '소비자기본법 제10조'"""
        import re

        pattern = r"([\w가-힣]+법?)\s*제?(\d+)조"
        match = re.search(pattern, "소비자기본법 제10조에 대해 알려줘")
        assert match is not None
        assert match.group(1) == "소비자기본법"
        assert match.group(2) == "10"

    def test_article_pattern_without_je(self):
        """'제' 없이 조문번호: '전자상거래법 17조'"""
        import re

        pattern = r"([\w가-힣]+법?)\s*제?(\d+)조"
        match = re.search(pattern, "전자상거래법 17조")
        assert match is not None
        assert match.group(2) == "17"

    def test_article_pattern_no_match(self):
        """조문 패턴 없는 일반 쿼리"""
        import re

        pattern = r"([\w가-힣]+법?)\s*제?(\d+)조"
        match = re.search(pattern, "환불 받을 수 있나요?")
        assert match is None

    def test_law_name_normalization(self):
        """법률명 정규화: '전자상거래' → '전자상거래법'"""
        import re

        pattern = r"([\w가-힣]+법?)\s*제?(\d+)조"
        match = re.search(pattern, "전자상거래 제20조")
        assert match is not None
        law_name_part = match.group(1)
        if not law_name_part.endswith("법"):
            law_name_part = law_name_part + "법"
        assert law_name_part == "전자상거래법"


# ============================================================================
# CriteriaRetrievalAgent tests
# ============================================================================


class TestCriteriaRetrievalAgentMeta:
    """CriteriaRetrievalAgent 메타데이터 테스트"""

    def test_agent_name(self):
        from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent

        agent = CriteriaRetrievalAgent()
        assert agent.agent_name == "retrieval_criteria"

    def test_agent_description_not_empty(self):
        from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent

        agent = CriteriaRetrievalAgent()
        assert len(agent.agent_description) > 0


class TestCriteriaRetrievalAgentFormatting:
    """CriteriaRetrievalAgent 결과 포맷팅 테스트"""

    def test_format_results(self):
        from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent

        agent = CriteriaRetrievalAgent()
        results = [
            _make_similar_chunk_result(
                chunk_id="criteria_1",
                text="분쟁해결기준 내용",
                similarity=0.8,
                category="전자제품",
                metadata={
                    "source_label": "분쟁해결기준",
                    "item": "노트북",
                    "title": "전자제품 기준",
                },
            ),
        ]
        formatted = agent._format_results(results)
        assert len(formatted) == 1
        assert formatted[0]["chunk_id"] == "criteria_1"
        assert formatted[0]["metadata"]["category"] == "전자제품"

    def test_build_sources(self):
        from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent

        agent = CriteriaRetrievalAgent()
        results = [
            _make_similar_chunk_result(
                chunk_id="criteria_1",
                category="서비스",
                similarity=0.75,
                metadata={"source_label": "소비자분쟁해결기준", "item": "헬스장"},
            ),
        ]
        sources = agent._build_sources(results)
        assert len(sources) == 1
        assert sources[0]["type"] == "criteria"
        assert sources[0]["category"] == "서비스"


class TestCriteriaKeywordExtraction:
    """CriteriaRetrievalAgent 키워드 추출 테스트"""

    def test_extract_item_from_metadata(self):
        """metadata에서 품목 추출"""
        from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent

        agent = CriteriaRetrievalAgent()
        task_input = {"metadata_filter": {"item": "종묘"}}
        result = agent._extract_keywords_from_query("종묘 분쟁", task_input)
        assert result == "종묘"

    def test_extract_no_keyword(self):
        """키워드 추출 실패 시 빈 문자열"""
        from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent

        agent = CriteriaRetrievalAgent()
        result = agent._extract_keywords_from_query("", None)
        assert result == ""


# ============================================================================
# CaseRetrievalAgent tests
# ============================================================================


class TestCaseRetrievalAgentMeta:
    """CaseRetrievalAgent 메타데이터 테스트"""

    def test_agent_name(self):
        from app.agents.retrieval.case_agent import CaseRetrievalAgent

        agent = CaseRetrievalAgent()
        assert agent.agent_name == "retrieval_case"

    def test_domain_key(self):
        from app.agents.retrieval.case_agent import CaseRetrievalAgent

        agent = CaseRetrievalAgent()
        assert agent.domain_key == "case"


class TestCaseRetrievalAgentFilters:
    """CaseRetrievalAgent 검색 필터 테스트"""

    def test_default_filter(self):
        """기본 필터: dataset_filter='case'"""
        from app.agents.retrieval.case_agent import CaseRetrievalAgent

        agent = CaseRetrievalAgent()
        filters = agent._get_search_filters()
        assert filters["dataset_filter"] == "case"

    def test_single_category_filter(self):
        """단일 카테고리 필터"""
        from app.agents.retrieval.case_agent import CaseRetrievalAgent

        agent = CaseRetrievalAgent()
        filters = agent._get_search_filters({"categories": ["조정"]})
        assert filters["category_filter"] == "조정"

    def test_multiple_categories_no_filter(self):
        """복수 카테고리 → category_filter 없음 (전체 검색)"""
        from app.agents.retrieval.case_agent import CaseRetrievalAgent

        agent = CaseRetrievalAgent()
        filters = agent._get_search_filters({"categories": ["조정", "해결"]})
        assert "category_filter" not in filters


class TestCaseRetrievalAgentFormatting:
    """CaseRetrievalAgent 결과 포맷팅 테스트"""

    def test_format_results(self):
        from app.agents.retrieval.case_agent import CaseRetrievalAgent

        agent = CaseRetrievalAgent()
        results = [_make_search_result()]
        formatted = agent._format_results(results)
        assert len(formatted) == 1
        assert formatted[0]["chunk_id"] == "case_chunk_1"
        assert formatted[0]["doc_title"] == "노트북 환불 분쟁"
        assert formatted[0]["source_org"] == "한국소비자원"

    def test_build_sources(self):
        from app.agents.retrieval.case_agent import CaseRetrievalAgent

        agent = CaseRetrievalAgent()
        results = [_make_search_result()]
        sources = agent._build_sources(results)
        assert sources[0]["type"] == "mediation_case"
        assert sources[0]["doc_id"] == "doc_1"


# ============================================================================
# CounselRetrievalAgent tests
# ============================================================================


class TestCounselRetrievalAgentMeta:
    """CounselRetrievalAgent 메타데이터 테스트"""

    def test_agent_name(self):
        from app.agents.retrieval.counsel_agent import CounselRetrievalAgent

        agent = CounselRetrievalAgent()
        assert agent.agent_name == "retrieval_counsel"

    def test_domain_key(self):
        from app.agents.retrieval.counsel_agent import CounselRetrievalAgent

        agent = CounselRetrievalAgent()
        assert agent.domain_key == "counsel"


class TestCounselRetrievalAgentFilters:
    """CounselRetrievalAgent 검색 필터 테스트"""

    def test_default_filter_includes_counsel_category(self):
        """기본 필터: dataset_filter='case', category_filter='상담'"""
        from app.agents.retrieval.counsel_agent import CounselRetrievalAgent

        agent = CounselRetrievalAgent()
        filters = agent._get_search_filters()
        assert filters["dataset_filter"] == "case"
        assert filters["category_filter"] == "상담"

    def test_multiple_categories_removes_filter(self):
        """복수 카테고리 → category_filter 제거"""
        from app.agents.retrieval.counsel_agent import CounselRetrievalAgent

        agent = CounselRetrievalAgent()
        filters = agent._get_search_filters({"categories": ["상담", "조정"]})
        assert "category_filter" not in filters

    def test_single_category_override(self):
        """단일 카테고리 → category_filter 덮어쓰기"""
        from app.agents.retrieval.counsel_agent import CounselRetrievalAgent

        agent = CounselRetrievalAgent()
        filters = agent._get_search_filters({"categories": ["해결"]})
        assert filters["category_filter"] == "해결"


class TestCounselRetrievalAgentFormatting:
    """CounselRetrievalAgent 결과 포맷팅 테스트"""

    def test_format_results(self):
        from app.agents.retrieval.counsel_agent import CounselRetrievalAgent

        agent = CounselRetrievalAgent()
        results = [_make_search_result(doc_title="상담 사례")]
        formatted = agent._format_results(results)
        assert formatted[0]["title"] == "상담 사례"

    def test_build_sources(self):
        from app.agents.retrieval.counsel_agent import CounselRetrievalAgent

        agent = CounselRetrievalAgent()
        results = [_make_search_result()]
        sources = agent._build_sources(results)
        assert sources[0]["type"] == "counsel_case"


# ============================================================================
# BaseRetrievalAgent tests
# ============================================================================


class TestBaseRetrievalAgentProcess:
    """BaseRetrievalAgent.process() 흐름 테스트"""

    def test_validate_request_missing_query(self):
        """user_query 누락 시 에러"""
        from app.agents.retrieval.case_agent import CaseRetrievalAgent

        agent = CaseRetrievalAgent()
        error = agent.validate_request({"context": {}})
        assert error is not None
        assert "user_query" in error

    def test_validate_request_valid(self):
        """유효한 요청"""
        from app.agents.retrieval.case_agent import CaseRetrievalAgent

        agent = CaseRetrievalAgent()
        error = agent.validate_request({"context": {"user_query": "환불 방법"}})
        assert error is None

    @pytest.mark.asyncio
    async def test_process_missing_task_input(self):
        """retrieval_task_input 누락 시 failure 반환"""
        from app.agents.retrieval.case_agent import CaseRetrievalAgent

        agent = CaseRetrievalAgent()
        request = {
            "context": {
                "user_query": "환불 방법",
                "query_analysis": {},
            }
        }
        result = await agent.process(request)
        assert result["status"] == "failure"
        assert "retrieval_task_input" in result["message"]

    @pytest.mark.asyncio
    async def test_process_missing_user_query(self):
        """user_query 누락 시 failure 반환"""
        from app.agents.retrieval.case_agent import CaseRetrievalAgent

        agent = CaseRetrievalAgent()
        request = {"context": {}}
        result = await agent.process(request)
        assert result["status"] == "failure"

    @pytest.mark.asyncio
    async def test_process_search_exception(self):
        """검색 중 예외 발생 시 failure 반환"""
        from app.agents.retrieval.case_agent import CaseRetrievalAgent

        agent = CaseRetrievalAgent()
        request = {
            "context": {
                "user_query": "환불",
                "query_analysis": {},
                "retrieval_task_input": {"top_k": 5},
            }
        }
        with patch.object(
            agent, "_execute_search", side_effect=Exception("DB connection failed")
        ):
            result = await agent.process(request)
        assert result["status"] == "failure"
        assert "오류" in result["message"]

    @pytest.mark.asyncio
    async def test_process_no_results(self):
        """검색 결과 없을 때 failure + empty results"""
        from app.agents.retrieval.case_agent import CaseRetrievalAgent

        agent = CaseRetrievalAgent()
        request = {
            "context": {
                "user_query": "없는 데이터",
                "query_analysis": {},
                "retrieval_task_input": {"top_k": 5},
            }
        }
        with patch.object(
            agent, "_execute_search", new_callable=AsyncMock, return_value=[]
        ):
            result = await agent.process(request)
        assert result["status"] == "failure"
        assert result["result"]["results"] == []

    @pytest.mark.asyncio
    async def test_process_success(self):
        """성공적인 검색 결과 반환"""
        from app.agents.retrieval.case_agent import CaseRetrievalAgent

        agent = CaseRetrievalAgent()
        mock_results = [_make_search_result()]
        request = {
            "context": {
                "user_query": "노트북 환불",
                "query_analysis": {},
                "retrieval_task_input": {"top_k": 5},
            }
        }
        with patch.object(
            agent, "_execute_search", new_callable=AsyncMock, return_value=mock_results
        ):
            result = await agent.process(request)
        assert result["status"] == "success"
        assert result["from_agent"] == "retrieval_case"
        assert len(result["result"]["results"]) == 1
        assert result["result"]["max_similarity"] == 0.78
