"""
똑소리 프로젝트 - ReAct LLM 기반 추론 테스트
작성일: 2026-01-17
S2-8: EXAONE 3.5 2.4B 통합 테스트

테스트 범위:
1. ExaoneLLMClient 클래스 테스트
2. LLM 기반 react_think_node 테스트
3. 규칙 기반 폴백 테스트
"""

import pytest
import os
import json
from typing import Dict, Any
from unittest.mock import patch, MagicMock

from app.llm import ExaoneLLMClient, LLMUnavailableError
from app.orchestrator.state import ChatState, create_initial_state
from app.orchestrator.nodes.react_think import (
    react_think_node,
    _llm_based_think,
    _rule_based_think,
    _build_think_prompt,
    _parse_llm_response,
    REACT_THINK_SYSTEM_PROMPT,
)


class TestExaoneLLMClient:
    """ExaoneLLMClient 클래스 테스트"""

    def test_init_reads_env_variables(self):
        """환경 변수에서 설정 읽기"""
        with patch.dict(os.environ, {
            'EXAONE_RUNPOD_URL': 'https://test-pod-8000.proxy.runpod.net/v1',
            'EXAONE_RUNPOD_API_KEY': 'test-api-key',
            'EXAONE_MODEL': 'test-model',
            'EXAONE_TIMEOUT': '15',
            'EXAONE_TEMPERATURE': '0.2',
            'EXAONE_MAX_TOKENS': '1024',
        }):
            client = ExaoneLLMClient()

            assert client.runpod_url == 'https://test-pod-8000.proxy.runpod.net/v1'
            assert client.api_key == 'test-api-key'
            assert client.model == 'test-model'
            assert client.timeout == 15
            assert client.temperature == 0.2
            assert client.max_tokens == 1024

    def test_init_uses_defaults(self):
        """기본값 사용 테스트"""
        with patch.dict(os.environ, {}, clear=True):
            # 환경 변수 없이 생성
            with patch.dict(os.environ, {'EXAONE_RUNPOD_URL': ''}):
                client = ExaoneLLMClient()

                assert client.runpod_url == ''
                assert client.api_key == 'dummy'
                assert client.model == 'LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct'
                assert client.timeout == 10
                assert client.temperature == 0.1
                assert client.max_tokens == 512

    @patch('app.llm.exaone_client.requests.get')
    def test_health_check_success(self, mock_get):
        """RunPod 헬스체크 성공"""
        mock_get.return_value.status_code = 200

        with patch.dict(os.environ, {
            'EXAONE_RUNPOD_URL': 'https://test-pod-8000.proxy.runpod.net/v1'
        }):
            client = ExaoneLLMClient()
            result = client.health_check()

            assert result is True
            mock_get.assert_called_once_with(
                'https://test-pod-8000.proxy.runpod.net/health',
                timeout=5
            )

    @patch('app.llm.exaone_client.requests.get')
    def test_health_check_failure_status_code(self, mock_get):
        """RunPod 헬스체크 실패 (비정상 상태코드)"""
        mock_get.return_value.status_code = 503

        with patch.dict(os.environ, {
            'EXAONE_RUNPOD_URL': 'https://test-pod-8000.proxy.runpod.net/v1'
        }):
            client = ExaoneLLMClient()
            result = client.health_check()

            assert result is False

    @patch('app.llm.exaone_client.requests.get')
    def test_health_check_failure_timeout(self, mock_get):
        """RunPod 헬스체크 실패 (타임아웃)"""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()

        with patch.dict(os.environ, {
            'EXAONE_RUNPOD_URL': 'https://test-pod-8000.proxy.runpod.net/v1'
        }):
            client = ExaoneLLMClient()
            result = client.health_check()

            assert result is False

    @patch('app.llm.exaone_client.requests.get')
    def test_health_check_failure_connection_error(self, mock_get):
        """RunPod 헬스체크 실패 (연결 오류)"""
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError()

        with patch.dict(os.environ, {
            'EXAONE_RUNPOD_URL': 'https://test-pod-8000.proxy.runpod.net/v1'
        }):
            client = ExaoneLLMClient()
            result = client.health_check()

            assert result is False

    def test_health_check_no_url_configured(self):
        """RUNPOD_URL 미설정 시 헬스체크 실패"""
        with patch.dict(os.environ, {'EXAONE_RUNPOD_URL': ''}):
            client = ExaoneLLMClient()
            result = client.health_check()

            assert result is False

    @patch('app.llm.exaone_client.requests.get')
    def test_is_available_caches_result(self, mock_get):
        """is_available()이 결과를 캐싱하는지 확인"""
        mock_get.return_value.status_code = 200

        with patch.dict(os.environ, {
            'EXAONE_RUNPOD_URL': 'https://test-pod-8000.proxy.runpod.net/v1'
        }):
            client = ExaoneLLMClient()

            # 첫 번째 호출
            result1 = client.is_available()
            # 두 번째 호출
            result2 = client.is_available()

            assert result1 is True
            assert result2 is True
            # health_check는 한 번만 호출되어야 함
            assert mock_get.call_count == 1

    @patch('app.llm.exaone_client.requests.get')
    def test_reset_availability_clears_cache(self, mock_get):
        """reset_availability()가 캐시를 지우는지 확인"""
        mock_get.return_value.status_code = 200

        with patch.dict(os.environ, {
            'EXAONE_RUNPOD_URL': 'https://test-pod-8000.proxy.runpod.net/v1'
        }):
            client = ExaoneLLMClient()

            # 첫 번째 호출
            client.is_available()
            assert mock_get.call_count == 1

            # 캐시 리셋
            client.reset_availability()

            # 다시 호출 → 새로운 헬스체크
            client.is_available()
            assert mock_get.call_count == 2

    def test_generate_raises_when_unavailable(self):
        """서버 불가 시 LLMUnavailableError 발생"""
        with patch.dict(os.environ, {'EXAONE_RUNPOD_URL': ''}):
            client = ExaoneLLMClient()

            with pytest.raises(LLMUnavailableError) as exc_info:
                client.generate("system", "user")

            assert "unavailable" in str(exc_info.value).lower()

    @patch('app.llm.exaone_client.requests.get')
    @patch('app.llm.exaone_client.OpenAI')
    def test_generate_returns_response(self, mock_openai_class, mock_get):
        """LLM 응답 반환 테스트"""
        # 헬스체크 성공
        mock_get.return_value.status_code = 200

        # OpenAI 클라이언트 mock
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"thought": "테스트", "action": "search_all", "should_continue": true}'
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_client.chat.completions.create.return_value = mock_response

        with patch.dict(os.environ, {
            'EXAONE_RUNPOD_URL': 'https://test-pod-8000.proxy.runpod.net/v1'
        }):
            client = ExaoneLLMClient()
            result = client.generate("시스템 프롬프트", "사용자 프롬프트")

            assert '{"thought"' in result
            mock_client.chat.completions.create.assert_called_once()


