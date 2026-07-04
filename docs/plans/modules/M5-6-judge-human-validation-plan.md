# M5-6 answer-quality judge ↔ human 일치도 검증 (계획서)

- 작성일: 2026-07-04
- 모듈: `M5-6` answer-quality judge 신뢰도 검증
- 선행: `M5-5`(judge 점수 산출: `quality_answer_scores.json`), `M5-4/4b`(retrieval judge-human kappa 패턴+교훈)
- 상위: §M5 (품질 평가) — M5의 마지막 모듈. 완료 시 M5 종료.
- 성격: **검증 전용.** 새 `/chat` 실행·pod 불필요(M5-5 채점 데이터 재사용). DB/스키마 변경 없음.

## 0. 한 줄 요약

M5-5의 answer-quality judge(faithfulness/coverage/hallucination)가 **human과 얼마나 일치하는지** 표본에 human 라벨을 달아 exact/binary/kappa로 수치화한다. 목적은 M5-5 A/B/B 지표를 **얼마나 신뢰할지**를 정하는 것. M5-4b 교훈대로 binary/coarse 우선, kappa는 신중히 해석.

## 1. 배경 (왜 필요한가)

- M5-5는 A/B/B 답변품질 수치를 냈지만, **judge 자체가 얼마나 맞는지는 미검증**이다.
- M5-4b에서 retrieval judge는 human과 **체계적으로 어긋났다**(kappa 0.18~0.21 fair, 3단계 등급경계 불안정). answer judge도 검증 없이 확정 지표로 쓰면 위험.
- 따라서 M5-5 지표에 신뢰구간을 부여하려면 judge-human 일치도가 선행돼야 한다.

## 2. 범위

### 목표
- M5-5 **substantive 답변 31건 전수**(A 10 / B-frontier 12 / B-exaone 9)에 human 라벨 부착.
- judge vs human 일치도를 **축별**로 산출:
  - **faithfulness** (0/1/2): exact / binary(≥1) / kappa
  - **coverage** (key_point별 0/1): pointwise exact agreement / kappa (포인트 단위)
  - **hallucinated_citation** (0/1): exact / kappa
- 축별 confusion + 불일치 케이스 목록 → judge rubric 개선 근거.

### 비목표
- 새 /chat 실행·pod·retriever/프롬프트 개선.
- **safety 규칙 파트**(`legal_judgment`/`certainty_expression`) 검증 — 이건 결정적 regex(`detect_violations`)라 judge가 아님 → 검증 대상 아님. hallucination judge만 검증.
- 백엔드 버그 수정(#67/#68, M5 완료 후 배치).
- 다중 라벨러/IAA(라벨러는 사용자 1인) — 단일 라벨러 기준.

## 3. 표본·설계 주의 (M5-5 실측 기반)

- substantive 31건은 소량 → **전수 라벨**(표본추출 불필요, 라벨 부담 적음).
- **faithfulness 편중**: judge 분포가 `2`=29건 / `1`=2건 (분산 거의 없음). → **kappa paradox**(높은 일치율에도 kappa가 낮게/불안정하게 나옴) 위험. 따라서 faithfulness는 **% 일치율을 주지표**로, kappa는 참고로. coverage(포인트 단위, 분산 큼)가 kappa 해석에 더 적합.
- 단일 라벨러라 IAA는 못 구함 → 결과는 "judge가 이 라벨러와 얼마나 맞나"로 한정 해석.

## 4. 재사용 자산 (신규 프레임워크 금지)

| 자산 | 역할 | M5-6에서 |
| --- | --- | --- |
| `quality_answer_log.jsonl` | (id, label, query, answer, contexts, key_points, must_not) | 라벨링 워크시트 소스 |
| `quality_answer_scores.json` | judge 점수(faithfulness/coverage/hallucination) | 비교 대상(정답 아님, 비교축) |
| `judge_retrieval_relevance.py::cohen_kappa` | kappa + exact/binary 집계 | 일치도 계산 재사용 |
| `judge_answer_quality.py` rubric 프롬프트 | 채점 기준 문구 | human 라벨 지침과 **동일 rubric** 사용(정합) |

## 5. 작업 단계 (Impl 단계에서 수행)

1. **라벨 워크시트 생성**: `build_human_label_template.py` — `quality_answer_log.jsonl`에서 substantive 31건만 뽑아 라벨용 jsonl 생성. **judge 점수는 숨김**(anchoring bias 방지). 각 레코드에 빈 라벨 필드(`h_faithfulness`, `h_coverage`[key_point별], `h_hallucinated_citation`) + rubric 요약 주석.
2. **human 라벨링(사용자)**: 워크시트를 채운다. 동일 rubric(§M5-5) 적용. 산출: `quality_answer_human_labels.jsonl`.
3. **일치도 산출**: `agreement_answer_quality.py` — human 라벨 ⨝ judge 점수 → 축별 exact/binary/kappa + confusion + 불일치 목록. `cohen_kappa` 재사용.
4. **문서화**: `M5-6-judge-human-validation-results.md` — 축별 일치도 표 + kappa paradox 주석 + 불일치 원인 분류 + M5-5 지표 신뢰도 판정(어느 축을 얼마나 믿을지).

## 6. 산출물 (Impl PR 예정)

- `backend/scripts/evaluation/build_human_label_template.py`
- `backend/scripts/evaluation/agreement_answer_quality.py`
- `backend/data/golden_set/quality_answer_human_template.jsonl` (빈 워크시트)
- `backend/data/golden_set/quality_answer_human_labels.jsonl` (사용자 라벨)
- `backend/data/golden_set/quality_answer_agreement.json` + results 문서

## 7. 완료 기준 / 검증

- [ ] substantive 31건 워크시트 생성(judge 점수 미노출) + 사용자 라벨 완료.
- [ ] faithfulness/coverage/hallucination 축별 exact/binary/kappa 산출.
- [ ] 불일치 케이스 목록 + kappa paradox·소량·단일라벨러 caveat 문서화.
- [ ] M5-5 지표 신뢰도 판정(축별 "믿을 만함/주의") 명시.
- [ ] 새 /chat·pod·DB/스키마 변경 없음, M5-5 데이터 불변.

## 8. Next gate → M5 종료

- M5-6 완료 시 **M5(품질 평가 레이어) 종료.** 이후 우선순위: M6(라이브 모니터링) → M4-A, 그리고 배치해둔 백엔드 버그(#67/#68) 개선을 "측정된 before/after"로 처리([[ddoksori-portfolio-priority-shift]]).

## 9. 열린 결정 (PR 리뷰에서 확정)

- **라벨 범위**: 전수 31건(제안) vs 층화 표본. → 소량이라 전수 권장.
- **coverage 라벨 단위**: key_point별 0/1(제안, judge와 동일 단위) 확정.
- **hallucination 판정 기준**: "근거(contexts)에 없는 구체적 조문·사례 인용"으로 human/judge 동일 정의 확정.
