import pytest
from langgraph.graph import END

from app.orchestrator.graph import (
    _route_after_query_analysis,
    _route_after_retrieval,
    _route_after_review,
    SIMILARITY_THRESHOLD_HIGH,
)
from app.orchestrator import create_initial_state


class TestRouteAfterQueryAnalysis:

    def test_general_query_goes_to_retrieval(self):
        state = create_initial_state(user_query="안녕하세요", chat_type='general')
        state['query_analysis'] = {'query_type': 'general', 'needs_clarification': False, 'extracted_info': {}}
        
        result = _route_after_query_analysis(state)
        assert result == 'retrieval'

    def test_dispute_with_info_goes_to_retrieval(self):
        state = create_initial_state(user_query="노트북 환불", chat_type='dispute')
        state['query_analysis'] = {
            'query_type': 'dispute',
            'needs_clarification': False,
            'extracted_info': {'purchase_item': '노트북'},
        }
        
        result = _route_after_query_analysis(state)
        assert result == 'retrieval'

    def test_dispute_needs_clarification_no_info_goes_to_ask(self):
        state = create_initial_state(user_query="환불해줘", chat_type='dispute')
        state['query_analysis'] = {
            'query_type': 'dispute',
            'needs_clarification': True,
            'extracted_info': {},
        }
        
        result = _route_after_query_analysis(state)
        assert result == 'ask_clarification'

    def test_dispute_needs_clarification_with_item_goes_to_retrieval(self):
        state = create_initial_state(user_query="환불해줘", chat_type='dispute')
        state['query_analysis'] = {
            'query_type': 'dispute',
            'needs_clarification': True,
            'extracted_info': {'purchase_item': '노트북'},
        }
        
        result = _route_after_query_analysis(state)
        assert result == 'retrieval'

    def test_dispute_needs_clarification_with_details_goes_to_retrieval(self):
        state = create_initial_state(user_query="환불해줘", chat_type='dispute')
        state['query_analysis'] = {
            'query_type': 'dispute',
            'needs_clarification': True,
            'extracted_info': {'dispute_details': '화면 불량'},
        }
        
        result = _route_after_query_analysis(state)
        assert result == 'retrieval'

    def test_no_query_analysis_defaults_to_retrieval(self):
        state = create_initial_state(user_query="테스트", chat_type='dispute')
        state['query_analysis'] = None
        
        result = _route_after_query_analysis(state)
        assert result == 'retrieval'

    def test_law_query_goes_to_retrieval(self):
        state = create_initial_state(user_query="전자상거래법 조항", chat_type='dispute')
        state['query_analysis'] = {
            'query_type': 'law',
            'needs_clarification': False,
            'extracted_info': {},
        }
        
        result = _route_after_query_analysis(state)
        assert result == 'retrieval'

    def test_criteria_query_goes_to_retrieval(self):
        state = create_initial_state(user_query="분쟁조정기준", chat_type='dispute')
        state['query_analysis'] = {
            'query_type': 'criteria',
            'needs_clarification': False,
            'extracted_info': {},
        }
        
        result = _route_after_query_analysis(state)
        assert result == 'retrieval'


