-- ============================================
-- Migration: BGE-M3 Dense + Sparse Vector Support
-- Date: 2026-01-17
-- Purpose: Add BGE-M3 embedding columns for hybrid retrieval
-- ============================================

-- 1. Add BGE-M3 Dense vector column (1024 dimensions)
ALTER TABLE chunks
ADD COLUMN IF NOT EXISTS bge_dense_vector vector(1024);

-- 2. Add BGE-M3 Sparse vector column (JSONB format: {token_id: weight})
ALTER TABLE chunks
ADD COLUMN IF NOT EXISTS bge_sparse_vector JSONB;

-- 3. Add BGE-M3 encoding status flag
ALTER TABLE chunks
ADD COLUMN IF NOT EXISTS bge_m3_encoded BOOLEAN DEFAULT FALSE;

-- 4. Add active embedding model column (for A/B testing)
ALTER TABLE chunks
ADD COLUMN IF NOT EXISTS active_embedding_model VARCHAR(50) DEFAULT 'kure-v1';

-- 5. Add comments
COMMENT ON COLUMN chunks.bge_dense_vector IS 'BGE-M3 dense embedding vector (1024 dimensions)';
COMMENT ON COLUMN chunks.bge_sparse_vector IS 'BGE-M3 sparse vector: {token_id: weight} JSONB format. Only non-zero tokens stored.';
COMMENT ON COLUMN chunks.bge_m3_encoded IS 'BGE-M3 encoding completion status';
COMMENT ON COLUMN chunks.active_embedding_model IS 'Active embedding model: kure-v1 or bge-m3';

-- 6. Create IVFFlat index for BGE-M3 Dense vector (cosine similarity)
CREATE INDEX IF NOT EXISTS idx_chunks_bge_dense_ivfflat
ON chunks USING ivfflat(bge_dense_vector vector_cosine_ops) WITH (lists = 100);

-- 7. Create GIN index for BGE-M3 Sparse vector (JSONB search)
CREATE INDEX IF NOT EXISTS idx_chunks_bge_sparse_gin
ON chunks USING GIN (bge_sparse_vector);

-- 8. Create index for BGE-M3 encoding status
CREATE INDEX IF NOT EXISTS idx_chunks_bge_m3_encoded
ON chunks(bge_m3_encoded)
WHERE bge_m3_encoded = FALSE;

-- 9. Create composite index for active BGE-M3 encoded chunks
CREATE INDEX IF NOT EXISTS idx_chunks_bge_active
ON chunks(doc_id, chunk_type)
WHERE bge_m3_encoded = TRUE AND drop = FALSE;

-- 10. Create index for active embedding model filtering
CREATE INDEX IF NOT EXISTS idx_chunks_active_model
ON chunks(active_embedding_model)
WHERE drop = FALSE;

-- 11. Function: BGE-M3 sparse vector dot product
-- Calculates dot product between two sparse vectors
CREATE OR REPLACE FUNCTION bge_sparse_dot_product(
    vec1 JSONB,
    vec2 JSONB
) RETURNS FLOAT AS $$
DECLARE
    result FLOAT := 0.0;
    key TEXT;
BEGIN
    -- NULL check
    IF vec1 IS NULL OR vec2 IS NULL THEN
        RETURN 0.0;
    END IF;

    -- Iterate over vec1 keys and compute dot product
    FOR key IN SELECT jsonb_object_keys(vec1)
    LOOP
        IF vec2 ? key THEN
            result := result + (vec1->>key)::FLOAT * (vec2->>key)::FLOAT;
        END IF;
    END LOOP;

    RETURN result;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- 12. Function: Check if sparse vector contains specific token
CREATE OR REPLACE FUNCTION bge_sparse_contains_token(
    sparse_vec JSONB,
    token_id TEXT
) RETURNS BOOLEAN AS $$
BEGIN
    RETURN sparse_vec ? token_id;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- 13. Apply same columns to criteria_units table (if exists)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'criteria_units') THEN
        ALTER TABLE criteria_units
        ADD COLUMN IF NOT EXISTS bge_dense_vector vector(1024);

        ALTER TABLE criteria_units
        ADD COLUMN IF NOT EXISTS bge_sparse_vector JSONB;

        ALTER TABLE criteria_units
        ADD COLUMN IF NOT EXISTS bge_m3_encoded BOOLEAN DEFAULT FALSE;

        RAISE NOTICE 'BGE-M3 columns added to criteria_units table';
    END IF;
END $$;

-- 14. Update statistics
ANALYZE chunks;

-- 15. Migration completion message
DO $$
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE 'BGE-M3 Support Migration Complete';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Added columns:';
    RAISE NOTICE '  - bge_dense_vector (vector 1024)';
    RAISE NOTICE '  - bge_sparse_vector (JSONB)';
    RAISE NOTICE '  - bge_m3_encoded (BOOLEAN)';
    RAISE NOTICE '  - active_embedding_model (VARCHAR)';
    RAISE NOTICE '';
    RAISE NOTICE 'Created indexes:';
    RAISE NOTICE '  - idx_chunks_bge_dense_ivfflat (IVFFlat)';
    RAISE NOTICE '  - idx_chunks_bge_sparse_gin (GIN)';
    RAISE NOTICE '';
    RAISE NOTICE 'Created functions:';
    RAISE NOTICE '  - bge_sparse_dot_product(vec1, vec2)';
    RAISE NOTICE '  - bge_sparse_contains_token(vec, token)';
    RAISE NOTICE '';
    RAISE NOTICE 'Next step: Run embed_bge_m3_all_data.py';
    RAISE NOTICE '========================================';
END $$;
