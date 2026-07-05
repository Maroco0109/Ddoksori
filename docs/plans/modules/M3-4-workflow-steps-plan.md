# M3-4 workflow step 저장 (계획서 + migration 초안)

- 작성일: 2026-06-24
- 모듈: `M3-4` workflow step 저장 (node sequence + latency)
- 선행: `M3-1` 인벤토리, `M3-2` `workflow_runs` 설계, `M3-3` run 저장(라이브 검증, `run_id` 표준)
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md` §M3 (L116)
- 성격: **설계 문서 + `006_workflow_steps.sql` 초안.** 실제 적용·저장 코드·라이브 검증은 M3-4 구현(후속). A 무변경, B는 step 타이머만 추가.

## 0. 한 줄 요약

run 1건의 실행 경로를 **step N행**으로 풀어 저장한다. `workflow_steps`는 `workflow_runs(run_id)`를 FK로 참조하고, 각 step에 **seq·step_name·category·duration_ms**를 둔다. A는 `build_pipeline_summary().per_node`(seq+node+duration)를 그대로 매핑, **B는 `run_b`에 경량 단계 타이머를 추가**해 A와 동등한 step별 latency를 확보한다. `category` 컬럼으로 A 노드와 B 블록을 **공통 범주(guardrail/retrieval/generation/…)** 로 묶어 A/B를 SQL 비교 가능하게 한다.

## 1. 범위

### 목표 (완료 기준 = roadmap L116)
- `006_workflow_steps.sql` 설계(FK to `workflow_runs`).
- A·B의 step 시퀀스 + node별 duration 저장 → **node별 duration 조회 가능**.
- `category`로 A/B step 비교 가능.

### 비목표
- 실제 migration 적용·저장 코드·라이브 검증 = M3-4 **구현**(후속 PR).
- step의 input/output 스냅샷·state_changes 저장(아래 §4 D3) — 무겁고 "duration 조회"에 불필요 → 보류.
- retrieval 결과 품질/유사도 = M3-5 `retrieval_events`. LLM 토큰/provider = M3-6. guardrail 상세 = M3-7. (step은 "무슨 단계가 언제·얼마나" 까지만.)
- 스트리밍 `/chat/stream`, 조회 API, A/B 로직 변경.

## 2. 컬럼 설계 + 출처 매핑

| 컬럼 | 타입 | 출처 (M3-1) | 비고 |
| --- | --- | --- | --- |
| `step_id` | `UUID PK DEFAULT gen_random_uuid()` | (생성) | |
| `run_id` | `UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE` | M3-3 `workflow_runs.run_id` | run 삭제 시 step도 삭제 |
| `seq` | `INTEGER NOT NULL` | A `per_node[].seq` (`graph.py:231`) / B trace 순서 | run 내 실행 순서 |
| `step_name` | `VARCHAR(64) NOT NULL` | A `per_node[].node` / B `trace[].step` | 원문 노드/단계명 |
| `category` | `VARCHAR(16) NOT NULL` | (매핑, §3) | A 노드·B 블록 공통 범주 |
| `duration_ms` | `DOUBLE PRECISION` (nullable) | A `_node_timings[node].duration_ms` (`graph.py:284`) / **B 신규 타이머** | B도 채움(결정 ①) |
| `started_at` | `TIMESTAMP` (nullable) | A `_node_timings[node].start` / B 타이머 시작 | 정렬 보조(주 정렬은 seq) |

제약·인덱스:
- `UNIQUE (run_id, seq)` — 중복 방지.
- `INDEX (run_id)` — run별 step 조회.
- `INDEX (category)` — 범주별 집계.
- `category` CHECK: `IN ('guardrail','retrieval','generation','analysis','review','clarify','other')` (매핑이 항상 이 집합 내 값 보장, 미매핑은 `other`).

## 3. category 매핑 (A 노드 ↔ B 블록)

| category | A 노드 (`REGISTERED_NODES`) | B 블록 (`run_b` trace) |
| --- | --- | --- |
| `guardrail` | (모더레이션 단계) | `guardrail_input`, `guardrail_output` |
| `retrieval` | `retrieval_law`, `retrieval_criteria`, `retrieval_case`, `retrieval_merge` | `gate_retrieval` (+ `react` 내 tool 검색은 M3-5에서) |
| `generation` | `generation` | `react` (모델 답변 생성) |
| `analysis` | `query_analysis`, `supervisor` (라우팅) | — |
| `review` | `review` (legal review) | — |
| `clarify` | — | `clarify` |
| `other` | 위 매핑 외 노드 | 위 매핑 외 |

> 매핑은 **구현 시 단일 dict로 고정**(예: `_NODE_CATEGORY = {...}`, B는 step→category dict). A는 노드명 prefix(`retrieval_*`)로 범주화. 이 매핑이 A/B 비교의 핵심 계약이므로 한 곳에서 관리.

## 4. 설계 결정

- **D1. FK + ON DELETE CASCADE.** step은 run에 종속. M3-3 `workflow_runs.run_id`(UUID) 참조. run이 없으면 step도 없음.
- **D2. B 단계 타이머는 `run_b` 내부에만 추가(결정 ①).** A 무변경 원칙 유지. `guardrail_input/gate_retrieval/clarify/react/guardrail_output` 각 구간을 `perf_counter`로 감싸 trace 항목에 `duration_ms` 추가. 반환 trace에 step별 duration이 실리고, chat.py가 이를 `workflow_steps`로 저장.
- **D3. 스냅샷 보류.** `NodeTimingLog.input_snapshot/output_snapshot/state_changes`(`rag_logger.py:243-245`)는 저장하지 않는다(무겁고 회귀비교 핵심 아님). 필요 시 후속에서 `meta JSONB` 추가 재검토.
- **D4. category CHECK 유지하되 총함수 매핑.** 매핑이 항상 허용집합 값을 반환하므로 CHECK 위반→best-effort 침묵 드롭 위험 없음.
- **D5. 저장은 batch insert + best-effort 비차단(M3-3 패턴 재사용).** run 1건의 step N행을 한 번에 INSERT, 실패해도 `/chat` 안 깨짐.

## 5. Migration 초안 (`006_workflow_steps.sql` — 본 PR은 문서, 적용은 구현)

```sql
-- ============================================================
-- 006_workflow_steps.sql
-- Agent/RAG workflow 관측: run 내 step(node) 시퀀스 + latency (M3-4)
-- ⚠️ 수동 실행. workflow_runs(005) 선행 필요.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS workflow_steps (
    step_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id       UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
    seq          INTEGER      NOT NULL,
    step_name    VARCHAR(64)  NOT NULL,
    category     VARCHAR(16)  NOT NULL,
    duration_ms  DOUBLE PRECISION,
    started_at   TIMESTAMP,
    UNIQUE (run_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_workflow_steps_run      ON workflow_steps(run_id);
CREATE INDEX IF NOT EXISTS idx_workflow_steps_category ON workflow_steps(category);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_workflow_steps_category') THEN
        ALTER TABLE workflow_steps ADD CONSTRAINT check_workflow_steps_category
            CHECK (category IN ('guardrail','retrieval','generation','analysis','review','clarify','other'));
    END IF;
END $$;

COMMENT ON TABLE workflow_steps IS 'run 내 step(node) 시퀀스 + latency (A/B 공통, M3-4)';
COMMENT ON COLUMN workflow_steps.run_id IS 'workflow_runs FK (ON DELETE CASCADE)';
COMMENT ON COLUMN workflow_steps.seq IS 'run 내 실행 순서 (0-based)';
COMMENT ON COLUMN workflow_steps.step_name IS '원문 노드/단계명 (A node / B trace step)';
COMMENT ON COLUMN workflow_steps.category IS '공통 범주 (guardrail/retrieval/generation/analysis/review/clarify/other)';
COMMENT ON COLUMN workflow_steps.duration_ms IS 'step 실행 시간 (ms). A=node_timings, B=run_b 타이머';

DO $$ BEGIN RAISE NOTICE '✓ 006_workflow_steps.sql: workflow_steps table ready'; END $$;
```

## 6. 구현 시 변경 대상 (M3-4 구현 PR)

| 파일 | 변경 |
| --- | --- |
| `backend/app/database/migrations/006_workflow_steps.sql` | 신규(force-add; DB dir gitignore) |
| `backend/app/observability/workflow_steps.py` | 신규 `save_workflow_steps(run_id, steps[])` (batch, best-effort) + category 매핑 |
| `backend/app/variant_b/agent.py` | B 단계 `perf_counter` 타이머 추가 → trace에 `duration_ms` |
| `backend/app/api/chat.py` | A: `per_node`/`node_timings`로 step 구성·저장. B: `run_b` trace로 step 구성·저장. `workflow_runs` 저장 직후. |

## 7. 완료 기준 점검 (구현 시 검증)

- [ ] `006` 적용 + `\d workflow_steps`(FK/UNIQUE/CHECK/인덱스) 확인.
- [ ] A run → step N행, `SELECT step_name, category, duration_ms ... WHERE run_id=… ORDER BY seq` 로 node별 duration 조회.
- [ ] B run → step 행 + **duration_ms 채워짐**(타이머), category 매핑 확인.
- [ ] `category`별 A/B 집계 쿼리 동작(예: retrieval 평균 latency A vs B).
- [ ] best-effort: steps 저장 실패해도 `/chat` 200.
- [ ] A 파이프라인 로직 diff 0(B는 타이머만, 동작 무변경).

## 8. Next gate → M3-5

`retrieval_events` 저장(top-k/result count/similarity). step의 `retrieval` 범주를 자식으로 확장. A=S3 Retrieval/Structured 로그, B=`gate_retrieval` + `react` tool 검색(현재 step에선 미분해).
