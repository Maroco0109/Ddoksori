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

-- 멱등 CHECK 제약 (004~009 패턴과 동일)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_protocol_events_kind') THEN
        ALTER TABLE protocol_events ADD CONSTRAINT check_protocol_events_kind
            CHECK (kind IN ('node','ai','tool'));
    END IF;
END $$;

COMMENT ON TABLE protocol_events IS '내부 의사결정 궤적 (A inter-agent / B ReAct, M3-9)';
COMMENT ON COLUMN protocol_events.run_id IS 'workflow_runs FK (ON DELETE CASCADE)';
COMMENT ON COLUMN protocol_events.kind IS 'node(A 노드) / ai(B 모델 turn) / tool(B 도구 관찰)';
COMMENT ON COLUMN protocol_events.name IS 'A node_name / B tool 이름';
COMMENT ON COLUMN protocol_events.summary IS 'A protocol_summary / B tool_calls (JSONB)';
COMMENT ON COLUMN protocol_events.content IS 'B reasoning/관찰 preview (절단), A는 NULL';

DO $$ BEGIN RAISE NOTICE '✓ 010_protocol_events.sql: protocol_events table ready'; END $$;
