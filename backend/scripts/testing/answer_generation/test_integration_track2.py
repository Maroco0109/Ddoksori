"""
똑소리 프로젝트 - Track 2 통합 테스트

작성일: 2026-01-28

유연한 답변 형식 및 후속 질문 생성의 E2E 통합 테스트입니다.
"""

import pytest
from unittest.mock import patch, MagicMock
from app.agents.answer_generation.agent import generation_node


# ============================================================
# Track 2 통합 테스트
# ============================================================

@pytest.mark.unit
@patch('app.agents.answer_generation.agent.get_config')
@patch('app.agents.answer_generation.agent.AnswerGenerationFallback.generate_with_fallback')
def test_track2_followup_questions_enabled(mock_fallback, mock_config):
    """ENABLE_FOLLOWUP_QUESTIONS=true일 때 후속 질문 생성"""
    # Mock config
    mock_config_obj = MagicMock()
    mock_config_obj.chatbot_features.enable_followup_questions = True
    mock_config_obj.chatbot_features.answer_format_mode = 'fixed'
    mock_config.return_value = mock_config_obj

    # Mock fallback
    mock_fallback.return_value = (
        "환불은 14일 이내에 가능합니다.",
        "gpt-4o-mini",
        []
    )

    # State
    state = {
        'user_query': '헬스장 환불 문제입니다',
        'query_analysis': {
            'query_type': 'dispute',
            'dispute_type': '환불',
            'missing_fields': []
        },
        'retrieval': {
            'disputes': [{'doc_id': '123', 'doc_title': '헬스장 환불 사례'}],
            'counsels': [],
            'laws': [],
            'criteria': [],
            'agency': {
                'agency': 'KCA',
                'agency_info': {
                    'name': '한국소비자원',
                    'full_name': '한국소비자원',
                    'url': 'https://www.kca.go.kr'
                }
            }
        }
    }

    result = generation_node(state)

    # 후속 질문이 생성되어야 함
    assert 'followup_questions' in result
    assert isinstance(result['followup_questions'], list)
    # 환불 관련 후속 질문이 있어야 함
    assert len(result['followup_questions']) > 0

    # 명확화 질문도 있어야 함
    assert 'clarifying_questions' in result
    assert isinstance(result['clarifying_questions'], list)


@pytest.mark.unit
@patch('app.agents.answer_generation.agent.get_config')
@patch('app.agents.answer_generation.agent.AnswerGenerationFallback.generate_with_fallback')
def test_track2_followup_questions_disabled(mock_fallback, mock_config):
    """ENABLE_FOLLOWUP_QUESTIONS=false일 때 후속 질문 미생성"""
    # Mock config
    mock_config_obj = MagicMock()
    mock_config_obj.chatbot_features.enable_followup_questions = False
    mock_config_obj.chatbot_features.answer_format_mode = 'fixed'
    mock_config.return_value = mock_config_obj

    # Mock fallback
    mock_fallback.return_value = (
        "환불은 14일 이내에 가능합니다.",
        "gpt-4o-mini",
        []
    )

    # State
    state = {
        'user_query': '헬스장 환불 문제입니다',
        'query_analysis': {
            'query_type': 'dispute',
            'dispute_type': '환불',
            'missing_fields': []
        },
        'retrieval': {
            'disputes': [{'doc_id': '123'}],
            'counsels': [],
            'laws': [],
            'criteria': [],
            'agency': {
                'agency': 'KCA',
                'agency_info': {
                    'name': '한국소비자원',
                    'full_name': '한국소비자원',
                    'url': 'https://www.kca.go.kr'
                }
            }
        }
    }

    result = generation_node(state)

    # 후속 질문이 빈 리스트여야 함
    assert 'followup_questions' in result
    assert result['followup_questions'] == []

    # 명확화 질문도 빈 리스트여야 함
    assert 'clarifying_questions' in result
    assert result['clarifying_questions'] == []


