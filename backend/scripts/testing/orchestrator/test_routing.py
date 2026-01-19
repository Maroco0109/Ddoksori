import pytest
from unittest.mock import patch, MagicMock

from app.orchestrator.state import (
    ChatState_v2,
    create_initial_state_v2,
    QueryAnalysisResult_v2,
    SearchPlan,
    RetrievalReport_v2,
    ReviewReport_v2,
    SlotStatus,
)
from app.orchestrator.routing import (
    should_promote_to_rag,
    route_after_query_analysis,
    route_after_sufficiency,
    route_after_review,
)
from app.orchestrator.budget import (
    check_budget,
    check_iteration_budget,
    check_time_budget,
    increment_iteration,
    increment_search_round,
    BudgetTracker,
)
from app.orchestrator.nodes.search_plan import search_plan_node
from app.orchestrator.nodes.sufficiency import sufficiency_node


class TestFastPathPromotion:
    def test_promote_no_retrieval_with_legal_keyword(self):
        assert should_promote_to_rag("이건 위법인가요?", 'NO_RETRIEVAL') is True
        assert should_promote_to_rag("청약철회 기간", 'NO_RETRIEVAL') is True
        assert should_promote_to_rag("손해배상 받을 수 있나요", 'NO_RETRIEVAL') is True

    def test_no_promote_without_legal_keyword(self):
        assert should_promote_to_rag("안녕하세요", 'NO_RETRIEVAL') is False
        assert should_promote_to_rag("날씨가 좋네요", 'NO_RETRIEVAL') is False

    def test_no_promote_for_need_rag_mode(self):
        assert should_promote_to_rag("이건 위법인가요?", 'NEED_RAG') is False

    def test_no_promote_for_clarification_mode(self):
        assert should_promote_to_rag("청약철회", 'NEED_USER_CLARIFICATION') is False


class TestRouteAfterQueryAnalysis:
    def test_no_retrieval_goes_to_generation(self):
        state = create_initial_state_v2("안녕하세요")
        state['mode'] = 'NO_RETRIEVAL'
        assert route_after_query_analysis(state) == 'generation'

    def test_need_rag_goes_to_search_plan(self):
        state = create_initial_state_v2("헬스장 환불")
        state['mode'] = 'NEED_RAG'
        assert route_after_query_analysis(state) == 'search_plan'

    def test_need_clarification_goes_to_ask(self):
        state = create_initial_state_v2("")
        state['mode'] = 'NEED_USER_CLARIFICATION'
        assert route_after_query_analysis(state) == 'ask_clarification'

    def test_fast_path_promotion(self):
        state = create_initial_state_v2("이건 위법인가요?")
        state['mode'] = 'NO_RETRIEVAL'
        assert route_after_query_analysis(state) == 'search_plan'


class TestRouteAfterSufficiency:
    def _make_state_with_report(
        self,
        relevance: float,
        missing_slots: int = 0,
        search_round: int = 0,
        rounds_budget: int = 3,
    ) -> ChatState_v2:
        state = create_initial_state_v2("테스트 쿼리")
        
        coverage = []
        for i in range(missing_slots):
            slot: SlotStatus = {
                'slot_name': f'slot_{i}',
                'status': 'missing',
                'evidence_chunk_ids': [],
                'confidence': 0.0,
            }
            coverage.append(slot)
        
        report: RetrievalReport_v2 = {
            'relevance': relevance,
            'coverage': coverage,
            'diversity': 0.5,
            'marginal_gain': 0.1,
            'total_chunks': 5,
            'sources_distribution': {'disputes': 2, 'counsels': 3},
        }
        state['retrieval_report_v2'] = report
        state['search_round'] = search_round
        
        plan: SearchPlan = {
            'retrievers': ['hybrid'],
            'top_k': 10,
            'rerank': True,
            'rounds_budget': rounds_budget,
            'time_budget_ms': 10000,
            'filters': {},
            'query': 'test',
        }
        state['search_plan'] = plan
        
        return state

    def test_high_relevance_no_missing_goes_to_generation(self):
        state = self._make_state_with_report(relevance=0.8, missing_slots=0)
        assert route_after_sufficiency(state) == 'generation'

    def test_low_relevance_after_search_asks_clarification(self):
        state = self._make_state_with_report(relevance=0.2, search_round=1)
        assert route_after_sufficiency(state) == 'ask_clarification'

    def test_medium_relevance_within_budget_continues_search(self):
        state = self._make_state_with_report(relevance=0.5, search_round=1, rounds_budget=3)
        assert route_after_sufficiency(state) == 'search_plan'

    def test_budget_exhausted_goes_to_generation(self):
        state = self._make_state_with_report(relevance=0.5, search_round=3, rounds_budget=3)
        assert route_after_sufficiency(state) == 'generation'

    def test_no_report_goes_to_generation(self):
        state = create_initial_state_v2("test")
        assert route_after_sufficiency(state) == 'generation'


