# M8 결과 — A(결정론) vs A-hub(LLM 슈퍼바이저 라우팅) 격리 측정

- 작성일: 2026-07-05
- 목적: "A의 슈퍼바이저가 LLM 라우팅 대신 결정론 라우팅으로 동결된 것"이 정당했는지를 **숫자로** 검증.
- 방법: dead code로 남아있던 LLM 라우팅 경로를 A-hub variant(routing_mode="llm")로 부활 → 동일 그래프에서 결정론-A vs LLM-A-hub를 격리 측정.
- 데이터: quality_eval_v1 goldenset 12문항 × (A, A-hub). A-hub 라우팅 모델 = gpt-4o(config 기본, A-hub에 유리한 강모델). 로컬 격리 인스턴스(:8001)에서 실행, DB 적재 후 read-only 집계.

## 1. 측정 결과 (실측)

### 요청 수준

| variant | n | error_rate | latency avg | p50 | p95 | max | 답변 평균 길이 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **A (결정론)** | 12 | 0% | **10.8s** | 11.4s | 12.7s | 14.3s | 745자 |
| **A-hub (LLM/gpt-4o)** | 12 | 0% | **18.9s** | 17.1s | 19.7s | 36.5s | 737자 |

→ A-hub는 **latency +74%**(avg 10.8s→18.9s, 요청당 +약 8s), 답변 길이·품질은 사실상 동일.

### 라우팅 결정 계측 (A-hub, gpt-4o)

| 지표 | 값 |
| --- | --- |
| 라우팅 결정 총계 | 60 (12문항 × 평균 5스텝) |
| **결정론과 일치율** | **60/60 = 100%** |
| fallback(무효/파싱실패) | 0 (0%) |
| 라우팅 LLM latency | avg 1.42s, p95 2.18s (결정당) |

→ LLM 슈퍼바이저는 결정론 라우터와 **완전히 동일한 결정**을 내렸다(query_analyst→retrieval_team→answer_drafter→legal_reviewer→respond). 요청당 +8s는 곧 **5스텝 × 1.4s 라우팅 LLM 오버헤드**다.

## 2. 핵심 결론

**이 파이프라인에서 LLM 슈퍼바이저 라우팅은 결정론 라우팅을 100% 그대로 재현하면서 지연·비용만 추가하는 순수 오버헤드다.** 파이프라인이 본질적으로 선형(분석→검색→생성→검토→응답)이라 라우팅에 "판단"할 여지가 거의 없기 때문. 즉 A를 결정론으로 동결한 것은 정당했고, 측정으로 뒷받침된다:

- **지연**: A-hub +74%(요청당 +8s). 라우팅 LLM 호출이 스텝마다 누적.
- **비용**: A-hub는 요청당 +5 gpt-4o 호출(총 60회) — 결정 변화 0.
- **품질**: 경로가 동일하므로 답변 품질 동등(길이 745 vs 737).
- **신뢰성(모델 민감도)**: 강모델(gpt-4o)은 0 에러지만, **약모델(gpt-4o-mini) 스모크에서는 LLM이 query_analyst를 반복 선택해 루프→반복상한→에러 답변**(1문항에서 라우팅 11회 중 10회 결정론과 불일치, ~48s). 즉 LLM 라우팅은 모델 품질에 취약하고 실패 모드가 존재한다.

이는 Anthropic "Building Effective Agents"의 **workflow vs agent** 교훈과 일치한다: 선형 파이프라인은 workflow(결정론 조율)가 낫고, 자율 agent(LLM 라우팅/tool-calling)는 필요할 때만. A/B(=결정론 workflow vs ReAct agent) 대비의 실증적 근거.

## 3. 공정성 caveat (측정 중 교정)

A-hub에 불리하지 않도록 측정 전 두 가지를 교정했다(코드 커밋에 반영):

1. **계측 유실 교정**: 타이밍 래퍼가 trace를 덮어써 라우팅 계측이 사라지던 것을 supervisor state 경유로 적재.
2. **파서 버그 교정(공정성)**: 원본 dead code의 JSON 파서가 `"request": {}` 중첩 빈 객체를 먼저 잡아 gpt-4o의 **유효한** 결정을 전부 무효 처리(→불리)하던 것을 outermost 객체 추출로 수정. 이 교정 후 gpt-4o 일치율 0%→100%.

즉 위 결과는 "약한 원본 구현" 탓이 아니라 **파서를 고쳐 LLM에 최선의 조건을 준 상태에서도** LLM 라우팅이 결정론을 재현할 뿐 이득이 없음을 보인다.

- caveat: 표본 12문항(quality set), dispute 도메인. gpt-4o-mini 실패 모드는 스모크(1문항) 근거. 대규모/타 도메인 재현은 후속.

## 4. 재현 방법

```bash
# 백엔드(격리 인스턴스): SUPERVISOR_LLM_ENABLED=true, SUPERVISOR_LLM_MODEL=gpt-4o
psql ... -f backend/app/database/migrations/012_workflow_runs_variant_ahub.sql
python backend/scripts/evaluation/run_answer_eval.py --variant A     --label A    --session-prefix m8 --eval-set backend/data/golden_set/quality_eval_v1.jsonl
python backend/scripts/evaluation/run_answer_eval.py --variant A-hub --label Ahub --session-prefix m8 --eval-set backend/data/golden_set/quality_eval_v1.jsonl
PYTHONPATH=backend python backend/scripts/evaluation/m8_routing_report.py --session-prefix m8
```

관련: [A 결정 기록](../../architecture/2026-07-05-a-orchestration-decision.md), [mainline 결정 프레임워크](M7-mainline-decision-framework.md).
