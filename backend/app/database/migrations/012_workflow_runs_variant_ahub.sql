-- 012: workflow_runs.variant에 'A-hub' 허용 (M8)
--
-- A-hub = MAS(A)와 동일 그래프 + LLM 슈퍼바이저 라우팅. A(결정론) vs A-hub(LLM)
-- 격리 측정을 위해 별도 variant 라벨로 적재한다. 기존 CHECK (variant IN ('A','B'))가
-- A-hub INSERT를 막으므로 제약을 갱신한다. variant는 VARCHAR(8)이라 'A-hub'(5자) 수용.
--
-- 자식 테이블(protocol_events/llm_calls/…)은 variant에 CHECK가 없어 변경 불필요.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'check_workflow_runs_variant'
    ) THEN
        ALTER TABLE workflow_runs DROP CONSTRAINT check_workflow_runs_variant;
    END IF;

    ALTER TABLE workflow_runs ADD CONSTRAINT check_workflow_runs_variant
        CHECK (variant IN ('A', 'A-hub', 'B'));
END $$;
