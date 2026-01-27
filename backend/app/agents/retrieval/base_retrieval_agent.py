"""
BaseRetrievalAgent - Retrieval Agent 공통 베이스 클래스

4개의 Retrieval Agent(Law, Criteria, Case, Counsel)가 공유하는 공통 로직을 정의합니다.
LLM: EXAONE-4.0-1.2B (쿼리 재작성), Fallback: gpt-4.1-nano

각 에이전트는 독립된 EXAONE vLLM 인스턴스를 사용할 수 있습니다.
환경변수 설정:
    - RETRIEVAL_LLM_LAW_URL: Law Agent용 EXAONE URL
    - RETRIEVAL_LLM_CRITERIA_URL: Criteria Agent용 EXAONE URL
    - RETRIEVAL_LLM_CASE_URL: Case Agent용 EXAONE URL
    - RETRIEVAL_LLM_COUNSEL_URL: Counsel Agent용 EXAONE URL
설정되지 않은 경우 공통 EXAONE_RUNPOD_URL 사용 (싱글톤 fallback)
"""

import asyncio
import logging
import os
from abc import abstractmethod
from typing import Dict, Any, List, ClassVar, Optional

from openai import OpenAI, APIError, APITimeoutError

from ..base import BaseAgent
from ...common.config import get_config

logger = logging.getLogger(__name__)


def _get_db_config() -> Dict[str, str]:
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', '5432'),
        'dbname': os.getenv('DB_NAME', 'ddoksori'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'postgres'),
    }


def _get_embed_api_url() -> str:
    return os.getenv('EMBED_API_URL', 'http://localhost:8001/embed')


# 도메인별 EXAONE 클라이언트 캐시 (독립 인스턴스)
_domain_exaone_clients: Dict[str, OpenAI] = {}
# 공통 fallback 클라이언트 (에이전트별 URL 미설정 시)
_shared_exaone_client: Optional[OpenAI] = None
_shared_openai_client: Optional[OpenAI] = None


