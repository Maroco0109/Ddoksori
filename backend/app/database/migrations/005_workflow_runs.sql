-- ============================================================
-- 005_workflow_runs.sql
-- Agent/RAG workflow 관측: 요청 단위 run 기록 (M3-2 설계, M3-3 적용)
--
-- 작성일: 2026-06-24
-- 설명: /chat 요청 1건 = row 1개. A(MAS)/B(Agentic) 공통.
--       상세(step/retrieval/llm/guardrail)는 후속 마이그레이션에서 FK 참조.
-- ⚠️ 주의: 수동 실행. DB 계정 권한 확인 후 적용.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS workflow_runs (
    run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    variant         VARCHAR(8)  NOT NULL,
    session_id      VARCHAR(255),
    chat_type       VARCHAR(20),
    query           TEXT        NOT NULL,
    status          VARCHAR(20) NOT NULL DEFAULT 'success',
    error_message   TEXT,
    total_time_ms   DOUBLE PRECISION,
    clarified       BOOLEAN,
    blocked         BOOLEAN,
    started_at      TIMESTAMP   DEFAULT NOW(),
    created_at      TIMESTAMP   DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_variant     ON workflow_runs(variant);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_session     ON workflow_runs(session_id);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_started     ON workflow_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_workflow_runs_status      ON workflow_runs(status);

-- 멱등 CHECK 제약 (004 패턴과 동일)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_workflow_runs_variant') THEN
        ALTER TABLE workflow_runs ADD CONSTRAINT check_workflow_runs_variant
            CHECK (variant IN ('A', 'B'));
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_workflow_runs_status') THEN
        ALTER TABLE workflow_runs ADD CONSTRAINT check_workflow_runs_status
            CHECK (status IN ('success', 'no_results', 'error'));
    END IF;
END $$;

COMMENT ON TABLE workflow_runs IS 'Agent/RAG workflow 요청 단위 run 기록 (A/B 공통, M3-2)';
COMMENT ON COLUMN workflow_runs.run_id IS '요청 고유 ID (= RAG 로그 request_id, A/B 공통 키)';
COMMENT ON COLUMN workflow_runs.variant IS '아키텍처 변종 (A=MAS, B=Agentic)';
COMMENT ON COLUMN workflow_runs.session_id IS '프론트엔드 세션 ID (느슨한 참조, FK 아님)';
COMMENT ON COLUMN workflow_runs.chat_type IS '채팅 유형 (dispute, general; B는 NULL 가능)';
COMMENT ON COLUMN workflow_runs.query IS '사용자 쿼리 원문';
COMMENT ON COLUMN workflow_runs.status IS '결과 상태 (success, no_results, error)';
COMMENT ON COLUMN workflow_runs.total_time_ms IS '요청 전체 처리 시간 (밀리초)';
COMMENT ON COLUMN workflow_runs.clarified IS '단발 clarification 발생 여부 (clarification_rate 집계용)';
COMMENT ON COLUMN workflow_runs.blocked IS 'guardrail 차단 여부 요약 (상세는 guardrail_events)';

DO $$ BEGIN
    RAISE NOTICE '✓ 005_workflow_runs.sql: workflow_runs table ready';
END $$;
