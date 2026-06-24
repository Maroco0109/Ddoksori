# M5-1 답변 본문 영속화 (계획서 + migration 초안)

- 작성일: 2026-06-24
- 모듈: `M5-1` 답변 본문 영속화 (품질 평가의 선결)
- 선행: `M3-3`(`workflow_runs`), `M3-5`(`retrieval_events`), B canonical=EXAONE(PR #55)
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md` §M5 (품질 평가)
- 성격: **설계 문서 + `011_workflow_runs_answer.sql` 초안.** 실제 적용·저장 코드·라이브 검증은 M5-1 구현(후속). A 무변경(read-only로 answer 읽기), B 무변경.

## 0. 한 줄 요약

`workflow_runs`에 **`answer TEXT` 컬럼을 추가**하고 동기 `/chat`의 A·B가 답변 본문을 저장한다. 이로써 run마다 **(query, answer, contexts=retrieval_events)** 삼요소가 갖춰져 **reference-free 답변 품질 평가**(faithfulness/answer-relevance, goldenset 없이도 가능)의 선결이 완성된다.

## 1. 범위

### 목표 (M5-1)
- run의 답변 본문 저장 → 조회 가능(`get_run_detail`에 자동 포함).
- 절단 없는 **전문** 저장(평가용).

### 비목표
- 실제 적용·저장 코드·라이브 검증 = M5-1 **구현**(후속 PR).
- cited sources/citations 저장 = 보류(faithfulness는 answer vs `retrieval_events`로 평가 가능). 필요 시 M5-follow.
- 평가 지표/judge 구현 = M5-4·M5-5. 본 모듈은 **데이터 선결**만.
- 스트리밍 `/chat/stream`(현재 `save_workflow_run` 미적용, M3-3-follow와 함께).

## 2. 설계

- **저장 위치**: `workflow_runs`에 `answer TEXT` 컬럼 추가(run 1:1, 결정). 절단 없음(Postgres TOAST가 처리).
- **출처**:
  - A: `final_state["final_answer"]`(chat.py에서 `answer` 변수, 이미 read-only 가용).
  - B: `b_result["answer"]`.
- **저장 경로**: 기존 `save_workflow_run(...)`에 `answer` 인자 추가. 동기 `/chat`의 B·A-success에서 전달. A-error는 답변 없음(NULL).
- **best-effort**: 기존 save 경로 그대로(실패해도 `/chat` 안 깨짐). A/B 로직 무변경.
- **clarify/blocked**: 반환된 메시지(clarify 질문/안전 fallback)가 answer로 저장됨 — status/clarified/blocked 플래그로 구분 가능(품질 평가 시 success만 필터).

## 3. Migration 초안 (`011_workflow_runs_answer.sql` — 본 PR은 문서)

```sql
-- ============================================================
-- 011_workflow_runs_answer.sql
-- 품질 평가 선결: workflow_runs에 답변 본문 컬럼 추가 (M5-1)
-- ⚠️ 수동 실행. workflow_runs(005) 선행 필요.
-- ============================================================

ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS answer TEXT;

COMMENT ON COLUMN workflow_runs.answer IS '생성된 답변 본문(전문). 품질 평가(faithfulness/relevance)용. clarify/blocked는 해당 메시지';

DO $$ BEGIN RAISE NOTICE '✓ 011_workflow_runs_answer.sql: workflow_runs.answer added'; END $$;
```

## 4. 구현 시 변경 대상 (M5-1 구현 PR)

| 파일 | 변경 |
| --- | --- |
| `backend/app/database/migrations/011_workflow_runs_answer.sql` | 신규(force-add) |
| `backend/app/observability/workflow_runs.py` | `save_workflow_run`/`insert_run`에 `answer` 인자 + INSERT 컬럼 추가 |
| `backend/app/api/chat.py` | B: `answer=b_result["answer"]`, A success: `answer=answer` 전달 |

## 5. 완료 기준 / 검증 (구현 시)

- [ ] `011` 적용 + `\d workflow_runs`에 `answer` 컬럼 확인.
- [ ] A run → `workflow_runs.answer`에 전문 저장(절단 없음).
- [ ] B run(EXAONE) → answer 저장.
- [ ] `GET /observability/runs/{id}`의 `run`에 `answer` 포함.
- [ ] (query, answer, retrieval_events) 삼요소가 한 run에서 조회됨 → 평가 입력 준비.
- [ ] best-effort: 저장 실패해도 `/chat` 200. A/B 로직 diff 0.

## 6. Next gate → M5-2 / M5-5

- **M5-2**: 평가 goldenset schema(검색 relevance + 답변 적합성 라벨). M4-A schema 확장.
- **M5-5(가능)**: answer가 저장되면 **goldenset 없이도** reference-free LLM-judge(faithfulness: answer가 retrieval_events chunk에 근거하는가 / answer-relevance: query에 부합하는가)를 먼저 붙일 수 있다. human goldenset(M5-3)은 judge 검증·retrieval relevance용으로 후속.
