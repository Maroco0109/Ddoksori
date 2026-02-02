"""
단일 쿼리 통합 테스트 - 전체 flow 확인
"""

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

# Setup path
backend_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_path))
env_path = backend_path / ".env"
load_dotenv(dotenv_path=env_path)

from app.agents.retrieval.counsel_agent import counsel_retrieval_agent


async def main():
    query = "노트북을 구매했는데 화면이 깨져서 도착했어요. 환불 가능한가요?"

    print("=" * 80)
    print("SINGLE QUERY INTEGRATION TEST")
    print("=" * 80)
    print(f"Query: {query}")
    print(f"Agent: counsel_retrieval_agent")
    print()

    # Create request
    request = {
        "context": {
            "user_query": query,
            "query_analysis": {
                "query_type": "dispute",
                "keywords": ["노트북", "화면", "깨짐", "환불"],
            },
        },
        "params": {
            "top_k": 5,
        },
    }

    # Execute
    print("Executing search...")
    result = await counsel_retrieval_agent.process(request)

    # Results
    print()
    print(f"Status: {result.get('status')}")
    print(f"Results: {len(result.get('result', {}).get('results', []))}")
    print()

    if result.get("status") == "success":
        for i, r in enumerate(result.get("result", {}).get("results", [])[:3], 1):
            print(f"[{i}] Similarity: {r.get('similarity', 0):.4f}")
            print(f"    {r.get('content', '')[:100]}...")
            print()
    else:
        print(f"Error: {result.get('message', 'Unknown error')}")

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
