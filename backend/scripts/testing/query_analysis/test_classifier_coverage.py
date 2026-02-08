"""
분류기 커버리지 테스트 - v2 LLM 덮어쓰기 보호 및 법률 패턴 매칭 검증

실행 방법:
    conda run -n dsr pytest backend/scripts/testing/query_analysis/test_classifier_coverage.py -v
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.agents.query_analysis.classifiers import (
    classify_mode,
    classify_query_type_with_confidence,
)


class TestClassifyQueryTypeWithConfidence:
    """classify_query_type_with_confidence 단위 테스트"""

    @pytest.mark.parametrize(
        "query,expected_type",
        [
            # 법률명 패턴 매칭
            ("소비자기본법", "law"),
            ("소비자보호법이 뭐야?", "law"),
            ("전자상거래법 위반", "law"),
            ("약관규제법 적용 범위", "law"),
            # 법률/법령/법적 확장 패턴
            ("관련 법령 알려줘", "law"),
            ("소비자보호 법률 정보", "law"),
            # 분쟁 패턴
            ("노트북 환불해줘", "dispute"),
            # 기준 패턴
            ("노트북 환불 기준 알려줘", "criteria"),
            # 일반 대화
            ("안녕", "general"),
            ("고마워", "general"),
            # 시스템 메타
            ("네가 뭐야?", "system_meta"),
        ],
    )
    @pytest.mark.unit
    def test_query_type_classification(self, query: str, expected_type: str):
        """쿼리별 유형 분류 검증"""
        query_type, confidence = classify_query_type_with_confidence(query)
        assert query_type == expected_type, (
            f"Query '{query}': expected type={expected_type}, got type={query_type} (confidence={confidence:.2f})"
        )

    @pytest.mark.parametrize(
        "query,min_confidence",
        [
            ("소비자기본법", 0.8),
            ("안녕", 0.85),
            ("네가 뭐야?", 0.9),
        ],
    )
    @pytest.mark.unit
    def test_confidence_levels(self, query: str, min_confidence: float):
        """confidence 수준 검증"""
        _, confidence = classify_query_type_with_confidence(query)
        assert confidence >= min_confidence, (
            f"Query '{query}': expected confidence >= {min_confidence}, got {confidence:.2f}"
        )


class TestV2LLMDowngradeProtection:
    """v2 LLM 덮어쓰기 보호 로직 테스트"""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_llm_general_blocked_when_rule_says_law(self):
        """rule-based가 law(0.9)일 때 LLM이 general 반환 → law 유지"""
        from app.agents.query_analysis.agent import query_analysis_node_v2

        state = {
            "user_query": "소비자기본법",
            "chat_type": "general",
            "onboarding": None,
            "conversation_history": [],
        }

        # LLM이 general을 반환하도록 mock
        mock_llm_result = ("general", 0.85, "정의형 질문")
        with patch(
            "app.agents.query_analysis.llm_classifier.llm_classify",
            new_callable=AsyncMock,
            return_value=mock_llm_result,
        ):
            # expand_query_with_llm_v2도 mock (LLM 호출 방지)
            with patch(
                "app.agents.query_analysis.expanders.expand_query_with_llm_v2",
                new_callable=AsyncMock,
                return_value=["소비자기본법"],
            ):
                result = await query_analysis_node_v2(state)

        # law가 유지되어야 함
        assert result["query_analysis"]["query_type"] == "law", (
            f"Expected query_type='law', got '{result['query_analysis']['query_type']}'"
        )
        assert result["mode"] == "NEED_RAG", (
            f"Expected mode='NEED_RAG', got '{result['mode']}'"
        )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_llm_specific_type_allowed_over_rule(self):
        """rule-based가 dispute(0.5)일 때 LLM이 law 반환 → law로 변경 허용"""
        from app.agents.query_analysis.agent import query_analysis_node_v2

        state = {
            "user_query": "이 제품 관련 법 조항",
            "chat_type": "general",
            "onboarding": None,
            "conversation_history": [],
        }

        # LLM이 law를 반환하도록 mock
        mock_llm_result = ("law", 0.90, "법 조항 정보 요청")
        with patch(
            "app.agents.query_analysis.llm_classifier.llm_classify",
            new_callable=AsyncMock,
            return_value=mock_llm_result,
        ):
            with patch(
                "app.agents.query_analysis.expanders.expand_query_with_llm_v2",
                new_callable=AsyncMock,
                return_value=["이 제품 관련 법 조항"],
            ):
                result = await query_analysis_node_v2(state)

        # LLM의 law가 적용되어야 함
        assert result["query_analysis"]["query_type"] == "law", (
            f"Expected query_type='law', got '{result['query_analysis']['query_type']}'"
        )


class TestModeClassification:
    """classify_mode 통합 테스트"""

    @pytest.mark.parametrize(
        "query_type,query,expected_mode",
        [
            ("law", "소비자기본법", "NEED_RAG"),
            ("criteria", "노트북 환불 기준", "NEED_RAG"),
            ("dispute", "환불 받고 싶어요", "NEED_RAG"),
            ("general", "안녕하세요", "NO_RETRIEVAL"),
            ("general", "오늘 날씨 어때?", "NO_RETRIEVAL"),
            ("system_meta", "네가 뭐야?", "NO_RETRIEVAL"),
            # Fast path promotion: general이지만 법률 키워드 포함
            ("general", "법률 상담 받고 싶어요", "NEED_RAG"),
            ("general", "환불 방법 알려줘", "NEED_RAG"),
        ],
    )
    @pytest.mark.unit
    def test_mode_routing(self, query_type: str, query: str, expected_mode: str):
        """query_type별 mode 라우팅 검증"""
        mode = classify_mode(query_type, False, query)
        assert mode == expected_mode, (
            f"Query '{query}' (type={query_type}): expected mode={expected_mode}, got {mode}"
        )


class TestLawPatternExpansion:
    """법률 정규식 확장 테스트"""

    @pytest.mark.parametrize(
        "query,expected_type",
        [
            ("소비자기본법", "law"),
            ("전자상거래법", "law"),
            ("관련 법령 알려줘", "law"),
            ("소비자보호 법률 정보", "law"),
        ],
    )
    @pytest.mark.unit
    def test_law_pattern_matching(self, query: str, expected_type: str):
        """확장된 법률 정규식 매칭 검증"""
        query_type, _ = classify_query_type_with_confidence(query)
        assert query_type == expected_type, (
            f"Query '{query}': expected type={expected_type}, got type={query_type}"
        )
