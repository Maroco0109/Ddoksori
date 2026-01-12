-- S1-1 Migration: Add citation metadata to mv_searchable_chunks
-- This migration recreates the materialized view to include source_org, url, collected_at, metadata
-- Applied: 2026-01-11
-- Author: S1-1 Implementation

BEGIN;

-- Drop existing materialized view if exists
DROP MATERIALIZED VIEW IF EXISTS mv_searchable_chunks CASCADE;

-- Recreate with citation metadata
CREATE MATERIALIZED VIEW mv_searchable_chunks AS
SELECT
    c.chunk_id,
    c.doc_id,
    c.chunk_type,
    c.content,
    d.doc_type,
    d.source_org,
    d.category_path,
    d.title,              -- For doc_title
    d.url,                -- S1-1: Citation metadata
    d.collected_at,       -- S1-1: Citation metadata
    d.metadata,           -- S1-1: For decision_date extraction
    to_tsvector('simple', c.content) AS content_vector
FROM chunks c
JOIN documents d ON c.doc_id = d.doc_id
WHERE c.drop = FALSE;  -- NOTE: No embedding requirement for FTS

-- Create indexes for performance
CREATE INDEX idx_mv_searchable_chunks_fts ON mv_searchable_chunks USING GIN(content_vector);
CREATE INDEX idx_mv_searchable_chunks_doc_type ON mv_searchable_chunks(doc_type);
CREATE INDEX idx_mv_searchable_chunks_source_org ON mv_searchable_chunks(source_org);
CREATE INDEX idx_mv_searchable_chunks_chunk_type ON mv_searchable_chunks(chunk_type);

COMMIT;

-- Verify view was created
SELECT count(*) AS total_chunks FROM mv_searchable_chunks;
SELECT doc_type, count(*) FROM mv_searchable_chunks GROUP BY doc_type ORDER BY doc_type;
