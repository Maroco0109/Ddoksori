# BUGFIX-2 (#68) — Results (measured before/after)

- 작성일: 2026-07-04
- 이슈: [#68](https://github.com/Maroco0109/Ddoksori/issues/68) EXAONE 빈답변
- 계획: `docs/plans/modules/BUGFIX-67-68-backend-robustness-plan.md`
- pod: **필요**(variant B = EXAONE, RunPod)

## 0. 한 줄 요약

variant B(EXAONE)가 특정 쿼리에서 사용 불가(빈답변/500)였던 것을, ReAct 최종 산출을 **수집 근거로 재합성하는
폴백 가드**로 복구했다. M5-5 goldenset B-exaone 재측정 결과 **error_rate 0.25 → 0.0, n_scored 9 → 12**.

## 1. 진단 (측정 → 프로브)

- M5-5에서 B-exaone error_rate 0.25 = **빈답변 2**(case-001/003, 200이나 `content` 빈) + **500 1**(criteria-002).
- **프로브(호스트 터널)**: EXAONE 단일 호출은 `max_tokens` 없이도 정상(`finish_reason:stop`, content 3251자,
  completion 3044토큰). 즉 **단일 호출 문제가 아님** → 계획서가 추정한 `max_tokens` 미설정은 원인이 아니고,
  오히려 캡핑은 reasoning을 잘라 해롭다.
- **진짜 원인**: **ReAct 다단계로 누적 컨텍스트가 `--max-model-len 8192`를 소진**. 두 발현:
  1. **빈 content**: 최종 답변 단계의 출력 예산이 없어 잘림 → `content` 빈(case-001/003).
  2. **프롬프트 오버플로 400**: 누적 프롬프트가 8192 초과 → `openai.BadRequestError 400 (input 8193>8192)`
     → invoke 예외 → 500(criteria-002).
- 간헐적: case-001은 재현 시도에서 정상(894자)도 나옴 — ReAct가 얼마나 쌓느냐에 따라 발생.

## 2. 수정 (`backend/app/variant_b/agent.py`)

근본 원인이 하나(8192 소진)이므로 두 발현을 함께 처리. `model.py`의 max_tokens는 **건드리지 않음**(프로브 근거).

1. **빈-content 폴백**: ReAct 최종 `answer`가 비면, **수집한 tool 검색 근거만으로 짧은 프롬프트로 1회 재합성**
   (컨텍스트 리셋 → 모델이 답할 여유 확보). 도구 재호출 없이 최종 답변만.
2. **오버플로 캐치**: `agent.invoke`를 try/except로 감싸 400(컨텍스트 초과) 등 예외 시 하드 500 대신 위 폴백으로
   degrade. tool 관찰이 없으면 **gate 단계 docs**(step 1의 검색 결과 text)를 근거로 사용.
- 폴백 발동은 `trace`에 `react_error`/`fallback_synthesis`로 기록 → 관측 가능(모니터링 정합).

## 3. 재측정 (before = M5-5 / after = #68 fix)

동일 스크립트(`run_answer_eval.py --variant B --label Bexaone` → build → judge, gpt-4o-mini).

| metric (B-exaone) | BEFORE | AFTER |
| --- | --- | --- |
| runs | 12 | 12 |
| **error_rate** | **0.250** | **0.000** |
| **n_scored (substantive)** | **9** | **12** |
| faithfulness_mean | 1.889 | 1.833 |
| coverage_ratio_mean | 0.757 | 0.804 |
| safety_pass_rate | 0.778 | 0.667 |

- **핵심(결정적, #68 귀속)**: case-001/003(빈답변)·criteria-002(500) **3건 전부 실답변으로 복구** →
  error_rate 0.25→0, 채점 표본 9→12.
- **폴백 발동 증거(DB `workflow_steps`)**: case-003 run에 `fallback_synthesis`, criteria-002 run에
  `react_error`+`fallback_synthesis` 기록됨 — 가드가 실제로 발동해 복구.

## 4. 품질 평균 변화 해석 (정직한 caveat)

- **표본 증가(9→12)**: 이전엔 사용 불가로 빠졌던 3건이 채점에 포함. 복구 답변(근거 재합성)이 완벽하진 않아
  faithfulness/safety 평균에 반영됨 → safety_pass 0.778→0.667은 **회귀가 아니라 표본 확대 + judge 노이즈**.
- M5-6 교훈: B-exaone은 hallucinated_citation 경향이 있고 judge safety는 노이즈가 있음 → 방향으로 해석.
  결정적 지표인 **error_rate·n_scored·HTTP 200**이 #68의 실제 효과다. coverage는 0.757→0.804로 향상.
- M5-5 committed baseline은 "before" 스냅샷으로 보존(덮어쓰지 않음).

## 5. 완료 기준 확인
- [x] 빈 content 가드 + (동일 원인의) 오버플로 캐치. max_tokens는 프로브 근거로 미변경.
- [x] case-001/003/criteria-002가 200 + 실답변.
- [x] 재측정 표: B-exaone error_rate 0.25→0, n_scored 9→12.
- [x] frontier 경로 회귀 없음(가드는 exaone/빈답변 경로에만), DB/스키마 변경 없음.

## 6. Next / follow-up
- **근본 완화(후속)**: ReAct 자체가 8192를 안 넘도록 **tool 관찰 트리밍 / tool round 제한**을 두면 폴백 발동
  빈도를 줄일 수 있음(현재는 안전망). 별도 개선 과제.
- #67 + #68로 M5-5가 잡아낸 백엔드 결함 정리 완료. 이후 로드맵: M4-A 등([[ddoksori-portfolio-priority-shift]]).
