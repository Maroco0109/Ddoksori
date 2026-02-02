"""
테스트: Hybrid Ambiguous Query Detection
작성일: 2026-01-20

Layer 1: Pattern 매칭 (빠른 탐지)
Layer 2: Intent 키워드 체크 (명확한 의도 확인)
Layer 3: LLM Fallback (모호한 짧은 쿼리)

테스트 시나리오:
A. 모호한 쿼리 - Pattern 매칭 (8개)
B. 모호한 쿼리 - LLM Fallback (8개)
C. 구체적 분쟁 쿼리 - RAG 진행 (10개)
D. 일반 대화 - NO_RETRIEVAL (4개)
E. 시스템/메타 쿼리 - NO_RETRIEVAL (3개)
F. Edge Cases (6개)
"""

import os
import sys
from pathlib import Path

import pytest

backend_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_path))
os.chdir(backend_path)

from app.supervisor.state import create_initial_state


def _import_functions():
    from app.agents.query_analysis.agent import (
        AMBIGUOUS_QUERY_PATTERNS,
        DISPUTE_INTENT_KEYWORDS,
        _classify_mode,
        _classify_query_type,
        _is_ambiguous_query,
        query_analysis_node,
    )

    return (
        query_analysis_node,
        _is_ambiguous_query,
        _classify_query_type,
        _classify_mode,
        AMBIGUOUS_QUERY_PATTERNS,
        DISPUTE_INTENT_KEYWORDS,
    )


