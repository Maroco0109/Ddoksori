"""CriteriaRetrievalAgent - 분쟁조정기준 검색 전용 에이전트. LLM: 2.4B (EXAONE)"""

import asyncio
import logging
import os
from typing import Dict, Any, List, ClassVar

from .base_retrieval_agent import BaseRetrievalAgent, _get_db_config, _get_embed_api_url
from .tools.specialized_retrievers import CriteriaRetriever, CriteriaSearchResult

logger = logging.getLogger(__name__)


class CriteriaRetrievalAgent(BaseRetrievalAgent):
    """분쟁조정기준(공정위 고시, 품목별 기준) 검색 에이전트"""
    
    agent_name: ClassVar[str] = "retrieval_criteria"
    agent_description: ClassVar[str] = "분쟁조정기준을 검색합니다. 환불/교환 기준이나 보상 규정이 필요할 때 호출됩니다."

    def _build_search_query(self, user_query: str, query_analysis: Dict[str, Any]) -> str:
        """쿼리 재작성 함수 (gpt-4o-mini 임시 사용)"""
        if not user_query or not user_query.strip():
            return user_query

        if not os.getenv("OPENAI_API_KEY"):
            logger.info("[CriteriaRetrievalAgent] OPENAI_API_KEY not set, skip LLM rewrite")
            return user_query

        try:
            from openai import OpenAI
            client = OpenAI()

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "당신은 사용자의 질문을 '분쟁조정 해결기준' 문서에서 잘 검색될 수 있게 변경해서 내뱉는 답안기입니다. 다음의 문장을 바꾸세요. 문장:"},
                    {"role": "user", "content": user_query},
                ],
                timeout=10,
            )

            rewritten = (response.choices[0].message.content or "").strip()
            if rewritten and rewritten != user_query:
                return rewritten

        except ImportError:
            logger.warning("[CriteriaRetrievalAgent] OpenAI package not installed, skip LLM rewrite")
        except Exception as e:
            logger.warning(f"[CriteriaRetrievalAgent] LLM rewrite failed: {e}")

        return user_query
    
    async def _execute_search(self, query: str, top_k: int) -> List[CriteriaSearchResult]:
        db_config = _get_db_config()
        embed_url = _get_embed_api_url()
        
        retriever = CriteriaRetriever(db_config, embed_url)
        retriever.connect()
        
        try:
            results = await asyncio.to_thread(retriever.search_two_stage, query, top_k)
            return results
        finally:
            retriever.close()
    
    def _format_results(self, results: List[CriteriaSearchResult]) -> List[Dict[str, Any]]:
        return [
            {
                "unit_id": r.unit_id,
                "source_id": r.source_id,
                "source_label": r.source_label,
                "category": r.category,
                "industry": r.industry,
                "item_group": r.item_group,
                "item": r.item,
                "dispute_type": r.dispute_type,
                "unit_text": r.unit_text,
                "similarity": r.similarity,
            }
            for r in results
        ]
    
    def _build_sources(self, results: List[CriteriaSearchResult]) -> List[Dict[str, Any]]:
        return [
            {
                "type": "criteria",
                "index": i + 1,
                "unit_id": r.unit_id,
                "source_label": r.source_label,
                "category": r.category,
                "item": r.item,
                "similarity": r.similarity,
            }
            for i, r in enumerate(results)
        ]


criteria_retrieval_agent = CriteriaRetrievalAgent()

__all__ = ["CriteriaRetrievalAgent", "criteria_retrieval_agent"]
