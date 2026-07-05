# -*- coding: utf-8 -*-
"""M2-6R-① deterministic tool smoke (no model, no pod).

Validates the B tools directly against the local DB:
  - search domain filter (law -> law_guide rows, case -> case rows)
  - verify_citation: present ref -> 확인됨, fake ref -> NOT FOUND
  - get_law_article / get_case_detail return text

Usage (B venv; OPENAI_API_KEY + local pgvector DB):
  python backend/scripts/testing/variant_b/smoke_tools.py --env <repo>/.env
"""

import argparse
import os
import sys
from pathlib import Path

for _k in ("LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING", "LANGCHAIN_TRACING"):
    os.environ[_k] = "false"

BACKEND_DIR = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND_DIR))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=str(BACKEND_DIR.parent / ".env"))
    args = ap.parse_args()
    try:
        from dotenv import load_dotenv
        if os.path.exists(args.env):
            load_dotenv(args.env)
    except Exception:
        pass

    from app.variant_b.tools import (
        get_case_detail,
        get_law_article,
        search,
        search_consumer_disputes,
        verify_citation,
    )

    ok = True

    print("=" * 70)
    print("[1] domain filter")
    for dom, expect in [("law", "law_guide"), ("criteria", "law_guide"), ("case", "case")]:
        docs, mx = search("환불 기준", top_k=5, domain=dom)
        types = {d["dataset_type"] for d in docs}
        passed = bool(docs) and types == {expect}
        ok = ok and passed
        print(f"  domain={dom:8} n={len(docs)} dataset_types={types} max_cos={mx:.3f} -> {'OK' if passed else 'FAIL'}")
    # domain=law/criteria should differ in document_type — spot check via tool output
    print("  search_consumer_disputes(domain=law) sample:")
    print("   ", search_consumer_disputes.invoke({"query": "청약철회", "domain": "law", "top_k": 1})[:160].replace("\n", " "))

    print("=" * 70)
    print("[2] verify_citation")
    present = verify_citation.invoke({"reference": "전자상거래 등에서의 소비자보호에 관한 법률 제35조"})
    fake = verify_citation.invoke({"reference": "존재하지않는소비자법 제999조"})
    p_ok = "확인됨" in present
    f_ok = "NOT FOUND" in fake
    ok = ok and p_ok and f_ok
    print(f"  present ref -> {'OK' if p_ok else 'FAIL'}: {present[:120]}")
    print(f"  fake ref    -> {'OK' if f_ok else 'FAIL'}: {fake[:120]}")

    print("=" * 70)
    print("[3] get_law_article")
    art = get_law_article.invoke({"law_name": "전자상거래", "article_number": "제35조"})
    a_ok = "찾지 못함" not in art and len(art) > 20
    ok = ok and a_ok
    print(f"  -> {'OK' if a_ok else 'FAIL'}: {art[:160].replace(chr(10), ' ')}")

    print("=" * 70)
    print("[4] get_case_detail")
    case = get_case_detail.invoke({"identifier": "crawl_semantic_상담_5110_full_1"})
    c_ok = "찾지 못함" not in case and len(case) > 20
    ok = ok and c_ok
    print(f"  -> {'OK' if c_ok else 'FAIL'}: {case[:160].replace(chr(10), ' ')}")

    print("=" * 70)
    print(f"RESULT: {'ALL OK' if ok else 'SOME FAILED'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
