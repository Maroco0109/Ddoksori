-- ============================================================
-- 007_retrieval_events.sql
-- Agent/RAG workflow 관측: 검색 호출별 결과 품질 (M3-5)
--
-- 작성일: 2026-06-24
-- 설명: 검색 호출 1회 = row 1개. A(4섹션)/B(gate+tool) 공통.
--       top_chunks JSONB에 top-k의 (chunk_id, similarity, rank) 보존.
-- ⚠️ 주의: 수동 실행. workflow_runs(005) 선행 필요.
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS retrieval_events (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL REFERENCES workflow_runs(run_id) ON DELETE CASCADE,
    seq             INTEGER      NOT NULL,
    source          VARCHAR(16)  NOT NULL,
    query           TEXT,
    domain          VARCHAR(16),
    top_k           INTEGER,
    result_count    INTEGER      NOT NULL,
    max_similarity  DOUBLE PRECISION,
    avg_similarity  DOUBLE PRECISION,
    top_chunks      JSONB,
    created_at      TIMESTAMP    DEFAULT NOW(),
    UNIQUE (run_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_retrieval_events_run    ON retrieval_events(run_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_events_source ON retrieval_events(source);

-- 멱등 CHECK 제약 (004~006 패턴과 동일)
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'check_retrieval_events_source') THEN
        ALTER TABLE retrieval_events ADD CONSTRAINT check_retrieval_events_source
            CHECK (source IN ('law','criteria','case','counsel','gate','tool','dense','other'));
    END IF;
END $$;

COMMENT ON TABLE retrieval_events IS '검색 호출별 결과 품질 (A/B 공통, M3-5)';
COMMENT ON COLUMN retrieval_events.run_id IS 'workflow_runs FK (ON DELETE CASCADE)';
COMMENT ON COLUMN retrieval_events.seq IS 'run 내 retrieval 순번 (0-based)';
COMMENT ON COLUMN retrieval_events.source IS 'A 섹션(law/criteria/case/counsel) / B 단계(gate/tool)';
COMMENT ON COLUMN retrieval_events.domain IS 'B tool 검색 대상 (all/law/criteria/case); A는 NULL';
COMMENT ON COLUMN retrieval_events.top_chunks IS 'top-k [{chunk_id, similarity, rank}] (JSONB)';

DO $$ BEGIN RAISE NOTICE '✓ 007_retrieval_events.sql: retrieval_events table ready'; END $$;
