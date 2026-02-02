"""
PR 2: Query Analysis Enhancement (Hybrid Intent & Synonyms)
Tests for improved synonym recognition, hybrid classification, and multi-query expansion.
"""

import pytest

from app.agents.query_analysis.agent import (
    VERB_SYNONYMS,
    _create_synonym_variant_query,
    _extract_keywords,
    _generate_search_queries,
)


class TestSynonymRecognition:

    def test_synonym_normalization_refund(self):
        query = "돈 돌려받고 싶어요"
        keywords = _extract_keywords(query)

        assert "환불" in keywords

    def test_synonym_normalization_exchange(self):
        query = "다른 제품으로 바꿔줘"
        keywords = _extract_keywords(query)

        assert "교환" in keywords

    def test_synonym_normalization_repair(self):
        query = "노트북 고쳐줘"
        keywords = _extract_keywords(query)

        assert "수리" in keywords

    def test_mixed_keywords_with_synonyms(self):
        query = "노트북 환급받고 싶어요"
        keywords = _extract_keywords(query)

        assert "노트북" in keywords
        assert "환불" in keywords

    def test_no_synonym_for_regular_words(self):
        query = "노트북 구매했어요"
        keywords = _extract_keywords(query)

        assert "노트북" in keywords
        assert "구매했어요" in keywords


class TestMultiQueryExpansion:

    def test_multi_query_generates_multiple_variants(self):
        original = "노트북 환불"
        expanded = "노트북 환불 분쟁조정 피해구제"
        keywords = ["노트북", "환불"]

        queries = _generate_search_queries(original, expanded, keywords)

        assert len(queries) >= 2
        assert original in queries
        assert expanded in queries

    def test_synonym_variant_query_creation(self):
        keywords = ["환불"]

        variant = _create_synonym_variant_query("환불 요청", keywords)

        assert variant is not None
        assert any(syn in variant for syn in VERB_SYNONYMS["환불"][:2])

    def test_multi_query_includes_keyword_combination(self):
        original = "노트북"
        expanded = "노트북 분쟁"
        keywords = ["노트북", "환불", "피해"]

        queries = _generate_search_queries(original, expanded, keywords)

        assert len(queries) >= 3
        keyword_query_found = any("노트북 환불" in q for q in queries)
        assert keyword_query_found

    def test_multi_query_max_four_queries(self):
        original = "노트북 환불"
        expanded = "노트북 환불 분쟁조정"
        keywords = ["노트북", "환불", "분쟁", "조정"]

        queries = _generate_search_queries(original, expanded, keywords)

        assert len(queries) <= 4


class TestIntentClassification:

    def test_general_vs_dispute_distinction(self):
        from app.agents.query_analysis.agent import _classify_query_type

        general_query = "환불이 뭐예요?"
        dispute_query = "환불해 주세요"

        general_type = _classify_query_type(general_query)
        dispute_type = _classify_query_type(dispute_query)

        assert general_type in ("general", "ambiguous")
        assert dispute_type == "dispute"

    def test_synonym_in_dispute_classification(self):
        from app.agents.query_analysis.agent import _classify_query_type

        query = "돈 돌려받고 싶어요"

        query_type = _classify_query_type(query)

        assert query_type == "dispute"


class TestEndToEndQueryAnalysis:

    @pytest.mark.skip(reason="Requires full state and LLM integration")
    def test_full_query_analysis_with_synonyms(self):
        from app.agents.query_analysis.agent import query_analysis_node

        state = {
            "user_query": "노트북 돌려받고 싶어요",
            "chat_type": "dispute",
            "onboarding": None,
        }

        result = query_analysis_node(state)

        query_analysis = result.get("query_analysis")
        assert query_analysis is not None
        assert "환불" in query_analysis.get("keywords", [])
        assert len(query_analysis.get("search_queries", [])) >= 2
