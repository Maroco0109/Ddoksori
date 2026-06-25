# -*- coding: utf-8 -*-
"""
M5-4 secondary: LLM-judge vs human relevance agreement.

For each query in the quality retrieval log, an LLM grades the relevance of
each top-k retrieved chunk to the query on the SAME 0/1/2 graded scale used by
the human `relevant[]` labels (0=not, 1=partially, 2=highly relevant). We then
measure how well the LLM judge agrees with the human ground truth — the
"judge vs human" cross-validation axis (reference-free judging, scored against
human labels).

This is the lightweight, plan-aligned form of the secondary LLM cross-check
(RAGAS context_relevancy is the same idea via the RAGAS framework). Bounded,
seed-free deterministic prompt, temperature 0.

Metrics (over all retrieved (query, chunk) pairs):
  - exact_agreement: judge grade == human grade
  - binary_agreement: (judge>=1) == (human>=1)
  - cohen_kappa: chance-corrected agreement on the 0/1/2 grades
  - confusion: human-grade x judge-grade counts

Input: quality_retrieval_log.jsonl (build_quality_retrieval_log.py).

Usage:
  python backend/scripts/evaluation/judge_retrieval_relevance.py \
    --log backend/data/golden_set/quality_retrieval_log.jsonl \
    --model gpt-4o-mini --env .env \
    --out backend/data/golden_set/quality_judge_agreement.json
"""

import argparse
import json
import os

from dotenv import load_dotenv
from openai import OpenAI

PROMPT = (
    "당신은 한국 소비자 분쟁 도메인의 검색 평가자입니다. 사용자 질문과 검색된 문서 조각이 주어집니다.\n"
    "각 문서 조각이 질문에 답하는 데 얼마나 관련 있는지 0/1/2로 채점하세요.\n"
    "2 = 질문의 핵심에 직접 답하는 매우 관련 있는 근거, 1 = 부분적으로 관련(보조 근거), 0 = 무관.\n"
    "반드시 JSON만 출력: {\"grades\": [정수, ...]} (조각 순서대로, 길이 동일)."
)


def judge_query(client: OpenAI, model: str, query: str, contexts):
    blocks = "\n\n".join(f"[{i}] {c[:1200]}" for i, c in enumerate(contexts))
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": f"질문: {query}\n\n문서 조각들:\n{blocks}"},
        ],
    )
    data = json.loads(resp.choices[0].message.content)
    grades = [int(g) for g in data.get("grades", [])]
    # pad/trim defensively
    grades = (grades + [0] * len(contexts))[: len(contexts)]
    return [max(0, min(2, g)) for g in grades]


def cohen_kappa(pairs):
    cats = [0, 1, 2]
    n = len(pairs)
    if n == 0:
        return 0.0
    po = sum(1 for a, b in pairs if a == b) / n
    pe = 0.0
    for c in cats:
        pa = sum(1 for a, _ in pairs if a == c) / n
        pb = sum(1 for _, b in pairs if b == c) / n
        pe += pa * pb
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def main() -> int:
    ap = argparse.ArgumentParser(description="M5-4 LLM-judge vs human relevance agreement.")
    ap.add_argument("--log", required=True)
    ap.add_argument("--model", default=os.getenv("JUDGE_MODEL", "gpt-4o-mini"))
    ap.add_argument("--env", default=os.path.join(os.getcwd(), ".env"))
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if os.path.exists(args.env):
        load_dotenv(args.env)
    client = OpenAI()

    rows = [json.loads(l) for l in open(args.log, encoding="utf-8") if l.strip()]
    pairs = []  # (human_grade, judge_grade)
    per_query = []
    for r in rows:
        human = {x["chunk_id"]: int(x.get("grade", 0)) for x in r.get("relevant", [])}
        retrieved = r["retrieved"]
        contexts = [x["text"] for x in retrieved]
        jgrades = judge_query(client, args.model, r["user_input"], contexts)
        qpairs = []
        for x, jg in zip(retrieved, jgrades):
            hg = human.get(x["chunk_id"], 0)
            pairs.append((hg, jg))
            qpairs.append({"chunk_id": x["chunk_id"], "human": hg, "judge": jg})
        per_query.append({"id": r["id"], "pairs": qpairs})

    n = len(pairs)
    exact = sum(1 for a, b in pairs if a == b) / n if n else 0.0
    binary = sum(1 for a, b in pairs if (a >= 1) == (b >= 1)) / n if n else 0.0
    kappa = cohen_kappa(pairs)
    confusion = {f"h{h}_j{j}": sum(1 for a, b in pairs if a == h and b == j)
                 for h in (0, 1, 2) for j in (0, 1, 2)}

    out = {
        "model": args.model,
        "n_pairs": n,
        "n_queries": len(rows),
        "exact_agreement": round(exact, 4),
        "binary_agreement": round(binary, 4),
        "cohen_kappa": round(kappa, 4),
        "confusion": confusion,
        "per_query": per_query,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: out[k] for k in
                      ["model", "n_pairs", "n_queries", "exact_agreement", "binary_agreement", "cohen_kappa"]},
                     ensure_ascii=False))
    print("saved:", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
