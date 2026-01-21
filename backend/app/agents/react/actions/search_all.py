from typing import Dict, Any

from ..action_registry import BaseAction, ActionResult
from ....orchestrator.state import ChatState
from .base import get_db_config, get_embed_api_url, merge_retrieval, build_sources_from_retrieval


class SearchAllAction(BaseAction):
    name = "search_all"
    description = "분쟁사례, 상담사례, 법령, 기준 전체 검색"

    def execute(self, state: ChatState, query: str) -> ActionResult:
        current_retrieval = state.get('retrieval') or {}

        try:
            from ...retrieval.tools.specialized_retrievers import StructuredRetriever

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

            retrieval = merge_retrieval(current_retrieval, raw_result)
            sources = build_sources_from_retrieval(retrieval)

            return ActionResult(
                observation=observation,
                retrieval=retrieval,
                sources=sources,
            )

        except Exception as e:
            return ActionResult(observation=f"검색 실패: {str(e)}")
