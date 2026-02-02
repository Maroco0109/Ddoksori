# -*- coding: utf-8 -*-
"""Smoke test for LawRetrievalAgent.process()."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for path in (str(ROOT), str(BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)


def _load_env() -> None:
    env_path = BACKEND / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


def main() -> int:
    _load_env()

    from backend.app.agents.retrieval.law_agent import LawRetrievalAgent

    agent = LawRetrievalAgent()
    expanded_queries = [
        "중고 거래 중 배송 중 훼손",
        "배송 중 훼손 시 배상 책임",
        "중고 거래 배송 중 훼손 배상 범위",
        "배송 중 사고 판매자 책임 법령",
        "배송 중 훼손 소비자 배상",
    ]
    request = {
        "context": {
            "user_query": "저는 중고 그래픽 카드를 구매했는데, 배송 과정에서 파손된 것 같습니다. 이 경우 제가 판매자에게 대금을 환불받거나 손해배상을 청구할 수 있는 방법이 무엇인지 알고 싶습니다. 특히, 배송 중 파손 위험에 대해 판매자가 어떤 책임을 져야 하는지 궁금합니다.",
            "query_analysis": {},
            "retrieval_task_input": {
                "expanded_queries": expanded_queries,
                "agent_keywords": ["환불", "손해배상", "배송", "파손"],
                "metadata_filter": {
                    "dataset_type": "law_guide",
                    "document_types": ["법률", "시행령"],
                    "categories": None,
                },
                "top_k": 5,
                "ignore_threshold": False,
            },
        },
    }

    result = agent.process(request)
    if hasattr(result, "__await__"):
        import asyncio

        result = asyncio.run(result)

    payload = {
        "queries": {
            "user_query": request["context"]["user_query"],
            "expanded_queries": expanded_queries,
            "agent_keywords": request["context"]["retrieval_task_input"][
                "agent_keywords"
            ],
        },
        "result": result,
    }
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = (
        ROOT
        / "backend"
        / "logs"
        / "law_agent_log"
        / f"law_agent_test_result_{timestamp}.json"
    )
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
