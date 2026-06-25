# M5-3 human goldenset 시드 라벨링 (결과)

- 완료일: 2026-06-25
- 모듈: `M5-3` human goldenset 시드 라벨링
- 산출물: `backend/data/golden_set/quality_eval_v1.jsonl` (12레코드)
- 성격: 데이터 라벨링(AI 근거기반 초안 → 2차 검토 → 사용자 확정). 코드/DB 변경 없음.

## 1. 무엇을 했나

기존 12쿼리(`ab_retrieval_eval_v2.jsonl`, law/criteria/case 4개씩)의 `relevant[]`를 보존 복사하고,
M5-2 통합 schema대로 `key_points` / `must_not` / `expected_behavior` / `severity` / `category`를 부여했다.

- `key_points`는 각 쿼리의 **grade-2 relevant chunk 원문**(5432 DB `vector_chunks.text`, 37개 unique chunk)에 근거해 작성(환각 방지).
- `must_not`은 전 쿼리 공통 baseline `["legal_judgment", "certainty_expression", "hallucinated_citation"]`.
- `severity`는 `normal`.

## 2. 라벨링·검수 프로세스

1. AI 근거기반 초안: grade-2 chunk 원문에서 핵심 사실 추출 → `key_points` 초안.
2. 2차 모델 교차검토(GPT 5.5)로 12쿼리 적합성 판정(적합/조건부/부적합).
3. 지적사항을 실제 법령·소비자분쟁해결기준으로 **웹 검증** 후 반영.
4. ground truth가 도메인 판단에 달린 2건은 사용자 결정으로 확정.

## 3. 교차검토 반영 내역 (웹 검증 근거)

| ID | 지적 | 검증 결과 | 조치 |
| --- | --- | --- | --- |
| law-002 | 간접할부 소비자→신용제공자 통지 누락 | 할부거래법 **제8조③**: 소비자도 신용제공자에 철회 서면 발송해야 효력(발송일) | key_point 추가 |
| law-003 | 서면을 필수로 오인 위험 | 방판법 **제8조④**: 서면은 선택, 발송일 효력 | "필수 아님·입증 위해 권장"으로 reword |
| criteria-002 | 가액 미기재 시 50만원 한도 누락 | 분쟁해결기준/택배 표준약관: 미기재 시 배상한도 50만원 | key_point 추가 |
| criteria-004 | 부대물품/사은품 처리가 현행 기준과 상이 | 현행(2024.12.27 개정)은 사은품 반환 프레임 | **사용자 결정**: 해당 항목 삭제, 검증된 핵심(이용일수+10%)만 유지 |
| case-004 | 인터넷콘텐츠·원격학원 기준 혼합 | 인터넷콘텐츠업(이용일수+10%) ≠ 원격교습/학원(실제 수강분 제외) | **사용자 결정**: 원격교습/학원 기준으로 통일(실제 수강분 제외) |

적합 판정(law-001/004, criteria-001/003, case-001)과 경미 주의(case-002/003)는 원안 유지(case-002는 expected_behavior에 고정값 단정 방지 문구 보강).

## 4. 완료 기준 점검

- [x] 12레코드 모두 `key_points`(≥1)·`must_not`(=baseline 3)·`relevant[]` 보유.
- [x] 각 `key_points`가 해당 쿼리 grade-2 chunk 원문에 근거(환각 아님).
- [x] 2차 모델 교차검토 지적 → 법령 웹 검증 → 반영, 쟁점 2건 사용자 확정(ground truth).
- [x] JSONL 파싱 정상, M5-2 schema 필드 일치.
- [x] 기존 `ab_retrieval_eval_v2.jsonl` 불변(별도 파일).

## 5. Next gate → M5-4 / M5-5

- M5-4: `relevant[grade]` vs `retrieval_events.top_chunks` → precision@k/nDCG(A/B).
- M5-5: `workflow_runs.answer` + contexts vs `key_points`/`must_not` → coverage/faithfulness/safety LLM-judge.
- caveat: 12쿼리는 시드(소량 앵커). 통계적 대표성보다 judge 검증·smoke 기준. 확장은 후속.
