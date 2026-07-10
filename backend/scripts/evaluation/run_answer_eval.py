# -*- coding: utf-8 -*-
"""Run a goldenset through /chat to persist answers (M5-5 quality; M4-A4 security).

Reuses the live `/chat` endpoint (no new execution path): each goldenset query
is POSTed once, which triggers the existing M5-1/M3 persistence
(`workflow_runs.answer` + `retrieval_events`). Runs are tagged by a dedicated
`session_id = <prefix>-<label>-<id>` so the build step can unambiguously pick
them out of the DB — including telling B-frontier from B-exaone, which both
store `variant='B'`.

The `--session-prefix` selects the campaign namespace:
  - `m5-5` (default) -> quality eval, consumed by build_answer_eval_log.py.
  - `m4a`            -> M4-A security eval; point --eval-set at the security set.

M4-A4 (security runner) typical 1-case smoke:
  python backend/scripts/evaluation/run_answer_eval.py \
    --eval-set backend/data/golden_set/security_eval_v1.jsonl \
    --session-prefix m4a --variant A --label A --limit 1
  # variant B needs the backend's VARIANT_B_MODEL_SPEC set (frontier|exaone);
  # exaone additionally needs the EXAONE pod/tunnel healthy.

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
    ap.add_argument("--variant", choices=["A", "A-hub", "B"], required=True)
    ap.add_argument("--label", required=True,
                    help="session tag component, e.g. A / Bfrontier / Bexaone")
    ap.add_argument("--session-prefix", default="m5-5",
                    help="campaign namespace for session_id (m5-5=quality, m4a=security)")
    ap.add_argument("--limit", type=int, default=None,
                    help="run only the first N cases (e.g. 1 for a smoke run)")
    ap.add_argument("--dry-run", action="store_true",
                    help="build and print request bodies without POSTing (no infra needed)")
    ap.add_argument("--api", default=os.getenv("EVAL_API_BASE", "http://localhost:8000"))
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--chat-type", default="dispute", choices=["dispute", "general"])
    ap.add_argument("--timeout", type=int, default=120,
                    help="per-request timeout (s); EXAONE runs can be slow")
    ap.add_argument("--delay", type=float, default=7.0,
                    help="sleep between requests (s) to stay under the API rate limit")
    args = ap.parse_args()

    rows = load_eval_set(args.eval_set)
    if args.limit is not None:
        rows = rows[: args.limit]
    url = args.api.rstrip("/") + "/chat"
    mode = "DRY-RUN" if args.dry_run else "run"
    print(f"[{mode}] {len(rows)} queries -> {url} variant={args.variant} "
          f"label={args.label} prefix={args.session_prefix}")

    ok, failed = 0, 0
    for i, s in enumerate(rows):
        qid = s.get("id")
        session_id = f"{args.session_prefix}-{args.label}-{qid}"
        body = {
            "message": s["query"],
            "session_id": session_id,
            "chat_type": args.chat_type,
            "top_k": args.top_k,
            "variant": args.variant,
        }
        if args.dry_run:
            ok += 1
            print(f"  [{i+1:2}/{len(rows)}] {qid} session_id={session_id} "
                  f"body={json.dumps(body, ensure_ascii=False)}")
            continue
        if i > 0 and args.delay > 0:
            time.sleep(args.delay)
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

    tail = "(dry-run: nothing persisted)" if args.dry_run else (
        f"runs persisted with session_id prefix '{args.session_prefix}-{args.label}-'.")
    print(f"[{'DRY-RUN' if args.dry_run else 'run'}] done: ok={ok} failed={failed}. {tail}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
