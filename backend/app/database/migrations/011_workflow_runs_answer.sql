-- ============================================================
-- 011_workflow_runs_answer.sql
-- 품질 평가 선결: workflow_runs에 답변 본문 컬럼 추가 (M5-1)
-- ⚠️ 수동 실행. workflow_runs(005) 선행 필요.
-- ============================================================

ALTER TABLE workflow_runs ADD COLUMN IF NOT EXISTS answer TEXT;

COMMENT ON COLUMN workflow_runs.answer IS '생성된 답변 본문(전문). 품질 평가(faithfulness/relevance)용. clarify/blocked는 해당 메시지';

DO $$ BEGIN RAISE NOTICE '✓ 011_workflow_runs_answer.sql: workflow_runs.answer added'; END $$;
