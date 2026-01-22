from ..action_registry import BaseAction, ActionResult
from ....orchestrator.state import ChatState
from .base import get_db_config, get_embed_api_url, merge_retrieval, build_sources_from_retrieval


class SearchCriteriaAction(BaseAction):
    name = "search_criteria"
    description = "분쟁해결기준만 추가 검색"

    def execute(self, state: ChatState, query: str) -> ActionResult:
        current_retrieval = state.get('retrieval') or {}

        try:
            from ...retrieval.tools.specialized_retrievers import StructuredRetriever

            retriever = StructuredRetriever(get_db_config(), get_embed_api_url())
            retriever.connect()

            try:
                result = retriever.search_criteria(query=query, top_k=5)
            finally:
                retriever.close()

            observation = f"분쟁해결기준 {len(result)}건 검색 완료"
            retrieval = merge_retrieval(current_retrieval, result, section='criteria')
            sources = build_sources_from_retrieval(retrieval)

            return ActionResult(
                observation=observation,
                retrieval=retrieval,
                sources=sources,
            )

        except Exception as e:
            return ActionResult(observation=f"기준 검색 실패: {str(e)}")