class BaseRetrievalAgent(BaseAgent):
    """Retrieval Agent 공통 베이스 - 검색 결과 포맷팅 및 에러 처리 공유"""

    required_inputs: ClassVar[List[str]] = ["user_query"]
    provided_outputs: ClassVar[List[str]] = ["results", "sources", "max_similarity", "avg_similarity"]

    default_top_k: ClassVar[int] = 3

    # 서브클래스에서 오버라이드: 도메인 키 (law, criteria, case, counsel)
    domain_key: ClassVar[str] = ""

    domain_rewrite_prompt: ClassVar[str] = ""

    def _get_exaone_client_for_domain(self) -> Optional[OpenAI]:
        """
        도메인별 EXAONE 클라이언트를 반환합니다.

        우선순위:
        1. 에이전트별 URL 설정 (RETRIEVAL_LLM_{DOMAIN}_URL)
        2. 공통 URL (EXAONE_RUNPOD_URL)
        """
        global _domain_exaone_clients, _shared_exaone_client

        config = get_config()
        timeout = config.retrieval_llm.timeout

        # 1. 에이전트별 URL 확인
        domain_url = config.retrieval_llm.get_url_for_domain(self.domain_key)

        if domain_url:
            # 도메인별 독립 클라이언트 사용
            if self.domain_key not in _domain_exaone_clients:
                _domain_exaone_clients[self.domain_key] = OpenAI(
                    base_url=domain_url,
                    api_key=os.getenv('EXAONE_RUNPOD_API_KEY', 'dummy'),
                    timeout=timeout
                )
                logger.info(f"[{self.agent_name}] Created domain-specific EXAONE client: {domain_url}")
            return _domain_exaone_clients[self.domain_key]

        # 2. 공통 URL fallback
        if _shared_exaone_client is None:
            runpod_url = os.getenv('EXAONE_RUNPOD_URL')
            if runpod_url:
                _shared_exaone_client = OpenAI(
                    base_url=runpod_url,
                    api_key=os.getenv('EXAONE_RUNPOD_API_KEY', 'dummy'),
                    timeout=timeout
                )
        return _shared_exaone_client

    def _get_openai_client(self) -> Optional[OpenAI]:
        """OpenAI fallback 클라이언트 반환 (공유)"""
        global _shared_openai_client

        if _shared_openai_client is None:
            api_key = os.getenv('OPENAI_API_KEY')
            config = get_config()
            if api_key:
                _shared_openai_client = OpenAI(
                    api_key=api_key,
                    timeout=config.retrieval_llm.timeout
                )
        return _shared_openai_client
    
    async def _rewrite_query_for_domain(self, query: str) -> str:
        """
        도메인별 쿼리 재작성을 수행합니다.

        각 에이전트는 자신의 도메인에 맞는 독립된 EXAONE 인스턴스를 사용합니다.
        실패 시 공통 OpenAI fallback으로 전환됩니다.
        """
        if not self.domain_rewrite_prompt:
            return query

        config = get_config()
        timeout = config.retrieval_llm.timeout
        prompt = self.domain_rewrite_prompt.format(query=query)
        system_prompt = "You are a query rewriting assistant. Output only the rewritten query, nothing else."

        # Try EXAONE first (도메인별 또는 공통 클라이언트)
        exaone_client = self._get_exaone_client_for_domain()
        if exaone_client:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._call_llm,
                        exaone_client,
                        config.models.retrieval_llm,
                        system_prompt,
                        prompt
                    ),
                    timeout=timeout
                )
                if result:
                    logger.info(f"[{self.agent_name}] EXAONE query rewrite (domain={self.domain_key}): '{query}' -> '{result}'")
                    return result
            except asyncio.TimeoutError:
                logger.warning(f"[{self.agent_name}] EXAONE query rewrite timeout (domain={self.domain_key})")
            except Exception as e:
                logger.warning(f"[{self.agent_name}] EXAONE query rewrite failed (domain={self.domain_key}): {e}")

        # Fallback to gpt-4.1-nano
        openai_client = self._get_openai_client()
        if openai_client:
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self._call_llm,
                        openai_client,
                        config.models.retrieval_fallback,
                        system_prompt,
                        prompt
                    ),
                    timeout=timeout
                )
                if result:
                    logger.info(f"[{self.agent_name}] Fallback query rewrite: '{query}' -> '{result}'")
                    return result
            except asyncio.TimeoutError:
                logger.warning(f"[{self.agent_name}] Fallback query rewrite timeout")
            except Exception as e:
                logger.warning(f"[{self.agent_name}] Fallback query rewrite failed: {e}")

        logger.info(f"[{self.agent_name}] Using original query (no rewrite)")
        return query
    
    def _call_llm(self, client: OpenAI, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=256
            )
            content = response.choices[0].message.content
            if content:
                return content.strip()
        except (APIError, APITimeoutError) as e:
            logger.warning(f"[{self.agent_name}] LLM API error: {e}")
        return None
    
    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        error = self.validate_request(request)
        if error:
            return self.report_to_supervisor(status="failure", result=None, message=error)
        
        context = request.get("context", {})
        user_query = context.get("user_query", "")
        query_analysis = context.get("query_analysis", {})
        
        base_query = self._build_search_query(user_query, query_analysis)
        search_query = await self._rewrite_query_for_domain(base_query)
        top_k = request.get("params", {}).get("top_k", self.default_top_k)
        
        try:
            results = await self._execute_search(search_query, top_k)
            
            if not results:
                return self.report_to_supervisor(
                    status="failure",
                    result={"results": [], "sources": []},
                    message=f"{self.agent_name}: 검색 결과 없음. 다른 키워드로 재시도 권장."
                )
            
            formatted_results = self._format_results(results)
            sources = self._build_sources(results)
            
            max_sim = max((r.get("similarity", 0) for r in formatted_results), default=0)
            avg_sim = sum(r.get("similarity", 0) for r in formatted_results) / len(formatted_results) if formatted_results else 0
            
            return self.report_to_supervisor(
                status="success",
                result={
                    "results": formatted_results,
                    "sources": sources,
                    "max_similarity": max_sim,
                    "avg_similarity": avg_sim,
                },
                message=f"{self.agent_name}: {len(results)}건 검색 완료 (max_sim: {max_sim:.3f})"
            )
            
        except Exception as e:
            return self.report_to_supervisor(
                status="failure",
                result=None,
                message=f"{self.agent_name} 검색 오류: {str(e)}"
            )
    
    def _build_search_query(self, user_query: str, query_analysis: Dict[str, Any]) -> str:
        rewritten = query_analysis.get("rewritten_query")
        if rewritten and rewritten != user_query:
            return rewritten
        return user_query
    
    @abstractmethod
    async def _execute_search(self, query: str, top_k: int) -> List[Any]:
        """서브클래스에서 구현: 실제 검색 수행"""
        pass
    
    @abstractmethod
    def _format_results(self, results: List[Any]) -> List[Dict[str, Any]]:
        """서브클래스에서 구현: 결과 포맷팅"""
        pass
    
    @abstractmethod
    def _build_sources(self, results: List[Any]) -> List[Dict[str, Any]]:
        """서브클래스에서 구현: 출처 정보 생성"""
        pass


__all__ = ["BaseRetrievalAgent", "_get_db_config", "_get_embed_api_url"]
