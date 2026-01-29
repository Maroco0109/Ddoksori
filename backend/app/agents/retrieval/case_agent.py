"""CaseRetrievalAgent - 분쟁조정사례 검색 전용 에이전트"""

import asyncio
import logging
from typing import Dict, Any, List, ClassVar, Optional

from .base_retrieval_agent import BaseRetrievalAgent, _get_db_config, _get_embed_api_url
from .tools.hybrid_retriever import HybridRetriever
from .tools.retriever import SearchResult

logger = logging.getLogger(__name__)


class CaseRetrievalAgent(BaseRetrievalAgent):
    """분쟁조정사례(mediation_case) 검색 에이전트 - 법적 효력이 있는 분쟁조정 결과"""

    agent_name: ClassVar[str] = "retrieval_case"
    agent_description: ClassVar[str] = "분쟁조정사례를 검색합니다. 유사한 분쟁 해결 선례가 필요할 때 호출됩니다."
    domain_key: ClassVar[str] = "case"

    async def _execute_search(
        self,
        query: str,
        top_k: int,
        metadata_filter: Optional[Dict[str, Any]] = None,
        ignore_threshold: bool = False
    ) -> List[SearchResult]:
        """
        2단계 우선순위 사례 검색: (해결+조정) 우선 → 상담 보충

        검색 전략:
        1단계: 해결+조정 사례 (핵심 참고 자료) - 실제 분쟁 해결 사례
        2단계: 결과 부족 시 상담 사례로 보충 (단순 상담 기록)

        category 분류:
        - 해결: 피해구제/해결 사례 (1,874건)
        - 조정: 분쟁조정위원회 조정 사례 (20,992건)
        - 상담: 단순 전화 상담 사례 (11,342건)

        v2: metadata_filter 지원
            - dataset_type: 기본값 'case'
            - categories: ['조정', '해결', '상담'] 등
              → 조정/해결 2-3개 우선, 상담 1-2개 보충
        """
        db_config = _get_db_config()
        embed_url = _get_embed_api_url()

        retriever = HybridRetriever(db_config, embed_url)
        retriever.connect()

        try:
            # === v2: 메타데이터 필터 적용 ===
            dataset_type = 'case'  # 기본값
            primary_categories = ['해결', '조정']  # 핵심 사례 우선
            secondary_categories = ['상담']  # 보충용

            if metadata_filter:
                # dataset_type 오버라이드
                if metadata_filter.get('dataset_type'):
                    dataset_type = metadata_filter['dataset_type']

                # categories 필터 적용 (v2)
                if metadata_filter.get('categories'):
                    requested_categories = metadata_filter['categories']
                    # 우선순위 분리: 조정/해결 vs 상담
                    primary_categories = [c for c in requested_categories if c in ['해결', '조정']]
                    secondary_categories = [c for c in requested_categories if c == '상담']

                    # 요청된 카테고리만 검색 (기본 우선순위 무시)
                    if not primary_categories and not secondary_categories:
                        # 모든 요청 카테고리로 단일 검색
                        primary_categories = requested_categories
                        secondary_categories = []

            logger.info(
                f"[CaseRetrieval v2] dataset_type={dataset_type}, "
                f"primary={primary_categories}, secondary={secondary_categories}"
            )

            # === PR-4: 사례 우선순위 검색 시작 ===

            combined = []
            seen_ids = set()

            # 1단계: 해결+조정 사례 (핵심 참고 자료)
            if primary_categories:
                # v2: 조정/해결 2-3개 목표
                primary_k = min(top_k, 3) if secondary_categories else top_k
                primary_results = await asyncio.to_thread(
                    retriever.search,
                    query=query,
                    top_k=primary_k,
                    dataset_type_filter=dataset_type,
                    category_filter=primary_categories,
                )
                for r in primary_results:
                    if r.chunk_id not in seen_ids:
                        seen_ids.add(r.chunk_id)
                        combined.append(r)

            # 2단계: 상담 사례로 보충 (v2: 1-2개 목표)
            if secondary_categories and len(combined) < top_k:
                remaining = min(top_k - len(combined), 2)  # 최대 2개
                counsel_results = await asyncio.to_thread(
                    retriever.search,
                    query=query,
                    top_k=remaining,
                    dataset_type_filter=dataset_type,
                    category_filter=secondary_categories,
                )
                for r in counsel_results:
                    if r.chunk_id not in seen_ids:
                        seen_ids.add(r.chunk_id)
                        combined.append(r)

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
