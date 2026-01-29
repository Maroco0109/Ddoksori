"""LawRetrievalAgent - 법령 검색 전용 에이전트"""

import asyncio
from typing import Dict, Any, List, ClassVar, Optional

from .base_retrieval_agent import BaseRetrievalAgent, _get_db_config, _get_embed_api_url
from .tools.hybrid_retriever import HybridRetriever
from .tools.retriever import SearchResult


class LawRetrievalAgent(BaseRetrievalAgent):
    """법령(소비자보호법, 전자상거래법 등) 검색 에이전트"""

    agent_name: ClassVar[str] = "retrieval_law"
    agent_description: ClassVar[str] = "관련 법령 조항을 검색합니다. 법률적 근거가 필요할 때 호출됩니다."
    domain_key: ClassVar[str] = "law"

    async def _execute_search(
        self,
        query: str,
        top_k: int,
        metadata_filter: Optional[Dict[str, Any]] = None,
        ignore_threshold: bool = False
    ) -> List[SearchResult]:
        """
        계층적 법령 검색: 항/호 (구체적) 우선 → 조 (넓은 범위) 보충

        검색 전략:
        1단계: 항_분할, 호_분할 (구체적인 조항) 먼저 검색
        2단계: 결과 부족 시 조_전체 (넓은 범위)로 보충

        v2: metadata_filter 지원
            - dataset_type: 기본값 'law_guide'
            - document_types: ['법률', '시행령'] 등 (chunk_type_filter로 매핑)
        """
        db_config = _get_db_config()
        embed_url = _get_embed_api_url()

        retriever = HybridRetriever(db_config, embed_url)
        retriever.connect()

        try:
            # === v2: 메타데이터 필터 적용 ===
            dataset_type = 'law_guide'  # 기본값
            chunk_types_detailed = ['항_분할', '호_분할']
            chunk_types_broad = ['조_전체']

            if metadata_filter:
                # dataset_type 오버라이드
                if metadata_filter.get('dataset_type'):
                    dataset_type = metadata_filter['dataset_type']

                # document_types → chunk_type_filter 매핑 (v2)
                # 법률 → 조_전체, 항_분할, 호_분할 등 유지
                # 시행령 → 동일하게 처리 (법령 구조 동일)
                # v2에서는 현재 기본 로직 유지 (추후 확장 가능)

            # === PR-3: 계층적 법령 검색 시작 ===

            # 1단계: 구체적인 항/호 단위 먼저 검색
            detailed_results = await asyncio.to_thread(
                retriever.search,
                query=query,
                top_k=top_k,
                dataset_type_filter=dataset_type,
                chunk_type_filter=chunk_types_detailed,  # 구체적 조항 우선
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
                dataset_type_filter=dataset_type,
                chunk_type_filter=chunk_types_broad,  # 넓은 범위
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
