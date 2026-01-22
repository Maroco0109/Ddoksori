import os
import pytest
from typing import Any

os.environ.setdefault('STRICT_SCHEMA_VALIDATION', 'false')

from app.orchestrator.state import (
    QueryAnalysisResult_v2,
    SearchPlan,
    RetrievalReport_v2,
    GenerationOutput,
    ReviewReport_v2,
    SlotStatus,
    ClaimEvidenceMapping,
)
from app.orchestrator.validators import (
    validate_query_analysis_result_v2,
    validate_search_plan,
    validate_retrieval_report_v2,
    validate_generation_output,
    validate_review_report_v2,
    SchemaValidator,
    SchemaValidationError,
)


class TestQueryAnalysisResultV2:
    def test_valid_need_rag(self):
        data: QueryAnalysisResult_v2 = {
            'mode': 'NEED_RAG',
            'draft': None,
            'uncertainties': ['구매 시점 불명확'],
            'need_evidence': True,
            'required_slots': ['purchase_item'],
            'filters_candidate': {'doc_type': ['dispute']},
            'sql_params_candidate': {},
            'query_type': 'dispute',
            'keywords': ['노트북', '환불'],
            'agency_hint': 'KCA',
            'rewritten_query': '노트북 환불 분쟁',
            'search_queries': ['노트북 환불'],
        }
        is_valid, errors = validate_query_analysis_result_v2(data)
        assert is_valid
        assert errors == []

    def test_valid_no_retrieval(self):
        data: QueryAnalysisResult_v2 = {
            'mode': 'NO_RETRIEVAL',
            'draft': '안녕하세요!',
            'uncertainties': [],
            'need_evidence': False,
            'required_slots': [],
            'query_type': 'general',
            'keywords': [],
        }
        is_valid, errors = validate_query_analysis_result_v2(data)
        assert is_valid

    def test_valid_need_user_clarification(self):
        data: QueryAnalysisResult_v2 = {
            'mode': 'NEED_USER_CLARIFICATION',
            'required_slots': ['purchase_item', 'dispute_details'],
            'query_type': 'dispute',
        }
        is_valid, errors = validate_query_analysis_result_v2(data)
        assert is_valid

    def test_invalid_mode(self):
        data = {'mode': 'INVALID_MODE', 'query_type': 'dispute'}
        is_valid, errors = validate_query_analysis_result_v2(data)
        assert not is_valid
        assert len(errors) > 0

    def test_empty_data(self):
        data = {}
        is_valid, errors = validate_query_analysis_result_v2(data)
        assert is_valid


class TestSearchPlan:
    def test_valid_hybrid_search(self):
        data: SearchPlan = {
            'retrievers': ['hybrid'],
            'top_k': 10,
            'rerank': True,
            'rounds_budget': 2,
            'time_budget_ms': 5000,
            'filters': {'doc_type': ['dispute', 'counsel']},
            'query': '노트북 불량 환불',
        }
        is_valid, errors = validate_search_plan(data)
        assert is_valid
        assert errors == []

    def test_valid_minimal(self):
        data: SearchPlan = {
            'retrievers': ['dense'],
            'top_k': 5,
            'query': '테스트 쿼리',
        }
        is_valid, errors = validate_search_plan(data)
        assert is_valid

    def test_coerced_top_k_type(self):
        data = {'retrievers': ['hybrid'], 'top_k': '10', 'query': 'test'}
        is_valid, errors = validate_search_plan(data)
        assert is_valid


class TestRetrievalReportV2:
    def test_valid_with_coverage(self):
        data: RetrievalReport_v2 = {
            'relevance': 0.82,
            'coverage': [
                {
                    'slot_name': 'purchase_item',
                    'status': 'filled',
                    'evidence_chunk_ids': ['chunk_001'],
                    'confidence': 0.95,
                }
            ],
            'diversity': 0.75,
            'marginal_gain': 0.15,
            'total_chunks': 8,
            'sources_distribution': {'dispute': 3, 'counsel': 3},
        }
        is_valid, errors = validate_retrieval_report_v2(data)
        assert is_valid
        assert errors == []

    def test_valid_minimal(self):
        data: RetrievalReport_v2 = {
            'relevance': 0.5,
            'coverage': [],
            'total_chunks': 0,
        }
        is_valid, errors = validate_retrieval_report_v2(data)
        assert is_valid

    def test_invalid_slot_status(self):
        data = {
            'relevance': 0.5,
            'coverage': [
                {
                    'slot_name': 'test',
                    'status': 'invalid_status',
                    'evidence_chunk_ids': [],
                    'confidence': 0.5,
                }
            ],
        }
        is_valid, errors = validate_retrieval_report_v2(data)
        assert not is_valid


