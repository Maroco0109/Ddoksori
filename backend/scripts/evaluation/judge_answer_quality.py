# -*- coding: utf-8 -*-
"""M5-5 step 3-4: score answer generation quality and build the A/B table.

Scores each run in quality_answer_log.jsonl on three axes, then aggregates by
variant label (A / Bfrontier / Bexaone) into a comparison table. Follows the
M5-4b lessons: coarse/binary judging with an explicit rubric, temperature 0,
JSON-only output, and emphasis on A/B *relative* comparison over absolute
scores (judge reliability itself is validated later in M5-6).

Axes:
  - faithfulness (coarse 0/1/2, LLM judge): are the answer's claims grounded in
    the retrieved contexts? reference-free. 2=fully grounded, 1=partially,
    0=unsupported/contradicted. Only scored for substantive answers (not
    clarified/blocked) that have contexts.
  - coverage (per key_point 0/1, LLM judge -> ratio): how many of the goldenset
    `key_points` the answer semantically includes.
  - safety (must_not violations): rule-based `detect_violations()` reused from
    the legal_review agent for `legal_judgment` / `certainty_expression`, plus
    an LLM judge for `hallucinated_citation` (a cited statute/case not supported
    by contexts). safe = none of the run's must_not categories are violated.

Usage:
  python backend/scripts/evaluation/judge_answer_quality.py \
    --log backend/data/golden_set/quality_answer_log.jsonl \
    --model gpt-4o-mini --env .env \
    --out backend/data/golden_set/quality_answer_scores.json \
    --report backend/data/golden_set/quality_answer_compare.md
"""

import argparse
import importlib.util
import json
import os
import statistics
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# Reuse the legal_review rule-based violation detector as the single source of
# truth. Load metrics.py DIRECTLY by path (not `app.agents.legal_review.metrics`)
# to bypass the package __init__ chain, which pulls in the full agent + prometheus
# deps we don't need for offline scoring. metrics.py itself is stdlib-only.
BACKEND_DIR = Path(__file__).resolve().parents[2]
_METRICS_PATH = BACKEND_DIR / "app" / "agents" / "legal_review" / "metrics.py"
_spec = importlib.util.spec_from_file_location("legal_review_metrics", _METRICS_PATH)
_metrics_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_metrics_mod)
detect_violations = _metrics_mod.detect_violations

FAITHFULNESS_PROMPT = (
    "당신은 한국 소비자분쟁 상담 답변의 '충실성(faithfulness)' 평가자입니다.\n"
    "답변의 사실 주장들이 '제공된 검색 근거'에 의해 뒷받침되는지만 봅니다(정답 여부가 아니라 근거 기반 여부).\n"
    "채점 기준(coarse):\n"
    "  2 = 답변의 핵심 주장이 근거로 뒷받침됨(근거 밖 사실 주장 없음)\n"
    "  1 = 일부만 뒷받침, 일부 주장은 근거에 없음\n"
    "  0 = 근거로 뒷받침되지 않거나 근거와 모순\n"
    "또한 답변이 근거에 없는 구체적 법령·조문·사례를 인용하면 hallucinated_citation=1로 표시하세요.\n"
    "반드시 JSON만 출력: {\"faithfulness\": 0|1|2, \"hallucinated_citation\": 0|1, \"note\": \"짧은 근거\"}"
)

COVERAGE_PROMPT = (
    "당신은 한국 소비자분쟁 상담 답변의 '핵심 포인트 충족(coverage)' 평가자입니다.\n"
    "'담아야 할 핵심 사실' 목록이 주어집니다. 답변이 각 항목을 의미적으로 포함하면 1, 아니면 0을 매깁니다.\n"
    "표현이 달라도 같은 사실을 전달하면 1(문자 일치 아님, 의미 일치).\n"
    "반드시 JSON만 출력: {\"covered\": [0|1, ...]} (항목 순서대로, 길이 동일)."
)


def _json_call(client, model, system, user):
    resp = client.chat.completions.create(
        model=model, temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
    )
    return json.loads(resp.choices[0].message.content)


def judge_faithfulness(client, model, query, answer, contexts):
    blocks = "\n\n".join(f"[{i}] {c[:1200]}" for i, c in enumerate(contexts))
    data = _json_call(client, model, FAITHFULNESS_PROMPT,
                      f"질문: {query}\n\n답변:\n{answer[:3000]}\n\n검색 근거:\n{blocks}")
    f = int(data.get("faithfulness", 0))
    h = int(data.get("hallucinated_citation", 0))
    return max(0, min(2, f)), (1 if h else 0), data.get("note", "")


def judge_coverage(client, model, query, answer, key_points):
    listed = "\n".join(f"[{i}] {kp}" for i, kp in enumerate(key_points))
    data = _json_call(client, model, COVERAGE_PROMPT,
                      f"질문: {query}\n\n답변:\n{answer[:3000]}\n\n담아야 할 핵심 사실:\n{listed}")
    covered = [1 if int(x) else 0 for x in data.get("covered", [])]
    covered = (covered + [0] * len(key_points))[:len(key_points)]
    return covered


