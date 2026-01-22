import os
import logging
from typing import Any, TypeVar, get_type_hints
from functools import lru_cache

from pydantic import TypeAdapter, ValidationError

from .state import (
    QueryAnalysisResult_v2,
    SearchPlan,
    RetrievalReport_v2,
    GenerationOutput,
    ReviewReport_v2,
    QueryAnalysisResult,
    RetrievalResult,
    ReviewResult,
)

logger = logging.getLogger(__name__)

T = TypeVar('T')

STRICT_MODE = os.getenv('STRICT_SCHEMA_VALIDATION', 'false').lower() == 'true'


@lru_cache(maxsize=32)
def _get_adapter(schema_type: type) -> TypeAdapter:
    return TypeAdapter(schema_type)


class SchemaValidationError(Exception):
    def __init__(self, schema_name: str, errors: list, data: Any):
        self.schema_name = schema_name
        self.errors = errors
        self.data = data
        super().__init__(f"{schema_name} 스키마 검증 실패: {errors}")


def validate_schema(data: Any, schema_type: type[T], schema_name: str) -> tuple[bool, list[str]]:
    adapter = _get_adapter(schema_type)
    try:
        adapter.validate_python(data)
        return True, []
    except ValidationError as e:
        errors = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
        logger.warning(f"[SchemaValidation] {schema_name} 검증 실패: {errors}")
        
        if STRICT_MODE:
            raise SchemaValidationError(schema_name, errors, data)
        
        return False, errors


def validate_query_analysis_result_v2(data: Any) -> tuple[bool, list[str]]:
    return validate_schema(data, QueryAnalysisResult_v2, 'QueryAnalysisResult_v2')


def validate_search_plan(data: Any) -> tuple[bool, list[str]]:
    return validate_schema(data, SearchPlan, 'SearchPlan')


def validate_retrieval_report_v2(data: Any) -> tuple[bool, list[str]]:
    return validate_schema(data, RetrievalReport_v2, 'RetrievalReport_v2')


def validate_generation_output(data: Any) -> tuple[bool, list[str]]:
    return validate_schema(data, GenerationOutput, 'GenerationOutput')


def validate_review_report_v2(data: Any) -> tuple[bool, list[str]]:
    return validate_schema(data, ReviewReport_v2, 'ReviewReport_v2')


def validate_query_analysis_result(data: Any) -> tuple[bool, list[str]]:
    return validate_schema(data, QueryAnalysisResult, 'QueryAnalysisResult')


def validate_retrieval_result(data: Any) -> tuple[bool, list[str]]:
    return validate_schema(data, RetrievalResult, 'RetrievalResult')


def validate_review_result(data: Any) -> tuple[bool, list[str]]:
    return validate_schema(data, ReviewResult, 'ReviewResult')


class SchemaValidator:
    def __init__(self, strict: bool | None = None):
        self.strict = strict if strict is not None else STRICT_MODE
    
    def validate(self, data: Any, schema_type: type[T], schema_name: str) -> tuple[bool, list[str]]:
        adapter = _get_adapter(schema_type)
        try:
            adapter.validate_python(data)
            return True, []
        except ValidationError as e:
            errors = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
            logger.warning(f"[SchemaValidation] {schema_name} 검증 실패: {errors}")
            
            if self.strict:
                raise SchemaValidationError(schema_name, errors, data)
            
            return False, errors
    
    def validate_all_agent_outputs(
        self,
        query_analysis: Any = None,
        search_plan: Any = None,
        retrieval_report: Any = None,
        generation_output: Any = None,
        review_report: Any = None,
    ) -> dict[str, tuple[bool, list[str]]]:
        results = {}
        
        if query_analysis is not None:
            results['query_analysis_v2'] = self.validate(
                query_analysis, QueryAnalysisResult_v2, 'QueryAnalysisResult_v2'
            )
        
        if search_plan is not None:
            results['search_plan'] = self.validate(
                search_plan, SearchPlan, 'SearchPlan'
            )
        
        if retrieval_report is not None:
            results['retrieval_report_v2'] = self.validate(
                retrieval_report, RetrievalReport_v2, 'RetrievalReport_v2'
            )
        
        if generation_output is not None:
            results['generation_output'] = self.validate(
                generation_output, GenerationOutput, 'GenerationOutput'
            )
        
        if review_report is not None:
            results['review_report_v2'] = self.validate(
                review_report, ReviewReport_v2, 'ReviewReport_v2'
            )
        
        return results


def get_validator(strict: bool | None = None) -> SchemaValidator:
    return SchemaValidator(strict=strict)


__all__ = [
    'SchemaValidationError',
    'SchemaValidator',
    'validate_schema',
    'validate_query_analysis_result_v2',
    'validate_search_plan',
    'validate_retrieval_report_v2',
    'validate_generation_output',
    'validate_review_report_v2',
    'validate_query_analysis_result',
    'validate_retrieval_result',
    'validate_review_result',
    'get_validator',
    'STRICT_MODE',
]
