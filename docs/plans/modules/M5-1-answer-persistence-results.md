# M5-1 답변 본문 영속화 (결과 문서)

- 작성일: 2026-06-24
- 모듈: `M5-1` 답변 본문 영속화 (품질 평가 선결)
- 계획서: `docs/plans/modules/M5-1-answer-persistence-plan.md`
- 상위 계획: §M5
- 성격: 코드 구현 + 라이브 검증. A/B 로직 무변경(answer read-only 전달).

## 0. 한 줄 결론

`workflow_runs`에 `answer TEXT` 컬럼(011)을 추가하고 동기 `/chat`의 A·B가 답변 본문을 저장한다. A(733자)·**B(EXAONE, 1488자)** 전문 저장을 라이브 검증. 이제 run마다 **(query, answer, contexts=retrieval_events)** 삼요소가 갖춰져 reference-free 품질 평가의 선결이 완료됐다.

## 1. 구현 내용

| 파일 | 변경 |
| --- | --- |
| `backend/app/database/migrations/011_workflow_runs_answer.sql` | 신규 (`ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS answer TEXT`) |
| `backend/app/observability/workflow_runs.py` | `save_workflow_run`/`insert_run`에 `answer` 인자 + INSERT 컬럼 |
| `backend/app/api/chat.py` | B: `answer=b_result.get("answer")`, A success: `answer=answer` |

## 2. 라이브 검증 결과 (5432 DB, RunPod EXAONE up)

- 011 적용: `\d workflow_runs`에 `answer text` 확인.
- A success run → `answer` 733자 전문 저장.
- B success run(**EXAONE**) → `answer` 1488자 전문 저장(절단 없음).
- `get_run_detail`의 `run`에 `answer` 포함(1488자) 확인 → 평가 입력(q/a/contexts)이 한 응답에 모임.

```
variant | status  | ans_len | preview
 B      | success |   1488  | 택배 분실 시 보상 요구 대상과 기준은 ...
 A      | success |    733  | [답변 요약] ● 택배사의 과실로 인한 ...
```

| 검증 항목 | 결과 |
| --- | --- |
| 011 적용 + answer 컬럼 | ✅ |
| A run → answer 전문 저장 | ✅ 733자 |
| B run(EXAONE) → answer 전문 저장 | ✅ 1488자 |
| `get_run_detail`에 answer 포함 | ✅ |
| (query, answer, retrieval_events) 삼요소 확보 | ✅ |
| A/B 로직 diff 0 (answer read-only 전달) | ✅ |

(best-effort 비차단은 M3-3에서 검증된 동일 `save_workflow_run` 경로 — answer 인자 추가뿐.)

## 3. Next → M5-5(가능) / M5-2

- answer가 저장됐으므로 **goldenset 없이도** reference-free LLM-judge(faithfulness: answer가 `retrieval_events` chunk에 근거하는가 / answer-relevance: query 부합)를 먼저 붙일 수 있다(M5-5).
- human goldenset(M5-2 schema → M5-3 시드)은 judge 검증 + retrieval relevance(precision@k/nDCG)용으로 후속.
