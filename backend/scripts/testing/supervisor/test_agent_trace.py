"""
MAS Agent Trace Logging System 테스트

TraceEntry, summarize_node_output, build_pipeline_summary를 테스트합니다.
"""

import operator
from typing import get_type_hints

import pytest

from app.supervisor.graph import build_pipeline_summary, summarize_node_output
from app.supervisor.state.control import TraceEntry


@pytest.mark.unit
def test_trace_entry_fields():
    """TraceEntry TypedDict가 정확히 5개의 필드를 가지는지 확인"""
    expected_fields = {
        "node_name",
        "timestamp",
        "duration_ms",
        "protocol_summary",
        "metadata",
    }
    hints = get_type_hints(TraceEntry)
    actual_fields = set(hints.keys())
    assert (
        actual_fields == expected_fields
    ), f"Expected {expected_fields}, got {actual_fields}"

    entry: TraceEntry = {
        "node_name": "test_node",
        "timestamp": 123.456,
        "duration_ms": 100.0,
        "protocol_summary": {"test": "data"},
        "metadata": {"extra": "info"},
    }
    assert entry["node_name"] == "test_node"
    assert entry["duration_ms"] == 100.0


@pytest.mark.unit
def test_summarize_node_output_cache_check():
    """cache_check 노드의 summarization 테스트"""
    assert summarize_node_output("cache_check", {"_cache_hit": True}) == {
        "cache_hit": True
    }
    assert summarize_node_output("cache_check", {"_cache_hit": False}) == {
        "cache_hit": False
    }


@pytest.mark.unit
def test_summarize_node_output_query_analysis():
    """query_analysis 노드의 summarization 테스트"""
    result = {
        "query_analysis": {
            "intent": "dispute",
            "retriever_types": ["law", "criteria"],
            "keywords": ["환불", "청약"],
        },
        "expanded_queries": ["q1", "q2"],
    }
    summary = summarize_node_output("query_analysis", result)
    assert summary["intent"] == "dispute"
    assert summary["retriever_types"] == ["law", "criteria"]
    assert summary["keyword_count"] == 2
    assert summary["expanded_query_count"] == 2


@pytest.mark.unit
def test_summarize_node_output_retrieval_agent():
    """retrieval agent 노드의 summarization 테스트"""
    result = {
        "individual_retrieval_results": [
            {
                "source": "law",
                "documents": [{"id": 1}, {"id": 2}],
                "max_similarity": 0.85,
                "search_time_ms": 150.5,
            }
        ]
    }
    summary = summarize_node_output("retrieval_law", result)
    assert summary["source"] == "law"
    assert summary["document_count"] == 2
    assert summary["max_similarity"] == 0.85
    assert summary["search_time_ms"] == 150.5
    assert summary["has_error"] is False

    # Test with error
    result_err = {
        "individual_retrieval_results": [
            {
                "source": "criteria",
                "documents": [],
                "max_similarity": 0.0,
                "search_time_ms": 50.0,
                "error": "Connection timeout",
            }
        ]
    }
    summary_err = summarize_node_output("retrieval_criteria", result_err)
    assert summary_err["has_error"] is True
    assert summary_err["document_count"] == 0


@pytest.mark.unit
def test_summarize_node_output_retrieval_merge():
    """retrieval_merge 노드의 summarization 테스트"""
    result = {
        "retrieval": {
            "law_results": [1, 2, 3],
            "criteria_results": [1],
            "dispute_results": [],
            "counsel_results": [],
        }
    }
    summary = summarize_node_output("retrieval_merge", result)
    assert summary["total_documents"] == 4
    assert summary["sections"]["law_results"] == 3
    assert summary["sections"]["criteria_results"] == 1


@pytest.mark.unit
def test_summarize_node_output_generation():
    """generation 노드의 summarization 테스트"""
    result = {
        "draft_answer": "x" * 500,
        "has_sufficient_evidence": True,
        "cited_cases": [1, 2],
    }
    summary = summarize_node_output("generation", result)
    assert summary["has_sufficient_evidence"] is True
    assert summary["answer_length"] == 500
    assert summary["cited_case_count"] == 2


@pytest.mark.unit
def test_summarize_node_output_review():
    """review 노드의 summarization 테스트"""
    result = {
        "review": {
            "passed": False,
            "violations": [{"type": "prohibited"}],
        }
    }
    summary = summarize_node_output("review", result)
    assert summary["passed"] is False
    assert summary["violation_count"] == 1


@pytest.mark.unit
def test_summarize_node_output_unknown_node():
    """알 수 없는 노드 이름 테스트"""
    assert summarize_node_output("nonexistent", {"some": "data"}) is None


