"""LawRetrievalAgent - 법령 검색 전용 에이전트. LLM: 2.4B (EXAONE)"""

import asyncio
from typing import Dict, Any, List, ClassVar

from .base_retrieval_agent import BaseRetrievalAgent, _get_db_config, _get_embed_api_url
from .tools.hybrid_retriever import HybridRetriever
from .tools.retriever import SearchResult


class LawRetrievalAgent(BaseRetrievalAgent):
    """법령(소비자보호법, 전자상거래법 등) 검색 에이전트"""

    agent_name: ClassVar[str] = "retrieval_law"
    agent_description: ClassVar[str] = "관련 법령 조항을 검색합니다. 법률적 근거가 필요할 때 호출됩니다."
    domain_key: ClassVar[str] = "law"
    domain_rewrite_prompt: ClassVar[str] = "Convert this user query into a formal legal search query focusing on relevant laws and regulations: {query}"
    
    async def _execute_search(self, query: str, top_k: int) -> List[SearchResult]:
        """
        계층적 법령 검색: 항/호 (구체적) 우선 → 조 (넓은 범위) 보충

        검색 전략:
        1단계: 항_분할, 호_분할 (구체적인 조항) 먼저 검색
        2단계: 결과 부족 시 조_전체 (넓은 범위)로 보충
        """
        db_config = _get_db_config()
        embed_url = _get_embed_api_url()

        retriever = HybridRetriever(db_config, embed_url)
        retriever.connect()

        try:
            # === PR-3: 계층적 법령 검색 시작 ===

            # 1단계: 구체적인 항/호 단위 먼저 검색
            detailed_results = await asyncio.to_thread(
                retriever.search,
                query=query,
                top_k=top_k,
                dataset_type_filter='law_guide',
                chunk_type_filter=['항_분할', '호_분할'],  # 구체적 조항 우선
            )

            # 결과가 충분하면 반환
            if len(detailed_results) >= top_k:
                return detailed_results[:top_k]

            # 2단계: 조 단위 (넓은 범위)로 보충
            remaining = top_k - len(detailed_results)
            article_results = await asyncio.to_thread(
                retriever.search,
                query=query,
                top_k=remaining,
                dataset_type_filter='law_guide',
                chunk_type_filter=['조_전체'],  # 넓은 범위
            )

            # 중복 제거 후 병합
            seen_ids = {r.chunk_id for r in detailed_results}
            unique_articles = [r for r in article_results if r.chunk_id not in seen_ids]

            combined = detailed_results + unique_articles
            # === PR-3: 계층적 법령 검색 끝 ===

            return combined[:top_k]

        finally:
            retriever.close()
    
    def _format_results(self, results: List[SearchResult]) -> List[Dict[str, Any]]:
        formatted = []
        for r in results:
            meta = r.metadata or {}
            full_path = None
            if isinstance(meta, dict):
                # RDS law_guide stores a hierarchy path list.
                hp = meta.get('hierarchy_path')
                if isinstance(hp, list):
                    full_path = ' > '.join(str(x) for x in hp if x)
                else:
                    full_path = meta.get('full_path')

            formatted.append({
                'unit_id': None,
                'law_name': meta.get('law_name') if isinstance(meta, dict) else None,
                'full_path': full_path,
                'text': r.content,
                'similarity': r.similarity,
            })
        return formatted
    
    def _build_sources(self, results: List[SearchResult]) -> List[Dict[str, Any]]:
        sources: List[Dict[str, Any]] = []
        for i, r in enumerate(results):
            meta = r.metadata or {}
            full_path = None
            if isinstance(meta, dict):
                hp = meta.get('hierarchy_path')
                if isinstance(hp, list):
                    full_path = ' > '.join(str(x) for x in hp if x)
                else:
                    full_path = meta.get('full_path')

            sources.append({
                'type': 'law',
                'index': i + 1,
                'unit_id': None,
                'law_name': r.doc_title,
                'full_path': full_path,
                'similarity': r.similarity,
            })
        return sources


law_retrieval_agent = LawRetrievalAgent()

__all__ = ["LawRetrievalAgent", "law_retrieval_agent"]
