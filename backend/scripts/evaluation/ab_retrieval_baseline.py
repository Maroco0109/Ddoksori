# -*- coding: utf-8 -*-
"""
M2-4R A/B Retrieval Eval Harness (standalone, minimal deps).

Measures retrieval quality (nDCG@k, HitRate@k, MRR) of variant A's CORE retriever
on a fixed, id-labeled graded eval set, by calling the SAME SQL function A uses
(`search_hybrid_rrf`) directly. A's runtime code is NOT imported or modified;
this script only reads from the DB.

Deps: psycopg2-binary, openai, python-dotenv (minimal venv; no app stack).

Eval set JSONL (one object per line):
  {
    "id": "law-001",
    "domain": "law|criteria|case",
    "query": "...",
    "relevant": [{"chunk_id": "...", "grade": 2}, {"chunk_id": "...", "grade": 1}]
  }
  grade scale: 2 = highly relevant, 1 = partially relevant, 0 = not relevant (omit).

Usage:
  python backend/scripts/evaluation/ab_retrieval_baseline.py \
    --eval-set backend/data/golden_set/ab_retrieval_eval.jsonl \
    --variant A --k 5 10 --rrf-k 10 \
    --out backend/data/golden_set/ab_retrieval_baseline_A.json \
    --report backend/data/golden_set/ab_retrieval_baseline_A.md
"""

import argparse
import json
import math
import os
import statistics
from datetime import datetime
from typing import Dict, List

import psycopg2
from dotenv import load_dotenv
from openai import OpenAI

EMBED_MODEL = "text-embedding-3-large"
EMBED_DIM = 1536


def embed(client: OpenAI, text: str) -> List[float]:
    return (
        client.embeddings.create(model=EMBED_MODEL, input=text, dimensions=EMBED_DIM)
        .data[0]
        .embedding
    )


def retrieve_chunk_ids(cur, query: str, emb: List[float], top_k: int, rrf_k: int) -> List[str]:
    """Variant A core retriever: the exact SQL function A uses, no filters, no expansion."""
    cur.execute(
        "SELECT chunk_id FROM search_hybrid_rrf("
        "%s::text, %s::vector(1536), NULL::varchar(20), NULL::varchar(50), "
        "NULL::varchar(20), NULL::integer, %s::integer, %s::integer)",
        (query, str(emb), top_k, rrf_k),
    )
    return [r[0] for r in cur.fetchall()]


def dcg(relevances: List[float], k: int) -> float:
    return sum(rel / math.log2(i + 2) for i, rel in enumerate(relevances[:k]))


def ndcg_at_k(relevances: List[float], k: int) -> float:
    ideal = sorted(relevances, reverse=True)
    idcg = dcg(ideal, k)
    return dcg(relevances, k) / idcg if idcg > 0 else 0.0


def hit_rate_at_k(relevances: List[float], k: int) -> float:
    return 1.0 if any(r >= 1 for r in relevances[:k]) else 0.0


def mrr(relevances: List[float]) -> float:
    for i, r in enumerate(relevances):
        if r >= 1:
            return 1.0 / (i + 1)
    return 0.0


