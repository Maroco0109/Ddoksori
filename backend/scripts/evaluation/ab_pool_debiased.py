# -*- coding: utf-8 -*-
"""M2-7R de-biased pooling: system-agnostic, per-domain candidate pool.

The M2-4R label pool was drawn only from A's domain=all retrieval on a
case-dominated corpus, so law/criteria queries got case-heavy labels (penalizing
B's domain routing). This pools each query across ALL domains
(all/law/criteria/case) and unions the candidates, so the right doc TYPE
(법령/별표/사례) is always a labeling candidate regardless of any system's routing.

Output (per query): candidates with snippet + which domains surfaced each, for a
human to RE-JUDGE by topical relevance (doc-type/system agnostic).

Deps: B venv + OPENAI_API_KEY + local pgvector DB. (No model / no pod.)

Usage: python backend/scripts/evaluation/ab_pool_debiased.py \
  --queries backend/data/golden_set/ab_eval_queries.jsonl --per-domain 6 --out /tmp/pool_v2.jsonl
"""

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

DOMAINS = ["all", "law", "criteria", "case"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", required=True)
    ap.add_argument("--per-domain", type=int, default=6)
    ap.add_argument("--snippet", type=int, default=130)
    ap.add_argument("--out", required=True)
    ap.add_argument("--env", default=str(BACKEND_DIR.parent / ".env"))
    args = ap.parse_args()

    if os.path.exists(args.env):
        try:
            from dotenv import load_dotenv
            load_dotenv(args.env)
        except Exception:
            pass

    from app.variant_b.tools import search

    queries = []
    with open(args.queries, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                queries.append(json.loads(line))

    out_rows = []
    for q in queries:
        pool = {}  # chunk_id -> {chunk_id, dataset_type, category, cosine, snippet, domains}
        for dom in DOMAINS:
            docs, _ = search(q["query"], top_k=args.per_domain, domain=dom)
            for d in docs:
                cid = d["chunk_id"]
                if cid not in pool:
                    snip = " ".join((d["text"] or "").split())[: args.snippet]
                    pool[cid] = {
                        "chunk_id": cid, "dataset_type": d["dataset_type"],
                        "category": d["category"], "cosine": round(d["cosine"], 4),
                        "snippet": snip, "domains": [dom],
                    }
                else:
                    pool[cid]["domains"].append(dom)
                    pool[cid]["cosine"] = max(pool[cid]["cosine"], round(d["cosine"], 4))
        cands = sorted(pool.values(), key=lambda x: x["cosine"], reverse=True)
        out_rows.append({"id": q["id"], "domain": q.get("domain", ""), "query": q["query"],
                         "n_candidates": len(cands), "candidates": cands})

    with open(args.out, "w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    total = sum(r["n_candidates"] for r in out_rows)
    print(f"pooled {len(out_rows)} queries, {total} candidates -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