class TestParseLLMResponse:
    """_parse_llm_response 함수 테스트"""

    def test_parse_valid_json(self):
        """유효한 JSON 파싱"""
        response = '{"thought": "분석 결과", "action": "search_all", "should_continue": true}'
        result = _parse_llm_response(response)

        assert result is not None
        assert result['thought'] == '분석 결과'
        assert result['action'] == 'search_all'
        assert result['should_continue'] is True

    def test_parse_json_with_markdown_block(self):
        """마크다운 코드블록으로 감싸진 JSON 파싱"""
        response = '''```json
{"thought": "분석 결과", "action": "generate", "should_continue": false}
```'''
        result = _parse_llm_response(response)

        assert result is not None
        assert result['action'] == 'generate'
        assert result['should_continue'] is False

    def test_parse_json_with_generic_block(self):
        """일반 코드블록으로 감싸진 JSON 파싱"""
        response = '''```
{"thought": "테스트", "action": "search_criteria", "should_continue": true}
```'''
        result = _parse_llm_response(response)

        assert result is not None
        assert result['action'] == 'search_criteria'

    def test_parse_invalid_json_returns_none(self):
        """유효하지 않은 JSON → None 반환"""
        response = "이것은 JSON이 아닙니다."
        result = _parse_llm_response(response)

        assert result is None

    def test_parse_missing_fields_returns_none(self):
        """필수 필드 누락 → None 반환"""
        response = '{"thought": "분석", "action": "search_all"}'  # should_continue 누락
        result = _parse_llm_response(response)

        assert result is None


