# -*- coding: utf-8 -*-
"""
M5-4 secondary: build a retrieval-context log for the quality goldenset.

Reuses variant A's CORE retriever (embed + search_hybrid_rrf) from
ab_retrieval_baseline.py — no new retrieval logic. For each query in the
quality goldenset it records the top-k retrieved chunks (id + text), so the
output can feed both:
  - RAGAS context_relevancy (LLM judge, reference-free), and
  - a judge-vs-human relevance agreement check against the human `relevant[]`.

Output JSONL (one line per query):
  {
    "id": "law-001",
    "user_input": "<query>",
    "retrieved": [{"rank": 0, "chunk_id": "...", "text": "..."}, ...],
    "retrieved_contexts": ["<text>", ...],   # RAGAS-compatible
    "relevant": [{"chunk_id": "...", "grade": 2}, ...]  # human labels (copied)
  }

Usage:
  python backend/scripts/evaluation/build_quality_retrieval_log.py \
    --eval-set backend/data/golden_set/quality_eval_v1.jsonl \
    --top-k 5 --rrf-k 10 --env .env \
    --out backend/data/golden_set/quality_retrieval_log.jsonl
"""

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from openai import OpenAI

# Reuse the exact embed + retrieve logic of the A baseline (no duplication).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ab_retrieval_baseline import embed, retrieve_chunk_ids, load_eval_set  # noqa: E402


def fetch_texts(cur, chunk_ids):
    if not chunk_ids:
        return {}
    cur.execute(
        "SELECT chunk_id, text FROM vector_chunks WHERE chunk_id = ANY(%s)",
        (chunk_ids,),
    )
    return {r[0]: r[1] for r in cur.fetchall()}


def main() -> int:
    ap = argparse.ArgumentParser(description="M5-4 quality retrieval-context log builder (variant A core).")
    ap.add_argument("--eval-set", required=True)
    ap.add_argument("--top-k", type=int, default=5)
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
        load_dotenv(args.env)  # OPENAI_API_KEY only
    client = OpenAI()

    conn = psycopg2.connect(
        host=args.db_host, port=args.db_port, dbname=args.db_name,
        user=args.db_user, password=args.db_password,
    )
    rows = load_eval_set(args.eval_set)
    out_lines = []
    with conn.cursor() as cur:
        for s in rows:
            query = s["query"]
            emb = embed(client, query)
            ids = retrieve_chunk_ids(cur, query, emb, args.top_k, args.rrf_k)
            texts = fetch_texts(cur, ids)
            retrieved = [
                {"rank": i, "chunk_id": cid, "text": texts.get(cid, "")}
                for i, cid in enumerate(ids)
            ]
            out_lines.append({
                "id": s.get("id"),
                "user_input": query,
                "retrieved": retrieved,
                "retrieved_contexts": [r["text"] for r in retrieved],
                "relevant": s.get("relevant", []),
            })
    conn.close()

    with open(args.out, "w", encoding="utf-8") as f:
        for r in out_lines:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(out_lines)} queries -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
