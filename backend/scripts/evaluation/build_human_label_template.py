# -*- coding: utf-8 -*-
"""M5-6 step 1: build a blank human-label worksheet for judge validation.

Emits the M5-5 **substantive** runs (errored/empty excluded) as a labeling
worksheet, with the judge's scores DELIBERATELY OMITTED so the human labels
without anchoring bias. Each record carries what the labeler needs to judge:
query, answer, key_points (for coverage), and the retrieved contexts (for
faithfulness / hallucinated_citation).

The human fills three fields on the SAME rubric as judge_answer_quality.py:
  - h_faithfulness           : 0 / 1 / 2  (2=근거 뒷받침, 1=일부, 0=미근거·모순)
  - h_coverage               : [0|1, ...] length == len(key_points)
  - h_hallucinated_citation  : 0 / 1  (contexts에 없는 구체적 조문·사례 인용 = 1)

Reads M5-5 outputs (no re-run): quality_answer_log.jsonl (content) +
quality_answer_scores.json (errored flag). Join by (label, id).

Usage:
  python backend/scripts/evaluation/build_human_label_template.py \
    --log backend/data/golden_set/quality_answer_log.jsonl \
    --scores backend/data/golden_set/quality_answer_scores.json \
    --out backend/data/golden_set/quality_answer_human_template.jsonl \
    --ctx-chars 800
"""

import argparse
import json


def main() -> int:
    ap = argparse.ArgumentParser(description="M5-6 blank human-label worksheet (judge scores hidden).")
    ap.add_argument("--log", default="backend/data/golden_set/quality_answer_log.jsonl")
    ap.add_argument("--scores", default="backend/data/golden_set/quality_answer_scores.json")
    ap.add_argument("--out", default="backend/data/golden_set/quality_answer_human_template.jsonl")
    ap.add_argument("--ctx-chars", type=int, default=800, help="truncate each context for readability")
    args = ap.parse_args()

    log = {}
    for line in open(args.log, encoding="utf-8"):
        if line.strip():
            r = json.loads(line)
            log[(r["label"], r["id"])] = r

    scores = json.load(open(args.scores, encoding="utf-8"))
    substantive = [r for r in scores["per_run"] if not r["errored"]]

    rows = []
    for s in substantive:
        r = log.get((s["label"], s["id"]))
        if not r:
            continue
        kps = r.get("key_points", [])
        rows.append({
            "id": r["id"],
            "label": r["label"],
            "query": r["query"],
            "answer": r["answer"],
            "key_points": kps,
            "contexts": [c[: args.ctx_chars] for c in r.get("contexts", [])],
            # --- fill these (judge scores intentionally hidden) ---
            "h_faithfulness": None,               # 0 / 1 / 2
            "h_coverage": [None] * len(kps),      # per key_point: 0 / 1
            "h_hallucinated_citation": None,      # 0 / 1
        })

    rows.sort(key=lambda x: (x["label"], x["id"]))
    with open(args.out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    from collections import Counter
    print(f"wrote {len(rows)} blank label records -> {args.out}")
    print("per label:", dict(Counter(r["label"] for r in rows)))
    print("fill: h_faithfulness (0/1/2), h_coverage ([0|1] per key_point), h_hallucinated_citation (0/1)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
