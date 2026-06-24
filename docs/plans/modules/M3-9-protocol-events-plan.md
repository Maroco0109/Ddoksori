# M3-9 protocol event 저장 (계획서 + migration 초안)

- 작성일: 2026-06-24
- 모듈: `M3-9` protocol event 저장 (A inter-agent 소통 + B ReAct 궤적)
- 선행: `M3-1`~`M3-8` (5개 저장 테이블 + 조회 API, `run_id` 표준, A frozen·B 계측 패턴)
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md` §M3 (확장: M3-8 이후 추가 모듈)
- 성격: **설계 문서 + `010_protocol_events.sql` 초안.** 실제 적용·저장 코드·라이브 검증은 M3-9 구현(후속). A 무변경(read-only), B는 메시지 궤적 distill만 추가.
- 동기: M3 검토에서 확인된 **목표 1(에이전트 소통/e2e 디버깅) 미달** 보완. "Query가 어떤 판단을 거쳐 Answer가 됐나"를 A·B 양쪽에서 쿼리 가능하게 한다.

## 0. 한 줄 요약

run의 **내부 의사결정 궤적**을 `protocol_events` N행으로 저장한다. **A는 supervisor 라우팅/노드별 `protocol_summary`**(`_agent_trace_entries`에서 read-only), **B는 ReAct 메시지 궤적**(`result["messages"]`의 AIMessage 추론+tool_calls, ToolMessage 관찰)을 distill해 기록. A·B가 **하나의 테이블**에서 `kind`로 구분되어 "에이전트가 무슨 판단으로 다음으로 넘겼나 / 모델이 무슨 근거로 도구를 불렀나"를 SQL로 추적한다.

## 1. 범위

### 목표
- A inter-agent 프로토콜(supervisor `next_agent`/`reasoning`, query_analysis `intent` 등) 영속화.
- B ReAct 궤적(모델 reasoning + tool 호출/관찰 순서) 영속화.
- → run 1건의 e2e 의사결정 흐름을 `/observability/runs/{id}`(M3-8 확장) 또는 SQL로 조회.

### 비목표
- 실제 적용·저장 코드·라이브 검증 = M3-9 **구현**(후속 PR).
- A 노드 **계측/수정**(frozen): 이미 만들어지는 `protocol_summary`만 읽는다.
- 답변 본문/품질 평가 = 별도(평가 모듈). 본 모듈은 **과정 추적**만.
- 시각화 UI, 스트리밍 `/chat/stream`.

## 2. 컬럼 설계 + 출처 매핑

| 컬럼 | 타입 | 출처 | 비고 |
| --- | --- | --- | --- |
| `event_id` | `UUID PK DEFAULT gen_random_uuid()` | (생성) | |
| `run_id` | `UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE` | M3-3 | run 종속 |
| `seq` | `INTEGER NOT NULL` | 궤적 순서 | |
| `variant` | `VARCHAR(8) NOT NULL` | A/B | 필터 편의(denormalized) |
| `kind` | `VARCHAR(12) NOT NULL` | node(A) / ai(B) / tool(B) | 행 성격 |
| `name` | `VARCHAR(64)` | A=node_name / B tool=tool name / B ai=NULL | |
| `summary` | `JSONB` | A=`protocol_summary` / B ai=`tool_calls` | 구조화 판단 |
| `content` | `TEXT` | B ai=reasoning preview / B tool=관찰 preview / A=NULL | 본문(절단) |
| `created_at` | `TIMESTAMP DEFAULT NOW()` | | |

제약·인덱스: `INDEX(run_id)`, `INDEX(variant)`, `INDEX(kind)`, `UNIQUE(run_id, seq)`, `kind` CHECK(node/ai/tool).

## 3. A 매핑 (read-only from `_agent_trace_entries`)

- `final_state["_agent_trace_entries"]`(M3-1 인벤토리 S4) = `TraceEntry{node_name, timestamp, duration_ms, protocol_summary, metadata}` 리스트(append-only).
- timestamp 순 정렬 → 각 항목을 `kind='node'`, `name=node_name`, `summary=protocol_summary`로 1행.
- 예: supervisor → `{current_phase, next_agent, reasoning_preview}`, query_analysis → `{intent, retriever_types}` 가 `summary`에 그대로. **A 무변경**(이미 생성되는 값 읽기).

## 4. B 매핑 (run_b 메시지 distill — B만 추가)

- `run_b`의 `result["messages"]`를 distill해 `protocol_messages` 반환(B만 수정, 답변 무변경):
  - `AIMessage` → `{kind:'ai', content: (content[:N]), tool_calls: [{name,args}]}` (모델 판단/호출 결정)
  - `ToolMessage` → `{kind:'tool', name: tool_name, content: (observation[:N])}` (도구 관찰)
  - `HumanMessage`(쿼리) 제외.
- `chat.py`가 이를 seq 순 `protocol_events`로 저장.
- **content 절단**: ToolMessage(검색 결과)는 길어서 preview(예: 500자)로 절단(용량 관리).
- caveat: gpt-4o-mini ReAct는 reasoning 텍스트가 짧을 수 있음(tool_calls/관찰은 확실).

## 5. Migration 초안 (`010_protocol_events.sql` — 본 PR은 문서)

```sql
-- ============================================================
-- 010_protocol_events.sql
-- Agent/RAG workflow 관측: 내부 의사결정 궤적 (M3-9)
--   A=inter-agent protocol_summary, B=ReAct 메시지 궤적.
-- ⚠️ 수동 실행. workflow_runs(005) 선행 필요.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS protocol_events (
    event_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id      UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
    seq         INTEGER      NOT NULL,
    variant     VARCHAR(8)   NOT NULL,
    kind        VARCHAR(12)  NOT NULL,
    name        VARCHAR(64),
    summary     JSONB,
    content     TEXT,
    created_at  TIMESTAMP    DEFAULT NOW(),
    UNIQUE (run_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_protocol_events_run     ON protocol_events(run_id);
CREATE INDEX IF NOT EXISTS idx_protocol_events_variant ON protocol_events(variant);
CREATE INDEX IF NOT EXISTS idx_protocol_events_kind    ON protocol_events(kind);

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_protocol_events_kind') THEN
        ALTER TABLE protocol_events ADD CONSTRAINT check_protocol_events_kind
            CHECK (kind IN ('node','ai','tool'));
    END IF;
END $$;

COMMENT ON TABLE protocol_events IS '내부 의사결정 궤적 (A inter-agent / B ReAct, M3-9)';
COMMENT ON COLUMN protocol_events.kind IS 'node(A 노드) / ai(B 모델 turn) / tool(B 도구 관찰)';
COMMENT ON COLUMN protocol_events.summary IS 'A protocol_summary / B tool_calls (JSONB)';
COMMENT ON COLUMN protocol_events.content IS 'B reasoning/관찰 preview (절단), A는 NULL';

DO $$ BEGIN RAISE NOTICE '✓ 010_protocol_events.sql: protocol_events table ready'; END $$;
```

## 6. 구현 시 변경 대상 (M3-9 구현 PR)

| 파일 | 변경 |
| --- | --- |
| `backend/app/database/migrations/010_protocol_events.sql` | 신규(force-add) |
| `backend/app/observability/protocol_events.py` | 신규 `save_protocol_events` + `build_a_protocol_events(trace_entries)` + `build_b_protocol_events(protocol_messages)` |
| `backend/app/variant_b/agent.py` | `result["messages"]` distill → `protocol_messages` 반환 (B만) |
| `backend/app/api/chat.py` | A: `_agent_trace_entries`로 events. B: `protocol_messages`로 events. |
| `backend/app/observability/query.py` | (선택) `get_run_detail`에 `protocol_events` 자식 추가(M3-8 확장) |

## 7. 완료 기준 점검 (구현 시 검증)

- [ ] `010` 적용 + `\d protocol_events`(FK/UNIQUE/CHECK/인덱스).
- [ ] A run → 노드 시퀀스 + `summary`에 supervisor `next_agent`/`reasoning` 등 조회.
- [ ] B run → ai/tool 궤적(어떤 도구를 어떤 인자로, 관찰 무엇) seq 순 조회.
- [ ] `/observability/runs/{id}` 또는 SQL로 run의 e2e 의사결정 흐름 확인.
- [ ] best-effort: 저장 실패해도 `/chat` 200.
- [ ] A 로직 diff 0(read-only; B는 distill만).

## 8. caveat / 인계

- A `protocol_events`는 `workflow_steps`와 노드가 겹침(중복) — 단, steps=timing/category, protocol=판단 content로 **관심사 분리**. 조회 시 join.
- B reasoning 빈약 가능(모델 특성). content 절단으로 용량 관리.
- 이 모듈은 **과정 추적**까지. 검색/답변 **품질 평가**(relevance/faithfulness, human goldenset + LLM-judge)는 별도 평가 모듈로 후속(검토에서 합의된 목표 2).

## 9. Next (평가 방향, 후속 논의)

검토에서 합의: ① 답변 본문 영속화 → ② human goldenset(검색 relevance + 답변 적합성 라벨) → ③ LLM-judge 자동 채점(goldenset로 judge 검증). M3-9(과정) 이후 **평가 레이어**로 진행.
