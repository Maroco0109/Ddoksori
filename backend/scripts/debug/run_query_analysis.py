import argparse
import asyncio
import json
import os
import sys
from typing import Any, Dict, Optional


def _parse_onboarding(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid onboarding JSON: {exc}") from exc


def _ensure_backend_on_path() -> None:
    # Allow running directly from repo root without installing the package.
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)


def _run_v1(state: Dict[str, Any]) -> Dict[str, Any]:
    from app.agents.query_analysis.agent import query_analysis_node

    return query_analysis_node(state)


async def _run_v2(state: Dict[str, Any]) -> Dict[str, Any]:
    from app.agents.query_analysis.agent import query_analysis_node_v2

    return await query_analysis_node_v2(state)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the query analysis agent with a sample input."
    )
    parser.add_argument("query", help="User query text")
    parser.add_argument(
        "--chat-type",
        default="general",
        choices=["general", "dispute"],
        help="Chat type for analysis",
    )
    parser.add_argument(
        "--onboarding",
        default=None,
        help='Onboarding JSON (e.g. {"purchase_item":"헬스장 회원권"})',
    )
    parser.add_argument(
        "--v1",
        action="store_true",
        help="Use query_analysis_node (sync, rule-based).",
    )
    args = parser.parse_args()

    _ensure_backend_on_path()

    onboarding = _parse_onboarding(args.onboarding)
    state: Dict[str, Any] = {
        "user_query": args.query,
        "chat_type": args.chat_type,
        "onboarding": onboarding,
    }

    if args.v1:
        result = _run_v1(state)
    else:
        result = asyncio.run(_run_v2(state))

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
