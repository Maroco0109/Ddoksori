"""
Baseline Retrieval Test - 개선 전 정량적 지표 측정

이 스크립트는 검색 개선 전/후를 비교하기 위한 기준선 테스트입니다.

NOTE: This is a standalone script, not a pytest test file.
Run directly: python backend/scripts/testing/retrieval/test_baseline_retrieval.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import pytest
from dotenv import load_dotenv

# Mark entire module to skip in pytest collection
# This is a standalone script, not a pytest test
pytestmark = pytest.mark.skip(reason="Standalone script - run directly, not via pytest")

# Add backend to path
backend_path = str(Path(__file__).parent.parent.parent.parent)
sys.path.insert(0, backend_path)

# Load .env file from backend directory
env_path = Path(backend_path) / ".env"
load_dotenv(dotenv_path=env_path)

from app.agents.query_analysis.agent import query_analysis_node
from app.agents.retrieval.case_agent import case_retrieval_agent
from app.agents.retrieval.counsel_agent import counsel_retrieval_agent
from app.agents.retrieval.criteria_agent import criteria_retrieval_agent
from app.agents.retrieval.law_agent import law_retrieval_agent
from app.supervisor.state import ChatState

# 테스트 쿼리 세트
TEST_QUERIES = [
    # 원본 쿼리
    "노트북을 구매했는데 화면이 깨져서 도착했어요. 환불 가능한가요?",
    # 유사 제품 쿼리
    "노트북 구매 3일만에 액정 불량 환불 요청",
    "스마트폰 화면 깨짐 교환 가능한가요?",
    "태블릿 액정 파손 반품하고 싶어요",
    # 다른 제품 쿼리
    "냉장고 소음 불량 수리 거부",
    "세탁기 구매 후 바로 고장났어요",
    "에어컨 냉방 안 돼요 환불 받을 수 있나요?",
    # 법령 관련 쿼리
    "전자제품 하자 환불 기준 알려줘",
    "청약철회 기간이 언제까지인가요?",
    "제조물 책임법에 대해 설명해줘",
]


async def run_single_query(query: str, agent, agent_name: str) -> Dict[str, Any]:
    """단일 쿼리 테스트 (helper function, not a pytest test)"""
    try:
        # query_analysis_node로 쿼리 분석
        state = ChatState(
            user_query=query,
            chat_type="dispute",
        )

        # 동기 함수이므로 asyncio.to_thread 사용
        analysis_result = await asyncio.to_thread(query_analysis_node, state)
        query_analysis = analysis_result.get("query_analysis", {})

        # Agent 호출
        request = {
            "context": {
                "user_query": query,
                "query_analysis": query_analysis,
            },
            "params": {
                "top_k": 5,
            },
        }

        result = await agent.process(request)

        # 결과 추출
        status = result.get("status", "failure")
        agent_result = result.get("result", {})
        results = agent_result.get("results", [])
        max_similarity = agent_result.get("max_similarity", 0.0)
        avg_similarity = agent_result.get("avg_similarity", 0.0)

        return {
            "query": query,
            "agent": agent_name,
            "status": status,
            "num_results": len(results),
            "max_similarity": max_similarity,
            "avg_similarity": avg_similarity,
            "has_results": len(results) > 0,
            "similarities": [r.get("similarity", 0.0) for r in results],
        }

    except Exception as e:
        return {
            "query": query,
            "agent": agent_name,
            "status": "error",
            "error": str(e),
            "num_results": 0,
            "max_similarity": 0.0,
            "avg_similarity": 0.0,
            "has_results": False,
            "similarities": [],
        }


async def run_baseline_tests() -> Dict[str, Any]:
    """모든 테스트 실행"""

    agents = [
        (law_retrieval_agent, "law"),
        (criteria_retrieval_agent, "criteria"),
        (case_retrieval_agent, "case"),
        (counsel_retrieval_agent, "counsel"),
    ]

    all_results = []

    print("=" * 80)
    print("BASELINE RETRIEVAL TEST - 개선 전 지표 측정")
    print("=" * 80)
    print(f"Test time: {datetime.now().isoformat()}")
    print(f"Total queries: {len(TEST_QUERIES)}")
    print(f"Total agents: {len(agents)}")
    print()

    for query_idx, query in enumerate(TEST_QUERIES, 1):
        print(f"\n[Query {query_idx}/{len(TEST_QUERIES)}] {query}")
        print("-" * 80)

        for agent, agent_name in agents:
            result = await run_single_query(query, agent, agent_name)
            all_results.append(result)

            status_icon = "✓" if result["has_results"] else "✗"
            print(
                f"  {status_icon} {agent_name:10s}: "
                f"{result['num_results']} results, "
                f"max_sim={result['max_similarity']:.3f}, "
                f"avg_sim={result['avg_similarity']:.3f}"
            )

    # 집계 통계
    print("\n" + "=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)

    total_tests = len(all_results)
    success_tests = sum(1 for r in all_results if r["has_results"])

    # Agent별 통계
    for agent_name in ["law", "criteria", "case", "counsel"]:
        agent_results = [r for r in all_results if r["agent"] == agent_name]
        agent_success = sum(1 for r in agent_results if r["has_results"])
        agent_recall = agent_success / len(agent_results) if agent_results else 0
        agent_avg_sim = (
            sum(r["avg_similarity"] for r in agent_results) / len(agent_results)
            if agent_results
            else 0
        )

        print(f"\n[{agent_name.upper()}]")
        print(f"  Recall: {agent_success}/{len(agent_results)} = {agent_recall:.2%}")
        print(f"  Avg Similarity: {agent_avg_sim:.3f}")
        print(
            f"  Avg Results: {sum(r['num_results'] for r in agent_results) / len(agent_results):.1f}"
        )

    # 전체 통계
    print(f"\n[OVERALL]")
    print(f"  Total Tests: {total_tests}")
    print(f"  Success Tests: {success_tests}")
    print(f"  Recall Rate: {success_tests / total_tests:.2%}")
    print(
        f"  Avg Similarity (all): {sum(r['avg_similarity'] for r in all_results) / total_tests:.3f}"
    )

    # Query별 성공률
    print(f"\n[PER-QUERY ANALYSIS]")
    for query_idx, query in enumerate(TEST_QUERIES, 1):
        query_results = [r for r in all_results if r["query"] == query]
        query_success = sum(1 for r in query_results if r["has_results"])
        print(f"  Query {query_idx}: {query_success}/4 agents found results")

    # 결과 반환
    summary = {
        "timestamp": datetime.now().isoformat(),
        "test_type": "baseline",
        "total_queries": len(TEST_QUERIES),
        "total_agents": len(agents),
        "total_tests": total_tests,
        "success_tests": success_tests,
        "recall_rate": success_tests / total_tests,
        "avg_similarity": sum(r["avg_similarity"] for r in all_results) / total_tests,
        "agent_stats": {},
        "query_results": [],
    }

    # Agent별 통계 추가
    for agent_name in ["law", "criteria", "case", "counsel"]:
        agent_results = [r for r in all_results if r["agent"] == agent_name]
        agent_success = sum(1 for r in agent_results if r["has_results"])
        summary["agent_stats"][agent_name] = {
            "recall": agent_success / len(agent_results) if agent_results else 0,
            "avg_similarity": (
                sum(r["avg_similarity"] for r in agent_results) / len(agent_results)
                if agent_results
                else 0
            ),
            "avg_results": (
                sum(r["num_results"] for r in agent_results) / len(agent_results)
                if agent_results
                else 0
            ),
        }

    # Query별 결과 추가
    for query in TEST_QUERIES:
        query_results = [r for r in all_results if r["query"] == query]
        query_success = sum(1 for r in query_results if r["has_results"])
        summary["query_results"].append(
            {
                "query": query,
                "agents_with_results": query_success,
                "results": query_results,
            }
        )

    return summary


async def main():
    """메인 실행 함수"""

    # 테스트 실행
    summary = await run_baseline_tests()

    # 로그 파일 저장
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"baseline_{timestamp}.json"

    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 80}")
    print(f"Log saved to: {log_file}")
    print(f"{'=' * 80}")

    return summary


if __name__ == "__main__":
    asyncio.run(main())