def load_eval_set(path: str) -> List[Dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="M2-4R A/B retrieval eval (variant A core retriever).")
    ap.add_argument("--eval-set", required=True)
    ap.add_argument("--variant", default="A")
    ap.add_argument("--k", type=int, nargs="+", default=[5, 10])
    ap.add_argument("--rrf-k", type=int, default=10)
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", default=None)
    ap.add_argument("--env", default=os.path.join(os.getcwd(), ".env"))
    ap.add_argument("--db-host", default=os.getenv("EVAL_DB_HOST", "localhost"))
    ap.add_argument("--db-port", type=int, default=int(os.getenv("EVAL_DB_PORT", "5432")))
    ap.add_argument("--db-name", default=os.getenv("EVAL_DB_NAME", "ddoksori"))
    ap.add_argument("--db-user", default=os.getenv("EVAL_DB_USER", "postgres"))
    ap.add_argument("--db-password", default=os.getenv("EVAL_DB_PASSWORD", "postgres"))
    args = ap.parse_args()

    if os.path.exists(args.env):
        load_dotenv(args.env)  # OPENAI_API_KEY only

    samples = load_eval_set(args.eval_set)
    max_k = max(args.k)
    client = OpenAI()
    conn = psycopg2.connect(
        host=args.db_host, port=args.db_port, dbname=args.db_name,
        user=args.db_user, password=args.db_password,
    )
    cur = conn.cursor()

    per_query = []
    agg: Dict[str, List[float]] = {}
    for k in args.k:
        agg[f"ndcg@{k}"] = []
        agg[f"hit_rate@{k}"] = []
    agg["mrr"] = []

    for s in samples:
        grade_map = {r["chunk_id"]: float(r.get("grade", 1)) for r in s.get("relevant", [])}
        emb = embed(client, s["query"])
        retrieved = retrieve_chunk_ids(cur, s["query"], emb, max_k, args.rrf_k)
        relevances = [grade_map.get(cid, 0.0) for cid in retrieved]

        row = {"id": s["id"], "domain": s.get("domain", ""), "n_labeled": len(grade_map)}
        for k in args.k:
            row[f"ndcg@{k}"] = ndcg_at_k(relevances, k)
            row[f"hit_rate@{k}"] = hit_rate_at_k(relevances, k)
            agg[f"ndcg@{k}"].append(row[f"ndcg@{k}"])
            agg[f"hit_rate@{k}"].append(row[f"hit_rate@{k}"])
        row["mrr"] = mrr(relevances)
        agg["mrr"].append(row["mrr"])
        per_query.append(row)

    cur.close()
    conn.close()

    summary = {m: (statistics.fmean(v) if v else None) for m, v in agg.items()}
    payload = {
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "variant": args.variant,
        "eval_set": args.eval_set,
        "n_queries": len(samples),
        "k_values": args.k,
        "rrf_k": args.rrf_k,
        "embed_model": EMBED_MODEL,
        "retriever": "search_hybrid_rrf (core, no expansion, no filters)",
        "summary": summary,
        "per_query": per_query,
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    if args.report:
        lines = [
            f"# A/B Retrieval Baseline — variant {args.variant}",
            "",
            f"- timestamp: {payload['timestamp']}",
            f"- eval set: `{args.eval_set}` ({len(samples)} queries)",
            f"- retriever: {payload['retriever']}, rrf_k={args.rrf_k}, embed={EMBED_MODEL}",
            "",
            "## Summary (mean)",
            "",
            "| metric | value |",
            "| --- | --- |",
        ]
        for m, v in summary.items():
            lines.append(f"| {m} | {v:.4f} |" if v is not None else f"| {m} | - |")
        lines += ["", "## Per-domain (mean nDCG@10 / HitRate@10)", "", "| domain | n | nDCG@10 | HitRate@10 |", "| --- | --- | --- | --- |"]
        domains: Dict[str, List[Dict]] = {}
        for r in per_query:
            domains.setdefault(r["domain"], []).append(r)
        for d, rs in sorted(domains.items()):
            nd = statistics.fmean([r["ndcg@10"] for r in rs]) if any("ndcg@10" in r for r in rs) else 0.0
            hr = statistics.fmean([r["hit_rate@10"] for r in rs]) if any("hit_rate@10" in r for r in rs) else 0.0
            lines.append(f"| {d} | {len(rs)} | {nd:.4f} | {hr:.4f} |")
        with open(args.report, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    print(f"variant={args.variant} n={len(samples)} summary={json.dumps(summary, ensure_ascii=False)}")
    print(f"saved: {args.out}" + (f" , {args.report}" if args.report else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
