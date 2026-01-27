"""CaseRetrievalAgent - 분쟁조정사례 검색 전용 에이전트. LLM: 2.4B (EXAONE)"""

import asyncio
from typing import Dict, Any, List, ClassVar

from .base_retrieval_agent import BaseRetrievalAgent, _get_db_config, _get_embed_api_url
from .tools.hybrid_retriever import HybridRetriever
from .tools.retriever import SearchResult


class CaseRetrievalAgent(BaseRetrievalAgent):
    """분쟁조정사례(mediation_case) 검색 에이전트 - 법적 효력이 있는 분쟁조정 결과"""

    agent_name: ClassVar[str] = "retrieval_case"
    agent_description: ClassVar[str] = "분쟁조정사례를 검색합니다. 유사한 분쟁 해결 선례가 필요할 때 호출됩니다."
    domain_key: ClassVar[str] = "case"
    domain_rewrite_prompt: ClassVar[str] = "Convert this problem description into a similar case search query: {query}"
    
    async def _execute_search(self, query: str, top_k: int) -> List[SearchResult]:
        """
        2단계 우선순위 사례 검색: (해결+조정) 우선 → 상담 보충

        검색 전략:
        1단계: 해결+조정 사례 (핵심 참고 자료) - 실제 분쟁 해결 사례
        2단계: 결과 부족 시 상담 사례로 보충 (단순 상담 기록)

        category 분류:
        - 해결: 피해구제/해결 사례 (1,874건)
        - 조정: 분쟁조정위원회 조정 사례 (20,992건)
        - 상담: 단순 전화 상담 사례 (11,342건)
        """
        db_config = _get_db_config()
        embed_url = _get_embed_api_url()

        retriever = HybridRetriever(db_config, embed_url)
        retriever.connect()

        try:
            # === PR-4: 사례 우선순위 검색 시작 ===

            # 1단계: 해결+조정 사례 (핵심 참고 자료)
            primary_results = await asyncio.to_thread(
                retriever.search,
                query=query,
                top_k=top_k,
                dataset_type_filter='case',
                category_filter=['해결', '조정'],  # 핵심 사례 우선
            )

            # 결과가 충분하면 반환
            if len(primary_results) >= top_k:
                return primary_results[:top_k]

            # 2단계: 상담 사례로 보충 (부족분만)
            remaining = top_k - len(primary_results)
            counsel_results = await asyncio.to_thread(
                retriever.search,
                query=query,
                top_k=remaining,
                dataset_type_filter='case',
                category_filter=['상담'],  # 보충용
            )

            # 중복 제거 후 병합
            seen_ids = {r.chunk_id for r in primary_results}
            unique_counsel = [r for r in counsel_results if r.chunk_id not in seen_ids]

            combined = primary_results + unique_counsel
            # === PR-4: 사례 우선순위 검색 끝 ===

            return combined[:top_k]

        finally:
            retriever.close()
    
    def _format_results(self, results: List[SearchResult]) -> List[Dict[str, Any]]:
        formatted: List[Dict[str, Any]] = []
        for r in results:
            formatted.append({
                'chunk_id': r.chunk_id,
                'doc_id': r.doc_id,
                'chunk_type': r.chunk_type,
                'content': r.content,
                'doc_title': r.doc_title,
                'title': r.doc_title,
                'source_org': r.source_org,
                'url': r.url,
                'decision_date': r.decision_date,
                'similarity': r.similarity,
            })
        return formatted
    
    def _build_sources(self, results: List[SearchResult]) -> List[Dict[str, Any]]:
        return [
            {
                'type': 'mediation_case',
                'index': i + 1,
                'chunk_id': r.chunk_id,
                'doc_id': r.doc_id,
                'doc_title': r.doc_title,
                'source_org': r.source_org,
                'similarity': r.similarity,
            }
            for i, r in enumerate(results)
        ]


case_retrieval_agent = CaseRetrievalAgent()

__all__ = ["CaseRetrievalAgent", "case_retrieval_agent"]
