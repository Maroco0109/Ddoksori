# -*- coding: utf-8 -*-
"""M5-5 step 2: build the answer-scoring log by joining DB runs + goldenset.

Reads the runs persisted by run_answer_eval.py (session_id prefix `m5-5-`) from
`workflow_runs`, attaches their retrieved contexts from `retrieval_events`
(chunk_ids -> text via `vector_chunks`, reusing the M5-4 fetch pattern), and
joins each run to its `quality_eval_v1.jsonl` record (key_points / must_not) by
goldenset id parsed from the session_id.

The session_id convention `m5-5-<label>-<id>` carries the variant label so
B-frontier and B-exaone (both `variant='B'` in the DB) stay separable. When a
label+id has multiple runs (re-runs), the latest by `created_at` wins.

Output JSONL (one line per run), the scoring input for judge_answer_quality.py:
  {
    "id": "law-001", "label": "A", "variant": "A", "run_id": "...",
    "query": "...", "answer": "...",
    "clarified": false, "blocked": false,
    "contexts": ["<chunk text>", ...],
    "key_points": ["..."], "must_not": ["legal_judgment", ...]
  }

Usage:
  python backend/scripts/evaluation/build_answer_eval_log.py \
    --eval-set backend/data/golden_set/quality_eval_v1.jsonl --env .env \
    --out backend/data/golden_set/quality_answer_log.jsonl
"""

import argparse
import json
import os

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv


def load_goldenset(path):
    by_id = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                by_id[r["id"]] = r
    return by_id


def parse_session(session_id):
    """m5-5-<label>-<id> -> (label, id). id may contain '-' (e.g. law-001)."""
    if not session_id or not session_id.startswith("m5-5-"):
        return None, None
    rest = session_id[len("m5-5-"):]
    label, sep, qid = rest.partition("-")
    return (label, qid) if sep else (None, None)


def fetch_latest_runs(cur, max_contexts):
    """Latest run per session_id under the m5-5- prefix, with joined contexts."""
    cur.execute(
        """
        SELECT DISTINCT ON (session_id)
               run_id, session_id, variant, status, query, answer, clarified, blocked, created_at
        FROM workflow_runs
        WHERE session_id LIKE 'm5-5-%'
        ORDER BY session_id, created_at DESC
        """
    )
    runs = cur.fetchall()

    out = []
    for run in runs:
        label, qid = parse_session(run["session_id"])
        if not qid:
            continue
        # contexts: aggregate chunk_ids across this run's retrieval_events (dedup, order-preserving)
        cur.execute(
            "SELECT top_chunks FROM retrieval_events WHERE run_id = %s ORDER BY seq",
            (run["run_id"],),
        )
        chunk_ids, seen = [], set()
        for (top_chunks,) in cur.fetchall():
            for c in (top_chunks or []):
                cid = c.get("chunk_id")
                if cid and cid not in seen:
                    seen.add(cid)
                    chunk_ids.append(cid)
        chunk_ids = chunk_ids[:max_contexts]
        texts = fetch_texts(cur, chunk_ids)
        contexts = [texts.get(cid, "") for cid in chunk_ids]
        out.append({
            "run_id": run["run_id"],
            "session_id": run["session_id"],
            "label": label,
            "qid": qid,
            "variant": run["variant"],
            "status": run["status"],
            "query": run["query"],
            "answer": run["answer"] or "",
            "clarified": bool(run["clarified"]),
            "blocked": bool(run["blocked"]),
            "contexts": contexts,
        })
    return out


def fetch_texts(cur, chunk_ids):
    if not chunk_ids:
        return {}
    cur.execute(
        "SELECT chunk_id, text FROM vector_chunks WHERE chunk_id = ANY(%s)",
        (chunk_ids,),
    )
    return {r[0]: r[1] for r in cur.fetchall()}


def main() -> int:
    ap = argparse.ArgumentParser(description="M5-5 answer-eval log builder (DB runs + goldenset).")
    ap.add_argument("--eval-set", default="backend/data/golden_set/quality_eval_v1.jsonl")
    ap.add_argument("--out", default="backend/data/golden_set/quality_answer_log.jsonl")
    ap.add_argument("--max-contexts", type=int, default=10,
                    help="cap contexts per run to bound judge tokens")
    ap.add_argument("--env", default=os.path.join(os.getcwd(), ".env"))
    ap.add_argument("--db-host", default=os.getenv("EVAL_DB_HOST", "localhost"))
    ap.add_argument("--db-port", type=int, default=int(os.getenv("EVAL_DB_PORT", "5432")))
    ap.add_argument("--db-name", default=os.getenv("EVAL_DB_NAME", "ddoksori"))
    ap.add_argument("--db-user", default=os.getenv("EVAL_DB_USER", "postgres"))
    ap.add_argument("--db-password", default=os.getenv("EVAL_DB_PASSWORD", "postgres"))
    args = ap.parse_args()

    if os.path.exists(args.env):
        load_dotenv(args.env)

    goldenset = load_goldenset(args.eval_set)
    conn = psycopg2.connect(
        host=args.db_host, port=args.db_port, dbname=args.db_name,
        user=args.db_user, password=args.db_password,
    )
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        runs = fetch_latest_runs(cur, args.max_contexts)
    conn.close()

    out_rows, missing = [], []
    for r in runs:
        gold = goldenset.get(r["qid"])
        if not gold:
            missing.append(r["qid"])
            continue
        out_rows.append({
            "id": r["qid"],
            "label": r["label"],
            "variant": r["variant"],
            "status": r["status"],
            "run_id": r["run_id"],
            "query": r["query"],
            "answer": r["answer"],
            "clarified": r["clarified"],
            "blocked": r["blocked"],
            "contexts": r["contexts"],
            "key_points": gold.get("key_points", []),
            "must_not": gold.get("must_not", []),
        })

    out_rows.sort(key=lambda x: (x["label"] or "", x["id"]))
    with open(args.out, "w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    labels = sorted({r["label"] for r in out_rows if r["label"]})
    print(f"wrote {len(out_rows)} rows -> {args.out}")
    print(f"labels: {labels}  (rows/label: "
          + ", ".join(f"{l}={sum(1 for r in out_rows if r['label']==l)}" for l in labels) + ")")
    if missing:
        print(f"WARNING: {len(missing)} runs had no goldenset match: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
