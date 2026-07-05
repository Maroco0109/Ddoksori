# -*- coding: utf-8 -*-
"""M2-5R variant B smoke: ReAct + tool + deterministic cosine clarification gate.

Runs B on a clear query (expects tool call + grounded answer) and an ambiguous
query (expects single-shot clarification). Prints trace.

Usage (B venv with langgraph/langchain-openai; OPENAI_API_KEY + local pgvector DB):
  python backend/scripts/testing/variant_b/smoke_b.py --model frontier --tau 0.45
  python backend/scripts/testing/variant_b/smoke_b.py --model exaone   # needs pod
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Disable LangSmith tracing for the smoke (avoids noisy 403s if a key is in .env).
# Set before load_dotenv (override=False) so .env cannot re-enable it.
for _k in ("LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING", "LANGCHAIN_TRACING"):
    os.environ[_k] = "false"

# Make `app` importable (backend/ is parents[3] of this file)
BACKEND_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND_DIR))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="frontier", choices=["frontier", "exaone"])
    ap.add_argument("--tau", type=float, default=0.45)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--env", default=str(BACKEND_DIR.parent / ".env"))
    ap.add_argument("--query", default=None, help="single query (overrides defaults)")
    args = ap.parse_args()

    try:
        from dotenv import load_dotenv
        if os.path.exists(args.env):
            load_dotenv(args.env)
    except Exception:
        pass

    from app.variant_b.agent import run_b

    queries = (
        [args.query]
        if args.query
        else [
            "온라인으로 산 옷을 단순 변심으로 환불받고 싶은데 가능한가요?",  # clear -> answer
            "도와주세요",  # ambiguous -> clarification
        ]
    )

    for q in queries:
        r = run_b(q, model_spec=args.model, tau=args.tau, top_k=args.top_k)
        print("=" * 70)
        print(f"Q: {q}")
        print(f"  clarified={r['clarified']}  max_cosine={r['max_cosine']:.4f}")
        print(f"  tool_calls={json.dumps(r['tool_calls'], ensure_ascii=False)}")
        print(f"  A: {r['answer'][:600]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