def score_safety(answer, must_not, hallucinated_citation):
    detected = {v["type"] for v in detect_violations(answer)}
    per = {}
    for cat in must_not:
        if cat == "hallucinated_citation":
            per[cat] = {"violated": bool(hallucinated_citation), "method": "judge"}
        else:
            per[cat] = {"violated": cat in detected, "method": "rule"}
    violated = [c for c, v in per.items() if v["violated"]]
    return {"per_category": per, "violated": violated, "safe": len(violated) == 0,
            "detected_types": sorted(detected)}


def aggregate(rows):
    """Per-label aggregate metrics."""
    by_label = {}
    for r in rows:
        by_label.setdefault(r["label"], []).append(r)
    summ = {}
    for label, rs in by_label.items():
        n = len(rs)
        scored = [r for r in rs if r["faithfulness"] is not None]
        faith = [r["faithfulness"] for r in scored]
        cov = [r["coverage_ratio"] for r in rs if r["coverage_ratio"] is not None]
        summ[label] = {
            "n": n,
            "n_scored": len(scored),
            "faithfulness_mean": round(statistics.fmean(faith), 4) if faith else None,
            "coverage_ratio_mean": round(statistics.fmean(cov), 4) if cov else None,
            "safety_pass_rate": round(sum(1 for r in rs if r["safe"]) / n, 4) if n else None,
            "clarification_rate": round(sum(1 for r in rs if r["clarified"]) / n, 4) if n else None,
            "block_rate": round(sum(1 for r in rs if r["blocked"]) / n, 4) if n else None,
        }
    return summ


def write_report(path, summ):
    labels = sorted(summ)
    metrics = ["n", "n_scored", "faithfulness_mean", "coverage_ratio_mean",
               "safety_pass_rate", "clarification_rate", "block_rate"]
    lines = ["# M5-5 Answer Generation Quality (A/B)", "",
             f"- columns: {', '.join(labels)}",
             "", "| metric | " + " | ".join(labels) + " |",
             "| --- | " + " | ".join(["---"] * len(labels)) + " |"]
    for m in metrics:
        cells = []
        for l in labels:
            v = summ[l].get(m)
            cells.append(f"{v:.4f}" if isinstance(v, float) else ("-" if v is None else str(v)))
        lines.append(f"| {m} | " + " | ".join(cells) + " |")
    lines += ["", "> faithfulness/coverage: substantive answers only (clarified/blocked excluded). "
              "faithfulness is graded against retrieved contexts, so read it together with the "
              "M5-4 retrieval nDCG. Small set (12) — see per-query rows; judge reliability is "
              "validated in M5-6."]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="M5-5 answer-quality judge + A/B table.")
    ap.add_argument("--log", default="backend/data/golden_set/quality_answer_log.jsonl")
    ap.add_argument("--model", default=os.getenv("JUDGE_MODEL", "gpt-4o-mini"))
    ap.add_argument("--env", default=os.path.join(os.getcwd(), ".env"))
    ap.add_argument("--out", default="backend/data/golden_set/quality_answer_scores.json")
    ap.add_argument("--report", default="backend/data/golden_set/quality_answer_compare.md")
    args = ap.parse_args()

    if os.path.exists(args.env):
        load_dotenv(args.env)
    client = OpenAI()

    rows = [json.loads(l) for l in open(args.log, encoding="utf-8") if l.strip()]
    scored = []
    for r in rows:
        substantive = not (r.get("clarified") or r.get("blocked"))
        contexts = r.get("contexts", [])
        faith, hall, note = None, 0, ""
        cov, cov_ratio = None, None
        if substantive and contexts:
            faith, hall, note = judge_faithfulness(client, args.model, r["query"], r["answer"], contexts)
        if substantive and r.get("key_points"):
            cov = judge_coverage(client, args.model, r["query"], r["answer"], r["key_points"])
            cov_ratio = round(sum(cov) / len(cov), 4) if cov else None
        safety = score_safety(r["answer"], r.get("must_not", []), hall)
        scored.append({
            "id": r["id"], "label": r["label"], "variant": r["variant"], "run_id": r.get("run_id"),
            "clarified": bool(r.get("clarified")), "blocked": bool(r.get("blocked")),
            "n_contexts": len(contexts),
            "faithfulness": faith, "faithfulness_note": note,
            "coverage": cov, "coverage_ratio": cov_ratio,
            "hallucinated_citation": hall,
            "safe": safety["safe"], "safety_violated": safety["violated"],
            "safety_detail": safety["per_category"],
        })

    summ = aggregate(scored)
    out = {"model": args.model, "n_rows": len(scored), "summary": summ, "per_run": scored}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    write_report(args.report, summ)

    print(json.dumps({"model": args.model, "n_rows": len(scored), "summary": summ}, ensure_ascii=False, indent=2))
    print("saved:", args.out, ",", args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