class TestBuildThinkPrompt:
    """_build_think_prompt 함수 테스트"""

    def test_prompt_contains_user_query(self):
        """프롬프트에 사용자 질문 포함"""
        state = create_initial_state(
            user_query="노트북 환불하고 싶어요",
            chat_type='dispute',
        )

        prompt = _build_think_prompt(state)

        assert "노트북 환불하고 싶어요" in prompt

    def test_prompt_contains_iteration_info(self):
        """프롬프트에 반복 정보 포함"""
        state = create_initial_state(
            user_query="테스트",
            chat_type='dispute',
        )
        state['current_iteration'] = 1
        state['max_iterations'] = 3

        prompt = _build_think_prompt(state)

        assert "2/3" in prompt  # current_iteration + 1

    def test_prompt_contains_retrieval_counts(self):
        """프롬프트에 검색 결과 수 포함"""
        state = create_initial_state(
            user_query="테스트",
            chat_type='dispute',
        )
        state['retrieval'] = {
            'disputes': [{'id': 1}, {'id': 2}],
            'counsels': [{'id': 1}],
            'laws': [],
            'criteria': [{'id': 1}],
            'max_similarity': 0.75,
        }

        prompt = _build_think_prompt(state)

        assert "분쟁사례: 2건" in prompt
        assert "상담사례: 1건" in prompt
        assert "관련 법령: 0건" in prompt
        assert "분쟁해결기준: 1건" in prompt
        assert "0.75" in prompt


class TestReactThinkLLM:
    """LLM 기반 react_think_node 테스트"""

    @patch('app.llm.ExaoneLLMClient')
    def test_llm_based_think_generates_valid_result(self, mock_client_class):
        """LLM 기반 추론이 유효한 결과 반환"""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.generate.return_value = '{"thought": "검색 필요", "action": "search_all", "should_continue": true}'

        state = create_initial_state(
            user_query="노트북 환불",
            chat_type='dispute',
        )

        result = _llm_based_think(state)

        assert result['last_thought'] == '검색 필요'
        assert result['last_action'] == 'search_all'
        assert result['should_continue'] is True
        assert result['current_iteration'] == 1

    @patch('app.llm.ExaoneLLMClient')
    def test_llm_decides_search_all_on_empty_retrieval(self, mock_client_class):
        """빈 검색 결과에서 search_all 결정"""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.generate.return_value = '{"thought": "검색 데이터 없음", "action": "search_all", "should_continue": true}'

        state = create_initial_state(
            user_query="노트북 환불",
            chat_type='dispute',
        )

        result = _llm_based_think(state)

        assert result['last_action'] == 'search_all'
        assert result['should_continue'] is True

    @patch('app.llm.ExaoneLLMClient')
    def test_llm_decides_generate_on_sufficient_data(self, mock_client_class):
        """충분한 데이터에서 generate 결정"""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.generate.return_value = '{"thought": "충분한 정보 수집", "action": "generate", "should_continue": false}'

        state = create_initial_state(
            user_query="노트북 환불",
            chat_type='dispute',
        )
        state['retrieval'] = {
            'disputes': [{'id': 1}],
            'counsels': [{'id': 1}],
            'laws': [{'id': 1}],
            'criteria': [{'id': 1}],
            'max_similarity': 0.8,
        }
        state['current_iteration'] = 1

        result = _llm_based_think(state)

        assert result['last_action'] is None  # generate → action = None
        assert result['should_continue'] is False

    @patch('app.llm.ExaoneLLMClient')
    def test_fallback_to_rule_on_llm_unavailable(self, mock_client_class):
        """LLM 불가 시 규칙 기반 폴백"""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.generate.side_effect = LLMUnavailableError("Server unavailable")

        state = create_initial_state(
            user_query="노트북 환불",
            chat_type='dispute',
        )

        result = _llm_based_think(state)

        # 규칙 기반 폴백 → 첫 반복, 데이터 없음 → search_all
        assert result['last_action'] == 'search_all'
        assert result['should_continue'] is True

    @patch('app.llm.ExaoneLLMClient')
    def test_fallback_to_rule_on_parse_error(self, mock_client_class):
        """JSON 파싱 오류 시 규칙 기반 폴백"""
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.generate.return_value = "이것은 JSON이 아닙니다"

        state = create_initial_state(
            user_query="노트북 환불",
            chat_type='dispute',
        )

        result = _llm_based_think(state)

        # 규칙 기반 폴백 동작
        assert 'last_thought' in result
        assert 'last_action' in result
        assert 'should_continue' in result


