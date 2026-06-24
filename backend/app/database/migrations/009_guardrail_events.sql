-- ============================================================
-- 009_guardrail_events.sql
-- Agent/RAG workflow 관측: 입력/출력 보안 판단 (M3-7)
--
-- 작성일: 2026-06-24
-- 설명: 보안 판단 1회 = row 1개. A(input/output moderation + review)/B(input/output).
-- ⚠️ 주의: 수동 실행. workflow_runs(005) 선행 필요.
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

-- 멱등 CHECK 제약 (004~008 패턴과 동일)
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
COMMENT ON COLUMN guardrail_events.run_id IS 'workflow_runs FK (ON DELETE CASCADE)';
COMMENT ON COLUMN guardrail_events.stage IS 'input/output(moderation) / review(legal_review)';
COMMENT ON COLUMN guardrail_events.source IS 'moderation / legal_review';
COMMENT ON COLUMN guardrail_events.decision IS 'block/flag/pass';
COMMENT ON COLUMN guardrail_events.reason IS 'A=guardrail_type/violation types, B=flagged categories';
COMMENT ON COLUMN guardrail_events.detail IS 'review violations / moderation categories (JSONB)';

DO $$ BEGIN RAISE NOTICE '✓ 009_guardrail_events.sql: guardrail_events table ready'; END $$;
