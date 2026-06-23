# -*- coding: utf-8 -*-
"""M2-7R A/B comparison runner.

Runs variant B (run_b) per eval query, captures the agent's retrieved chunk_ids
(instrumented), and scores retrieval nDCG@k / HitRate@k / MRR on the SAME eval
set + labels as the M2-4R A baseline. Also reports clarification_rate,
block_rate, and mean latency.

Writes per-model B results to ab_compare_<model>.json, then emits a combined
markdown table (A baseline + every ab_compare_*.json found) to the report path.

Deps: the B venv (langgraph/langchain-openai/psycopg2/openai) + OPENAI_API_KEY +
local pgvector DB. For --model exaone the pod must be up and EXAONE_MODEL set
(e.g. EXAONE_MODEL=LGAI-EXAONE/EXAONE-4.5-33B).

Usage:
  python backend/scripts/evaluation/ab_compare.py --model frontier
  EXAONE_MODEL=LGAI-EXAONE/EXAONE-4.5-33B \
    python backend/scripts/evaluation/ab_compare.py --model exaone
"""

import argparse
import glob
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

for _k in ("LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING", "LANGCHAIN_TRACING"):
    os.environ[_k] = "false"

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

GOLDEN = BACKEND_DIR / "data" / "golden_set"
DEFAULT_EVAL = GOLDEN / "ab_retrieval_eval.jsonl"
A_BASELINE = GOLDEN / "ab_retrieval_baseline_A.json"


def dcg(rels, k):
    return sum(r / math.log2(i + 2) for i, r in enumerate(rels[:k]))


def ndcg_at_k(rels, k):
    ideal = sorted(rels, reverse=True)
    idcg = dcg(ideal, k)
    return dcg(rels, k) / idcg if idcg > 0 else 0.0


def hit_rate_at_k(rels, k):
    return 1.0 if any(r >= 1 for r in rels[:k]) else 0.0


def mrr(rels):
    for i, r in enumerate(rels):
        if r >= 1:
            return 1.0 / (i + 1)
    return 0.0


def load_eval(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def run_b_column(model, eval_rows, k_values, tau, top_k):
    from app.variant_b.agent import run_b

    per_query = []
    agg = {f"ndcg@{k}": [] for k in k_values}
    agg.update({f"hit_rate@{k}": [] for k in k_values})
    agg["mrr"] = []
    latencies, n_clarified, n_blocked, n_scored = [], 0, 0, 0

    for s in eval_rows:
        grade_map = {r["chunk_id"]: float(r.get("grade", 1)) for r in s.get("relevant", [])}
        t0 = time.time()
        r = run_b(s["query"], model_spec=model, tau=tau, top_k=top_k)
        latency_ms = (time.time() - t0) * 1000.0
        latencies.append(latency_ms)

        row = {"id": s["id"], "domain": s.get("domain", ""),
               "clarified": bool(r.get("clarified")), "blocked": bool(r.get("blocked")),
               "latency_ms": round(latency_ms, 1)}
        if r.get("clarified"):
            n_clarified += 1
        elif r.get("blocked"):
            n_blocked += 1
        else:
            retrieved = r.get("retrieved_chunk_ids", [])
            rels = [grade_map.get(cid, 0.0) for cid in retrieved]
            for k in k_values:
                row[f"ndcg@{k}"] = ndcg_at_k(rels, k)
                row[f"hit_rate@{k}"] = hit_rate_at_k(rels, k)
                agg[f"ndcg@{k}"].append(row[f"ndcg@{k}"])
                agg[f"hit_rate@{k}"].append(row[f"hit_rate@{k}"])
            row["mrr"] = mrr(rels)
            row["n_retrieved"] = len(retrieved)
            agg["mrr"].append(row["mrr"])
            n_scored += 1
        per_query.append(row)

    summary = {m: (statistics.fmean(v) if v else None) for m, v in agg.items()}
    summary["clarification_rate"] = n_clarified / len(eval_rows) if eval_rows else 0.0
    summary["block_rate"] = n_blocked / len(eval_rows) if eval_rows else 0.0
    summary["mean_latency_ms"] = statistics.fmean(latencies) if latencies else None
    summary["n_scored"] = n_scored
    return summary, per_query


def a_baseline_summary():
    if not A_BASELINE.exists():
        return None
    return json.loads(A_BASELINE.read_text(encoding="utf-8")).get("summary")


def write_report(report_path, k_values):
    """Combine A baseline + every ab_compare_<model>.json into a markdown table."""
    cols = []
    a = a_baseline_summary()
    if a:
        cols.append(("A (MAS core retriever)", a))
    for p in sorted(glob.glob(str(GOLDEN / "ab_compare_*.json"))):
        data = json.loads(Path(p).read_text(encoding="utf-8"))
        cols.append((f"B-{data['model']}", data["summary"]))

    metrics = []
    for k in k_values:
        metrics += [f"ndcg@{k}", f"hit_rate@{k}"]
    metrics += ["mrr", "clarification_rate", "block_rate", "mean_latency_ms"]

    lines = ["# M2-7R A/B Comparison (retrieval)", "",
             f"- eval set: `{DEFAULT_EVAL.name}` | columns: {', '.join(c[0] for c in cols)}",
             "", "| metric | " + " | ".join(c[0] for c in cols) + " |",
             "| --- | " + " | ".join(["---"] * len(cols)) + " |"]
    for met in metrics:
        cells = []
        for _, summ in cols:
            v = summ.get(met)
            cells.append(f"{v:.4f}" if isinstance(v, (int, float)) else "-")
        lines.append(f"| {met} | " + " | ".join(cells) + " |")
    lines += ["", "> A HitRate/MRR are pooling-inflated (labels drawn from A top-15); "
              "B columns become discriminative. nDCG is the headline. clarified/blocked "
              "queries excluded from retrieval metrics (see clarification_rate/block_rate)."]
    Path(report_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="frontier", choices=["frontier", "exaone"])
    ap.add_argument("--eval-set", default=str(DEFAULT_EVAL))
    ap.add_argument("--k", type=int, nargs="+", default=[5, 10])
    ap.add_argument("--tau", type=float, default=0.45)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--env", default=str(BACKEND_DIR.parent / ".env"))
    ap.add_argument("--report", default=str(GOLDEN / "ab_compare_report.md"))
    args = ap.parse_args()

    if os.path.exists(args.env):
        try:
            from dotenv import load_dotenv
            load_dotenv(args.env)
        except Exception:
            pass

    eval_rows = load_eval(args.eval_set)
    summary, per_query = run_b_column(args.model, eval_rows, args.k, args.tau, args.top_k)

    out = GOLDEN / f"ab_compare_{args.model}.json"
    payload = {"model": args.model, "eval_set": Path(args.eval_set).name,
               "n_queries": len(eval_rows), "k_values": args.k, "tau": args.tau,
               "summary": summary, "per_query": per_query}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(args.report, args.k)

    print(f"model={args.model} n={len(eval_rows)} summary={json.dumps(summary, ensure_ascii=False)}")
    print(f"saved: {out} , {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