@pytest.mark.unit
def test_summarize_node_output_supervisor_truncation():
    """supervisor 노드의 reasoning 텍스트 truncation 테스트"""
    result = {
        "supervisor": {
            "reasoning": "x" * 300,
            "current_phase": "retrieval",
            "next_agent": "query_analyst",
            "iteration_count": 1,
        }
    }
    summary = summarize_node_output("supervisor", result)
    assert summary["current_phase"] == "retrieval"
    assert summary["next_agent"] == "query_analyst"
    assert summary["iteration_count"] == 1
    assert len(summary["reasoning_preview"]) == 203  # 200 + '...'
    assert summary["reasoning_preview"].endswith("...")


@pytest.mark.unit
def test_build_pipeline_summary():
    """build_pipeline_summary가 timestamp 기준으로 정렬하고 seq를 할당하는지 테스트"""
    entries = [
        {
            "node_name": "cache_check",
            "timestamp": 3.0,
            "duration_ms": 50.0,
            "protocol_summary": {"cache_hit": False},
            "metadata": None,
        },
        {
            "node_name": "supervisor",
            "timestamp": 1.0,
            "duration_ms": 100.0,
            "protocol_summary": {"current_phase": "init"},
            "metadata": None,
        },
        {
            "node_name": "query_analysis",
            "timestamp": 2.0,
            "duration_ms": 75.0,
            "protocol_summary": {"intent": "general"},
            "metadata": None,
        },
    ]
    summary = build_pipeline_summary(entries, 225.0)

    assert summary["total_duration_ms"] == 225.0
    assert summary["node_count"] == 3
    assert summary["node_sequence"] == ["supervisor", "query_analysis", "cache_check"]

    per_node = summary["per_node"]
    assert per_node[0] == {
        "seq": 0,
        "node": "supervisor",
        "duration_ms": 100.0,
        "summary": {"current_phase": "init"},
    }
    assert per_node[1] == {
        "seq": 1,
        "node": "query_analysis",
        "duration_ms": 75.0,
        "summary": {"intent": "general"},
    }
    assert per_node[2] == {
        "seq": 2,
        "node": "cache_check",
        "duration_ms": 50.0,
        "summary": {"cache_hit": False},
    }


@pytest.mark.unit
def test_build_pipeline_summary_empty():
    """빈 trace entries 리스트 테스트"""
    summary = build_pipeline_summary([], 0.0)
    assert summary["node_count"] == 0
    assert summary["node_sequence"] == []
    assert summary["per_node"] == []


@pytest.mark.unit
def test_trace_timestamp_ordering():
    """trace entries가 timestamp로 정렬되는지 확인"""
    entries = [
        {
            "node_name": "a",
            "timestamp": 3.0,
            "duration_ms": 10.0,
            "protocol_summary": None,
            "metadata": None,
        },
        {
            "node_name": "b",
            "timestamp": 1.0,
            "duration_ms": 10.0,
            "protocol_summary": None,
            "metadata": None,
        },
        {
            "node_name": "c",
            "timestamp": 2.0,
            "duration_ms": 10.0,
            "protocol_summary": None,
            "metadata": None,
        },
    ]
    summary = build_pipeline_summary(entries, 30.0)
    assert summary["node_sequence"] == ["b", "c", "a"]


@pytest.mark.unit
def test_trace_operator_add_merge():
    """병렬 브랜치 merge 시뮬레이션: operator.add로 trace entries 병합"""
    e1: TraceEntry = {
        "node_name": "retrieval_law",
        "timestamp": 1.0,
        "duration_ms": 50.0,
        "protocol_summary": {"source": "law"},
        "metadata": None,
    }
    e2: TraceEntry = {
        "node_name": "retrieval_criteria",
        "timestamp": 1.1,
        "duration_ms": 60.0,
        "protocol_summary": {"source": "criteria"},
        "metadata": None,
    }
    e3: TraceEntry = {
        "node_name": "retrieval_case",
        "timestamp": 1.2,
        "duration_ms": 70.0,
        "protocol_summary": {"source": "case"},
        "metadata": None,
    }

    merged = operator.add(operator.add([e1], [e2]), [e3])
    assert len(merged) == 3
    assert merged[0]["node_name"] == "retrieval_law"
    assert merged[1]["node_name"] == "retrieval_criteria"
    assert merged[2]["node_name"] == "retrieval_case"

    summary = build_pipeline_summary(merged, 180.0)
    assert summary["node_count"] == 3
    assert summary["node_sequence"] == [
        "retrieval_law",
        "retrieval_criteria",
        "retrieval_case",
    ]
