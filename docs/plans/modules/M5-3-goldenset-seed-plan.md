# M5-3 human goldenset 시드 라벨링 (계획서)

- 작성일: 2026-06-25
- 모듈: `M5-3` human goldenset 시드 라벨링
- 선행: `M5-2`(평가 goldenset schema), 기존 `ab_retrieval_eval_v2.jsonl`(검색 relevance 12쿼리)
- 상위 계획: §M5 (품질 평가)
- 성격: **데이터 라벨링.** AI 근거기반 초안 → 사용자 검수 → 확정. 코드/DB 변경 없음. pod 불필요.

## 0. 한 줄 요약

기존 12쿼리(law/criteria/case 4개씩)에 M5-2 schema대로 **`key_points`/`must_not`를 부여**해 `backend/data/golden_set/quality_eval_v1.jsonl`을 만든다. **검색 relevance(`relevant[]`)는 기존 파일에서 복사**하고, 답변 라벨은 **AI가 relevant chunk 원문(DB)에 근거해 초안 → 사용자가 법률 정확성 검수·수정 → 확정**. 최종 ground truth는 사용자.

## 1. 범위

### 목표
- 12쿼리 통합 goldenset 레코드 완성(`relevant[]` + `key_points` + `must_not` + 선택 필드).
- M5-4/M5-5가 바로 소비할 `quality_eval_v1.jsonl` 산출.

### 비목표
- 쿼리셋 **확장**(새 쿼리·새 retrieval 라벨) = 후속(시드는 기존 12개만).
- 평가 스크립트(M5-4/M5-5), 코드/DB 변경.

## 2. 라벨링 프로세스 (AI 초안 → 사용자 검수, 결정)

1. **seed**: `ab_retrieval_eval_v2.jsonl`의 각 레코드(`id/domain/query/relevant[]`)를 복사.
2. **AI 근거기반 초안**(제가 수행):
   - 각 쿼리의 **grade=2 relevant chunk 원문**을 5432 DB(`vector_chunks.text`)에서 읽어,
   - `key_points`: 답변이 담아야 할 **핵심 사실 2~4개**를 그 원문에 근거해 작성(환각 방지). 예: "청약철회 기간 7일(전자상거래법 제17조)".
   - `must_not`: baseline `["legal_judgment","certainty_expression","hallucinated_citation"]` + 쿼리별 추가(예: off_topic 위험 시).
   - 선택 필드 `expected_behavior`/`severity`/`category`는 명확할 때만 기입.
3. **사용자 검수**(핵심): 제가 **검수용 표**(쿼리 / grade-2 근거 요약 / 제안 key_points / 제안 must_not)를 제시 → 사용자가 **법률 정확성** 기준으로 승인·수정. 수정분 반영.
4. **확정**: 검수 완료분을 `quality_eval_v1.jsonl`로 기록(JSONL, tracked).

## 3. 산출물

- `backend/data/golden_set/quality_eval_v1.jsonl` — 12레코드, M5-2 통합 schema.
- (검수 보조) 검수 과정/근거 요약은 PR 설명 또는 짧은 results 노트에 기록.

## 4. 완료 기준 / 검증

- [ ] 12레코드 모두 `key_points`(≥1)·`must_not`(≥baseline) 보유, `relevant[]` 보존.
- [ ] 각 `key_points`가 해당 쿼리 grade-2 chunk 원문에 근거(환각 아님) — 검수에서 확인.
- [ ] **사용자 검수·승인 완료**(ground truth 확정).
- [ ] JSONL 파싱 정상, M5-2 schema 필드 일치.
- [ ] 기존 `ab_retrieval_eval_v2.jsonl` **불변**(별도 파일).

## 5. caveat / 인계

- 12쿼리는 **시드(소량 앵커)**. 통계적 대표성보다 judge 검증·smoke 기준. 확장은 후속.
- `key_points`는 "정답 문구"가 아니라 "포함돼야 할 사실" → M5-5 coverage 채점은 의미 일치(LLM-judge) 기준, 문자열 일치 아님.
- `must_not`는 기존 review/guardrail 라벨과 1:1 → M5-5 safety 채점이 review 결과와 비교 가능.

## 6. Next gate → M5-4 / M5-5

- **M5-4**: `relevant[grade]` vs `retrieval_events.top_chunks` → precision@k/nDCG(A/B).
- **M5-5**: `workflow_runs.answer` + contexts vs `key_points`/`must_not` → coverage/faithfulness/safety LLM-judge.
