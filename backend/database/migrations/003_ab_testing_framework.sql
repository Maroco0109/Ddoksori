-- Migration: A/B Testing Framework
-- Description: Add tables for experiment management and outcome tracking
-- Created: 2026-01-21

-- Experiments table: stores experiment definitions
CREATE TABLE IF NOT EXISTS experiments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    description TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'draft',  -- draft, active, paused, completed
    traffic_split_config JSONB NOT NULL,  -- e.g., {"A": 0.5, "B": 0.5}
    variants JSONB NOT NULL,  -- e.g., ["A", "B"]
    metadata JSONB,  -- additional config (e.g., target metrics, hypothesis)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    CONSTRAINT valid_status CHECK (status IN ('draft', 'active', 'paused', 'completed'))
);

-- Experiment outcomes table: stores metric tracking data
CREATE TABLE IF NOT EXISTS experiment_outcomes (
    id SERIAL PRIMARY KEY,
    experiment_id INTEGER NOT NULL REFERENCES experiments(id) ON DELETE CASCADE,
    subject_id VARCHAR(255) NOT NULL,  -- user_id or session_id
    variant VARCHAR(50) NOT NULL,
    metric_name VARCHAR(100) NOT NULL,
    metric_value NUMERIC,
    metric_type VARCHAR(50) DEFAULT 'numeric',  -- numeric, boolean, string
    metadata JSONB,  -- additional context (e.g., request_id, chat_type)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for experiment_outcomes
CREATE INDEX IF NOT EXISTS idx_experiment_subject ON experiment_outcomes(experiment_id, subject_id);
CREATE INDEX IF NOT EXISTS idx_experiment_variant ON experiment_outcomes(experiment_id, variant);
CREATE INDEX IF NOT EXISTS idx_outcomes_created_at ON experiment_outcomes(created_at);

-- Index for faster variant assignment lookups
CREATE INDEX IF NOT EXISTS idx_experiments_name_status ON experiments(name, status);

-- Comments for documentation
COMMENT ON TABLE experiments IS 'A/B test experiment definitions with traffic split configuration';
COMMENT ON TABLE experiment_outcomes IS 'Metric tracking data for A/B test experiments';
COMMENT ON COLUMN experiments.traffic_split_config IS 'JSON object defining traffic split ratios per variant';
COMMENT ON COLUMN experiment_outcomes.subject_id IS 'User or session identifier for consistent variant assignment';