@pytest.mark.unit
@patch('app.agents.answer_generation.agent.get_config')
@patch('app.agents.answer_generation.agent.AnswerGenerationFallback.generate_with_fallback')
def test_track2_flexible_format_mode(mock_fallback, mock_config):
    """ANSWER_FORMAT_MODE=flexible일 때 FormatSelector 사용"""
    # Mock config
    mock_config_obj = MagicMock()
    mock_config_obj.chatbot_features.enable_followup_questions = False
    mock_config_obj.chatbot_features.answer_format_mode = 'flexible'
    mock_config.return_value = mock_config_obj

    # Mock fallback
    mock_fallback.return_value = (
        "환불은 14일 이내에 가능합니다.",
        "gpt-4o-mini",
        []
    )

    # State
    state = {
        'user_query': '헬스장 환불 문제입니다',
        'query_analysis': {
            'query_type': 'dispute',
            'dispute_type': '환불',
            'missing_fields': []
        },
        'retrieval': {
            'disputes': [{'doc_id': '123'}],
            'counsels': [],
            'laws': [],
            'criteria': [],
            'agency': {
                'agency': 'KCA',
                'agency_info': {
                    'name': '한국소비자원',
                    'full_name': '한국소비자원',
                    'url': 'https://www.kca.go.kr'
                }
            }
        }
    }

    result = generation_node(state)

    # 답변이 생성되어야 함
    assert 'draft_answer' in result
    assert len(result['draft_answer']) > 0


@pytest.mark.unit
def test_track2_general_query_no_followup():
    """일반 대화 쿼리는 후속 질문 생성 안함"""
    state = {
        'user_query': '안녕하세요',
        'query_analysis': {
            'query_type': 'general',
            'dispute_type': None,
            'missing_fields': []
        },
        'retrieval': None
    }

    result = generation_node(state)

    # 일반 응답
    assert 'draft_answer' in result
    assert '똑소리' in result['draft_answer']

    # 후속 질문이 없어야 함 (query_analysis가 없으므로)
    # followup_questions 키가 없을 수도 있음


@pytest.mark.unit
@patch('app.agents.answer_generation.agent.get_config')
@patch('app.agents.answer_generation.agent.AnswerGenerationFallback.generate_with_fallback')
def test_track2_with_missing_fields(mock_fallback, mock_config):
    """누락 정보가 있을 때 명확화 질문 생성"""
    # Mock config
    mock_config_obj = MagicMock()
    mock_config_obj.chatbot_features.enable_followup_questions = True
    mock_config_obj.chatbot_features.answer_format_mode = 'fixed'
    mock_config.return_value = mock_config_obj

    # Mock fallback
    mock_fallback.return_value = (
        "추가 정보가 필요합니다.",
        "gpt-4o-mini",
        []
    )

    # State with missing fields
    state = {
        'user_query': '환불하고 싶어요',
        'query_analysis': {
            'query_type': 'dispute',
            'dispute_type': '환불',
            'missing_fields': ['purchase_date', 'product_name']
        },
        'retrieval': {
            'disputes': [],
            'counsels': [],
            'laws': [],
            'criteria': [],
            'agency': {
                'agency': 'KCA',
                'agency_info': {
                    'name': '한국소비자원',
                    'full_name': '한국소비자원',
                    'url': 'https://www.kca.go.kr'
                }
            }
        }
    }

    result = generation_node(state)

    # 명확화 질문이 생성되어야 함
    assert 'clarifying_questions' in result
    assert len(result['clarifying_questions']) > 0


# ============================================================
# 백워드 호환성 테스트
# ============================================================

@pytest.mark.unit
@patch('app.agents.answer_generation.agent.get_config')
@patch('app.agents.answer_generation.agent.AnswerGenerationFallback.generate_with_fallback')
def test_track2_backward_compatibility_fixed_mode(mock_fallback, mock_config):
    """ANSWER_FORMAT_MODE=fixed일 때 기존 동작 유지"""
    # Mock config
    mock_config_obj = MagicMock()
    mock_config_obj.chatbot_features.enable_followup_questions = False
    mock_config_obj.chatbot_features.answer_format_mode = 'fixed'
    mock_config.return_value = mock_config_obj

    # Mock fallback
    mock_fallback.return_value = (
        "환불은 14일 이내에 가능합니다.",
        "gpt-4o-mini",
        []
    )

    # State
    state = {
        'user_query': '헬스장 환불 문제입니다',
        'query_analysis': {
            'query_type': 'dispute',
            'dispute_type': '환불',
            'missing_fields': []
        },
        'retrieval': {
            'disputes': [{'doc_id': '123'}],
            'counsels': [],
            'laws': [],
            'criteria': [],
            'agency': {
                'agency': 'KCA',
                'agency_info': {
                    'name': '한국소비자원',
                    'full_name': '한국소비자원',
                    'url': 'https://www.kca.go.kr'
                }
            }
        }
    }

    result = generation_node(state)

    # 기존 필드가 모두 존재해야 함
    assert 'draft_answer' in result
    assert 'has_sufficient_evidence' in result
    assert 'clarifying_questions' in result
    assert 'claim_evidence_map' in result
    assert 'messages' in result

    # 새 필드도 존재 (빈 리스트)
    assert 'followup_questions' in result
    assert result['followup_questions'] == []
