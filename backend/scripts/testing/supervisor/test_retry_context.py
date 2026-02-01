"""
Retry Context 단위 테스트 (Phase 7: LegalReviewer 재생성 지원)

작성일: 2026-01-31

테스트 대상:
- backend/app/agents/answer_generation/agent.py의 _build_retry_prompt_supplement()
- backend/app/agents/answer_generation/agent.py의 generation_node_v2()
- backend/app/agents/answer_generation/fallback.py의 generate_with_fallback()
- backend/app/agents/answer_generation/tools/generator.py의 generate_structured_answer()
"""

import pytest
from typing import Dict, Any, List, Optional
from unittest.mock import patch, MagicMock, AsyncMock

# 전체 파일에 unit 마커 적용 (DB/LLM 의존성 없음)
pytestmark = pytest.mark.unit


# === Test Fixtures ===

@pytest.fixture
def sample_violations() -> List[Dict[str, str]]:
    """샘플 위반사항 (LegalReviewer가 반환한 형식)"""
    return [
        {
            'type': 'factual_inconsistency',
            'description': '검색 결과에 없는 내용을 언급했습니다',
            'suggestion': '검색된 문서의 내용만 사용하여 답변을 재구성하세요',
        },
        {
            'type': 'prohibited_expression',
            'description': '단정적 표현("~해야 합니다")을 사용했습니다',
            'suggestion': '추천형 표현("~하시는 것을 권장합니다")으로 수정하세요',
        },
    ]


@pytest.fixture
def sample_retry_context(sample_violations) -> Dict[str, Any]:
    """샘플 retry_context"""
    return {
        'violations': sample_violations,
        'previous_draft': '이전 답변 내용입니다...',
        'retry_count': 1,
    }


@pytest.fixture
def empty_retry_context() -> Dict[str, Any]:
    """빈 violations를 가진 retry_context"""
    return {
        'violations': [],
        'previous_draft': '',
        'retry_count': 0,
    }


@pytest.fixture
def mock_state_with_retry(sample_retry_context) -> Dict[str, Any]:
    """retry_context가 포함된 Mock ChatState"""
    return {
        'user_query': '노트북 환불이 안됩니다',
        'query_analysis': {
            'query_type': 'dispute',
            'keywords': ['노트북', '환불'],
            'expanded_queries': ['노트북 환불 분쟁 사례'],
        },
        'retrieval': {
            'laws': [{'chunk_id': 'law_001', 'title': '소비자기본법'}],
            'criteria': [],
            'disputes': [{'chunk_id': 'case_001', 'title': '노트북 환불 사례'}],
            'counsels': [],
            'max_similarity': 0.85,
            'avg_similarity': 0.80,
        },
        'retry_context': sample_retry_context,
    }


@pytest.fixture
def mock_state_without_retry() -> Dict[str, Any]:
    """retry_context가 없는 일반 ChatState"""
    return {
        'user_query': '노트북 환불이 안됩니다',
        'query_analysis': {
            'query_type': 'dispute',
            'keywords': ['노트북', '환불'],
        },
        'retrieval': {
            'laws': [{'chunk_id': 'law_001'}],
            'disputes': [{'chunk_id': 'case_001'}],
            'max_similarity': 0.85,
        },
        'retry_context': None,
    }


# === Unit Tests ===

class TestBuildRetryPromptSupplement:
    """_build_retry_prompt_supplement() 함수 테스트"""

    def test_build_retry_prompt_with_violations(self, sample_retry_context):
        """violations가 있을 때 프롬프트 보충 문자열 생성"""
        from app.agents.answer_generation.agent import _build_retry_prompt_supplement

        result = _build_retry_prompt_supplement(sample_retry_context)

        # 제목 헤더 포함
        assert "이전 답변 검토 결과" in result
        assert "반드시 수정 필요" in result

        # 위반사항 타입 포함
        assert "[factual_inconsistency]" in result
        assert "[prohibited_expression]" in result

        # 설명 포함
        assert "검색 결과에 없는 내용" in result
        assert "단정적 표현" in result

        # 제안 포함
        assert "제안:" in result
        assert "검색된 문서의 내용만" in result

    def test_build_retry_prompt_empty_violations(self, empty_retry_context):
        """violations가 빈 리스트일 때"""
        from app.agents.answer_generation.agent import _build_retry_prompt_supplement

        result = _build_retry_prompt_supplement(empty_retry_context)

        # 빈 문자열 반환
        assert result == ""

    def test_build_retry_prompt_none_context(self):
        """retry_context가 None일 때"""
        from app.agents.answer_generation.agent import _build_retry_prompt_supplement

        result = _build_retry_prompt_supplement(None)

        # 빈 문자열 반환
        assert result == ""

    def test_build_retry_prompt_violations_without_suggestion(self):
        """suggestion이 없는 violation 처리"""
        from app.agents.answer_generation.agent import _build_retry_prompt_supplement

        retry_context = {
            'violations': [
                {
                    'type': 'error_type',
                    'description': '문제 설명',
                    # suggestion 없음
                }
            ],
            'retry_count': 1,
        }

        result = _build_retry_prompt_supplement(retry_context)

        # description은 포함되지만 suggestion은 없음
        assert "문제 설명" in result
        assert "제안:" not in result

    def test_build_retry_prompt_string_violations(self):
        """violations가 문자열 리스트일 때 (하위 호환)"""
        from app.agents.answer_generation.agent import _build_retry_prompt_supplement

        retry_context = {
            'violations': [
                "첫 번째 위반사항",
                "두 번째 위반사항",
            ],
            'retry_count': 1,
        }

        result = _build_retry_prompt_supplement(retry_context)

        # 문자열 그대로 출력
        assert "1. 첫 번째 위반사항" in result
        assert "2. 두 번째 위반사항" in result


