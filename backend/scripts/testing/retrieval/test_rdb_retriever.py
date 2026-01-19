import pytest
from unittest.mock import patch, MagicMock

from app.orchestrator.state import (
    ChatState_v2,
    create_initial_state_v2,
    QueryAnalysisResult_v2,
    SqlParamsCandidate,
)
from app.orchestrator.nodes.search_plan import (
    search_plan_node,
    _select_retrievers,
    RETRIEVER_TYPE_RDB as SEARCH_PLAN_RDB,
    RETRIEVER_TYPE_HYBRID,
)
from app.agents.retrieval.agent import (
    retrieval_node_v2,
    _execute_retrieval_by_type,
    RETRIEVER_TYPE_RDB,
)
from app.agents.retrieval.tools.rdb_retriever import (
    CriteriaRDBRetriever,
    LawRDBRetriever,
    RDBRetriever,
    CriteriaRDBResult,
    LawRDBResult,
)


class TestSqlParamsCandidate:
    def test_schema_has_criteria_fields(self):
        params: SqlParamsCandidate = {
            'category': '용역(서비스)',
            'industry': '체육시설업',
            'item_group': '헬스장',
            'item': '헬스회원권',
            'dispute_type': '해지/환불',
            'enable_rdb_query': True,
            'preferred_tables': ['criteria_units'],
        }
        
        assert params['category'] == '용역(서비스)'
        assert params['item_group'] == '헬스장'
        assert params['enable_rdb_query'] is True

    def test_schema_has_law_fields(self):
        params: SqlParamsCandidate = {
            'law_name': '소비자기본법',
            'article_no': '17',
            'paragraph_no': '1',
            'enable_rdb_query': True,
            'preferred_tables': ['law_units'],
        }
        
        assert params['law_name'] == '소비자기본법'
        assert params['article_no'] == '17'


class TestSelectRetrieversWithRDB:
    def test_rdb_added_when_enabled(self):
        sql_params = {'enable_rdb_query': True}
        retrievers = _select_retrievers('dispute', sql_params=sql_params)
        
        assert SEARCH_PLAN_RDB in retrievers
        assert retrievers[0] == SEARCH_PLAN_RDB

    def test_rdb_not_added_when_disabled(self):
        sql_params = {'enable_rdb_query': False}
        retrievers = _select_retrievers('dispute', sql_params=sql_params)
        
        assert SEARCH_PLAN_RDB not in retrievers

    def test_rdb_not_added_when_no_sql_params(self):
        retrievers = _select_retrievers('dispute')
        
        assert SEARCH_PLAN_RDB not in retrievers


class TestSearchPlanWithRDB:
    def test_rdb_retriever_selected_for_criteria_query(self):
        state = create_initial_state_v2("헬스장 환불 기준")
        analysis: QueryAnalysisResult_v2 = {
            'mode': 'NEED_RAG',
            'uncertainties': [],
            'need_evidence': True,
            'required_slots': [],
            'filters_candidate': {},
            'sql_params_candidate': {
                'item_group': '헬스장',
                'dispute_type': '환불',
                'enable_rdb_query': True,
                'preferred_tables': ['criteria_units'],
            },
            'query_type': 'criteria',
            'keywords': ['헬스장', '환불', '기준'],
            'agency_hint': 'KCA',
            'rewritten_query': '헬스장 환불 분쟁조정기준',
            'search_queries': [],
        }
        state['query_analysis_v2'] = analysis
        
        result = search_plan_node(state)
        plan = result['search_plan']
        
        assert SEARCH_PLAN_RDB in plan['retrievers']
        assert plan['filters'].get('item_group') == '헬스장'
        assert plan['filters'].get('enable_rdb_query') is True

    def test_combined_filters_include_sql_params(self):
        state = create_initial_state_v2("소비자기본법 17조")
        analysis: QueryAnalysisResult_v2 = {
            'mode': 'NEED_RAG',
            'uncertainties': [],
            'need_evidence': True,
            'required_slots': [],
            'filters_candidate': {'doc_type': 'law'},
            'sql_params_candidate': {
                'law_name': '소비자기본법',
                'article_no': '17',
                'enable_rdb_query': True,
                'preferred_tables': ['law_units'],
            },
            'query_type': 'law',
            'keywords': ['소비자기본법', '17조'],
            'agency_hint': None,
            'rewritten_query': '소비자기본법 제17조',
            'search_queries': [],
        }
        state['query_analysis_v2'] = analysis
        
        result = search_plan_node(state)
        plan = result['search_plan']
        
        assert plan['filters'].get('doc_type') == 'law'
        assert plan['filters'].get('law_name') == '소비자기본법'
        assert plan['filters'].get('article_no') == '17'


