-- ============================================================
-- 008_llm_calls.sql
-- Agent/RAG workflow 관측: LLM 호출 provider/model/token/fallback (M3-6)
--
-- 작성일: 2026-06-24
-- 설명: LLM 호출 1회 = row 1개. A 노드(supervisor/query_analysis/generation)/B(react).
-- ⚠️ 주의: 수동 실행. workflow_runs(005) 선행 필요.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS llm_calls (
    call_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id            UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
    seq               INTEGER      NOT NULL,
    component         VARCHAR(24)  NOT NULL,
    provider          VARCHAR(16),
    model             VARCHAR(64),
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    total_tokens      INTEGER,
    n_calls           INTEGER      NOT NULL DEFAULT 1,
    fallback          BOOLEAN,
    status            VARCHAR(12)  NOT NULL DEFAULT 'ok',
    error_message     TEXT,
    created_at        TIMESTAMP    DEFAULT NOW(),
    UNIQUE (run_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_llm_calls_run      ON llm_calls(run_id);
CREATE INDEX IF NOT EXISTS idx_llm_calls_provider ON llm_calls(provider);
CREATE INDEX IF NOT EXISTS idx_llm_calls_model    ON llm_calls(model);

-- 멱등 CHECK 제약 (004~007 패턴과 동일)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_llm_calls_status') THEN
        ALTER TABLE llm_calls ADD CONSTRAINT check_llm_calls_status
            CHECK (status IN ('ok','error'));
    END IF;
END $$;

COMMENT ON TABLE llm_calls IS 'LLM 호출 provider/model/token/fallback (A/B 공통, M3-6)';
COMMENT ON COLUMN llm_calls.run_id IS 'workflow_runs FK (ON DELETE CASCADE)';
COMMENT ON COLUMN llm_calls.component IS 'A 노드(supervisor/query_analysis/generation) / B react';
COMMENT ON COLUMN llm_calls.provider IS 'openai/runpod_vllm/anthropic/rule_based/other (파생)';
COMMENT ON COLUMN llm_calls.model IS '실제/설정 모델 (예: gpt-4o, gpt-4o-mini, LGAI-EXAONE/EXAONE-4.5-33B)';
COMMENT ON COLUMN llm_calls.n_calls IS 'A=1, B=react 모델 호출 수 (집계행)';
COMMENT ON COLUMN llm_calls.fallback IS 'rule_based/safe_fallback 등 폴백 여부';

DO $$ BEGIN RAISE NOTICE '✓ 008_llm_calls.sql: llm_calls table ready'; END $$;