class TestRouteAfterRetrieval:

    def test_general_query_always_goes_to_generation(self):
        state = create_initial_state(user_query="안녕", chat_type='general')
        state['query_analysis'] = {'query_type': 'general'}
        state['retrieval'] = None
        
        result = _route_after_retrieval(state)
        assert result == 'generation'

    def test_high_similarity_goes_to_generation(self):
        state = create_initial_state(user_query="노트북 환불", chat_type='dispute')
        state['query_analysis'] = {'query_type': 'dispute'}
        state['retrieval'] = {
            'max_similarity': 0.75,
            'disputes': [{'chunk_id': '1'}],
            'counsels': [],
        }
        
        result = _route_after_retrieval(state)
        assert result == 'generation'

    def test_threshold_boundary_goes_to_generation(self):
        state = create_initial_state(user_query="노트북 환불", chat_type='dispute')
        state['query_analysis'] = {'query_type': 'dispute'}
        state['retrieval'] = {
            'max_similarity': SIMILARITY_THRESHOLD_HIGH,
            'disputes': [{'chunk_id': '1'}],
            'counsels': [],
        }
        
        result = _route_after_retrieval(state)
        assert result == 'generation'

    def test_below_threshold_goes_to_low_similarity(self):
        state = create_initial_state(user_query="노트북 환불", chat_type='dispute')
        state['query_analysis'] = {'query_type': 'dispute'}
        state['retrieval'] = {
            'max_similarity': SIMILARITY_THRESHOLD_HIGH - 0.01,
            'disputes': [{'chunk_id': '1'}],
            'counsels': [],
        }
        
        result = _route_after_retrieval(state)
        assert result == 'low_similarity_prompt'

    def test_no_results_goes_to_low_similarity(self):
        state = create_initial_state(user_query="노트북 환불", chat_type='dispute')
        state['query_analysis'] = {'query_type': 'dispute'}
        state['retrieval'] = {
            'max_similarity': 0.8,
            'disputes': [],
            'counsels': [],
        }
        
        result = _route_after_retrieval(state)
        assert result == 'low_similarity_prompt'

    def test_no_retrieval_goes_to_low_similarity(self):
        state = create_initial_state(user_query="노트북 환불", chat_type='dispute')
        state['query_analysis'] = {'query_type': 'dispute'}
        state['retrieval'] = None
        
        result = _route_after_retrieval(state)
        assert result == 'low_similarity_prompt'

    def test_only_counsels_with_high_similarity(self):
        state = create_initial_state(user_query="노트북 환불", chat_type='dispute')
        state['query_analysis'] = {'query_type': 'dispute'}
        state['retrieval'] = {
            'max_similarity': 0.7,
            'disputes': [],
            'counsels': [{'chunk_id': '1'}],
        }
        
        result = _route_after_retrieval(state)
        assert result == 'generation'


class TestRouteAfterReview:

    def test_passed_review_goes_to_end(self):
        state = create_initial_state(user_query="테스트", chat_type='dispute')
        state['review'] = {'passed': True, 'violations': []}
        state['retry_count'] = 0
        
        result = _route_after_review(state)
        assert result == END

    def test_failed_review_first_retry(self):
        state = create_initial_state(user_query="테스트", chat_type='dispute')
        state['review'] = {'passed': False, 'violations': ['violation1']}
        state['retry_count'] = 0
        
        result = _route_after_review(state)
        assert result == 'generation'

    def test_failed_review_second_retry(self):
        state = create_initial_state(user_query="테스트", chat_type='dispute')
        state['review'] = {'passed': False, 'violations': ['violation1']}
        state['retry_count'] = 1
        
        result = _route_after_review(state)
        assert result == 'generation'

    def test_failed_review_max_retries_goes_to_end(self):
        state = create_initial_state(user_query="테스트", chat_type='dispute')
        state['review'] = {'passed': False, 'violations': ['violation1']}
        state['retry_count'] = 2
        
        result = _route_after_review(state)
        assert result == END

    def test_no_review_goes_to_end(self):
        state = create_initial_state(user_query="테스트", chat_type='dispute')
        state['review'] = None
        state['retry_count'] = 0
        
        result = _route_after_review(state)
        assert result == END

    def test_passed_review_ignores_retry_count(self):
        state = create_initial_state(user_query="테스트", chat_type='dispute')
        state['review'] = {'passed': True, 'violations': []}
        state['retry_count'] = 5
        
        result = _route_after_review(state)
        assert result == END


class TestRoutingEdgeCases:

    def test_empty_extracted_info_dict(self):
        state = create_initial_state(user_query="환불", chat_type='dispute')
        state['query_analysis'] = {
            'query_type': 'dispute',
            'needs_clarification': True,
            'extracted_info': {},
        }
        
        result = _route_after_query_analysis(state)
        assert result == 'ask_clarification'

    def test_extracted_info_with_empty_string_values(self):
        state = create_initial_state(user_query="환불", chat_type='dispute')
        state['query_analysis'] = {
            'query_type': 'dispute',
            'needs_clarification': True,
            'extracted_info': {'purchase_item': '', 'dispute_details': ''},
        }
        
        result = _route_after_query_analysis(state)
        assert result == 'ask_clarification'

    def test_zero_similarity_with_results(self):
        state = create_initial_state(user_query="테스트", chat_type='dispute')
        state['query_analysis'] = {'query_type': 'dispute'}
        state['retrieval'] = {
            'max_similarity': 0.0,
            'disputes': [{'chunk_id': '1'}],
            'counsels': [],
        }
        
        result = _route_after_retrieval(state)
        assert result == 'low_similarity_prompt'