class TestCriteriaRDBRetriever:
    def test_search_builds_correct_query(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []
        
        retriever = CriteriaRDBRetriever({'host': 'localhost'})
        retriever.conn = mock_conn
        
        retriever.search(
            category='용역(서비스)',
            industry='체육시설업',
            item_group='헬스장',
            top_k=5,
        )
        
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        query = call_args[0][0]
        params = call_args[0][1]
        
        assert 'cu.category ILIKE' in query
        assert 'cu.industry ILIKE' in query
        assert 'cu.item_group ILIKE' in query
        assert '%용역(서비스)%' in params
        assert '%체육시설업%' in params
        assert '%헬스장%' in params

    def test_search_dispute_resolution_targets_table2_table3(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []
        
        retriever = CriteriaRDBRetriever({'host': 'localhost'})
        retriever.conn = mock_conn
        
        retriever.search_dispute_resolution(
            item_keyword='헬스장',
            dispute_type='해지',
            top_k=5,
        )
        
        call_args = mock_cursor.execute.call_args
        query = call_args[0][0]
        
        assert "cu.source_id IN ('table2', 'table3')" in query


class TestLawRDBRetriever:
    def test_search_normalizes_article_number(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []
        
        retriever = LawRDBRetriever({'host': 'localhost'})
        retriever.conn = mock_conn
        
        retriever.search(
            law_name='전자상거래법',
            article_no='제17조',
            top_k=5,
        )
        
        call_args = mock_cursor.execute.call_args
        params = call_args[0][1]
        
        assert '17' in params

    def test_get_article_with_children_orders_by_level(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchall.return_value = []
        
        retriever = LawRDBRetriever({'host': 'localhost'})
        retriever.conn = mock_conn
        
        retriever.get_article_with_children(
            law_id='law_123',
            article_no='제17조',
        )
        
        call_args = mock_cursor.execute.call_args
        query = call_args[0][0]
        
        assert "CASE lu.level" in query
        assert "'article' THEN 1" in query
        assert "'paragraph' THEN 2" in query


class TestRDBRetriever:
    def test_search_from_params_routes_to_criteria(self):
        mock_criteria = MagicMock()
        mock_criteria.search.return_value = []
        mock_law = MagicMock()
        mock_law.search.return_value = []
        
        retriever = RDBRetriever({'host': 'localhost'})
        retriever.criteria_retriever = mock_criteria
        retriever.law_retriever = mock_law
        
        sql_params = {
            'category': '용역(서비스)',
            'item_group': '헬스장',
            'preferred_tables': ['criteria_units'],
        }
        
        retriever.search_from_params(sql_params, top_k=5)
        
        mock_criteria.search.assert_called_once()
        mock_law.search.assert_not_called()

    def test_search_from_params_routes_to_law(self):
        mock_criteria = MagicMock()
        mock_criteria.search.return_value = []
        mock_law = MagicMock()
        mock_law.search.return_value = []
        
        retriever = RDBRetriever({'host': 'localhost'})
        retriever.criteria_retriever = mock_criteria
        retriever.law_retriever = mock_law
        
        sql_params = {
            'law_name': '소비자기본법',
            'article_no': '17',
            'preferred_tables': ['law_units'],
        }
        
        retriever.search_from_params(sql_params, top_k=5)
        
        mock_law.search.assert_called_once()


class TestExecuteRetrievalByTypeRDB:
    def test_rdb_type_uses_rdb_retriever(self):
        with patch('app.agents.retrieval.tools.rdb_retriever.RDBRetriever') as MockRDB:
            mock_retriever = MagicMock()
            mock_retriever.search_from_params.return_value = {
                'criteria': [],
                'laws': [],
            }
            MockRDB.return_value = mock_retriever
            
            _execute_retrieval_by_type(
                retriever_type=RETRIEVER_TYPE_RDB,
                query='헬스장 환불',
                top_k=5,
                db_config={'host': 'localhost'},
                embed_api_url='http://localhost:8001/embed',
                filters={'item_group': '헬스장', 'enable_rdb_query': True},
            )
            
            MockRDB.assert_called_once()
            mock_retriever.connect.assert_called_once()
            mock_retriever.search_from_params.assert_called_once()
            mock_retriever.close.assert_called_once()

    def test_rdb_type_converts_results_to_standard_format(self):
        with patch('app.agents.retrieval.tools.rdb_retriever.RDBRetriever') as MockRDB:
            mock_retriever = MagicMock()
            mock_crit = CriteriaRDBResult(
                unit_id='crit_1',
                source_id='table2',
                source_label='별표2',
                category='용역',
                industry='체육시설업',
                item_group='헬스장',
                item='헬스회원권',
                dispute_type='해지',
                unit_text='해지 시 위약금...',
                doc={},
            )
            mock_law = LawRDBResult(
                doc_id='law_1',
                law_id='law_abc',
                law_name='소비자기본법',
                level='article',
                article_no='17',
                paragraph_no=None,
                item_no=None,
                subitem_no=None,
                path='제17조',
                text='소비자는...',
            )
            mock_retriever.search_from_params.return_value = {
                'criteria': [mock_crit],
                'laws': [mock_law],
            }
            MockRDB.return_value = mock_retriever
            
            result = _execute_retrieval_by_type(
                retriever_type=RETRIEVER_TYPE_RDB,
                query='test',
                top_k=5,
                db_config={'host': 'localhost'},
                embed_api_url='http://localhost:8001/embed',
                filters={},
            )
            
            assert len(result['criteria']) == 1
            assert result['criteria'][0]['unit_id'] == 'crit_1'
            assert result['criteria'][0]['similarity'] == 1.0
            
            assert len(result['laws']) == 1
            assert result['laws'][0]['unit_id'] == 'law_1'
            assert result['laws'][0]['law_name'] == '소비자기본법'


class TestRetrievalNodeV2WithRDB:
    def test_uses_rdb_when_in_search_plan(self):
        state = create_initial_state_v2("헬스장 환불 기준")
        state['mode'] = 'NEED_RAG'
        state['search_plan'] = {
            'retrievers': [RETRIEVER_TYPE_RDB, RETRIEVER_TYPE_HYBRID],
            'top_k': 5,
            'rerank': True,
            'rounds_budget': 3,
            'time_budget_ms': 10000,
            'filters': {
                'item_group': '헬스장',
                'enable_rdb_query': True,
            },
            'query': '헬스장 환불 분쟁조정기준',
        }
        
        with patch('app.agents.retrieval.agent._execute_retrieval_by_type') as mock_exec:
            mock_exec.return_value = {
                'agency': {},
                'disputes': [],
                'counsels': [],
                'laws': [],
                'criteria': [],
            }
            
            retrieval_node_v2(state)
            
            assert mock_exec.call_count == 2
            
            first_call = mock_exec.call_args_list[0]
            assert first_call[1]['retriever_type'] == RETRIEVER_TYPE_RDB


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-p', 'no:asyncio'])
