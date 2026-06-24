# M3-7 guardrail event 저장 (계획서 + migration 초안)

- 작성일: 2026-06-24
- 모듈: `M3-7` guardrail event 저장 (입력/출력 보안 판단)
- 선행: `M3-1`~`M3-6` (`workflow_runs`/`steps`/`retrieval_events`/`llm_calls`, `run_id` 표준, A frozen·B 계측 패턴)
- 상위 계획: §M3 (L119)
- 성격: **설계 문서 + `009_guardrail_events.sql` 초안.** 실제 적용·저장 코드·라이브 검증은 M3-7 구현(후속). A 무변경(read-only), B는 guardrail reason 계측만 추가.
- 비고: **M3 저장 계층의 마지막 테이블**(이후 M3-8 조회 API).

## 0. 한 줄 요약

run의 **보안 판단(guardrail)** 을 `guardrail_events` N행으로 저장한다. **A는 input_guardrail·output_guardrail(moderation) + review(규칙기반 법적/콘텐츠 위반) 3종**을 `_node_timings.output_snapshot`에서 read-only로 구성, **B는 guardrail_input·output 2종**(`run_b`에 moderation reason/categories 계측 추가). `decision`(pass/block/flag) + `reason` + `detail` JSONB로 A/B 차단/통과 사유를 SQL 비교한다.

## 1. 범위

### 목표 (완료 기준 = roadmap L119)
- `009_guardrail_events.sql` 설계(FK→`workflow_runs`).
- A·B의 block/pass + reason 저장 → **조회 가능**.

### 비목표
- 실제 적용·저장 코드·라이브 검증 = M3-7 **구현**(후속 PR).
- guardrail **정책 변경**(차단 기준·moderation 설정): 판단을 기록만, 동작 무변경.
- 조회 API = M3-8, 스트리밍 `/chat/stream`.

## 2. 컬럼 설계 + 출처 매핑

| 컬럼 | 타입 | 출처 | 비고 |
| --- | --- | --- | --- |
| `event_id` | `UUID PK DEFAULT gen_random_uuid()` | (생성) | |
| `run_id` | `UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE` | M3-3 | run 종속 |
| `seq` | `INTEGER NOT NULL` | 판단 순서 | |
| `stage` | `VARCHAR(12) NOT NULL` | input/output/review | guardrail 위치 |
| `source` | `VARCHAR(16) NOT NULL` | moderation/legal_review | A/B 공통 primitive |
| `decision` | `VARCHAR(8) NOT NULL` | block/flag/pass | 차단/플래그/통과 |
| `reason` | `TEXT` | A=guardrail_type/violation types / B=flagged categories | |
| `detail` | `JSONB` | A review=violations / B=categories | 상세 |
| `created_at` | `TIMESTAMP DEFAULT NOW()` | | |

제약·인덱스: `INDEX(run_id)`, `INDEX(stage)`, `INDEX(decision)`, `UNIQUE(run_id, seq)`, `stage` CHECK(input/output/review), `decision` CHECK(block/flag/pass).

## 3. A 매핑 (3종, read-only from `_node_timings.output_snapshot`)

M3-4가 수집한 node output_snapshot에서 노드별 값을 읽는다(A 무변경). (`graph.py` NODE_SNAPSHOT_FIELDS 기준)

| stage | source | 노드 | snapshot 필드 | decision / reason |
| --- | --- | --- | --- | --- |
| `input` | moderation | `input_guardrail` | `guardrail_blocked`, `guardrail_type` | block if blocked else pass; reason=`guardrail_type` |
| `output` | moderation | `output_guardrail` | `guardrail_blocked` | block if blocked else pass; reason=(type 미표면 → NULL) |
| `review` | legal_review | `review` | `review.passed`, `review.violations[]` | block/flag if not passed else pass; reason=violation types, detail=violations |

- **노드 실행 판정**: 해당 노드가 `_node_timings`에 있으면(=실행) 행 생성.
- output_guardrail snapshot엔 `guardrail_type`이 없음(graph.py:70) → output reason NULL(caveat).
- review는 현재 규칙기반(`ENABLE_LLM_REVIEW=false`)이며 `violations`(type/match)를 detail로 저장.

## 4. B 매핑 (2종, run_b reason 계측 — 결정)

