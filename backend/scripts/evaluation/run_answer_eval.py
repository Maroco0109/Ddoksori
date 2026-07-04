# -*- coding: utf-8 -*-
"""M5-5 step 1: run the quality goldenset through /chat to persist answers.

Reuses the live `/chat` endpoint (no new execution path): each goldenset query
is POSTed once, which triggers the existing M5-1/M3 persistence
(`workflow_runs.answer` + `retrieval_events`). Runs are tagged by a dedicated
`session_id = m5-5-<label>-<id>` so the build step (build_answer_eval_log.py)
can unambiguously pick them out of the DB — including telling B-frontier from
B-exaone, which both store `variant='B'`.

Model selection for variant B (frontier vs exaone) is a BACKEND concern: the
backend reads `VARIANT_B_MODEL_SPEC` at request time. So switch it on the
backend, then point this driver at the matching label. Typical passes:

  # backend up (VARIANT_B_MODEL_SPEC irrelevant for A):
  python backend/scripts/evaluation/run_answer_eval.py --variant A --label A

  # backend up with VARIANT_B_MODEL_SPEC=frontier:
  python backend/scripts/evaluation/run_answer_eval.py --variant B --label Bfrontier

  # backend up with VARIANT_B_MODEL_SPEC=exaone + EXAONE tunnel healthy:
  python backend/scripts/evaluation/run_answer_eval.py --variant B --label Bexaone

Bounded + sequential (12 queries). Idempotent per (label): re-running overwrites
the same session_id runs; the build step keeps the latest by created_at.
"""

import argparse
import json
import os
import sys
import time

import requests


def load_eval_set(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="M5-5 run goldenset through /chat (persist answers).")
    ap.add_argument("--eval-set", default="backend/data/golden_set/quality_eval_v1.jsonl")
    ap.add_argument("--variant", choices=["A", "B"], required=True)
    ap.add_argument("--label", required=True,
                    help="session tag component, e.g. A / Bfrontier / Bexaone")
    ap.add_argument("--api", default=os.getenv("EVAL_API_BASE", "http://localhost:8000"))
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--chat-type", default="dispute", choices=["dispute", "general"])
    ap.add_argument("--timeout", type=int, default=120,
                    help="per-request timeout (s); EXAONE runs can be slow")
    args = ap.parse_args()

    rows = load_eval_set(args.eval_set)
    url = args.api.rstrip("/") + "/chat"
    print(f"[run] {len(rows)} queries -> {url} variant={args.variant} label={args.label}")

    ok, failed = 0, 0
    for i, s in enumerate(rows):
        qid = s.get("id")
        session_id = f"m5-5-{args.label}-{qid}"
        body = {
            "message": s["query"],
            "session_id": session_id,
            "chat_type": args.chat_type,
            "top_k": args.top_k,
            "variant": args.variant,
        }
        t0 = time.time()
        try:
            r = requests.post(url, json=body, timeout=args.timeout)
            dt = (time.time() - t0) * 1000.0
            if r.status_code == 200:
                data = r.json()
                ans = (data.get("answer") or data.get("final_answer") or "")
                ok += 1
                print(f"  [{i+1:2}/{len(rows)}] {qid} {session_id} "
                      f"{r.status_code} {dt:.0f}ms answer_len={len(ans)}")
            else:
                failed += 1
                print(f"  [{i+1:2}/{len(rows)}] {qid} {session_id} "
                      f"HTTP {r.status_code} {r.text[:150]}")
        except Exception as e:
            failed += 1
            print(f"  [{i+1:2}/{len(rows)}] {qid} {session_id} ERROR {type(e).__name__}: {e}")

    print(f"[run] done: ok={ok} failed={failed}. runs persisted with session_id prefix "
          f"'m5-5-{args.label}-'. Next: build_answer_eval_log.py")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
