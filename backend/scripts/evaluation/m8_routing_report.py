# -*- coding: utf-8 -*-
"""M8: A(결정론) vs A-hub(LLM 슈퍼바이저 라우팅) 격리 측정 리포트.

이미 적재된 데이터만 읽는다(read-only, SELECT). run_answer_eval.py로 두 variant를
동일 goldenset에 흘려 넣은 뒤 실행한다:

  # 백엔드: SUPERVISOR_LLM_ENABLED=true, OPENAI_API_KEY 설정 후 기동
  python scripts/evaluation/run_answer_eval.py --variant A     --label A    --session-prefix m8
  python scripts/evaluation/run_answer_eval.py --variant A-hub --label Ahub --session-prefix m8
  python scripts/evaluation/m8_routing_report.py --session-prefix m8

집계:
  - workflow_runs(variant별): n, status(성공/에러), latency avg/p50/p95/max.
  - protocol_events(name='supervisor_routing', A-hub): 라우팅 결정 수/런당,
    fallback율, (비폴백 중) 결정론과의 일치율, reason 분포, 라우팅 LLM latency.

품질(faithfulness/coverage)은 기존 M5 파이프라인(build_answer_eval_log.py +
judge_answer_quality.py)을 variant별로 재사용해 별도 비교한다(본 스크립트 범위 밖).
"""

import argparse
import statistics
import sys
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

from app.common.config import get_config


def _conn():
    return psycopg2.connect(**get_config().database.get_connection_dict())


def _pct(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
    return s[k]


def run_stats(cur, session_prefix: str, variant: str) -> Dict[str, Any]:
    cur.execute(
        """
        SELECT status, total_time_ms
        FROM workflow_runs
        WHERE variant = %s AND session_id LIKE %s
        """,
        (variant, session_prefix + "%"),
    )
    rows = cur.fetchall()
    n = len(rows)
    lat = [r["total_time_ms"] for r in rows if r["total_time_ms"] is not None]
    status_counts: Dict[str, int] = {}
    for r in rows:
        status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1
    err = status_counts.get("error", 0)
    return {
        "variant": variant,
        "n": n,
        "status": status_counts,
        "error_rate": (err / n) if n else None,
        "latency_avg": (statistics.mean(lat) if lat else None),
        "latency_p50": _pct(lat, 50),
        "latency_p95": _pct(lat, 95),
        "latency_max": (max(lat) if lat else None),
    }


def routing_stats(cur, session_prefix: str, variant: str) -> Dict[str, Any]:
    """A-hub 라우팅 결정 계측(protocol_events name='supervisor_routing')."""
    cur.execute(
        """
        SELECT pe.summary AS summary
        FROM protocol_events pe
        JOIN workflow_runs wr ON wr.run_id = pe.run_id
        WHERE pe.name = 'supervisor_routing'
          AND wr.variant = %s
          AND wr.session_id LIKE %s
        """,
        (variant, session_prefix + "%"),
    )
    rows = cur.fetchall()
    decisions = [r["summary"] for r in rows if isinstance(r["summary"], dict)]
    n = len(decisions)
    if n == 0:
        return {"n_decisions": 0}

    fallback = sum(1 for d in decisions if d.get("fallback"))
    non_fb = [d for d in decisions if not d.get("fallback")]
    agree = sum(1 for d in non_fb if d.get("agree"))
    reasons: Dict[str, int] = {}
    for d in decisions:
        reasons[d.get("reason", "?")] = reasons.get(d.get("reason", "?"), 0) + 1
    lat = [
        d["latency_ms"]
        for d in decisions
        if isinstance(d.get("latency_ms"), (int, float))
    ]
    return {
        "n_decisions": n,
        "fallback": fallback,
        "fallback_rate": fallback / n,
        "n_non_fallback": len(non_fb),
        "agree": agree,
        "agree_rate": (agree / len(non_fb)) if non_fb else None,
        "reasons": reasons,
        "routing_latency_avg_ms": (statistics.mean(lat) if lat else None),
        "routing_latency_p95_ms": _pct(lat, 95),
    }


def _fmt(v: Any, nd: int = 1) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def main() -> int:
    ap = argparse.ArgumentParser(description="M8 A vs A-hub routing measurement report")
    ap.add_argument("--session-prefix", default="m8",
                    help="run_answer_eval의 --session-prefix와 동일 (기본 m8)")
    ap.add_argument("--variants", nargs="+", default=["A", "A-hub"])
    args = ap.parse_args()

    conn = _conn()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            runs = [run_stats(cur, args.session_prefix, v) for v in args.variants]
            routing = {
                v: routing_stats(cur, args.session_prefix, v)
                for v in args.variants
                if v == "A-hub"
            }
    finally:
        conn.close()

    print(f"# M8 라우팅 측정 리포트 (session_prefix='{args.session_prefix}')\n")

    print("## 1. 요청 수준 (variant별)\n")
    print("| variant | n | error_rate | latency avg | p50 | p95 | max |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for r in runs:
        print(
            f"| {r['variant']} | {r['n']} | {_fmt(r['error_rate'], 3)} | "
            f"{_fmt(r['latency_avg'], 0)} | {_fmt(r['latency_p50'], 0)} | "
            f"{_fmt(r['latency_p95'], 0)} | {_fmt(r['latency_max'], 0)} | "
        )
    print("\nstatus 분포:")
    for r in runs:
        print(f"- {r['variant']}: {r['status']}")

    print("\n## 2. 라우팅 결정 계측 (A-hub, LLM 슈퍼바이저)\n")
    for v, rt in routing.items():
        if rt.get("n_decisions", 0) == 0:
            print(f"- {v}: 라우팅 결정 이벤트 없음 (A-hub run 미적재 또는 LLM 미가용).")
            continue
        print(f"### {v}")
        print(f"- 라우팅 결정 총계: {rt['n_decisions']}")
        print(f"- fallback: {rt['fallback']} ({_fmt(rt['fallback_rate'], 3)}) "
              f"→ LLM 실패/무효로 결정론 폴백한 비율")
        print(f"- 결정론과 일치(비폴백 중): {rt['agree']}/{rt['n_non_fallback']} "
              f"({_fmt(rt['agree_rate'], 3)})")
        print(f"- reason 분포: {rt['reasons']}")
        print(f"- 라우팅 LLM latency: avg {_fmt(rt['routing_latency_avg_ms'], 0)}ms, "
              f"p95 {_fmt(rt['routing_latency_p95_ms'], 0)}ms")

    print("\n> 품질(faithfulness/coverage)은 M5 파이프라인으로 variant별 재실행해 비교.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
