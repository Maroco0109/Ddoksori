# -*- coding: utf-8 -*-
"""Smoke test for CriteriaRetrievalAgent.process()."""

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

    from backend.app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent

    agent = CriteriaRetrievalAgent()
    expanded_queries = [
        "세탁기 구입 후 2개월 만에 고장 교환 기준",
        "가전제품 초기불량 환불 가능 기간",
        "제품 하자 발생 시 수리/교환/환불 기준",
        "중대한 하자 소비자 분쟁해결기준",
        "내구재 하자 교환 환불 처리",
    ]
    request = {
        "context": {
            "user_query": "구입한 세탁기가 설치 후 두 달 만에 작동불량이 발생했습니다. 교환이나 환불이 가능한지 기준을 알고 싶습니다.",
            "query_analysis": {},
            "retrieval_task_input": {
                "expanded_queries": expanded_queries,
                "agent_keywords": ["세탁기", "고장", "교환", "환불"],
                "metadata_filter": {
                    "dataset_type": "law_guide",
                    "document_types": ["시행규칙", "별표"],
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
        / "criteria_agent_log"
        / f"criteria_agent_test_result_{timestamp}.json"
    )
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