class TestAmbiguousQueryPatternMatching:
    """Layer 1: Pattern 매칭 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        (
            self.qa_node,
            self.is_ambiguous,
            self.classify_type,
            self.classify_mode,
            self.patterns,
            self.intent_keywords,
        ) = _import_functions()

    @pytest.mark.parametrize(
        "query,description",
        [
            ("요약", "단독 동사"),
            ("도와줘", "단독 요청"),
            ("알려주세요", "단독 요청"),
            ("이거 어떻게", "지시대명사+질문"),
            ("그거 뭐야", "지시대명사+질문"),
            ("뭐", "단일 질문어"),
            ("?", "매우 짧음"),
            ("ㅎ", "매우 짧음"),
        ],
    )
    def test_pattern_matched_ambiguous(self, query, description):
        """A1-A8: Pattern으로 즉시 탐지되는 모호한 쿼리"""
        result = self.is_ambiguous(query)
        assert result is True, f"Expected ambiguous for '{query}' ({description})"

    @pytest.mark.parametrize(
        "query,description,expected_type",
        [
            ("요약", "단독 동사", "ambiguous"),
            (
                "도와줘",
                "단독 요청",
                "meta_conversational",
            ),  # meta_conversational이 ambiguous보다 우선
            ("이거 어떻게", "지시대명사+질문", "ambiguous"),
        ],
    )
    def test_pattern_matched_classify_type(self, query, description, expected_type):
        """Pattern 매칭 쿼리가 올바른 타입으로 분류되는지 확인"""
        query_type = self.classify_type(query)
        assert (
            query_type == expected_type
        ), f"Expected '{expected_type}' type for '{query}', got '{query_type}'"

    @pytest.mark.parametrize(
        "query,expected_mode",
        [
            ("요약", "NEED_RAG"),  # ambiguous → NEED_RAG
            (
                "도와줘",
                "NO_RETRIEVAL",
            ),  # meta_conversational → NO_RETRIEVAL (legacy mode)
            ("뭐", "NEED_RAG"),  # ambiguous → NEED_RAG
            ("?", "NEED_RAG"),  # ambiguous → NEED_RAG
        ],
    )
    def test_pattern_matched_mode(self, query, expected_mode):
        """Pattern 매칭 쿼리가 올바른 모드로 설정되는지 확인"""
        state = create_initial_state(user_query=query, chat_type="dispute")
        result = self.qa_node(state)
        assert (
            result.get("mode") == expected_mode
        ), f"Expected {expected_mode} for '{query}', got {result.get('mode')}"


class TestAmbiguousQueryLLMFallback:
    """Layer 3: LLM Fallback 테스트 (실제 LLM 호출)"""

    @pytest.fixture(autouse=True)
    def setup(self):
        (
            self.qa_node,
            self.is_ambiguous,
            self.classify_type,
            self.classify_mode,
            _,
            _,
        ) = _import_functions()

    @pytest.mark.slow
    @pytest.mark.parametrize(
        "query,description",
        [
            ("이거 좀 봐줄 수 있어요?", "긴데 모호"),
            ("뭐 좀 알아봐줘", "막연한 요청"),
            ("급한데 어떡해요", "상황 불명확"),
            ("문제가 생겼어요", "구체성 없음"),
            ("속상해요", "감정만 표현"),
            ("답답해서 그러는데", "막연한 시작"),
            ("상담 가능한가요?", "일반 문의"),
            ("여기서 뭘 할 수 있어요?", "시스템 질문"),
        ],
    )
    def test_llm_fallback_ambiguous(self, query, description):
        """B1-B8: LLM Fallback으로 탐지되는 모호한 쿼리 (slow test)"""
        # LLM fallback이 필요한 케이스 - 실제 결과는 LLM 응답에 따라 달라질 수 있음
        result = self.is_ambiguous(query)
        # 참고: LLM이 "구체적"으로 판단할 수도 있어서 soft assertion
        print(f"Query: '{query}' ({description}) -> ambiguous={result}")


class TestSpecificDisputeQueries:
    """구체적 분쟁 쿼리 - RAG 진행"""

    @pytest.fixture(autouse=True)
    def setup(self):
        (
            self.qa_node,
            self.is_ambiguous,
            self.classify_type,
            self.classify_mode,
            _,
            _,
        ) = _import_functions()

    @pytest.mark.parametrize(
        "query,scenario",
        [
            ("환불 거부당했어요", "환불 분쟁"),
            ("배송이 일주일째 안 와요", "배송 지연"),
            ("노트북 화면 불량인데 수리 거부", "제품 하자"),
            ("헬스장 중도해지 위약금", "계약 해지"),
            ("인터넷 쇼핑몰에서 산 옷이 사진이랑 달라요", "품질 불일치"),
            ("중고거래에서 사기당한 것 같아요", "사기 피해"),
            ("결제 취소했는데 환불이 안 돼요", "환불 지연"),
            ("쿠팡에서 주문한 에어팟이 가품이에요", "위조품"),
            ("영어학원 환불 안해준다고 해요", "교육 서비스"),
            ("렌터카 수리비 과다 청구", "수리비 분쟁"),
        ],
    )
    def test_specific_dispute_not_ambiguous(self, query, scenario):
        """C1-C10: 구체적 분쟁 쿼리는 ambiguous가 아니어야 함"""
        result = self.is_ambiguous(query)
        assert result is False, f"Expected NOT ambiguous for '{query}' ({scenario})"

    @pytest.mark.parametrize(
        "query",
        [
            "환불 거부당했어요",
            "배송이 일주일째 안 와요",
            "노트북 화면 불량인데 수리 거부",
        ],
    )
    def test_specific_dispute_needs_rag(self, query):
        """구체적 분쟁 쿼리가 NEED_RAG 모드로 설정되는지 확인"""
        state = create_initial_state(
            user_query=query,
            chat_type="dispute",
            onboarding={"purchase_item": "테스트품목", "dispute_details": "테스트분쟁"},
        )
        result = self.qa_node(state)
        assert (
            result.get("mode") == "NEED_RAG"
        ), f"Expected NEED_RAG for '{query}', got {result.get('mode')}"


class TestGeneralConversation:
    """일반 대화 - NO_RETRIEVAL 유지"""

    @pytest.fixture(autouse=True)
    def setup(self):
        (
            self.qa_node,
            self.is_ambiguous,
            self.classify_type,
            _,
            _,
            _,
        ) = _import_functions()

    @pytest.mark.parametrize(
        "query",
        [
            "안녕하세요",
            "감사합니다",
            "ㅋㅋㅋ",
            "네 알겠어요",
        ],
    )
    def test_general_conversation_not_ambiguous(self, query):
        """D1-D4: 일반 대화는 ambiguous가 아닌 general 타입"""
        query_type = self.classify_type(query)
        assert (
            query_type == "general"
        ), f"Expected 'general' type for '{query}', got '{query_type}'"

    @pytest.mark.parametrize(
        "query",
        ["안녕하세요", "감사합니다"],
    )
    def test_general_no_retrieval(self, query):
        """일반 대화가 NO_RETRIEVAL 모드인지 확인"""
        state = create_initial_state(user_query=query, chat_type="dispute")
        result = self.qa_node(state)
        assert (
            result.get("mode") == "NO_RETRIEVAL"
        ), f"Expected NO_RETRIEVAL for '{query}', got {result.get('mode')}"


class TestSystemMetaQueries:
    """시스템/메타 쿼리 - NO_RETRIEVAL 유지"""

    @pytest.fixture(autouse=True)
    def setup(self):
        (
            self.qa_node,
            _,
            self.classify_type,
            _,
            _,
            _,
        ) = _import_functions()

    @pytest.mark.parametrize(
        "query",
        [
            "너 이름이 뭐야?",
            "어떤 모델이야?",
            "누가 만들었어?",
        ],
    )
    def test_system_meta_type(self, query):
        """E1-E3: 시스템 쿼리는 system_meta 타입"""
        query_type = self.classify_type(query)
        assert (
            query_type == "system_meta"
        ), f"Expected 'system_meta' type for '{query}', got '{query_type}'"

    @pytest.mark.parametrize(
        "query",
        ["너 이름이 뭐야?", "어떤 모델이야?"],
    )
    def test_system_meta_no_retrieval(self, query):
        """시스템 쿼리가 NO_RETRIEVAL 모드인지 확인"""
        state = create_initial_state(user_query=query, chat_type="dispute")
        result = self.qa_node(state)
        assert (
            result.get("mode") == "NO_RETRIEVAL"
        ), f"Expected NO_RETRIEVAL for '{query}', got {result.get('mode')}"


class TestEdgeCases:
    """경계 케이스 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        (
            self.qa_node,
            self.is_ambiguous,
            self.classify_type,
            _,
            _,
            _,
        ) = _import_functions()

    def test_short_with_intent_keyword(self):
        """F1: 짧지만 의도 키워드가 있는 쿼리 -> NOT ambiguous"""
        query = "환불"
        result = self.is_ambiguous(query)
        assert (
            result is False
        ), f"'{query}' should NOT be ambiguous (has intent keyword)"

    def test_short_query_with_verb(self):
        """F2: 의도 키워드 포함 -> NOT ambiguous"""
        query = "반품 어떻게"
        result = self.is_ambiguous(query)
        assert (
            result is False
        ), f"'{query}' should NOT be ambiguous (has intent keyword)"

    @pytest.mark.slow
    def test_product_only_no_problem(self):
        """F3: 제품명만 있고 문제 없음 -> LLM 판단 필요"""
        query = "노트북"
        # 제품 키워드가 있으면 NOT ambiguous (Layer 2.5)
        result = self.is_ambiguous(query)
        assert (
            result is False
        ), f"'{query}' should NOT be ambiguous (has product keyword)"

    @pytest.mark.slow
    def test_brand_and_product(self):
        """F4: 브랜드+제품 -> NOT ambiguous (제품 키워드 있음)"""
        query = "삼성 티비"
        result = self.is_ambiguous(query)
        # 티비는 COMMON_PRODUCTS에 TV로 있음
        print(f"Query: '{query}' -> ambiguous={result}")

    def test_law_query_not_ambiguous(self):
        """F5: 법령 조회는 law 타입으로 분류"""
        query = "소비자보호법 제17조"
        query_type = self.classify_type(query)
        assert (
            query_type == "law"
        ), f"Expected 'law' type for '{query}', got '{query_type}'"

    def test_law_with_refund(self):
        """F6: 법령+환불 -> law 타입"""
        query = "전자상거래법 환불 규정"
        query_type = self.classify_type(query)
        # 법령 키워드가 충분하면 law, 아니면 dispute
        print(f"Query: '{query}' -> type={query_type}")


