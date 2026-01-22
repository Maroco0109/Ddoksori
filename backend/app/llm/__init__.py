"""
똑소리 프로젝트 - LLM 클라이언트 모듈
작성일: 2026-01-17
S2-8: EXAONE 3.5 2.4B 통합
S2-10: LLM 기반 쿼리 재작성 (Phase 3)

LLM 클라이언트 및 관련 유틸리티 제공.
"""

from .exaone_client import ExaoneLLMClient, LLMUnavailableError
from .query_cache import QueryCache, COMMON_REWRITES
from .query_rewriter import QueryRewriter, get_query_rewriter, LEGAL_TERMS
from .tool_calling_client import ToolCallingClient, ToolCallingUnavailableError

__all__ = [
    # S2-8: EXAONE Client
    'ExaoneLLMClient',
    'LLMUnavailableError',
    # S2-10: Query Rewriter
    'QueryRewriter',
    'get_query_rewriter',
    'QueryCache',
    'COMMON_REWRITES',
    'LEGAL_TERMS',
    # S3-PR3: Tool Calling Client
    'ToolCallingClient',
    'ToolCallingUnavailableError',
]