@pytest.mark.asyncio
class TestGenerationNodeV2RetryContext:
    """generation_node_v2의 retry_context 처리 테스트"""

    @patch('app.agents.answer_generation.fallback.AnswerGenerationFallback.generate_with_fallback')
    async def test_retry_supplement_passed_to_fallback(
        self, mock_fallback, mock_state_with_retry
    ):
        """retry_context 존재 시 generate_with_fallback()에 retry_supplement 전달"""
        from app.agents.answer_generation.agent import generation_node_v2

        # Mock 설정
        mock_fallback.return_value = ("재생성된 답변", "gpt-4o-mini", [])

        # 실행
        await generation_node_v2(mock_state_with_retry)

        # generate_with_fallback 호출 검증
        assert mock_fallback.called
        call_kwargs = mock_fallback.call_args.kwargs

        # retry_supplement 파라미터 전달 확인
        assert 'retry_supplement' in call_kwargs
        retry_supplement = call_kwargs['retry_supplement']

        # retry_supplement에 위반사항 내용 포함
        assert retry_supplement is not None
        assert len(retry_supplement) > 0
        assert "이전 답변 검토 결과" in retry_supplement
        assert "[factual_inconsistency]" in retry_supplement

    @patch('app.agents.answer_generation.fallback.AnswerGenerationFallback.generate_with_fallback')
    async def test_retry_supplement_not_passed_when_no_context(
        self, mock_fallback, mock_state_without_retry
    ):
        """retry_context 없을 때 retry_supplement=None 전달"""
        from app.agents.answer_generation.agent import generation_node_v2

        # Mock 설정
        mock_fallback.return_value = ("일반 답변", "gpt-4o-mini", [])

        # 실행
        await generation_node_v2(mock_state_without_retry)

        # generate_with_fallback 호출 검증
        assert mock_fallback.called
        call_kwargs = mock_fallback.call_args.kwargs

        # retry_supplement가 None
        assert call_kwargs.get('retry_supplement') is None

    @patch('app.agents.answer_generation.agent.get_answer_cache')
    @patch('app.agents.answer_generation.fallback.AnswerGenerationFallback.generate_with_fallback')
    async def test_cache_skipped_when_retry(
        self, mock_fallback, mock_cache, mock_state_with_retry
    ):
        """retry_context 존재 시 캐시 조회 생략"""
        from app.agents.answer_generation.agent import generation_node_v2

        # Mock 설정
        mock_cache_instance = MagicMock()
        mock_cache_instance.get.return_value = {
            'answer': '캐시된 답변',
            'has_evidence': True,
        }
        mock_cache.return_value = mock_cache_instance
        mock_fallback.return_value = ("재생성 답변", "gpt-4o-mini", [])

        # 실행
        result = await generation_node_v2(mock_state_with_retry)

        # 캐시 조회가 호출되지 않았는지 확인
        assert not mock_cache_instance.get.called

        # 재생성된 답변 사용
        assert result['draft_answer'] == "재생성 답변"


class TestFallbackRetrySupplementPropagation:
    """AnswerGenerationFallback의 retry_supplement 전파 테스트"""

    def test_fallback_passes_retry_supplement_to_generator(self):
        """generate_with_fallback()가 retry_supplement를 RAGGenerator에 전달"""
        from app.agents.answer_generation.fallback import AnswerGenerationFallback

        # Mock 설정
        with patch('app.agents.answer_generation.tools.generator.RAGGenerator.generate_structured_answer') as mock_gen:
            mock_gen.return_value = {
                'answer': '생성된 답변',
                'claim_evidence_map': [],
            }

            # 실행
            retry_supplement = "## 재생성 지침\n1. 단정적 표현 제거\n2. 검색 결과 기반"
            AnswerGenerationFallback.generate_with_fallback(
                query="테스트 질문",
                retrieval={'disputes': [], 'laws': []},
                agency_info={'agency': 'KCA'},
                retry_supplement=retry_supplement,
            )

            # generate_structured_answer 호출 검증
            assert mock_gen.called
            call_kwargs = mock_gen.call_args.kwargs

            # retry_supplement 전달 확인
            assert 'retry_supplement' in call_kwargs
            assert call_kwargs['retry_supplement'] == retry_supplement


