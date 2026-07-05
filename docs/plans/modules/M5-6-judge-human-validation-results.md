# M5-6 answer-quality judge ↔ reference 일치도 — Results

- 작성일: 2026-07-04
- 모듈: `M5-6` judge 신뢰도 검증 (M5의 마지막 모듈)
- 계획서: `docs/plans/modules/M5-6-judge-human-validation-plan.md`
- 선행: `M5-5`(judge 점수: `quality_answer_scores.json`), `M5-4/4b`(retrieval judge-human kappa 교훈)

## 0. 한 줄 요약

M5-5의 answer-quality judge(gpt-4o-mini)를 **substantive 31건 전수**에 대해 독립 레퍼런스 라벨과 대조해 축별 일치도를 냈다. 결과: **coverage는 신뢰 가능(exact 0.90 / kappa 0.80)**, **faithfulness는 binary만 신뢰(exact 0.87, binary 1.00, 단 graded는 judge가 체계적 과대평가)**, **hallucinated_citation은 보통(exact 0.87 / kappa 0.43, 양방향 불일치)**. 즉 M5-5 A/B/B 지표는 **상대 비교·coverage 중심으로 신뢰**하고, faithfulness 절대값과 safety는 과신하지 않는다.

## 1. 레퍼런스 라벨의 성격 (정직한 한계)

- 이 검증의 레퍼런스는 **AI 에이전트(별도 모델)가 웹으로 실제 한국 법령을 대조해 만든 독립 리뷰어 라벨**이다(사용자 지시로 진행). `law.go.kr`/CaseNote에서 전자상거래법 제17조(7일), 할부거래법 제8조(7일), 방문판매법 제8조(14일), 약관규제법 제6·8·9조, 상법 제137조, 제조물책임법 제3조 등을 검증했다.
- **엄밀히는 "human gold standard"가 아니다.** judge(gpt-4o-mini)와 **독립 리뷰어(web-grounded, 다른 모델)** 간 일치도이며, "judge vs human"이 아니라 **judge vs 독립 교차검증자**로 해석해야 한다. 진짜 human 라벨은 더 강한 근거가 되며, 후속 과제로 남긴다.
- 단일 레퍼런스(IAA 없음), 소량(31) → 결과는 신뢰의 **방향과 대략적 크기**를 주는 것으로 한정 해석.
- rubric은 M5-5 judge 프롬프트와 동일. 레퍼런스 라벨링 시 **judge 점수는 비노출**(anchoring 방지, `build_human_label_template.py`).

## 2. 결과 (judge ↔ reference, n=31 substantive)

| 축 | n | exact | binary | cohen_kappa |
| --- | --- | --- | --- | --- |
| **faithfulness** (0/1/2) | 31 | 0.871 | **1.000** | 0.446 |
| **coverage** (key_point 포인트 단위) | 101 | **0.901** | — | **0.802** |
| **hallucinated_citation** (0/1) | 31 | 0.871 | — | 0.426 |

- 불일치 총 18건. 산출물: `backend/data/golden_set/quality_answer_agreement.json`(축별 confusion + 불일치 목록), 라벨: `quality_answer_human_labels.jsonl`.

## 3. 불일치 패턴 (축별 진단)

### faithfulness — judge가 체계적 과대평가
- 불일치 4건이 **전부 human=1 / judge=2**. judge는 "일부만 근거"인 답을 "완전 근거(2)"로 올려친다.
- **binary(≥1) 일치 = 1.000**: "근거 있음/없음" 이분은 완벽. 등급(2 vs 1) 경계만 불안정.
- kappa 0.446(moderate)은 **kappa paradox** 영향(judge 분포가 2에 편중=29/31) → faithfulness는 **exact/ binary를 headline**으로 읽는다.
- **M5-4b 교훈 재확인**: graded LLM judge는 상향 편향, 절대 등급 과신 금지.

### coverage — 가장 신뢰 가능
- exact 0.901 / kappa 0.802(substantial). 불일치는 대부분 **judge=1 / human=0**(judge가 key_point 충족을 약간 후하게 인정).
- 포인트 단위(101쌍)라 분산이 커 kappa가 안정적 → M5-5의 coverage 결론(예: B-exaone coverage 최고)은 **유효**하게 받아들일 수 있다.

### hallucinated_citation — 보통, 양방향 노이즈
- exact 0.871 / kappa 0.426. 불일치가 **양방향**:
  - reviewer=1 / judge=0: **B-exaone `case-004`, `criteria-003`** — 답변이 contexts에 없는 조문(전자상거래법 제17조 등)을 인용했는데 **judge가 놓침**.
  - reviewer=0 / judge=1: **B-frontier `law-001`, `law-002`** — judge만 hallucination으로 플래그.
- 함의: M5-5의 safety(=must_not 중 hallucination) 수치는 이 축에서 ~13% 오차를 가진다. **judge 단독 hallucination 판정은 과신 금지**, 규칙 기반(legal_judgment/certainty)과 병행 해석.

## 4. M5-5 지표 신뢰도 최종 판정

| M5-5 지표 | 신뢰도 | 사용 지침 |
| --- | --- | --- |
| coverage | **높음** | 절대·상대 모두 사용 가능 |
| faithfulness | **binary/상대만** | "근거 있음" 판정·A/B 비교 OK, 절대 2.0의 "완벽"은 과신 금지 |
| safety(hallucination) | **보통** | A/B 경향 참고, 규칙 기반과 병행, judge 단독 확정 금지 |
| safety(규칙: legal_judgment/certainty) | (검증 대상 아님) | 결정적 regex라 신뢰 |

→ **M5-5의 핵심 결론들은 유지된다**: B-frontier 견고·최속, B-exaone coverage 최고이나 느리고 hallucination·error 많음, A 충실하나 crash. 단 "A faithfulness 2.0 = 완벽"은 상대 비교로만.

## 5. caveat

- **레퍼런스가 human이 아님**(§1) — 가장 큰 한계. judge와 독립 리뷰어의 일치이지 절대 정답과의 일치가 아니다.
- 소량(31), 단일 레퍼런스(IAA 없음), faithfulness 분포 편중(kappa paradox).
- 레퍼런스 라벨도 완벽하지 않음(예: `criteria-003` 품질보증기간은 현행 기준 2년인데 context는 1년 — context-ungrounded vs 사실 정확성 구분 필요). 일부 hallucination 판정은 "grounding(=contexts에 있나)" 정의에 민감.

## 6. Next → M5 종료

- **M5-6 완료 → M5(품질 평가 레이어) 종료.** M5-1~M5-6로 "검색 품질(M5-4) + 답변 품질(M5-5) + judge 신뢰도(M5-6)" 측정 체계 확보.
- 이후: M6(라이브 모니터링) → M4-A. 그리고 배치해둔 백엔드 버그(#67 regex 500 / #68 EXAONE 빈답변)를 "측정된 before/after 개선"으로 처리([[ddoksori-portfolio-priority-shift]]).
- 후속 강화 여지: 진짜 **human 라벨**로 레퍼런스 교체 시 "judge vs human" 정본 확보.
