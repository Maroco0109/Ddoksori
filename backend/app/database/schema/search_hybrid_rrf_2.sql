-- Recreate the enhanced hybrid RRF retrieval function used by law/criteria retrievers.
-- Source references:
-- - /home/maroco/data_collection_snippets/DB/01_00_unified_schema.sql for vector_chunks/search_hybrid_rrf schema shape
-- - /home/maroco/data_collection_snippets/DB/migrations/fix_search_hybrid_rrf_ambiguous_column.py for vc.* qualification pattern
-- - backend/app/agents/retrieval/docs/rds_internal_function.md for the documented search_hybrid_rrf_2 contract
--
-- Preconditions:
-- - pgvector extension is installed.
-- - public.vector_chunks exists.
-- - vector_chunks.embedding is vector(1536).
-- - vector_chunks.text_tsv is populated.

CREATE OR REPLACE FUNCTION search_hybrid_rrf_2(
    query_text TEXT,
    query_embedding vector(1536),
    filter_dataset VARCHAR(20) DEFAULT NULL,
    filter_category VARCHAR(50) DEFAULT NULL,
    filter_document_type VARCHAR(20)[] DEFAULT NULL,
    filter_chunk_type VARCHAR(50)[] DEFAULT NULL,
    filter_year_from INTEGER DEFAULT NULL,
    filter_year_to INTEGER DEFAULT NULL,
    result_limit INTEGER DEFAULT 10,
    rrf_k INTEGER DEFAULT 60
)
RETURNS TABLE (
    chunk_id VARCHAR(500),
    dataset_type VARCHAR(20),
    text TEXT,
    rrf_score FLOAT,
    bm25_score FLOAT,
    vector_similarity FLOAT,
    law_name VARCHAR(500),
    chunk_type VARCHAR(50),
    category VARCHAR(50),
    document_type VARCHAR(20),
    source_url VARCHAR(1000),
    source_file VARCHAR(500),
    printed_page INTEGER,
    source_year INTEGER,
    metadata JSONB
) AS $$
DECLARE
    normalized_query TEXT;
    ts_query tsquery;
BEGIN
    normalized_query := regexp_replace(coalesce(query_text, ''), '[[:space:]]+', ' OR ', 'g');
    ts_query := websearch_to_tsquery('simple', normalized_query);

    RETURN QUERY
    WITH bm25_results AS (
        SELECT
            vc.chunk_id,
            ts_rank_cd(
                '{0.1, 0.2, 0.4, 0.6}',
                vc.text_tsv,
                ts_query
            )::FLOAT AS score,
            ROW_NUMBER() OVER (
                ORDER BY ts_rank_cd(
                    '{0.1, 0.2, 0.4, 0.6}',
                    vc.text_tsv,
                    ts_query
                ) DESC
            ) AS rank
        FROM vector_chunks vc
        WHERE
            vc.text_tsv @@ ts_query
            AND ts_rank_cd(
                '{0.1, 0.2, 0.4, 0.6}',
                vc.text_tsv,
                ts_query
            ) >= 0.02
            AND (filter_dataset IS NULL OR vc.dataset_type = filter_dataset)
            AND (filter_category IS NULL OR vc.category = filter_category)
            AND (filter_document_type IS NULL OR vc.document_type = ANY(filter_document_type))
            AND (filter_chunk_type IS NULL OR vc.chunk_type = ANY(filter_chunk_type))
            AND (filter_year_from IS NULL OR vc.source_year >= filter_year_from)
            AND (filter_year_to IS NULL OR vc.source_year <= filter_year_to)
        ORDER BY score DESC
        LIMIT 100
    ),
    vector_results AS (
        SELECT
            vc.chunk_id,
            (1 - (vc.embedding <=> query_embedding))::FLOAT AS similarity,
            ROW_NUMBER() OVER (ORDER BY vc.embedding <=> query_embedding) AS rank
        FROM vector_chunks vc
        WHERE
            (filter_dataset IS NULL OR vc.dataset_type = filter_dataset)
            AND (filter_category IS NULL OR vc.category = filter_category)
            AND (filter_document_type IS NULL OR vc.document_type = ANY(filter_document_type))
            AND (filter_chunk_type IS NULL OR vc.chunk_type = ANY(filter_chunk_type))
            AND (filter_year_from IS NULL OR vc.source_year >= filter_year_from)
            AND (filter_year_to IS NULL OR vc.source_year <= filter_year_to)
        ORDER BY vc.embedding <=> query_embedding
        LIMIT 100
    ),
    rrf_combined AS (
        SELECT
            COALESCE(b.chunk_id, v.chunk_id) AS chunk_id,
            (
                COALESCE(1.0 / (rrf_k + b.rank), 0) +
                COALESCE(1.0 / (rrf_k + v.rank), 0)
            )::FLOAT AS rrf_score,
            COALESCE(b.score, 0)::FLOAT AS bm25_score,
            COALESCE(v.similarity, 0)::FLOAT AS vector_similarity
        FROM bm25_results b
        FULL OUTER JOIN vector_results v ON b.chunk_id = v.chunk_id
    )
    SELECT
        vc.chunk_id,
        vc.dataset_type,
        vc.text,
        rc.rrf_score,
        rc.bm25_score,
        rc.vector_similarity,
        vc.law_name,
        vc.chunk_type,
        vc.category,
        vc.document_type,
        vc.source_url,
        vc.source_file,
        vc.printed_page,
        vc.source_year,
        vc.metadata
    FROM rrf_combined rc
    JOIN vector_chunks vc ON rc.chunk_id = vc.chunk_id
    ORDER BY rc.rrf_score DESC
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;