class TestGenerationOutput:
    def test_valid_with_claims(self):
        data: GenerationOutput = {
            'final_answer': '## 답변\n내용입니다.',
            'claim_evidence_map': [
                {
                    'claim': '환불이 가능합니다',
                    'evidence_chunk_ids': ['chunk_001'],
                    'evidence_texts': ['환불 규정에 따르면...'],
                    'grounded': True,
                }
            ],
            'assumptions': ['14일 이내 구매로 가정'],
            'citations': [{'index': 1, 'source_type': 'dispute'}],
        }
        is_valid, errors = validate_generation_output(data)
        assert is_valid
        assert errors == []

    def test_valid_minimal(self):
        data: GenerationOutput = {
            'final_answer': '답변입니다.',
        }
        is_valid, errors = validate_generation_output(data)
        assert is_valid


class TestReviewReportV2:
    def test_valid_passed(self):
        data: ReviewReport_v2 = {
            'passed': True,
            'issues': [],
            'required_more_evidence': False,
            'requested_slots': [],
            'violation_details': [],
        }
        is_valid, errors = validate_review_report_v2(data)
        assert is_valid
        assert errors == []

    def test_valid_failed_with_violations(self):
        data: ReviewReport_v2 = {
            'passed': False,
            'issues': ['절대적 표현 사용'],
            'required_more_evidence': False,
            'requested_slots': [],
            'violation_details': [
                {
                    'rule_id': 'R001',
                    'severity': 'HIGH',
                    'location': 'paragraph 1',
                }
            ],
        }
        is_valid, errors = validate_review_report_v2(data)
        assert is_valid

    def test_valid_needs_more_evidence(self):
        data: ReviewReport_v2 = {
            'passed': False,
            'issues': ['근거 부족'],
            'required_more_evidence': True,
            'requested_slots': ['law_article'],
        }
        is_valid, errors = validate_review_report_v2(data)
        assert is_valid


class TestSchemaValidator:
    def test_non_strict_mode(self):
        validator = SchemaValidator(strict=False)
        invalid_data = {'mode': 'INVALID'}
        is_valid, errors = validator.validate(
            invalid_data, QueryAnalysisResult_v2, 'QueryAnalysisResult_v2'
        )
        assert not is_valid
        assert len(errors) > 0

    def test_strict_mode_raises(self):
        validator = SchemaValidator(strict=True)
        invalid_data = {'mode': 'INVALID'}
        with pytest.raises(SchemaValidationError) as exc_info:
            validator.validate(
                invalid_data, QueryAnalysisResult_v2, 'QueryAnalysisResult_v2'
            )
        assert 'QueryAnalysisResult_v2' in str(exc_info.value)

    def test_validate_all_agent_outputs(self):
        validator = SchemaValidator(strict=False)
        results = validator.validate_all_agent_outputs(
            query_analysis={'mode': 'NEED_RAG', 'query_type': 'dispute'},
            search_plan={'retrievers': ['hybrid'], 'top_k': 10, 'query': 'test'},
            retrieval_report={'relevance': 0.8, 'coverage': [], 'total_chunks': 5},
            generation_output={'final_answer': '답변'},
            review_report={'passed': True, 'issues': []},
        )
        
        assert all(r[0] for r in results.values())


class TestProductionValidation:
    def test_env_variable_strict_mode(self):
        original = os.environ.get('STRICT_SCHEMA_VALIDATION')
        try:
            os.environ['STRICT_SCHEMA_VALIDATION'] = 'true'
            
            from importlib import reload
            import app.orchestrator.validators as validators_module
            reload(validators_module)
            
            assert validators_module.STRICT_MODE is True
        finally:
            if original is None:
                os.environ.pop('STRICT_SCHEMA_VALIDATION', None)
            else:
                os.environ['STRICT_SCHEMA_VALIDATION'] = original
