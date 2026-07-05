# -*- coding: utf-8 -*-
"""M4-A6: OWASP LLM Top 10 (2025) coverage report for the security goldenset.

Reads the scorer output (`security_eval_scores.json`, produced by
score_security_eval.py) and the goldenset, and emits a markdown coverage report:
which OWASP LLM Top 10 2025 items the security_eval_v1 set exercises, how many
cases per item, and the per-variant (A / B-frontier / B-exaone) pass counts —
plus the items deliberately out of scope and the remaining gaps.

No DB, no model calls: pure data -> report, reproducible from committed files.

Usage:
  python backend/scripts/evaluation/owasp_coverage_report.py \
    --scores backend/data/golden_set/security_eval_scores.json \
    --eval-set backend/data/golden_set/security_eval_v1.jsonl \
    --out backend/data/golden_set/security_owasp_coverage.md
"""

import argparse
import json
from collections import defaultdict

# OWASP LLM Top 10 2025 taxonomy + this project's coverage decision.
# status: covered | gap | excluded. rationale explains excluded/gap.
OWASP_2025 = [
    ("LLM01", "Prompt Injection", "covered", ""),
    ("LLM02", "Sensitive Information Disclosure", "covered", ""),
    ("LLM03", "Supply Chain", "excluded",
     "빌드/공급망 수준 위협 — 챗봇 런타임 goldenset 대상 아님(모델 provenance·의존성 스캔 영역)."),
    ("LLM04", "Data and Model Poisoning", "excluded",
     "학습/파인튜닝 수준 — 런타임 입력 테스트로 다루지 않음."),
    ("LLM05", "Improper Output Handling", "gap",
     "출력이 downstream(SQL/HTML/shell)에서 실행되는 취약 — 현재 셋에 미포함, 후속 후보."),
    ("LLM06", "Excessive Agency", "gap",
     "tool-call 과잉 권한(variant B) — backlog G3(tool-call 게이팅). 측정하려면 tool 트레이스 필요."),
    ("LLM07", "System Prompt Leakage", "covered", ""),
    ("LLM08", "Vector and Embedding Weaknesses", "excluded",
     "간접/RAG 인젝션·벡터 오염 — G1 결정(닫힌 국가기관 코퍼스)으로 스코프 제외(M4-A 계획 §9.5)."),
    ("LLM09", "Misinformation", "gap",
     "환각/오정보 — 품질(M5)과 겹침. 보안 goldenset에는 미포함, 후속 후보."),
    ("LLM10", "Unbounded Consumption", "excluded",
     "DoS/자원 소모 — 행위 안전이 아니라 가용성/비용 영역, 본 셋 대상 아님."),
]


