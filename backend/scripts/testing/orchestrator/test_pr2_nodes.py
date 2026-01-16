"""
PR2 Node Functions 테스트
작성일: 2026-01-14

테스트 대상:
- query_analysis_node: 질의 분류, 키워드 추출, 누락 필드 탐지
- retrieval_node: 검색 결과 변환 (DB 없이 빈 결과 테스트)
- generation_node: 일반 대화 응답 생성 (LLM 없이)
- review_node: 금지 표현 탐지, 출처 검사
- ask_clarification_node: 추가 질문 생성
"""

import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_path))

import pytest
from typing import Dict, Any

from app.orchestrator.state import ChatState, create_initial_state, OnboardingInfo
from app.orchestrator.nodes.query_analysis import (
    query_analysis_node,
    _classify_query_type,
    _extract_keywords,
    _determine_agency_hint,
)
from app.orchestrator.nodes.retrieval import retrieval_node
from app.orchestrator.nodes.generation import generation_node
from app.orchestrator.nodes.review import (
    review_node,
    _check_prohibited_expressions,
    _check_citation_presence,
)
from app.orchestrator.nodes.ask_clarification import ask_clarification_node


class TestQueryAnalysisNode:
    def test_dispute_query_classification(self):
        state = create_initial_state(
            user_query="헬스장 환불 규정 알려줘",
            chat_type='dispute',
        )
        result = query_analysis_node(state)
        
        assert 'query_analysis' in result
        analysis = result['query_analysis']
        assert analysis['query_type'] == 'dispute'
        assert len(analysis['keywords']) > 0
    
    def test_general_query_classification(self):
        state = create_initial_state(
            user_query="안녕하세요",
            chat_type='general',
        )
        result = query_analysis_node(state)
        
        analysis = result['query_analysis']
        assert analysis['query_type'] == 'general'
        assert analysis['agency_hint'] is None
    
    def test_missing_onboarding_fields_detected(self):
        state = create_initial_state(
            user_query="환불 받고 싶어요",
            chat_type='dispute',
            onboarding=None,
        )
        result = query_analysis_node(state)
        
        analysis = result['query_analysis']
        assert analysis['needs_clarification'] is True
        assert 'purchase_item' in analysis['missing_fields']
    
    def test_complete_onboarding_no_clarification(self):
        onboarding: OnboardingInfo = {
            'purchase_item': '헬스장 회원권',
            'dispute_details': '중도 해지 시 환불 거부',
        }
        state = create_initial_state(
            user_query="환불 받을 수 있나요?",
            chat_type='dispute',
            onboarding=onboarding,
        )
        result = query_analysis_node(state)
        
        analysis = result['query_analysis']
        assert analysis['needs_clarification'] is False
        assert len(analysis['missing_fields']) == 0
    
    def test_agency_hint_kcdrc_for_game(self):
        state = create_initial_state(
            user_query="게임 아이템 환불 가능한가요?",
            chat_type='dispute',
        )
        result = query_analysis_node(state)
        
        analysis = result['query_analysis']
        assert analysis['agency_hint'] == 'KCDRC'
    
    def test_agency_hint_ecmc_for_secondhand(self):
        state = create_initial_state(
            user_query="중고거래 사기 당했어요",
            chat_type='dispute',
        )
        result = query_analysis_node(state)
        
        analysis = result['query_analysis']
        assert analysis['agency_hint'] == 'ECMC'


class TestQueryAnalysisHelpers:
    def test_classify_general_greeting(self):
        assert _classify_query_type("안녕하세요") == 'general'
        assert _classify_query_type("반가워요") == 'general'
        assert _classify_query_type("고마워") == 'general'
    
    def test_classify_dispute_default(self):
        assert _classify_query_type("환불 받고 싶어요") == 'dispute'
        assert _classify_query_type("헬스장 계약 해지") == 'dispute'
    
    def test_classify_law_query(self):
        assert _classify_query_type("소비자보호법 제7조 알려줘") == 'law'
        assert _classify_query_type("전자상거래법 조항 문의") == 'law'
    
    def test_extract_keywords(self):
        keywords = _extract_keywords("헬스장 회원권 환불 규정 알려주세요")
        assert '헬스장' in keywords
        assert '회원권' in keywords
        assert '환불' in keywords
    
    def test_agency_hint_default_kca(self):
        assert _determine_agency_hint("일반 제품 환불") == 'KCA'


class TestRetrievalNode:
    def test_general_query_skips_retrieval(self):
        state = create_initial_state(
            user_query="안녕하세요",
            chat_type='general',
        )
        state['query_analysis'] = {
            'query_type': 'general',
            'keywords': [],
            'agency_hint': None,
            'needs_clarification': False,
            'missing_fields': [],
        }
        
        result = retrieval_node(state)
        
        assert 'retrieval' in result
        assert result['retrieval']['disputes'] == []
        assert result['retrieval']['laws'] == []
        assert result['sources'] == []
    
    def test_dispute_query_without_db_returns_empty(self):
        state = create_initial_state(
            user_query="헬스장 환불",
            chat_type='dispute',
        )
        state['query_analysis'] = {
            'query_type': 'dispute',
            'keywords': ['헬스장', '환불'],
            'agency_hint': 'KCA',
            'needs_clarification': False,
            'missing_fields': [],
        }
        
        result = retrieval_node(state)
        
        assert 'retrieval' in result
        assert isinstance(result['sources'], list)


