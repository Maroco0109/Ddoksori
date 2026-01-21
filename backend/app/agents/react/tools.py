"""
똑소리 프로젝트 - LangChain @tool 도구 정의
작성일: 2026-01-21
S3-PR3: @tool 하이브리드 도입

LangChain의 @tool 데코레이터를 사용하여 검색 도구를 정의합니다.
이 도구들은 HybridToolExecutor에서 LLM 기반 도구 선택 시 사용됩니다.

주요 도구:
- search_all: 전체 섹션 검색
- search_criteria: 분쟁해결기준 검색
- search_laws: 법령 검색
- finish_search: 검색 종료

보안 고려사항:
- AVAILABLE_TOOLS만 허용 (allowlist)
- 도구 실행 시 DB 접근 범위 제한
- 사용자 입력은 sanitize 후 사용
"""

import logging
from typing import Dict, Any, List

from langchain_core.tools import tool

from .actions.base import (
    get_db_config,
    get_embed_api_url,
    merge_retrieval,
    build_sources_from_retrieval,
)

logger = logging.getLogger(__name__)


@tool
def search_all(query: str) -> str:
    """
    모든 데이터베이스에서 종합 검색합니다.
    분쟁조정사례, 상담사례, 법령, 기준을 모두 검색합니다.
    
    Args:
        query: 검색할 쿼리 문자열
    
    Returns:
        검색 결과 요약 텍스트
    """
    try:
        from ..retrieval.tools.specialized_retrievers import StructuredRetriever
        
        retriever = StructuredRetriever(get_db_config(), get_embed_api_url())
        retriever.connect()
        
        try:
            raw_result = retriever.search_all_sections(
                query=query,
                dispute_k=3,
                counsel_k=3,
                law_k=3,
                criteria_k=3,
            )
        finally:
            retriever.close()
        
        n_disputes = len(raw_result.get('disputes', []))
        n_counsels = len(raw_result.get('counsels', []))
        n_laws = len(raw_result.get('laws', []))
        n_criteria = len(raw_result.get('criteria', []))
        
        observation = (
            f"전체 검색 완료: 분쟁사례 {n_disputes}건, "
            f"상담사례 {n_counsels}건, 법령 {n_laws}건, 기준 {n_criteria}건"
        )
        
        logger.info(f"[tools.search_all] {observation}")
        return observation
        
    except Exception as e:
        logger.error(f"[tools.search_all] Error: {e}")
        return f"검색 실패: {str(e)}"


@tool
def search_criteria(query: str) -> str:
    """
    분쟁해결기준 데이터베이스에서 검색합니다.
    소비자분쟁해결기준, 품목별 기준, 기간표를 검색합니다.
    
    Args:
        query: 검색할 쿼리 문자열
    
    Returns:
        기준 검색 결과 요약 텍스트
    """
    try:
        from ..retrieval.tools.specialized_retrievers import StructuredRetriever
        
        retriever = StructuredRetriever(get_db_config(), get_embed_api_url())
        retriever.connect()
        
        try:
            result = retriever.search_criteria(query=query, top_k=5)
        finally:
            retriever.close()
        
        observation = f"분쟁해결기준 {len(result)}건 검색 완료"
        
        logger.info(f"[tools.search_criteria] {observation}")
        return observation
        
    except Exception as e:
        logger.error(f"[tools.search_criteria] Error: {e}")
        return f"기준 검색 실패: {str(e)}"


@tool
def search_laws(query: str) -> str:
    """
    법령 데이터베이스에서 검색합니다.
    소비자기본법, 전자상거래법 등 관련 법령을 검색합니다.
    
    Args:
        query: 검색할 쿼리 문자열
    
    Returns:
        법령 검색 결과 요약 텍스트
    """
    try:
        from ..retrieval.tools.specialized_retrievers import StructuredRetriever
        
        retriever = StructuredRetriever(get_db_config(), get_embed_api_url())
        retriever.connect()
        
        try:
            result = retriever.search_laws(query=query, top_k=5)
        finally:
            retriever.close()
        
        observation = f"법령 {len(result)}건 검색 완료"
        
        logger.info(f"[tools.search_laws] {observation}")
        return observation
        
    except Exception as e:
        logger.error(f"[tools.search_laws] Error: {e}")
        return f"법령 검색 실패: {str(e)}"


@tool
def finish_search() -> str:
    """
    검색을 종료하고 답변 생성 단계로 진행합니다.
    충분한 정보가 수집되었을 때 사용합니다.
    
    Returns:
        종료 확인 메시지
    """
    logger.info("[tools.finish_search] Search completed")
    return "검색 완료. 답변 생성 단계로 진행합니다."


# ============================================================================
# Tool Registry (Allowlist)
# ============================================================================

# 허용된 도구 목록 (LLM에 바인딩될 도구들)
AVAILABLE_TOOLS = [search_all, search_criteria, search_laws, finish_search]

# 도구 이름으로 조회할 수 있는 맵
TOOL_NAME_MAP = {t.name: t for t in AVAILABLE_TOOLS}


def get_tool_by_name(name: str):
    """
    이름으로 도구 조회
    
    Args:
        name: 도구 이름
    
    Returns:
        도구 함수 또는 None
    """
    return TOOL_NAME_MAP.get(name)


def is_allowed_tool(name: str) -> bool:
    """
    도구가 허용 목록에 있는지 확인
    
    Args:
        name: 도구 이름
    
    Returns:
        허용 여부
    """
    return name in TOOL_NAME_MAP


def get_tool_descriptions() -> List[Dict[str, str]]:
    """
    모든 도구의 설명 목록 반환
    
    Returns:
        [{name: str, description: str}, ...]
    """
    return [
        {"name": t.name, "description": t.description}
        for t in AVAILABLE_TOOLS
    ]
