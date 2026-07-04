# -*- coding: utf-8 -*-
"""M5-6 step 3: answer-quality judge <-> human agreement.

Joins the filled human worksheet (quality_answer_human_labels.jsonl) to the M5-5
judge scores (quality_answer_scores.json) by (label, id) and measures, per axis,
how well the judge agrees with the human:

  - faithfulness (0/1/2): exact / binary(>=1) agreement + Cohen's kappa
  - coverage    (per key_point 0/1): pointwise exact agreement + kappa (over all
    (run, key_point) pairs)
  - hallucinated_citation (0/1): exact agreement + kappa

Generalizes the M5-4 cohen_kappa (which hard-coded 0/1/2) to infer categories,
so the same routine serves the 3-cat and binary axes. Also lists disagreements
to feed rubric refinement. Read-only over M5-5 artifacts.

M5-4b caveat carried in: faithfulness is near-constant in this set, so kappa is
unstable there (kappa paradox) — read its % agreement as the headline.

Usage:
  python backend/scripts/evaluation/agreement_answer_quality.py \
    --labels backend/data/golden_set/quality_answer_human_labels.jsonl \
    --scores backend/data/golden_set/quality_answer_scores.json \
    --out backend/data/golden_set/quality_answer_agreement.json
"""

import argparse
import json


def cohen_kappa(pairs):
    """Chance-corrected agreement over (a, b) pairs; categories inferred."""
    n = len(pairs)
    if n == 0:
        return None
    cats = sorted({c for ab in pairs for c in ab})
    po = sum(1 for a, b in pairs if a == b) / n
    pe = 0.0
    for c in cats:
        pa = sum(1 for a, _ in pairs if a == c) / n
        pb = sum(1 for _, b in pairs if b == c) / n
        pe += pa * pb
    return round((po - pe) / (1 - pe), 4) if pe < 1 else 1.0


def confusion(pairs):
    cats = sorted({c for ab in pairs for c in ab})
    return {f"h{h}_j{j}": sum(1 for a, b in pairs if a == h and b == j)
            for h in cats for j in cats}


def axis_stats(pairs, binary=False):
    n = len(pairs)
    if n == 0:
        return {"n": 0}
    exact = round(sum(1 for a, b in pairs if a == b) / n, 4)
    out = {"n": n, "exact_agreement": exact, "cohen_kappa": cohen_kappa(pairs),
           "confusion": confusion(pairs)}
    if binary:
        out["binary_agreement"] = round(sum(1 for a, b in pairs if (a >= 1) == (b >= 1)) / n, 4)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="M5-6 answer-quality judge<->human agreement.")
    ap.add_argument("--labels", default="backend/data/golden_set/quality_answer_human_labels.jsonl")
    ap.add_argument("--scores", default="backend/data/golden_set/quality_answer_scores.json")
    ap.add_argument("--out", default="backend/data/golden_set/quality_answer_agreement.json")
    args = ap.parse_args()

    judge = {(r["label"], r["id"]): r
             for r in json.load(open(args.scores, encoding="utf-8"))["per_run"]}
    humans = [json.loads(l) for l in open(args.labels, encoding="utf-8") if l.strip()]

    faith_pairs, cov_pairs, hall_pairs = [], [], []
    disagreements = []
    skipped = []
    for h in humans:
        key = (h["label"], h["id"])
        j = judge.get(key)
        if not j or j.get("errored"):
            skipped.append(key)
            continue

        hf, jf = h.get("h_faithfulness"), j.get("faithfulness")
        if hf is not None and jf is not None:
            faith_pairs.append((int(hf), int(jf)))
            if int(hf) != int(jf):
                disagreements.append({"axis": "faithfulness", **dict(zip(("label", "id"), key)),
                                      "human": int(hf), "judge": int(jf)})

        hc, jc = h.get("h_coverage") or [], j.get("coverage") or []
        for i, (a, b) in enumerate(zip(hc, jc)):
            if a is not None and b is not None:
                cov_pairs.append((int(a), int(b)))
                if int(a) != int(b):
                    disagreements.append({"axis": "coverage", **dict(zip(("label", "id"), key)),
                                          "key_point": i, "human": int(a), "judge": int(b)})

        hh, jh = h.get("h_hallucinated_citation"), j.get("hallucinated_citation")
        if hh is not None and jh is not None:
            hall_pairs.append((int(hh), int(jh)))
            if int(hh) != int(jh):
                disagreements.append({"axis": "hallucinated_citation", **dict(zip(("label", "id"), key)),
                                      "human": int(hh), "judge": int(jh)})

    out = {
        "n_records": len(humans),
        "faithfulness": axis_stats(faith_pairs, binary=True),
        "coverage_pointwise": axis_stats(cov_pairs),
        "hallucinated_citation": axis_stats(hall_pairs),
        "disagreements": disagreements,
        "skipped": [list(k) for k in skipped],
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    summary = {k: {kk: vv for kk, vv in out[k].items() if kk != "confusion"}
               for k in ("faithfulness", "coverage_pointwise", "hallucinated_citation")}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"disagreements: {len(disagreements)} | skipped: {len(skipped)} | saved: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