현재 B trace의 `guardrail_input`/`guardrail_output`은 `{blocked, flagged, duration_ms}`만. 변경:
- `run_b`의 `check_input`/`check_output` `ModerationResult`에서 **flagged categories**(true인 항목)를 trace 항목에 추가(`categories`/`reason`). B만 수정, 동작 무변경.
- `chat.py`가 B trace의 guardrail 스텝으로 events 구성: stage=input/output, source=moderation, decision=block if blocked else (flag if flagged else pass), reason=flagged categories, detail=categories.

## 5. Migration 초안 (`009_guardrail_events.sql` — 본 PR은 문서)

```sql
-- ============================================================
-- 009_guardrail_events.sql
-- Agent/RAG workflow 관측: 입력/출력 보안 판단 (M3-7)
-- ⚠️ 수동 실행. workflow_runs(005) 선행 필요.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS guardrail_events (
    event_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
    seq         INTEGER      NOT NULL,
    stage       VARCHAR(12)  NOT NULL,
    source      VARCHAR(16)  NOT NULL,
    decision    VARCHAR(8)   NOT NULL,
    reason      TEXT,
    detail      JSONB,
    created_at  TIMESTAMP    DEFAULT NOW(),
    UNIQUE (run_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_guardrail_events_run      ON guardrail_events(run_id);
CREATE INDEX IF NOT EXISTS idx_guardrail_events_stage    ON guardrail_events(stage);
CREATE INDEX IF NOT EXISTS idx_guardrail_events_decision ON guardrail_events(decision);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_guardrail_events_stage') THEN
        ALTER TABLE guardrail_events ADD CONSTRAINT check_guardrail_events_stage
            CHECK (stage IN ('input','output','review'));
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_guardrail_events_decision') THEN
        ALTER TABLE guardrail_events ADD CONSTRAINT check_guardrail_events_decision
            CHECK (decision IN ('block','flag','pass'));
    END IF;
END $$;

COMMENT ON TABLE guardrail_events IS '입력/출력 보안 판단 (A/B 공통, M3-7)';
COMMENT ON COLUMN guardrail_events.stage IS 'input/output(moderation) / review(legal_review)';
COMMENT ON COLUMN guardrail_events.decision IS 'block/flag/pass';
COMMENT ON COLUMN guardrail_events.reason IS 'A=guardrail_type/violation types, B=flagged categories';
COMMENT ON COLUMN guardrail_events.detail IS 'review violations / moderation categories (JSONB)';

DO $$ BEGIN RAISE NOTICE '✓ 009_guardrail_events.sql: guardrail_events table ready'; END $$;
```

## 6. 구현 시 변경 대상 (M3-7 구현 PR)

| 파일 | 변경 |
| --- | --- |
| `backend/app/database/migrations/009_guardrail_events.sql` | 신규(force-add) |
| `backend/app/observability/guardrail_events.py` | 신규 `save_guardrail_events` + `build_a_guardrail_events(node_timings)` + `build_b_guardrail_events(trace)` |
| `backend/app/variant_b/agent.py` | guardrail trace에 moderation categories/reason 추가 (B만) |
| `backend/app/api/chat.py` | A: `node_timings` snapshot으로 events. B: `run_b` trace로 events. |

## 7. 완료 기준 점검 (구현 시 검증)

- [ ] `009` 적용 + `\d guardrail_events`(FK/UNIQUE/CHECK/인덱스).
- [ ] A run → input/output/review 행, decision/reason 조회(완료기준 L119).
- [ ] B run → guardrail input/output 행, **reason 채워짐**(categories 계측).
- [ ] decision별 A/B 집계(예: stage별 block rate A vs B).
- [ ] best-effort: 저장 실패해도 `/chat` 200.
- [ ] A 로직 diff 0(read-only; B는 reason 계측만).

## 8. caveat / 인계

- **A output reason NULL**: output_guardrail snapshot에 `guardrail_type` 미포함 → output 차단 사유는 NULL(상세는 후속에 A 노출 필요).
- **차단 사례 희소**: 정상 쿼리는 대부분 `pass` → block/flag 검증은 유해 입력 샘플로 별도 확인.

## 9. Next gate → M3-8

조회 API 최소 구현(read-only): 최근 run 목록 + run detail(steps/retrieval/llm/guardrail join). M3 저장 계층(M3-3~M3-7)을 소비. M3 모니터링 백본 마무리.