class TestReactThinkNodeModeSwitch:
    """react_think_node 모드 전환 테스트"""

    @patch('app.orchestrator.nodes.react_think._llm_based_think')
    def test_llm_mode_calls_llm_think(self, mock_llm_think):
        """REACT_THINK_MODE=llm → LLM 기반 추론 호출"""
        mock_llm_think.return_value = {
            'last_thought': 'LLM 추론',
            'last_action': 'search_all',
            'should_continue': True,
            'current_iteration': 1,
        }

        state = create_initial_state(
            user_query="테스트",
            chat_type='dispute',
        )

        with patch.dict(os.environ, {'REACT_THINK_MODE': 'llm'}):
            result = react_think_node(state)

        mock_llm_think.assert_called_once()
        assert result['last_thought'] == 'LLM 추론'

    @patch('app.orchestrator.nodes.react_think._rule_based_think')
    def test_rule_mode_calls_rule_think(self, mock_rule_think):
        """REACT_THINK_MODE=rule → 규칙 기반 추론 호출"""
        mock_rule_think.return_value = {
            'last_thought': '규칙 추론',
            'last_action': 'search_all',
            'should_continue': True,
            'current_iteration': 1,
        }

        state = create_initial_state(
            user_query="테스트",
            chat_type='dispute',
        )

        with patch.dict(os.environ, {'REACT_THINK_MODE': 'rule'}):
            result = react_think_node(state)

        mock_rule_think.assert_called_once()
        assert result['last_thought'] == '규칙 추론'

    @patch('app.orchestrator.nodes.react_think._rule_based_think')
    def test_default_mode_is_rule(self, mock_rule_think):
        """환경 변수 미설정 시 기본값은 rule"""
        mock_rule_think.return_value = {
            'last_thought': '기본 규칙',
            'last_action': None,
            'should_continue': False,
            'current_iteration': 1,
        }

        state = create_initial_state(
            user_query="테스트",
            chat_type='dispute',
        )

        # REACT_THINK_MODE 환경 변수 제거
        env = os.environ.copy()
        env.pop('REACT_THINK_MODE', None)
        with patch.dict(os.environ, env, clear=True):
            result = react_think_node(state)

        mock_rule_think.assert_called_once()


class TestSystemPrompt:
    """시스템 프롬프트 테스트"""

    def test_system_prompt_contains_actions(self):
        """시스템 프롬프트에 가능한 액션 포함"""
        assert 'search_all' in REACT_THINK_SYSTEM_PROMPT
        assert 'search_criteria' in REACT_THINK_SYSTEM_PROMPT
        assert 'search_laws' in REACT_THINK_SYSTEM_PROMPT
        assert 'generate' in REACT_THINK_SYSTEM_PROMPT

    def test_system_prompt_contains_json_format(self):
        """시스템 프롬프트에 JSON 형식 안내 포함"""
        assert 'JSON' in REACT_THINK_SYSTEM_PROMPT
        assert 'thought' in REACT_THINK_SYSTEM_PROMPT
        assert 'action' in REACT_THINK_SYSTEM_PROMPT
        assert 'should_continue' in REACT_THINK_SYSTEM_PROMPT