class TestGenerationNode:
    def test_general_greeting_response(self):
        state = create_initial_state(
            user_query="안녕하세요",
            chat_type='general',
        )
        state['query_analysis'] = {
            'query_type': 'general',
            'keywords': [],
            'agency_hint': None,
            'needs_clarification': False,
            'missing_fields': [],
        }
        
        result = generation_node(state)
        
        assert 'draft_answer' in result
        assert '똑소리' in result['draft_answer']
        assert result['has_sufficient_evidence'] is True
        assert 'messages' in result
    
    def test_no_retrieval_returns_fallback(self):
        state = create_initial_state(
            user_query="환불 받고 싶어요",
            chat_type='dispute',
        )
        state['query_analysis'] = {
            'query_type': 'dispute',
            'keywords': ['환불'],
            'agency_hint': 'KCA',
            'needs_clarification': False,
            'missing_fields': [],
        }
        state['retrieval'] = None
        
        result = generation_node(state)
        
        assert 'draft_answer' in result
        assert result['has_sufficient_evidence'] is False


class TestReviewNode:
    def test_general_query_passes_review(self):
        state = create_initial_state(
            user_query="안녕하세요",
            chat_type='general',
        )
        state['query_analysis'] = {
            'query_type': 'general',
            'keywords': [],
            'agency_hint': None,
            'needs_clarification': False,
            'missing_fields': [],
        }
        state['draft_answer'] = "안녕하세요! 똑소리입니다."
        
        result = review_node(state)
        
        assert result['review']['passed'] is True
        assert result['final_answer'] == state['draft_answer']
    
    def test_prohibited_expression_detected(self):
        violations = _check_prohibited_expressions(
            "이 경우 반드시 환불받아야 합니다. 소송에서 이길 수 있습니다."
        )
        assert len(violations) > 0
    
    def test_no_prohibited_expression(self):
        violations = _check_prohibited_expressions(
            "환불을 요청해 볼 수 있습니다. 가능성이 있습니다."
        )
        assert len(violations) == 0
    
    def test_citation_presence_check(self):
        assert _check_citation_presence("관련 법령: 소비자보호법 제7조", has_sources=True)
        assert _check_citation_presence("분쟁조정사례에 따르면...", has_sources=True)
        assert not _check_citation_presence("그냥 환불받으세요", has_sources=True)
    
    def test_dispute_answer_with_violations_filtered(self):
        state = create_initial_state(
            user_query="환불 가능한가요?",
            chat_type='dispute',
        )
        state['query_analysis'] = {
            'query_type': 'dispute',
            'keywords': ['환불'],
            'agency_hint': 'KCA',
            'needs_clarification': False,
            'missing_fields': [],
        }
        state['draft_answer'] = "반드시 환불받아야 합니다."
        state['sources'] = []
        
        result = review_node(state)
        
        assert 'review' in result
        assert 'final_answer' in result


class TestAskClarificationNode:
    def test_generates_questions_for_missing_fields(self):
        state = create_initial_state(
            user_query="환불 받고 싶어요",
            chat_type='dispute',
        )
        state['query_analysis'] = {
            'query_type': 'dispute',
            'keywords': ['환불'],
            'agency_hint': 'KCA',
            'needs_clarification': True,
            'missing_fields': ['purchase_item', 'dispute_details'],
        }
        
        result = ask_clarification_node(state)
        
        assert 'final_answer' in result
        assert '제품' in result['final_answer'] or '서비스' in result['final_answer']
        assert 'clarifying_questions' in result
        assert len(result['clarifying_questions']) >= 2
    
    def test_no_missing_fields_fallback(self):
        state = create_initial_state(
            user_query="환불 받고 싶어요",
            chat_type='dispute',
        )
        state['query_analysis'] = {
            'query_type': 'dispute',
            'keywords': ['환불'],
            'agency_hint': 'KCA',
            'needs_clarification': False,
            'missing_fields': [],
        }
        
        result = ask_clarification_node(state)
        
        assert 'final_answer' in result
        assert result['clarifying_questions'] == []
    
    def test_no_query_analysis_default_questions(self):
        state = create_initial_state(
            user_query="도움이 필요해요",
            chat_type='dispute',
        )
        
        result = ask_clarification_node(state)
        
        assert 'final_answer' in result
        assert len(result['clarifying_questions']) > 0


class TestNodeIntegration:
    def test_full_flow_general_query(self):
        state = create_initial_state(
            user_query="안녕하세요",
            chat_type='general',
        )
        
        qa_result = query_analysis_node(state)
        state.update(qa_result)
        
        assert state['query_analysis']['query_type'] == 'general'
        
        ret_result = retrieval_node(state)
        state.update(ret_result)
        
        assert state['retrieval']['disputes'] == []
        
        gen_result = generation_node(state)
        state.update(gen_result)
        
        assert '똑소리' in state['draft_answer']
        
        rev_result = review_node(state)
        state.update(rev_result)
        
        assert state['review']['passed'] is True
        assert state['final_answer'] is not None
    
    def test_dispute_flow_needs_clarification(self):
        state = create_initial_state(
            user_query="환불 받고 싶어요",
            chat_type='dispute',
            onboarding=None,
        )
        
        qa_result = query_analysis_node(state)
        state.update(qa_result)
        
        assert state['query_analysis']['needs_clarification'] is True
        
        clarify_result = ask_clarification_node(state)
        state.update(clarify_result)
        
        assert '제품' in state['final_answer'] or '서비스' in state['final_answer']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
