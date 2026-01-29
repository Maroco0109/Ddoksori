"""
LLM 기반 쿼리 확장 모듈 (v2)

작성일: 2026-01-28

[역할 및 책임]
gpt-4o-mini를 사용하여 사용자 쿼리를 다중 검색 쿼리로 확장합니다.
- 동의어 확장: '환불' → ['청약철회', '계약해제', '반품']
- 개념 확장: '헬스장' → ['체육시설', '피트니스센터', '스포츠센터']
- 법률 용어 매핑: 일상어 → 법률 전문 용어
"""

import asyncio
import logging
from typing import List, Optional

from openai import AsyncOpenAI

from ...common.config import get_config

logger = logging.getLogger(__name__)

# LLM 쿼리 확장 프롬프트
QUERY_EXPANSION_SYSTEM_PROMPT = """당신은 소비자 분쟁 해결 시스템의 검색 쿼리 확장 전문가입니다.

사용자의 질문을 분석하여 관련 법령, 분쟁해결기준, 사례를 효과적으로 검색할 수 있도록
다양한 검색 쿼리로 확장해주세요.

확장 규칙:
1. 동의어 확장: 일상 용어를 법률/행정 용어로 변환
   - 환불 → 청약철회, 계약해제, 반환, 환급
   - 수리 → 수선, 하자보수, A/S
   - 교환 → 대체급부, 대품
   - 취소 → 계약해지, 철회

2. 품목 확장: 품목을 상위/유사 개념으로 확장
   - 헬스장 → 체육시설, 피트니스센터, 스포츠센터
   - 핸드폰 → 휴대전화, 이동통신단말기, 스마트폰
   - 자동차 → 승용차, 차량, 자동차

3. 상황 확장: 분쟁 상황을 다양한 표현으로 확장
   - 불량 → 하자, 결함, 고장
   - 피해 → 손해, 손실

주의사항:
- 최대 5개의 검색 쿼리를 생성하세요
- 각 쿼리는 30자 이내로 간결하게 작성하세요
- 원본 쿼리의 의미를 벗어나지 마세요
- JSON 배열 형식으로만 응답하세요 (예: ["쿼리1", "쿼리2", ...])"""

QUERY_EXPANSION_USER_PROMPT = """다음 사용자 질문을 확장해주세요:

원본 질문: {query}
추출된 키워드: {keywords}

JSON 배열 형식으로 확장된 검색 쿼리 목록을 반환하세요:"""


async def expand_query_with_llm(
    query: str,
    keywords: List[str],
    max_queries: int = 5,
    timeout: float = 3.0,
) -> Optional[List[str]]:
    """
    LLM을 사용하여 쿼리를 다중 검색 쿼리로 확장합니다.

    Args:
        query: 원본 사용자 쿼리
        keywords: 추출된 키워드 목록
        max_queries: 최대 생성 쿼리 수
        timeout: LLM 호출 타임아웃 (초)

    Returns:
        확장된 쿼리 목록 또는 None (실패 시)
    """
    config = get_config()

    try:
        client = AsyncOpenAI(api_key=config.openai_api_key)

        user_prompt = QUERY_EXPANSION_USER_PROMPT.format(
            query=query,
            keywords=", ".join(keywords) if keywords else "없음"
        )

        response = await asyncio.wait_for(
            client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": QUERY_EXPANSION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=200,
            ),
            timeout=timeout
        )

        content = response.choices[0].message.content.strip()

        # JSON 파싱
        import json
        expanded_queries = json.loads(content)

        if isinstance(expanded_queries, list):
            # 최대 개수 제한 및 원본 쿼리 포함
            result = [query]  # 원본 쿼리를 첫 번째로
            for eq in expanded_queries:
                if isinstance(eq, str) and eq not in result:
                    result.append(eq)
                if len(result) >= max_queries:
                    break

            logger.info(f"[LLM Expander] Expanded '{query[:30]}...' to {len(result)} queries")
            return result

        logger.warning(f"[LLM Expander] Invalid response format: {content}")
        return None

    except asyncio.TimeoutError:
        logger.warning(f"[LLM Expander] Timeout after {timeout}s for query: {query[:30]}...")
        return None

    except Exception as e:
        logger.warning(f"[LLM Expander] Error: {e}")
        return None


def expand_query_with_llm_sync(
    query: str,
    keywords: List[str],
    max_queries: int = 5,
    timeout: float = 3.0,
) -> Optional[List[str]]:
    """
    LLM 쿼리 확장의 동기 버전.

    기존 동기 코드와의 호환성을 위해 제공됩니다.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 이미 이벤트 루프가 실행 중인 경우 (FastAPI 등)
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    expand_query_with_llm(query, keywords, max_queries, timeout)
                )
                return future.result(timeout=timeout + 1)
        else:
            return loop.run_until_complete(
                expand_query_with_llm(query, keywords, max_queries, timeout)
            )
    except Exception as e:
        logger.warning(f"[LLM Expander Sync] Error: {e}")
        return None


__all__ = [
    "expand_query_with_llm",
    "expand_query_with_llm_sync",
    "QUERY_EXPANSION_SYSTEM_PROMPT",
    "QUERY_EXPANSION_USER_PROMPT",
]