class TestGeneratorAppendRetrySupplementToPrompt:
    """RAGGenerator.generate_structured_answer()의 retry_supplement 프롬프트 추가 테스트"""

    @patch('app.agents.answer_generation.tools.generator.OpenAI')
    def test_generator_appends_retry_supplement_to_system_prompt(self, mock_openai_class):
        """retry_supplement가 system_prompt에 추가되는지 검증"""
        from app.agents.answer_generation.tools.generator import RAGGenerator

        # Mock OpenAI 클라이언트 설정
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "생성된 답변"
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        # 실행
        generator = RAGGenerator(model='gpt-4o-mini', use_llm=True)
        retry_supplement = "## 재생성 지침\n이전 답변 수정 필요"

        generator.generate_structured_answer(
            query="테스트 질문",
            agency_info={'agency': 'KCA', 'agency_info': {}},
            disputes=[],
            counsels=[],
            laws=[],
            criteria=[],
            retry_supplement=retry_supplement,
        )

        # OpenAI API 호출 검증
        assert mock_client.chat.completions.create.called
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs

        # messages에서 system prompt 추출
        messages = call_kwargs['messages']
        system_message = next((m for m in messages if m['role'] == 'system'), None)

        # system_prompt에 retry_supplement 포함 확인
        assert system_message is not None
        assert "재생성 지침" in system_message['content']
        assert "이전 답변 수정 필요" in system_message['content']

    @patch('app.agents.answer_generation.tools.generator.OpenAI')
    def test_generator_without_retry_supplement(self, mock_openai_class):
        """retry_supplement=None일 때 시스템 프롬프트에 추가되지 않음"""
        from app.agents.answer_generation.tools.generator import RAGGenerator

        # Mock 설정
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "일반 답변"
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        # 실행
        generator = RAGGenerator(model='gpt-4o-mini', use_llm=True)

        generator.generate_structured_answer(
            query="테스트 질문",
            agency_info={'agency': 'KCA', 'agency_info': {}},
            disputes=[],
            counsels=[],
            laws=[],
            criteria=[],
            retry_supplement=None,  # None
        )

        # system_prompt에 재생성 지침 없음
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs['messages']
        system_message = next((m for m in messages if m['role'] == 'system'), None)

        assert system_message is not None
        assert "재생성 지침" not in system_message['content']


class TestEdgeCases:
    """Edge cases 테스트"""

    def test_violations_with_missing_fields(self):
        """violation dict에 필드가 누락된 경우"""
        from app.agents.answer_generation.agent import _build_retry_prompt_supplement

        retry_context = {
            'violations': [
                {'description': '타입 없음'},  # type 없음
                {'type': 'error'},  # description 없음
            ],
            'retry_count': 1,
        }

        result = _build_retry_prompt_supplement(retry_context)

        # 오류 없이 처리
        assert "타입 없음" in result or "[unknown]" in result

    @pytest.mark.asyncio
    @patch('app.agents.answer_generation.cache.get_answer_cache')
    @patch('app.agents.answer_generation.agent.RetrievalSufficiencyChecker')
    @patch('app.agents.answer_generation.fallback.AnswerGenerationFallback.generate_with_fallback')
    async def test_retry_context_with_high_retry_count(self, mock_fallback, mock_sufficiency, mock_cache):
        """retry_count가 높을 때 (재시도 제한 확인용)"""
        from app.agents.answer_generation.agent import generation_node_v2

        # Mock 설정
        mock_fallback.return_value = ("답변", "gpt-4o-mini", [])

        # Sufficiency checker mock
        mock_checker = MagicMock()
        mock_checker.evaluate.return_value = MagicMock(
            level='sufficient',
            is_sufficient=True,
            confidence=0.8,
        )
        mock_sufficiency.return_value = mock_checker

        # Cache mock
        mock_cache_instance = MagicMock()
        mock_cache_instance.get.return_value = None
        mock_cache.return_value = mock_cache_instance

        state = {
            'user_query': '테스트',
            'query_analysis': {'query_type': 'dispute'},
            'retrieval': {'laws': [], 'disputes': [], 'max_similarity': 0.8},
            'retry_context': {
                'violations': [{'type': 'test', 'description': 'test'}],
                'retry_count': 5,  # 높은 재시도 횟수
            },
        }

        # 정상 실행 (retry_count 제한은 상위 로직에서 처리)
        result = await generation_node_v2(state)
        assert result['draft_answer'] == "답변"