class TestRouteAfterReview:
    def test_passed_ends(self):
        state = create_initial_state_v2("test")
        review: ReviewReport_v2 = {
            'passed': True,
            'issues': [],
            'required_more_evidence': False,
            'requested_slots': [],
            'violation_details': [],
        }
        state['review_report_v2'] = review
        assert route_after_review(state) == '__end__'

    def test_failed_with_retries_regenerates(self):
        state = create_initial_state_v2("test")
        state['retry_count'] = 0
        review: ReviewReport_v2 = {
            'passed': False,
            'issues': ['violation found'],
            'required_more_evidence': False,
            'requested_slots': [],
            'violation_details': [],
        }
        state['review_report_v2'] = review
        assert route_after_review(state) == 'generation'

    def test_failed_max_retries_ends(self):
        state = create_initial_state_v2("test")
        state['retry_count'] = 2
        review: ReviewReport_v2 = {
            'passed': False,
            'issues': ['violation found'],
            'required_more_evidence': False,
            'requested_slots': [],
            'violation_details': [],
        }
        state['review_report_v2'] = review
        assert route_after_review(state) == '__end__'

    def test_needs_more_evidence_retrieves(self):
        state = create_initial_state_v2("test")
        state['retry_count'] = 0
        review: ReviewReport_v2 = {
            'passed': False,
            'issues': ['insufficient evidence'],
            'required_more_evidence': True,
            'requested_slots': ['dispute_case'],
            'violation_details': [],
        }
        state['review_report_v2'] = review
        assert route_after_review(state) == 'retrieval'


class TestBudgetManagement:
    def test_check_iteration_budget_within_limit(self):
        state = create_initial_state_v2("test")
        state['current_iteration'] = 1
        state['max_iterations'] = 2
        assert check_iteration_budget(state) is True

    def test_check_iteration_budget_exceeded(self):
        state = create_initial_state_v2("test")
        state['current_iteration'] = 2
        state['max_iterations'] = 2
        assert check_iteration_budget(state) is False

    def test_check_time_budget_within_limit(self):
        state = create_initial_state_v2("test")
        state['budget_remaining_ms'] = 10000
        assert check_time_budget(state) is True

    def test_check_time_budget_exhausted(self):
        state = create_initial_state_v2("test")
        state['budget_remaining_ms'] = 0
        assert check_time_budget(state) is False

    def test_check_budget_both_ok(self):
        state = create_initial_state_v2("test")
        state['current_iteration'] = 1
        state['max_iterations'] = 2
        state['budget_remaining_ms'] = 10000
        assert check_budget(state) is True

    def test_check_budget_iteration_exceeded(self):
        state = create_initial_state_v2("test")
        state['current_iteration'] = 2
        state['max_iterations'] = 2
        state['budget_remaining_ms'] = 10000
        assert check_budget(state) is False

    def test_increment_iteration(self):
        state = create_initial_state_v2("test")
        state['current_iteration'] = 0
        result = increment_iteration(state)
        assert result['current_iteration'] == 1

    def test_increment_search_round(self):
        state = create_initial_state_v2("test")
        state['search_round'] = 0
        result = increment_search_round(state)
        assert result['search_round'] == 1


class TestBudgetTracker:
    def test_initial_state_updates(self):
        tracker = BudgetTracker(max_iterations=3, max_execution_time_ms=15000)
        updates = tracker.get_initial_state_updates()
        
        assert updates['max_iterations'] == 3
        assert updates['max_execution_time_ms'] == 15000
        assert updates['budget_remaining_ms'] == 15000
        assert updates['current_iteration'] == 0
        assert updates['search_round'] == 0
        assert updates['retry_count'] == 0

    def test_elapsed_time(self):
        tracker = BudgetTracker(max_execution_time_ms=30000)
        tracker.start()
        import time
        time.sleep(0.01)
        assert tracker.elapsed_ms() >= 10

    def test_remaining_time(self):
        tracker = BudgetTracker(max_execution_time_ms=30000)
        tracker.start()
        remaining = tracker.remaining_ms()
        assert remaining <= 30000
        assert remaining > 29000


