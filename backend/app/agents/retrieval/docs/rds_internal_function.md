-- =====================================================
-- 6. 유틸리티 함수
-- =====================================================

-- 5.1 기본 벡터 유사도 검색 함수

CREATE OR REPLACE FUNCTION search_similar_chunks(
    query_embedding vector(1536),
    filter_dataset VARCHAR(20) DEFAULT NULL,
    filter_category VARCHAR(50) DEFAULT NULL,
    filter_law_name VARCHAR(500) DEFAULT NULL,
    filter_year INTEGER DEFAULT NULL,
    result_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    chunk_id VARCHAR(500),
    dataset_type VARCHAR(20),
    text TEXT,
    similarity FLOAT,
    law_name VARCHAR(500),
    chunk_type VARCHAR(50),
    category VARCHAR(50),
    source_url VARCHAR(1000),
    source_file VARCHAR(500),
    printed_page INTEGER,
    source_year INTEGER,
    metadata JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        vc.chunk_id,
        vc.dataset_type,
        vc.text,
        1 - (vc.embedding <=> query_embedding) AS similarity,
        vc.law_name,
        vc.chunk_type,
        vc.category,
        vc.source_url,
        vc.source_file,
        vc.printed_page,
        vc.source_year,
        vc.metadata
    FROM vector_chunks vc
    WHERE
        (filter_dataset IS NULL OR vc.dataset_type = filter_dataset)
        AND (filter_category IS NULL OR vc.category = filter_category)
        AND (filter_law_name IS NULL OR vc.law_name = filter_law_name)
        AND (filter_year IS NULL OR vc.source_year = filter_year)
    ORDER BY vc.embedding <=> query_embedding
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;

-- 5.2 하이브리드 검색 함수 (법령 + 사례 동시 검색)

CREATE OR REPLACE FUNCTION search_hybrid(
    query_embedding vector(1536),
    law_limit INTEGER DEFAULT 5,
    case_limit INTEGER DEFAULT 5,
    filter_category VARCHAR(50) DEFAULT NULL,
    filter_year INTEGER DEFAULT NULL
)
RETURNS TABLE (
    source VARCHAR(20),
    chunk_id VARCHAR(500),
    text TEXT,
    similarity FLOAT,
    law_name VARCHAR(500),
    category VARCHAR(50),
    source_url VARCHAR(1000),
    source_file VARCHAR(500),
    printed_page INTEGER,
    source_year INTEGER,
    metadata JSONB
) AS $$
BEGIN
    RETURN QUERY
    (
        -- 법령 검색
        SELECT
            'law_guide'::VARCHAR(20) as source,
            vc.chunk_id,
            vc.text,
            1 - (vc.embedding <=> query_embedding) AS similarity,
            vc.law_name,
            vc.category,
            vc.source_url,
            vc.source_file,
            vc.printed_page,
            vc.source_year,
            vc.metadata
        FROM vector_chunks vc
        WHERE vc.dataset_type = 'law_guide'
          AND (filter_year IS NULL OR vc.source_year = filter_year)
        ORDER BY vc.embedding <=> query_embedding
        LIMIT law_limit
    )
    UNION ALL
    (
        -- 사례 검색
        SELECT
            'case'::VARCHAR(20) as source,
            vc.chunk_id,
            vc.text,
            1 - (vc.embedding <=> query_embedding) AS similarity,
            vc.law_name,
            vc.category,
            vc.source_url,
            vc.source_file,
            vc.printed_page,
            vc.source_year,
            vc.metadata
        FROM vector_chunks vc
        WHERE vc.dataset_type = 'case'
          AND (filter_category IS NULL OR vc.category = filter_category)
          AND (filter_year IS NULL OR vc.source_year = filter_year)
        ORDER BY vc.embedding <=> query_embedding
        LIMIT case_limit
    )
    ORDER BY similarity DESC;
END;
$$ LANGUAGE plpgsql;

-- 5.3 메타데이터 키워드 검색 + 벡터 유사도

CREATE OR REPLACE FUNCTION search_with_keywords(
    query_embedding vector(1536),
    keyword TEXT,
    result_limit INTEGER DEFAULT 10
)
RETURNS TABLE (
    chunk_id VARCHAR(500),
    dataset_type VARCHAR(20),
    text TEXT,
    similarity FLOAT,
    metadata JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        vc.chunk_id,
        vc.dataset_type,
        vc.text,
        1 - (vc.embedding <=> query_embedding) AS similarity,
        vc.metadata
    FROM vector_chunks vc
    WHERE
        vc.dataset_type = 'law_guide'
        AND vc.metadata->'keywords' ? keyword
    ORDER BY vc.embedding <=> query_embedding
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;

-- 5.5 하이브리드 검색 함수 (BM25 + 벡터 + RRF)

-- BM25 키워드 검색 함수
CREATE OR REPLACE FUNCTION search_bm25(
    query_text TEXT,
    filter_dataset VARCHAR(20) DEFAULT NULL,
    filter_category VARCHAR(50) DEFAULT NULL,
    filter_document_type VARCHAR(20) DEFAULT NULL,
    result_limit INTEGER DEFAULT 100
)
RETURNS TABLE (
    chunk_id VARCHAR(500),
    dataset_type VARCHAR(20),
    text TEXT,
    bm25_score FLOAT,
    bm25_rank BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        vc.chunk_id,
        vc.dataset_type,
        vc.text,
        ts_rank_cd('{0.1, 0.2, 0.4, 0.6}', vc.text_tsv, plainto_tsquery('simple', query_text))::FLOAT as bm25_score,
        ROW_NUMBER() OVER (ORDER BY ts_rank_cd('{0.1, 0.2, 0.4, 0.6}', vc.text_tsv, plainto_tsquery('simple', query_text)) DESC) as bm25_rank
    FROM vector_chunks vc
    WHERE
        vc.text_tsv @@ plainto_tsquery('simple', query_text)
        AND (filter_dataset IS NULL OR vc.dataset_type = filter_dataset)
        AND (filter_category IS NULL OR vc.category = filter_category)
        AND (filter_document_type IS NULL OR vc.document_type = filter_document_type)
    ORDER BY bm25_score DESC
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;

-- 하이브리드 검색 함수 (RRF 통합)

CREATE OR REPLACE FUNCTION search_hybrid_rrf(
    query_text TEXT,
    query_embedding vector(1536),
    filter_dataset VARCHAR(20) DEFAULT NULL,
    filter_category VARCHAR(50) DEFAULT NULL,
    filter_document_type VARCHAR(20) DEFAULT NULL,
    filter_year INTEGER DEFAULT NULL,
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
BEGIN
    RETURN QUERY
    WITH bm25_results AS (
        SELECT
            vc.chunk_id,
            ts_rank_cd('{0.1, 0.2, 0.4, 0.6}', vc.text_tsv, plainto_tsquery('simple', query_text))::FLOAT as score,
            ROW_NUMBER() OVER (ORDER BY ts_rank_cd('{0.1, 0.2, 0.4, 0.6}', vc.text_tsv, plainto_tsquery('simple', query_text)) DESC) as rank
        FROM vector_chunks vc
        WHERE
            vc.text_tsv @@ plainto_tsquery('simple', query_text)
            AND (filter_dataset IS NULL OR vc.dataset_type = filter_dataset)
            AND (filter_category IS NULL OR vc.category = filter_category)
            AND (filter_document_type IS NULL OR vc.document_type = filter_document_type)
            AND (filter_year IS NULL OR vc.source_year = filter_year)
        ORDER BY score DESC
        LIMIT 100
    ),
    vector_results AS (
        SELECT
            vc.chunk_id,
            1 - (vc.embedding <=> query_embedding) as similarity,
            ROW_NUMBER() OVER (ORDER BY vc.embedding <=> query_embedding) as rank
        FROM vector_chunks vc
        WHERE
            (filter_dataset IS NULL OR vc.dataset_type = filter_dataset)
            AND (filter_category IS NULL OR vc.category = filter_category)
            AND (filter_document_type IS NULL OR vc.document_type = filter_document_type)
            AND (filter_year IS NULL OR vc.source_year = filter_year)
        ORDER BY vc.embedding <=> query_embedding
        LIMIT 100
    ),
    rrf_combined AS (
        SELECT
            COALESCE(b.chunk_id, v.chunk_id) as chunk_id,
            -- RRF: 1 / (k + rank)
            COALESCE(1.0 / (rrf_k + b.rank), 0) +
            COALESCE(1.0 / (rrf_k + v.rank), 0) as rrf_score,
            COALESCE(b.score, 0) as bm25_score,
            COALESCE(v.similarity, 0) as vector_similarity
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


-- 5.5-1 새 함수: search_hybrid_rrf_2 (document_type/ chunk_type 다중 필터, year from-to 추가)

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
BEGIN
    RETURN QUERY
    WITH bm25_results AS (
        SELECT
            vc.chunk_id,
            ts_rank_cd(
                '{0.1, 0.2, 0.4, 0.6}',
                vc.text_tsv,
                websearch_to_tsquery('simple', regexp_replace(query_text, '\s+', ' OR ', 'g'))
            )::FLOAT as score,
            ROW_NUMBER() OVER (
                ORDER BY ts_rank_cd(
                    '{0.1, 0.2, 0.4, 0.6}',
                    vc.text_tsv,
                    websearch_to_tsquery('simple', regexp_replace(query_text, '\s+', ' OR ', 'g'))
                ) DESC
            ) as rank
        FROM vector_chunks vc
        WHERE
            vc.text_tsv @@ websearch_to_tsquery('simple', regexp_replace(query_text, '\s+', ' OR ', 'g'))
            AND ts_rank_cd(
                '{0.1, 0.2, 0.4, 0.6}',
                vc.text_tsv,
                websearch_to_tsquery('simple', regexp_replace(query_text, '\s+', ' OR ', 'g'))
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
            (1 - (vc.embedding <=> query_embedding))::FLOAT as similarity,
            ROW_NUMBER() OVER (ORDER BY vc.embedding <=> query_embedding) as rank
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
            COALESCE(b.chunk_id, v.chunk_id) as chunk_id,
            -- RRF: 1 / (k + rank)
            (COALESCE(1.0 / (rrf_k + b.rank), 0) +
             COALESCE(1.0 / (rrf_k + v.rank), 0))::FLOAT as rrf_score,
            COALESCE(b.score, 0)::FLOAT as bm25_score,
            COALESCE(v.similarity, 0)::FLOAT as vector_similarity
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