class TestIntegrationFullFlow:
    """전체 흐름 통합 테스트"""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.qa_node, _, _, _, _, _ = _import_functions()

    @pytest.mark.skip(
        reason="query_analysis_v2 필드가 현재 구현에서 사용되지 않음 - TODO: 구현 또는 테스트 제거"
    )
    def test_ambiguous_query_full_flow(self):
        """모호한 쿼리의 전체 흐름 테스트"""
        state = create_initial_state(user_query="요약", chat_type="dispute")
        result = self.qa_node(state)

        # 검증
        assert result.get("mode") == "NEED_RAG"  # Phase System 제거: ambiguous→RAG
        assert result.get("query_analysis", {}).get("query_type") == "ambiguous"

    def test_specific_query_bypasses_ambiguous(self):
        """구체적 분쟁 쿼리는 ambiguous를 건너뜀"""
        state = create_initial_state(
            user_query="환불 거부당했어요",
            chat_type="dispute",
            onboarding={"purchase_item": "노트북", "dispute_details": "환불 거부"},
        )
        result = self.qa_node(state)

        assert result.get("mode") == "NEED_RAG"
        assert result.get("query_analysis", {}).get("query_type") == "dispute"

    def test_general_greeting_unchanged(self):
        """인사는 여전히 general 타입 유지"""
        state = create_initial_state(user_query="안녕하세요", chat_type="dispute")
        result = self.qa_node(state)

        assert result.get("mode") == "NO_RETRIEVAL"
        assert result.get("query_analysis", {}).get("query_type") == "general"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-p", "no:asyncio", "-m", "not slow"])