class TestSearchPlanNode:
    def test_creates_plan_without_query_analysis(self):
        state = create_initial_state_v2("헬스장 환불 문의")
        result = search_plan_node(state)
        
        assert 'search_plan' in result
        plan = result['search_plan']
        assert plan['retrievers'] == ['hybrid']
        assert plan['top_k'] == 10
        assert plan['rerank'] is True

    def test_creates_plan_for_dispute(self):
        state = create_initial_state_v2("헬스장 환불 문의")
        analysis: QueryAnalysisResult_v2 = {
            'mode': 'NEED_RAG',
            'uncertainties': [],
            'need_evidence': True,
            'required_slots': [],
            'filters_candidate': {},
            'sql_params_candidate': {},
            'query_type': 'dispute',
            'keywords': ['헬스장', '환불'],
            'agency_hint': 'KCA',
            'rewritten_query': '헬스장 환불 분쟁조정 피해구제',
            'search_queries': ['헬스장 환불'],
        }
        state['query_analysis_v2'] = analysis
        
        result = search_plan_node(state)
        plan = result['search_plan']
        
        assert 'hybrid' in plan['retrievers']
        assert 'dispute' in plan['retrievers']
        assert plan['rerank'] is True

    def test_creates_plan_for_law(self):
        state = create_initial_state_v2("소비자보호법 조항")
        analysis: QueryAnalysisResult_v2 = {
            'mode': 'NEED_RAG',
            'uncertainties': [],
            'need_evidence': True,
            'required_slots': [],
            'filters_candidate': {},
            'sql_params_candidate': {},
            'query_type': 'law',
            'keywords': ['소비자보호법'],
            'agency_hint': None,
            'rewritten_query': '소비자보호법 조항',
            'search_queries': ['소비자보호법'],
        }
        state['query_analysis_v2'] = analysis
        
        result = search_plan_node(state)
        plan = result['search_plan']
        
        assert 'law' in plan['retrievers']

    def test_creates_plan_for_general(self):
        state = create_initial_state_v2("안녕하세요")
        analysis: QueryAnalysisResult_v2 = {
            'mode': 'NO_RETRIEVAL',
            'uncertainties': [],
            'need_evidence': False,
            'required_slots': [],
            'filters_candidate': {},
            'sql_params_candidate': {},
            'query_type': 'general',
            'keywords': [],
            'agency_hint': None,
            'rewritten_query': '안녕하세요',
            'search_queries': [],
        }
        state['query_analysis_v2'] = analysis
        
        result = search_plan_node(state)
        plan = result['search_plan']
        
        assert plan['top_k'] == 5
        assert plan['rerank'] is False


class TestSufficiencyNode:
    def test_creates_report_without_retrieval(self):
        state = create_initial_state_v2("test")
        result = sufficiency_node(state)
        
        assert 'retrieval_report_v2' in result
        report = result['retrieval_report_v2']
        assert report['relevance'] == 0.0
        assert report['total_chunks'] == 0

    def test_creates_report_with_retrieval(self):
        state = create_initial_state_v2("test")
        state['retrieval'] = {
            'agency': {'name': 'KCA'},
            'disputes': [{'chunk_id': 'd1', 'similarity': 0.8}],
            'counsels': [{'chunk_id': 'c1', 'similarity': 0.7}],
            'laws': [],
            'criteria': [],
            'max_similarity': 0.8,
            'avg_similarity': 0.75,
        }
        
        result = sufficiency_node(state)
        report = result['retrieval_report_v2']
        
        assert report['relevance'] > 0
        assert report['total_chunks'] == 2
        assert report['diversity'] == 0.5
        assert report['sources_distribution']['disputes'] == 1
        assert report['sources_distribution']['counsels'] == 1

    def test_increments_search_round(self):
        state = create_initial_state_v2("test")
        state['search_round'] = 0
        
        result = sufficiency_node(state)
        
        assert result['search_round'] == 1

    def test_calculates_marginal_gain(self):
        state = create_initial_state_v2("test")
        state['retrieval'] = {
            'agency': {},
            'disputes': [{'chunk_id': 'd1', 'similarity': 0.9}],
            'counsels': [],
            'laws': [],
            'criteria': [],
            'max_similarity': 0.9,
            'avg_similarity': 0.9,
        }
        prev_report: RetrievalReport_v2 = {
            'relevance': 0.5,
            'coverage': [],
            'diversity': 0.25,
            'marginal_gain': 0.5,
            'total_chunks': 1,
            'sources_distribution': {},
        }
        state['retrieval_report_history'] = [prev_report]
        
        result = sufficiency_node(state)
        report = result['retrieval_report_v2']
        
        assert report['marginal_gain'] > 0


class TestV2GraphCreation:
    def test_v2_graph_creates_successfully(self):
        from app.orchestrator.graph import create_v2_chat_graph
        graph = create_v2_chat_graph()
        assert graph is not None

    def test_v2_graph_has_expected_nodes(self):
        from app.orchestrator.graph import create_v2_chat_graph
        graph = create_v2_chat_graph()
        
        nodes = list(graph.nodes.keys())
        expected_nodes = [
            'query_analysis',
            'search_plan',
            'retrieval',
            'sufficiency',
            'generation',
            'review',
            'ask_clarification',
        ]
        
        for node in expected_nodes:
            assert node in nodes, f"Missing node: {node}"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-p', 'no:asyncio'])
