"""
Adaptive RAG Features Test Suite

Tests for Adaptive RAG features including QueryComplexity classification,
display limits, HyDE generation, RetrievalOverflowCache, and config settings.

작성일: 2026-01-31
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.query_analysis.classifiers import (
    QueryComplexity,
    classify_query_complexity,
)
from app.common.config import get_config
from app.supervisor.nodes.retrieval_merge import _apply_display_limits

# ============================================================================
# Import modules under test
# ============================================================================


# ============================================================================
# Test 1: QueryComplexity Classification
# ============================================================================


class TestQueryComplexity:
    """QueryComplexity 분류 테스트"""

    @pytest.mark.unit
    def test_simple_query_short_words(self):
        """SIMPLE: 단어 수 ≤ 5 (짧은 키워드 질문)"""
        query = "환불 방법"  # 2 words
        result = classify_query_complexity(query)
        assert result == QueryComplexity.SIMPLE

        query2 = "노트북 환불 가능"  # 3 words
        result2 = classify_query_complexity(query2)
        assert result2 == QueryComplexity.SIMPLE

        query3 = "스마트폰 교환 절차 문의"  # 4 words
        result3 = classify_query_complexity(query3)
        assert result3 == QueryComplexity.SIMPLE

    @pytest.mark.unit
    def test_complex_query_compound_pattern(self):
        """COMPLEX: 복합 문장 구조 (인데/했는데/됐는데 + 요구)"""
        query = "구매한지 일주일 됐는데 환불 가능한가요"
        result = classify_query_complexity(query)
        assert result == QueryComplexity.COMPLEX

        query2 = "노트북 불량인데 교환해줘"
        result2 = classify_query_complexity(query2)
        assert result2 == QueryComplexity.COMPLEX

        query3 = "결제 완료했는데 배송이 안 되나요"
        result3 = classify_query_complexity(query3)
        assert result3 == QueryComplexity.COMPLEX

    @pytest.mark.unit
    def test_complex_query_long_sentence(self):
        """COMPLEX: 긴 문장 (단어 수 ≥ 15)"""
        # Make it longer - Korean counts words as space-separated tokens
        query = "온라인 쇼핑몰 에서 스마트폰 을 구매 했는데 화면 에 불량 이 있어서 환불 을 요청 하고 싶은데 방법 을 알려 주시면"
        word_count = len(query.split())
        assert word_count >= 15
        result = classify_query_complexity(query)
        assert result == QueryComplexity.COMPLEX

    @pytest.mark.unit
    def test_moderate_query(self):
        """MODERATE: 일반적 분쟁 상담 (6-14 words, 복합 패턴 없음)"""
        query = "노트북 불량으로 환불을 요청합니다"  # 4 words (short) - SIMPLE
        result = classify_query_complexity(query)
        assert result == QueryComplexity.SIMPLE

        # Need more words for MODERATE (6-14 words without compound pattern)
        query2 = "온라인 쇼핑몰 에서 구매 한 상품 이 불량 입니다 환불 방법 을 알려주세요"  # 13 words
        result2 = classify_query_complexity(query2)
        assert result2 == QueryComplexity.MODERATE

        query3 = "스마트폰 화면 깨짐 보상 받고 싶어요 어떻게 신청 하나요"  # 9 words
        result3 = classify_query_complexity(query3)
        assert result3 == QueryComplexity.MODERATE

    @pytest.mark.unit
    def test_complexity_priority_compound_over_length(self):
        """복합 패턴이 단어 수보다 우선순위가 높음"""
        # 단어 수는 적지만 복합 패턴이 있으면 COMPLEX
        query = "파손됐는데 어떻게 하나요"  # 3 words but has compound pattern
        result = classify_query_complexity(query)
        assert result == QueryComplexity.COMPLEX


# ============================================================================
# Test 2: Display Limits in retrieval_merge
# ============================================================================


class TestDisplayLimits:
    """도메인별 노출 수 제한 테스트"""

    @pytest.mark.unit
    def test_display_limits_no_truncation(self):
        """문서 수 ≤ 제한일 때 truncation 발생하지 않음"""
        merged = {
            "laws": [{"chunk_id": "law1", "title": "Test Law"}],
            "criteria": [{"chunk_id": "crit1"}, {"chunk_id": "crit2"}],
            "disputes": [{"chunk_id": "case1"}, {"chunk_id": "case2"}],
            "counsels": [{"chunk_id": "counsel1"}],
            "agency": {},
            "max_similarity": 0.85,
            "avg_similarity": 0.75,
        }

        # Config defaults: display_law=1, display_criteria=2, display_case=3, display_counsel=2
        result = _apply_display_limits(merged, session_id=None)

        # No truncation expected (all within limits)
        assert len(result["laws"]) == 1
        assert len(result["criteria"]) == 2
        assert len(result["disputes"]) == 2
        assert len(result["counsels"]) == 1

    @pytest.mark.unit
    def test_display_limits_with_truncation(self):
        """문서 수 > 제한일 때 상위 N개만 유지"""
        merged = {
            "laws": [
                {"chunk_id": "law1", "similarity": 0.9},
                {"chunk_id": "law2", "similarity": 0.8},
                {"chunk_id": "law3", "similarity": 0.7},
            ],
            "criteria": [
                {"chunk_id": "crit1"},
                {"chunk_id": "crit2"},
                {"chunk_id": "crit3"},
            ],
            "disputes": [{"chunk_id": f"case{i}"} for i in range(1, 6)],  # 5 cases
            "counsels": [
                {"chunk_id": "counsel1"},
                {"chunk_id": "counsel2"},
                {"chunk_id": "counsel3"},
            ],
            "agency": {},
            "max_similarity": 0.9,
            "avg_similarity": 0.8,
        }

        result = _apply_display_limits(merged, session_id=None)

        # Config defaults: display_law=1, display_criteria=2, display_case=3, display_counsel=2
        assert len(result["laws"]) == 1  # truncated from 3 to 1
        assert len(result["criteria"]) == 2  # truncated from 3 to 2
        assert len(result["disputes"]) == 3  # truncated from 5 to 3
        assert len(result["counsels"]) == 2  # truncated from 3 to 2

        # Check that top items are kept (order matters)
        assert result["laws"][0]["chunk_id"] == "law1"
        assert result["disputes"][0]["chunk_id"] == "case1"
        assert result["disputes"][2]["chunk_id"] == "case3"

    @pytest.mark.unit
    def test_display_limits_empty_sections(self):
        """빈 섹션도 에러 없이 처리"""
        merged = {
            "laws": [],
            "criteria": [],
            "disputes": [],
            "counsels": [],
            "agency": {},
            "max_similarity": 0.0,
            "avg_similarity": 0.0,
        }

        result = _apply_display_limits(merged, session_id=None)

        assert len(result["laws"]) == 0
        assert len(result["criteria"]) == 0
        assert len(result["disputes"]) == 0
        assert len(result["counsels"]) == 0


# ============================================================================
# Test 3: RetrievalOverflowCache (Redis-based)
# ============================================================================


class TestRetrievalOverflowCache:
    """Retrieval Overflow 캐시 테스트 (Redis 필요)"""

    @pytest.fixture
    def skip_no_redis(self):
        """Redis 미사용 시 테스트 스킵"""

        try:
            from app.common.cache import get_redis_client

            client = get_redis_client()
            if client is None:
                pytest.skip("Redis not available")
        except Exception:
            pytest.skip("Redis connection failed")

    @pytest.mark.integration
    def test_overflow_cache_set_and_get(self, skip_no_redis):
        """오버플로 캐시 저장 및 조회"""
        from app.supervisor.cache import RetrievalOverflowCache

        session_id = "test_session_overflow_001"
        overflow_data = {
            "laws": [{"chunk_id": "law_overflow_1"}],
            "criteria": [
                {"chunk_id": "crit_overflow_1"},
                {"chunk_id": "crit_overflow_2"},
            ],
            "disputes": [],
            "counsels": [{"chunk_id": "counsel_overflow_1"}],
        }

        # Set
        RetrievalOverflowCache.set_by_session(session_id, overflow_data)

        # Get
        retrieved = RetrievalOverflowCache.get_by_session(session_id)
        assert retrieved is not None
        assert len(retrieved["laws"]) == 1
        assert retrieved["laws"][0]["chunk_id"] == "law_overflow_1"
        assert len(retrieved["criteria"]) == 2
        assert len(retrieved["counsels"]) == 1

        # Cleanup
        RetrievalOverflowCache.invalidate_session(session_id)

    @pytest.mark.integration
    def test_overflow_cache_invalidate(self, skip_no_redis):
        """오버플로 캐시 무효화"""
        from app.supervisor.cache import RetrievalOverflowCache

        session_id = "test_session_overflow_002"
        overflow_data = {
            "laws": [{"chunk_id": "law1"}],
            "criteria": [],
            "disputes": [],
            "counsels": [],
        }

        RetrievalOverflowCache.set_by_session(session_id, overflow_data)
        assert RetrievalOverflowCache.get_by_session(session_id) is not None

        # Invalidate
        success = RetrievalOverflowCache.invalidate_session(session_id)
        assert success is True

        # Should return None after invalidation
        result = RetrievalOverflowCache.get_by_session(session_id)
        assert result is None


# ============================================================================
# Test 4: HyDE Module
# ============================================================================


class TestHyDEModule:
    """HyDE 가상 답변 생성 테스트"""

    @pytest.mark.unit
    def test_hyde_generator_initialization(self):
        """HyDEGenerator 초기화 테스트"""
        from app.agents.retrieval.tools.hyde import HyDEGenerator

        hyde = HyDEGenerator()
        assert hyde._model is not None
        assert hyde._max_tokens is not None
        assert hyde._api_key is not None

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_hyde_generate_with_domain(self):
        """HyDE 가상 답변 생성 (도메인별 프롬프트)"""
        from app.agents.retrieval.tools.hyde import HyDEGenerator

        # Mock at instance level
        hyde = HyDEGenerator()

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="가상 법률 답변 텍스트입니다."))
        ]
        mock_client.chat.completions.create.return_value = mock_response

        # Inject mocked client directly
        hyde._client = mock_client

        result = await hyde.generate(query="노트북 환불 가능한가요?", domain="law")

        assert result is not None
        assert "가상 법률 답변" in result
        mock_client.chat.completions.create.assert_called_once()

    @pytest.mark.llm
    @pytest.mark.asyncio
    async def test_hyde_generate_fallback_on_error(self):
        """HyDE 생성 실패 시 None 반환 (fallback)"""
        from app.agents.retrieval.tools.hyde import HyDEGenerator

        # Mock at instance level
        hyde = HyDEGenerator()

        mock_client = AsyncMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        # Inject mocked client directly
        hyde._client = mock_client

        result = await hyde.generate(query="노트북 환불 가능한가요?", domain="law")

        assert result is None  # Should return None on failure

    @pytest.mark.unit
    def test_hyde_prompts_exist_for_domains(self):
        """도메인별 HyDE 프롬프트 템플릿 존재 확인"""
        from app.agents.retrieval.tools.hyde import HYDE_PROMPTS

        expected_domains = ["law", "criteria", "case", "counsel", "default"]
        for domain in expected_domains:
            assert domain in HYDE_PROMPTS
            assert "{query}" in HYDE_PROMPTS[domain]


# ============================================================================
# Test 5: RetrievalSettings Config
# ============================================================================


class TestRetrievalSettings:
    """RetrievalSettings 설정 테스트"""

    @pytest.mark.unit
    def test_retrieval_settings_defaults(self):
        """RetrievalSettings 기본값 확인"""
        config = get_config().retrieval

        # RRF 설정
        assert config.rrf_k == 10

        # 도메인별 노출 수 제한
        assert config.display_law == 1
        assert config.display_criteria == 2
        assert config.display_case == 3
        assert config.display_counsel == 2

        # HyDE 설정
        assert config.hyde_enabled is True
        assert config.hyde_model == "gpt-4o-mini"
        assert config.hyde_max_tokens == 200

        # Adaptive RAG 설정
        assert config.adaptive_enabled is True
        assert config.simple_skip_hyde is True

        # 오버플로 캐시
        assert config.cache_overflow is True
        assert config.cache_ttl == 1800  # 30분

    @pytest.mark.unit
    def test_retrieval_settings_field_types(self):
        """RetrievalSettings 필드 타입 확인"""
        config = get_config().retrieval

        assert isinstance(config.rrf_k, int)
        assert isinstance(config.display_law, int)
        assert isinstance(config.display_criteria, int)
        assert isinstance(config.display_case, int)
        assert isinstance(config.display_counsel, int)
        assert isinstance(config.hyde_enabled, bool)
        assert isinstance(config.hyde_model, str)
        assert isinstance(config.hyde_max_tokens, int)
        assert isinstance(config.adaptive_enabled, bool)
        assert isinstance(config.simple_skip_hyde, bool)
        assert isinstance(config.cache_overflow, bool)
        assert isinstance(config.cache_ttl, int)


# ============================================================================
# Test 6: Adaptive Supervisor Routing (Integration)
# ============================================================================


class TestAdaptiveSupervisorRouting:
    """Adaptive 쿼리 복잡도에 따른 Supervisor 라우팅 테스트"""

    @pytest.mark.unit
    def test_state_with_query_complexity_simple(self):
        """query_complexity=simple 상태 존재 확인"""
        state = {
            "query_complexity": "simple",
            "mode": "NEED_RAG",
            "supervisor": {"completed_tasks": []},
        }
        assert state.get("query_complexity") == "simple"

    @pytest.mark.unit
    def test_state_with_query_complexity_complex(self):
        """query_complexity=complex 상태 존재 확인"""
        state = {
            "query_complexity": "complex",
            "mode": "NEED_RAG",
            "supervisor": {"completed_tasks": []},
        }
        assert state.get("query_complexity") == "complex"

    @pytest.mark.unit
    def test_full_pipeline_uses_query_complexity(self):
        """_full_pipeline_decision에서 query_complexity 사용 확인"""
        from app.supervisor.nodes.supervisor import SupervisorNode

        state_simple = {
            "query_complexity": "simple",
            "mode": "NEED_RAG",
            "supervisor": {"completed_tasks": []},
        }

        state_complex = {
            "query_complexity": "complex",
            "mode": "NEED_RAG",
            "supervisor": {"completed_tasks": []},
        }

        node = SupervisorNode()

        # Simple query: HyDE 생략 가능
        decision_simple = node._full_pipeline_decision(state_simple)
        assert decision_simple["action"] == "call_agent"
        assert decision_simple["target_agent"] == "retrieval_team"
        assert "query_complexity" in decision_simple["request"]
        assert decision_simple["request"]["query_complexity"] == "simple"

        # Complex query: HyDE 사용
        decision_complex = node._full_pipeline_decision(state_complex)
        assert decision_complex["action"] == "call_agent"
        assert decision_complex["target_agent"] == "retrieval_team"
        assert decision_complex["request"]["query_complexity"] == "complex"


# ============================================================================
# Summary Test
# ============================================================================


@pytest.mark.unit
def test_all_adaptive_rag_components_exist():
    """모든 Adaptive RAG 컴포넌트 존재 확인 (smoke test)"""
    # 1. QueryComplexity enum
    from app.agents.query_analysis.classifiers import QueryComplexity

    assert QueryComplexity.SIMPLE
    assert QueryComplexity.MODERATE
    assert QueryComplexity.COMPLEX

    # 2. classify_query_complexity function
    from app.agents.query_analysis.classifiers import classify_query_complexity

    result = classify_query_complexity("환불")
    assert result in [
        QueryComplexity.SIMPLE,
        QueryComplexity.MODERATE,
        QueryComplexity.COMPLEX,
    ]

    # 3. _apply_display_limits function
    from app.supervisor.nodes.retrieval_merge import _apply_display_limits

    test_merged = {
        "laws": [],
        "criteria": [],
        "disputes": [],
        "counsels": [],
        "agency": {},
        "max_similarity": 0.0,
        "avg_similarity": 0.0,
    }
    result = _apply_display_limits(test_merged, None)
    assert result is not None

    # 4. HyDEGenerator class
    from app.agents.retrieval.tools.hyde import HyDEGenerator

    hyde = HyDEGenerator()
    assert hyde is not None

    # 5. RetrievalOverflowCache class
    from app.supervisor.cache import RetrievalOverflowCache

    assert RetrievalOverflowCache is not None

    # 6. RetrievalSettings config
    config = get_config().retrieval
    assert config is not None
    assert hasattr(config, "rrf_k")
    assert hasattr(config, "display_law")
