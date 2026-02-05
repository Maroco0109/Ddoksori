"""LawRetrievalAgent - 법령 검색 전용 에이전트. LLM: 2.4B (EXAONE)"""

import asyncio
import logging
import os
from typing import Dict, Any, List, ClassVar

from .base_retrieval_agent import BaseRetrievalAgent, _get_db_config, _get_embed_api_url
from .tools.specialized_retrievers import LawRetriever, LawSearchResult


logger = logging.getLogger(__name__)


class LawRetrievalAgent(BaseRetrievalAgent):
    """법령(소비자보호법, 전자상거래법 등) 검색 에이전트"""
    
    agent_name: ClassVar[str] = "retrieval_law"
    agent_description: ClassVar[str] = "관련 법령 조항을 검색합니다. 법률적 근거가 필요할 때 호출됩니다."
    

    def _build_search_query(self, user_query: str, query_analysis: Dict[str, Any]) -> str:
        """쿼리 재작성 함수 (gpt-4o-mini 임시 사용)"""
        if not user_query or not user_query.strip():
            return user_query

        if not os.getenv("OPENAI_API_KEY"):
            logger.info("[LawRetrievalAgent] OPENAI_API_KEY not set, skip LLM rewrite")
            return user_query

        try:
            from openai import OpenAI
            client = OpenAI()

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "당신은 사용자의 질문을 법령 용어로 꾸며서 내뱉는 답안기입니다. 법률에 대해 유사도 검색이 잘 수행될 수 있도록 다음의 문장을 바꾸세요. 단, '판결문'이 아닌 '법률'입니다. 문장:"},
                    {"role": "user", "content": user_query},
                ],
                timeout=10,
            )

            rewritten = (response.choices[0].message.content or "").strip()
            if rewritten and rewritten != user_query:
                return rewritten

        except ImportError:
            logger.warning("[LawRetrievalAgent] OpenAI package not installed, skip LLM rewrite")
        except Exception as e:
            logger.warning(f"[LawRetrievalAgent] LLM rewrite failed: {e}")

        return user_query

    async def _execute_search(self, query: str, top_k: int) -> List[LawSearchResult]:
        db_config = _get_db_config()
        embed_url = _get_embed_api_url()
        
        retriever = LawRetriever(db_config, embed_url)
        retriever.connect()
        
        try:
            results = await asyncio.to_thread(retriever.search_two_stage, query, top_k)
            return results
        finally:
            retriever.close()
    
    def _format_results(self, results: List[LawSearchResult]) -> List[Dict[str, Any]]:
        return [
            {
                "unit_id": r.unit_id,
                "law_id": r.law_id,
                "law_name": r.law_name,
                "level": r.level,
                "article_no": r.article_no,
                "paragraph_no": r.paragraph_no,
                "item_no": r.item_no,
                "subitem_no": r.subitem_no,
                "full_path": r.full_path,
                "text": r.text,
                "similarity": r.similarity,
            }
            for r in results
        ]
    
    def _build_sources(self, results: List[LawSearchResult]) -> List[Dict[str, Any]]:
        return [
            {
                "type": "law",
                "index": i + 1,
                "unit_id": r.unit_id,
                "law_name": r.law_name,
                "full_path": r.full_path,
                "similarity": r.similarity,
            }
            for i, r in enumerate(results)
        ]


law_retrieval_agent = LawRetrievalAgent()

__all__ = ["LawRetrievalAgent", "law_retrieval_agent"]
