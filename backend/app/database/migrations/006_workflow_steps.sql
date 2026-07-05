-- ============================================================
-- 006_workflow_steps.sql
-- Agent/RAG workflow 관측: run 내 step(node) 시퀀스 + latency (M3-4)
--
-- 작성일: 2026-06-24
-- 설명: run 1 : step N. A(MAS 노드)/B(Agentic 블록) 공통.
--       category로 A 노드와 B 블록을 공통 범주로 묶어 A/B SQL 비교 가능.
-- ⚠️ 주의: 수동 실행. workflow_runs(005) 선행 필요.
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

-- 멱등 CHECK 제약 (004/005 패턴과 동일)
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
