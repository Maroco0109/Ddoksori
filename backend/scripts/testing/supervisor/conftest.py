import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.supervisor import (
    ChatState,
    create_initial_state,
    reset_graph,
)
from app.supervisor.graph_mas import create_mas_supervisor_graph


@pytest.fixture
def sample_dispute_state() -> ChatState:
    return create_initial_state(
        user_query="노트북 환불받고 싶어요. 구매한 지 일주일 됐는데 화면에 불량이 있어요.",
        chat_type="dispute",
        onboarding={
            "purchase_item": "노트북",
            "purchase_date": "2026-01-10",
            "purchase_place": "삼성전자",
            "purchase_amount": "1500000",
            "dispute_details": "화면 불량",
        },
    )


@pytest.fixture
def sample_general_state() -> ChatState:
    return create_initial_state(
        user_query="안녕하세요", chat_type="general", onboarding=None
    )


@pytest.fixture
def sample_minimal_info_state() -> ChatState:
    return create_initial_state(
        user_query="환불해주세요", chat_type="dispute", onboarding=None
    )


@pytest.fixture
def sample_law_query_state() -> ChatState:
    return create_initial_state(
        user_query="전자상거래법 청약철회 조항 알려주세요",
        chat_type="dispute",
        onboarding=None,
    )


@pytest.fixture
def mock_retrieval_result() -> Dict[str, Any]:
    return {
        "agency": {
            "agency": "KCA",
            "dispute_type": "1:N",
            "reason": "일반 소비자 분쟁",
            "confidence": 0.8,
        },
        "disputes": [
            {
                "chunk_id": "chunk_001",
                "doc_id": "doc_001",
                "doc_title": "노트북 환불 사례",
                "source_org": "KCA",
                "similarity": 0.75,
                "content": "노트북 화면 불량으로 인한 환불 사례...",
            }
        ],
        "counsels": [
            {
                "chunk_id": "chunk_002",
                "doc_id": "doc_002",
                "doc_title": "전자제품 환불 상담",
                "source_org": "KCA",
                "similarity": 0.70,
                "content": "전자제품 구매 후 환불 관련 상담...",
            }
        ],
        "laws": [],
        "criteria": [],
        "max_similarity": 0.75,
        "avg_similarity": 0.725,
    }


@pytest.fixture
def mock_low_similarity_retrieval() -> Dict[str, Any]:
    return {
        "agency": {
            "agency": "KCA",
            "dispute_type": "1:N",
            "reason": "일반 소비자 분쟁",
            "confidence": 0.7,
        },
        "disputes": [],
        "counsels": [],
        "laws": [],
        "criteria": [],
        "max_similarity": 0.0,
        "avg_similarity": 0.0,
    }


@pytest.fixture
def mock_query_analysis_result() -> Dict[str, Any]:
    return {
        "query_type": "dispute",
        "keywords": ["노트북", "환불", "화면", "불량"],
        "agency_hint": "KCA",
        "needs_clarification": False,
        "missing_fields": [],
        "extracted_info": {
            "purchase_item": "노트북",
            "dispute_details": "화면 불량",
        },
        "missing_fields_description": "",
        "rewritten_query": "노트북 환불 화면 불량 분쟁조정 피해구제 소비자",
        "search_queries": [
            "노트북 환불받고 싶어요",
            "노트북 환불 화면 불량 분쟁조정 피해구제 소비자",
        ],
        "expansion_applied": "dispute_item_verb: 노트북+환불",
    }


@pytest.fixture
def mock_needs_clarification_result() -> Dict[str, Any]:
    return {
        "query_type": "dispute",
        "keywords": ["환불"],
        "agency_hint": "KCA",
        "needs_clarification": True,
        "missing_fields": ["purchase_item", "dispute_details"],
        "extracted_info": {},
        "missing_fields_description": "구매 품목과 분쟁 상세 내용이 필요합니다.",
        "rewritten_query": "환불",
        "search_queries": ["환불해주세요"],
        "expansion_applied": "dispute_no_context",
    }


@pytest.fixture
def mock_review_passed() -> Dict[str, Any]:
    return {
        "passed": True,
        "violations": [],
        "filtered_answer": None,
    }


@pytest.fixture
def mock_review_failed() -> Dict[str, Any]:
    return {
        "passed": False,
        "violations": ["prohibited_expression: 반드시"],
        "filtered_answer": "수정된 답변...",
    }


@pytest.fixture
def uncompiled_graph():
    reset_graph()
    return create_mas_supervisor_graph()


@pytest.fixture
def compiled_graph():
    reset_graph()
    graph = create_mas_supervisor_graph()
    from langgraph.checkpoint.memory import MemorySaver

    return graph.compile(checkpointer=MemorySaver())


class MockRetriever:
    def __init__(self, results: Dict[str, Any]):
        self._results = results

    def connect(self):
        pass

    def close(self):
        pass

    def search(self, query: str, top_k: int = 5, **kwargs) -> List[Dict]:
        return self._results.get("disputes", []) + self._results.get("counsels", [])


class MockLLM:
    def __init__(self, response: str = "테스트 답변입니다."):
        self._response = response

    def invoke(self, prompt: str) -> str:
        return self._response


@pytest.fixture
def mock_retriever_factory(mock_retrieval_result):
    def _factory(results: Optional[Dict] = None):
        return MockRetriever(results or mock_retrieval_result)

    return _factory


@pytest.fixture
def mock_llm_factory():
    def _factory(response: str = "테스트 답변입니다."):
        return MockLLM(response)

    return _factory