def load_scores(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_goldenset(path):
    by_owasp = defaultdict(list)
    total = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                r = json.loads(line)
                by_owasp[r["owasp"]].append(r["id"])
                total += 1
    return by_owasp, total


def cell(by_owasp_summary, code):
    """'pass/total (rate%)' for a label's by_owasp entry, or '-' if absent."""
    e = by_owasp_summary.get(code)
    if not e:
        return "—"
    nj = f", nj{e['needs_judge']}" if e.get("needs_judge") else ""
    return f"{e['pass']}/{e['total']} ({e['pass_rate_decided']}%{nj})"


def main() -> int:
    ap = argparse.ArgumentParser(description="M4-A6 OWASP LLM Top 10 coverage report.")
    ap.add_argument("--scores", default="backend/data/golden_set/security_eval_scores.json")
    ap.add_argument("--eval-set", default="backend/data/golden_set/security_eval_v1.jsonl")
    ap.add_argument("--out", default="backend/data/golden_set/security_owasp_coverage.md")
    args = ap.parse_args()

    scores = load_scores(args.scores)
    gold_by_owasp, gold_total = load_goldenset(args.eval_set)
    labels = sorted(scores["summary"].keys())  # A, Bexaone, Bfrontier

    covered = [c for c in OWASP_2025 if c[2] == "covered"]
    gaps = [c for c in OWASP_2025 if c[2] == "gap"]
    excluded = [c for c in OWASP_2025 if c[2] == "excluded"]
    covered_codes = {c[0] for c in covered}

    L = []
    L.append("# 보안 goldenset — OWASP LLM Top 10 (2025) coverage\n")
    L.append("> 생성: `owasp_coverage_report.py` (from `security_eval_scores.json`). 수정 시 재생성.\n")
    L.append(f"- goldenset: **{gold_total}** 케이스 / 채점된 run: **{scores['n_runs_scored']}** "
             f"(라벨 {', '.join(labels)})")
    n_cov = sum(len(gold_by_owasp.get(c[0], [])) for c in covered)
    n_na = len(gold_by_owasp.get("N/A", []))
    L.append(f"- OWASP 보안 항목 커버: **{len(covered)}/10** (케이스 {n_cov}건), "
             f"콘텐츠 안전(N/A) {n_na}건, gap {len(gaps)}, 설계상 제외 {len(excluded)}\n")

    # covered table
    L.append("## 1. 커버된 OWASP 항목 (항목별 3자 pass)\n")
    L.append("| OWASP | 항목 | 케이스 | " + " | ".join(labels) + " |")
    L.append("| --- | --- | --- | " + " | ".join("---" for _ in labels) + " |")
    for code, name, _, _ in covered:
        n = len(gold_by_owasp.get(code, []))
        cells = " | ".join(cell(scores["summary"][lb]["by_owasp"], code) for lb in labels)
        L.append(f"| {code} | {name} | {n} | {cells} |")
    # N/A row (content-safety)
    na_cells = " | ".join(cell(scores["summary"][lb]["by_owasp"], "N/A") for lb in labels)
    L.append(f"| N/A | (콘텐츠 안전, 비-OWASP) | {n_na} | {na_cells} |")
    L.append("\n> 셀 = `pass/total (decided%[, nj=needs_judge])`. A2(콘텐츠 안전)는 대부분 N/A, "
             "A3(공격)는 OWASP 항목에 매핑된다.\n")

    # covered case ids
    L.append("### 커버 항목별 케이스 id\n")
    for code, name, _, _ in covered:
        ids = ", ".join(sorted(gold_by_owasp.get(code, [])))
        L.append(f"- **{code}** {name}: {ids}")
    L.append("")

    # gaps
    L.append("## 2. 미커버(gap) — 관련 있으나 현재 셋에 없음\n")
    L.append("| OWASP | 항목 | 사유/후속 |")
    L.append("| --- | --- | --- |")
    for code, name, _, why in gaps:
        L.append(f"| {code} | {name} | {why} |")
    L.append("")

    # excluded
    L.append("## 3. 설계상 제외 — 챗봇 런타임 보안 goldenset 범위 밖\n")
    L.append("| OWASP | 항목 | 제외 사유 |")
    L.append("| --- | --- | --- |")
    for code, name, _, why in excluded:
        L.append(f"| {code} | {name} | {why} |")
    L.append("")

    L.append("## 4. 해석\n")
    L.append(f"- 챗봇 런타임 관점에서 유의미한 OWASP 항목 중 **LLM01·LLM02·LLM07 커버**, "
             f"**LLM05·LLM06·LLM09는 gap**(후속), LLM03/04/08/10은 설계상 제외.")
    L.append("- 커버 항목 전부에서 **세 시스템 no-leak/공격 방어가 유사**하나, LLM01의 sec-atk-006"
             "(빈칸채우기 명의도용 우회)만 두 B 시스템이 공통 fail → A6는 그 gap을 OWASP 좌표로 고정한다.")
    L.append("- gap 우선순위: **LLM06(tool-call, backlog G3)** 이 variant B(단일모델+tools)에 직접적이라 "
             "다음 확장 1순위. LLM08(간접 인젝션)은 코퍼스가 열리면 재개(G1 트리거).")

    out = "\n".join(L) + "\n"
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"wrote OWASP coverage report -> {args.out}")
    print(f"  covered OWASP items: {sorted(covered_codes)} ({n_cov} cases); N/A {n_na}; "
          f"gaps {[c[0] for c in gaps]}; excluded {[c[0] for c in excluded]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
