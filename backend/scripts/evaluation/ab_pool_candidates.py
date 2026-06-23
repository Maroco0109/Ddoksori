# -*- coding: utf-8 -*-
"""
M2-4R labeling helper: pool retrieval candidates for human graded judgment.

For each seed query, runs the core retriever (`search_hybrid_rrf`, no filters) at a
wide top_k and dumps candidate chunks with short snippets, so a human can assign
graded relevance (0/1/2) and build the fixed eval set.

This is the standard IR "pooling" step. Caveat: the pool is drawn from A's hybrid
retriever top_k, so recall is bounded by what that retriever surfaces (documented
limitation of the v1 eval set).

Deps: psycopg2-binary, openai, python-dotenv.

Seed queries JSONL: {"id": "law-001", "domain": "law", "query": "..."}

Usage:
  python backend/scripts/evaluation/ab_pool_candidates.py \
    --queries backend/data/golden_set/ab_eval_queries.jsonl \
    --top-k 15 --snippet 140 \
    --out backend/data/golden_set/ab_pool.jsonl
"""

import argparse
import json
import os
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Pool retrieval candidates for labeling.")
    ap.add_argument("--queries", required=True)
    ap.add_argument("--top-k", type=int, default=15)
    ap.add_argument("--snippet", type=int, default=140)
    ap.add_argument("--rrf-k", type=int, default=10)
    ap.add_argument("--out", required=True)
    ap.add_argument("--env", default=os.path.join(os.getcwd(), ".env"))
    ap.add_argument("--db-host", default=os.getenv("EVAL_DB_HOST", "localhost"))
    ap.add_argument("--db-port", type=int, default=int(os.getenv("EVAL_DB_PORT", "5432")))
    ap.add_argument("--db-name", default=os.getenv("EVAL_DB_NAME", "ddoksori"))
    ap.add_argument("--db-user", default=os.getenv("EVAL_DB_USER", "postgres"))
    ap.add_argument("--db-password", default=os.getenv("EVAL_DB_PASSWORD", "postgres"))
    args = ap.parse_args()

    if os.path.exists(args.env):
        load_dotenv(args.env)

    queries = []
    with open(args.queries, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                queries.append(json.loads(line))

    client = OpenAI()
    conn = psycopg2.connect(
        host=args.db_host, port=args.db_port, dbname=args.db_name,
        user=args.db_user, password=args.db_password,
    )
    cur = conn.cursor()

    out_rows = []
    for q in queries:
        emb = embed(client, q["query"])
        cur.execute(
            "SELECT chunk_id, dataset_type, category, vector_similarity, text "
            "FROM search_hybrid_rrf(%s::text, %s::vector(1536), NULL::varchar(20), "
            "NULL::varchar(50), NULL::varchar(20), NULL::integer, %s::integer, %s::integer)",
            (q["query"], str(emb), args.top_k, args.rrf_k),
        )
        cands = []
        for cid, ds, cat, cos, text in cur.fetchall():
            snippet = " ".join((text or "").split())[: args.snippet]
            cands.append({
                "chunk_id": cid, "dataset_type": ds, "category": cat,
                "cosine": round(float(cos), 4), "snippet": snippet,
            })
        out_rows.append({"id": q["id"], "domain": q.get("domain", ""), "query": q["query"], "candidates": cands})

    cur.close()
    conn.close()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"pooled {len(out_rows)} queries -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
