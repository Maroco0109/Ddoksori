-- 똑소리 프로젝트 통합 데이터베이스 스키마 v2 (최종)
-- 작성일: 2026-01-06
-- RAG 시스템 최적화를 위한 개선된 스키마

-- pgvector 확장 활성화
CREATE EXTENSION IF NOT EXISTS vector;

-- 기존 테이블 삭제 (개발 환경용)
DROP TABLE IF EXISTS law_citation_map CASCADE;
DROP TABLE IF EXISTS law_version CASCADE;
DROP TABLE IF EXISTS law_node CASCADE;
DROP TABLE IF EXISTS laws CASCADE;
DROP TABLE IF EXISTS chunk_relations CASCADE;
DROP TABLE IF EXISTS chunks CASCADE;
DROP TABLE IF EXISTS documents CASCADE;

-- ============================================
-- 1. documents 테이블: 문서 메타데이터
-- ============================================
CREATE TABLE documents (
    doc_id VARCHAR(255) PRIMARY KEY,
    doc_type VARCHAR(50) NOT NULL,  
    -- 'law', 'mediation_case', 'counsel_case', 
    -- 'criteria_item', 'criteria_resolution', 'criteria_warranty', 'criteria_lifespan',
    -- 'guideline_content', 'guideline_ecommerce'
    title TEXT NOT NULL,
    source_org VARCHAR(100),  -- 'KCA', 'ECMC', 'KCDRC', 'statute', 'consumer.go.kr'
    category_path TEXT[],  -- 배열 타입으로 카테고리 경로 저장
    url TEXT,
    collected_at TIMESTAMP,
    metadata JSONB,  -- 유연한 메타데이터 저장
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 인덱스 생성
CREATE INDEX idx_documents_doc_type ON documents(doc_type);
CREATE INDEX idx_documents_source_org ON documents(source_org);
CREATE INDEX idx_documents_type_org ON documents(doc_type, source_org);  -- 복합 인덱스
CREATE INDEX idx_documents_category ON documents USING GIN(category_path);
CREATE INDEX idx_documents_metadata ON documents USING GIN(metadata);

-- 코멘트 추가
COMMENT ON TABLE documents IS '문서 메타데이터 테이블: 법령, 상담사례, 분쟁조정사례, 기준의 기본 정보';
COMMENT ON COLUMN documents.doc_type IS '문서 유형: law(법령), mediation_case(분쟁조정사례), counsel_case(피해구제사례), criteria_*(기준), guideline_*(가이드라인)';
COMMENT ON COLUMN documents.category_path IS '카테고리 경로 배열 (예: {상품(재화), 농수축산물, 란류})';
COMMENT ON COLUMN documents.source_org IS '출처 기관: KCA(한국소비자원), ECMC(전자거래분쟁조정위원회), KCDRC(지역분쟁조정위원회), statute(법령), consumer.go.kr(1372)';

-- ============================================
-- 2. chunks 테이블: 청크 및 임베딩
-- ============================================
CREATE TABLE chunks (
    chunk_id VARCHAR(255) PRIMARY KEY,
    doc_id VARCHAR(255) NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    chunk_total INTEGER NOT NULL,
    chunk_type VARCHAR(50),  -- 'article', 'paragraph', 'item_classification', 'resolution_row', 'decision', 'parties_claim', 'judgment', 'qa_combined', 'problem', 'solution', 'full', 'facts', 'claims', 'mediation_outcome' 등
    content TEXT NOT NULL,
    content_length INTEGER,
    embedding vector(1024),  -- KURE-v1 차원 (1024)
    drop BOOLEAN DEFAULT FALSE,  -- 삭제 플래그 (검색에서 제외할 청크)
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(doc_id, chunk_index),
    CHECK (chunk_index >= 0),  -- 0-based indexing
    CHECK (chunk_total > 0),
    CHECK (chunk_index < chunk_total)
);

-- 인덱스 생성
CREATE INDEX idx_chunks_doc_id ON chunks(doc_id);
CREATE INDEX idx_chunks_type ON chunks(chunk_type);
CREATE INDEX idx_chunks_doc_type ON chunks(doc_id, chunk_type);  -- 복합 인덱스
CREATE INDEX idx_chunks_embedding ON chunks USING ivfflat(embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_chunks_embedding_active ON chunks(chunk_type) WHERE embedding IS NOT NULL AND drop = FALSE;  -- 활성 청크만

-- 코멘트 추가
COMMENT ON TABLE chunks IS '청크 및 임베딩 테이블: 문서를 의미 단위로 분할한 청크와 벡터 임베딩';
COMMENT ON COLUMN chunks.chunk_type IS '청크 유형: article(조문), paragraph(항), item_classification(품목분류), resolution_row(해결기준), decision(결정), parties_claim(당사자주장), judgment(판단), qa_combined(질의응답), problem(질문), solution(답변), full(전체), facts(사건개요), claims(당사자주장), mediation_outcome(조정결과) 등';
COMMENT ON COLUMN chunks.embedding IS 'KURE-v1 모델로 생성된 1024차원 벡터 임베딩';
COMMENT ON COLUMN chunks.drop IS '삭제 플래그: TRUE인 경우 검색에서 제외 (데이터는 보존)';

-- ============================================
-- 3. chunk_relations 테이블: 청크 간 관계
-- ============================================
CREATE TABLE chunk_relations (
    source_chunk_id VARCHAR(255) NOT NULL REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    target_chunk_id VARCHAR(255) NOT NULL REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    relation_type VARCHAR(50) NOT NULL,  -- 'next', 'prev', 'related', 'cited', 'parent_article', 'child_paragraph', 'child_item', 'child_subitem'
    confidence FLOAT DEFAULT 1.0,  -- 관계 신뢰도 (0.0 ~ 1.0)
    created_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (source_chunk_id, target_chunk_id, relation_type),
    CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

-- 인덱스 생성
CREATE INDEX idx_chunk_relations_source ON chunk_relations(source_chunk_id);
CREATE INDEX idx_chunk_relations_target ON chunk_relations(target_chunk_id);
CREATE INDEX idx_chunk_relations_type ON chunk_relations(relation_type);

-- 코멘트 추가
COMMENT ON TABLE chunk_relations IS '청크 간 관계 테이블: 순서, 참조, 연관 관계 관리';
COMMENT ON COLUMN chunk_relations.relation_type IS '관계 유형: next(다음), prev(이전), related(연관), cited(인용), parent_article(상위 조문), child_paragraph(하위 항), child_item(하위 호), child_subitem(하위 목)';

-- ============================================
-- 4. laws 테이블: 법령 메타데이터
-- ============================================
CREATE TABLE laws (
    law_id VARCHAR(255) PRIMARY KEY,
    law_name TEXT NOT NULL,
    law_type VARCHAR(50),  -- 법률, 시행령, 시행규칙 등
    ministry VARCHAR(100),  -- 소관부처
    promulgation_date DATE,  -- 공포일자
    enforcement_date DATE,  -- 시행일자
    revision_type VARCHAR(50),  -- 제정, 개정, 일부개정 등
    domain VARCHAR(50) DEFAULT 'statute',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 인덱스 생성
CREATE INDEX idx_laws_law_name ON laws(law_name);
CREATE INDEX idx_laws_enforcement_date ON laws(enforcement_date);

-- 코멘트 추가
COMMENT ON TABLE laws IS '법령 메타데이터 테이블: 법령의 기본 정보';
COMMENT ON COLUMN laws.law_id IS '법령 고유 ID (법제처 법령ID)';
COMMENT ON COLUMN laws.enforcement_date IS '현재 시행일자 (최신 버전 기준)';

-- ============================================
-- 5. law_node 테이블: 법령 계층 구조
-- ============================================
CREATE TABLE law_node (
    doc_id VARCHAR(255) PRIMARY KEY,
    law_id VARCHAR(255) NOT NULL REFERENCES laws(law_id) ON DELETE CASCADE,
    parent_id VARCHAR(255) REFERENCES law_node(doc_id) DEFERRABLE INITIALLY DEFERRED,  -- 상위 노드 (article → paragraph → item → subitem)

    level VARCHAR(50) NOT NULL,  -- 'article', 'paragraph', 'item', 'subitem', 'chapter', 'section'
    is_indexable BOOLEAN NOT NULL DEFAULT TRUE,  -- 검색 가능 여부

    -- 조문 번호
    article_no VARCHAR(20),
    article_title TEXT,
    paragraph_no VARCHAR(20),
    item_no VARCHAR(20),
    subitem_no VARCHAR(20),

    -- 계층 경로 및 섹션 정보
    path TEXT,  -- 전체 경로 문자열 (예: "제17조 제1항 제2호")
    section_path JSONB DEFAULT '[]'::jsonb,  -- 편/장/절 경로 배열
    chapter_no VARCHAR(20),
    chapter_name TEXT,
    section_no VARCHAR(20),
    section_name TEXT,

    -- 본문 및 메타데이터
    text TEXT NOT NULL,  -- 조문 원문
    amendment_note TEXT,  -- 개정 노트 (예: "<2024.1.1>")

    -- 2단계 검색 지원
    search_stage VARCHAR(20),  -- 'stage1' (article-level) or 'stage2' (paragraph/item/subitem-level)

    -- 인용 정보
    ref_citations_internal JSONB DEFAULT '[]'::jsonb,  -- 내부 인용 (같은 법령 내)
    ref_citations_external JSONB DEFAULT '[]'::jsonb,  -- 외부 인용 (다른 법령)
    mentioned_laws JSONB DEFAULT '[]'::jsonb,  -- 언급된 법령

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 인덱스 생성
CREATE INDEX idx_law_node_law_id ON law_node(law_id);
CREATE INDEX idx_law_node_parent_id ON law_node(parent_id);
CREATE INDEX idx_law_node_level ON law_node(level);
CREATE INDEX idx_law_node_is_indexable ON law_node(is_indexable);
CREATE INDEX idx_law_node_law_article ON law_node(law_id, article_no);
CREATE INDEX idx_law_node_section_path ON law_node USING GIN(section_path);
CREATE INDEX idx_law_node_search_stage ON law_node(search_stage);

-- 코멘트 추가
COMMENT ON TABLE law_node IS '법령 계층 구조 테이블: 조/항/호/목 단위의 법령 노드';
COMMENT ON COLUMN law_node.level IS '노드 수준: article(조), paragraph(항), item(호), subitem(목), chapter(장), section(절)';
COMMENT ON COLUMN law_node.search_stage IS '검색 단계: stage1(조 수준 검색), stage2(항/호/목 정밀 검색)';
COMMENT ON COLUMN law_node.path IS '전체 계층 경로 (예: "전자상거래법 제17조 제1항 제2호")';

-- ============================================
-- 6. law_version 테이블: 법령 버전 관리
-- ============================================
CREATE TABLE law_version (
    version_id SERIAL PRIMARY KEY,
    law_id VARCHAR(255) NOT NULL REFERENCES laws(law_id) ON DELETE CASCADE,
    version_date DATE NOT NULL,  -- 시행일자
    version_type VARCHAR(50),  -- 제정, 개정, 일부개정, 전부개정 등
    description TEXT,  -- 개정 사유 또는 설명
    is_current BOOLEAN DEFAULT FALSE,  -- 현재 시행 버전 여부
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(law_id, version_date)
);

-- 인덱스 생성
CREATE INDEX idx_law_version_law_id ON law_version(law_id);
CREATE INDEX idx_law_version_date ON law_version(version_date);
CREATE INDEX idx_law_version_current ON law_version(law_id, is_current) WHERE is_current = TRUE;

-- 코멘트 추가
COMMENT ON TABLE law_version IS '법령 버전 관리 테이블: 법령의 시점별 개정 이력';
COMMENT ON COLUMN law_version.is_current IS '현재 시행 중인 버전 여부 (법령당 1개만 TRUE)';

-- ============================================
-- 7. law_citation_map 테이블: 사례-법령 연결
-- ============================================
CREATE TABLE law_citation_map (
    citation_id SERIAL PRIMARY KEY,
    source_type VARCHAR(50) NOT NULL,  -- 'mediation_case', 'counsel_case', 'criteria_rule'
    source_id VARCHAR(255) NOT NULL,  -- doc_id or chunk_id
    law_node_id VARCHAR(255) NOT NULL REFERENCES law_node(doc_id) ON DELETE CASCADE,
    citation_type VARCHAR(50),  -- 'direct' (직접 인용), 'related' (연관), 'applied' (적용)
    confidence FLOAT DEFAULT 1.0,  -- 연결 신뢰도 (0.0 ~ 1.0, 자동/수동 구분)
    created_by VARCHAR(50),  -- 'manual', 'auto', 'semi-auto'
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(source_type, source_id, law_node_id, citation_type),
    CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

-- 인덱스 생성
CREATE INDEX idx_law_citation_source ON law_citation_map(source_type, source_id);
CREATE INDEX idx_law_citation_law_node ON law_citation_map(law_node_id);
CREATE INDEX idx_law_citation_type ON law_citation_map(citation_type);

-- 코멘트 추가
COMMENT ON TABLE law_citation_map IS '사례-법령 연결 테이블: 상담/분쟁사례, 기준 규칙과 법령 조문 간의 인용/적용 관계';
COMMENT ON COLUMN law_citation_map.source_type IS '출처 유형: mediation_case(분쟁조정사례), counsel_case(상담사례), criteria_rule(분쟁조정기준)';
COMMENT ON COLUMN law_citation_map.citation_type IS '인용 유형: direct(직접 인용), related(연관), applied(적용)';
COMMENT ON COLUMN law_citation_map.created_by IS '생성 방식: manual(수동), auto(자동), semi-auto(반자동)';

-- ============================================
-- 8. 뷰: 문서와 청크 통합 조회
-- ============================================
CREATE OR REPLACE VIEW v_chunks_with_documents AS
SELECT 
    c.chunk_id,
    c.doc_id,
    c.chunk_index,
    c.chunk_total,
    c.chunk_type,
    c.content,
    c.content_length,
    c.embedding,
    c.drop,
    d.doc_type,
    d.title AS doc_title,
    d.source_org,
    d.category_path,
    d.url,
    d.metadata AS doc_metadata
FROM chunks c
JOIN documents d ON c.doc_id = d.doc_id;

COMMENT ON VIEW v_chunks_with_documents IS '청크와 문서 메타데이터를 통합 조회하는 뷰';

-- ============================================
-- 9. 함수: 벡터 유사도 검색
-- ============================================
CREATE OR REPLACE FUNCTION search_similar_chunks(
    query_embedding vector(1024),
    doc_type_filter VARCHAR(50) DEFAULT NULL,
    chunk_type_filter VARCHAR(50) DEFAULT NULL,
    source_org_filter VARCHAR(100) DEFAULT NULL,
    top_k INTEGER DEFAULT 10,
    min_similarity FLOAT DEFAULT 0.0
)
RETURNS TABLE (
    chunk_id VARCHAR(255),
    doc_id VARCHAR(255),
    chunk_type VARCHAR(50),
    content TEXT,
    doc_title TEXT,
    doc_type VARCHAR(50),
    source_org VARCHAR(100),
    category_path TEXT[],
    similarity FLOAT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.chunk_id,
        c.doc_id,
        c.chunk_type,
        c.content,
        d.title AS doc_title,
        d.doc_type,
        d.source_org,
        d.category_path,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM chunks c
    JOIN documents d ON c.doc_id = d.doc_id
    WHERE 
        c.drop = FALSE
        AND c.embedding IS NOT NULL
        AND (doc_type_filter IS NULL OR d.doc_type = doc_type_filter)
        AND (chunk_type_filter IS NULL OR c.chunk_type = chunk_type_filter)
        AND (source_org_filter IS NULL OR d.source_org = source_org_filter)
        AND (1 - (c.embedding <=> query_embedding)) >= min_similarity
    ORDER BY c.embedding <=> query_embedding
    LIMIT top_k;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION search_similar_chunks IS '벡터 유사도 기반 청크 검색 함수 (코사인 유사도, 다중 필터 지원)';

-- ============================================
-- 10. 함수: 청크 컨텍스트 확장
-- ============================================
CREATE OR REPLACE FUNCTION get_chunk_with_context(
    target_chunk_id VARCHAR(255),
    window_size INTEGER DEFAULT 1
)
RETURNS TABLE (
    chunk_id VARCHAR(255),
    doc_id VARCHAR(255),
    chunk_index INTEGER,
    chunk_type VARCHAR(50),
    content TEXT,
    is_target BOOLEAN
) AS $$
DECLARE
    target_doc_id VARCHAR(255);
    target_index INTEGER;
BEGIN
    -- 타겟 청크 정보 조회
    SELECT c.doc_id, c.chunk_index 
    INTO target_doc_id, target_index
    FROM chunks c 
    WHERE c.chunk_id = target_chunk_id;
    
    -- 타겟 청크와 주변 청크 반환
    RETURN QUERY
    SELECT 
        c.chunk_id,
        c.doc_id,
        c.chunk_index,
        c.chunk_type,
        c.content,
        (c.chunk_id = target_chunk_id) AS is_target
    FROM chunks c
    WHERE 
        c.doc_id = target_doc_id
        AND c.chunk_index >= (target_index - window_size)
        AND c.chunk_index <= (target_index + window_size)
        AND c.drop = FALSE
    ORDER BY c.chunk_index;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_chunk_with_context IS '특정 청크와 주변 청크를 함께 조회하는 함수 (컨텍스트 윈도우)';

-- ============================================
-- 11. 통계 뷰
-- ============================================
CREATE OR REPLACE VIEW v_data_statistics AS
SELECT 
    d.doc_type,
    d.source_org,
    COUNT(DISTINCT d.doc_id) AS document_count,
    COUNT(c.chunk_id) AS chunk_count,
    COUNT(CASE WHEN c.drop = FALSE THEN 1 END) AS active_chunk_count,
    AVG(c.content_length) AS avg_chunk_length,
    COUNT(CASE WHEN c.embedding IS NOT NULL THEN 1 END) AS embedded_chunk_count
FROM documents d
LEFT JOIN chunks c ON d.doc_id = c.doc_id
GROUP BY d.doc_type, d.source_org
ORDER BY d.doc_type, d.source_org;

COMMENT ON VIEW v_data_statistics IS '데이터 유형별 통계 정보 (문서 수, 청크 수, 평균 길이 등)';

-- ============================================
-- 12. 트리거: updated_at 자동 업데이트
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_chunks_updated_at
    BEFORE UPDATE ON chunks
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_laws_updated_at
    BEFORE UPDATE ON laws
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_law_node_updated_at
    BEFORE UPDATE ON law_node
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 8. criteria 테이블: 분쟁조정기준 원천 (S1-D3)
-- ============================================
CREATE TABLE IF NOT EXISTS criteria (
    source_id TEXT PRIMARY KEY,
    source_label TEXT,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE criteria IS '분쟁조정기준 데이터 원천 테이블 (별표1~4, 지침 등)';
COMMENT ON COLUMN criteria.source_id IS '원천 고유 식별자 (예: table1, table2, table3, table4, ecommerce_guideline, content_guideline)';
COMMENT ON COLUMN criteria.source_label IS '화면/문서 표시용 이름 (예: 별표1 품목 분류, 전자상거래 소비자보호 지침)';
COMMENT ON COLUMN criteria.description IS '원천 데이터에 대한 간단한 설명';

-- ============================================
-- 9. criteria_units 테이블: 분쟁조정기준 단위 레코드 (S1-D3)
-- ============================================
CREATE TABLE IF NOT EXISTS criteria_units (
    unit_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES criteria(source_id) ON DELETE CASCADE,
    record_type TEXT,
    unit_type TEXT,
    path_hint TEXT,
    unit_text TEXT NOT NULL,
    content_md5 TEXT,
    doc JSONB NOT NULL,
    embedding VECTOR(1024),  -- KURE-v1 Korean embedding model
    -- 계층 검색용 필드
    category TEXT,
    industry TEXT,
    item_group TEXT,
    item TEXT,
    dispute_type TEXT,
    search_stage TEXT,  -- 'stage1' 또는 'stage2'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE criteria_units IS '분쟁조정기준 단위 레코드 (검색·조회·RAG 활용)';
COMMENT ON COLUMN criteria_units.unit_id IS '단위 고유 식별자 (원천 ID + 내부 식별자 조합)';
COMMENT ON COLUMN criteria_units.source_id IS 'criteria.source_id 참조';
COMMENT ON COLUMN criteria_units.record_type IS '원천별 레코드 구분값 (예: item_chunk, rule_chunk, reference_block)';
COMMENT ON COLUMN criteria_units.unit_type IS '청킹 과정에서 생성된 세부 유형 (없을 경우 NULL)';
COMMENT ON COLUMN criteria_units.path_hint IS '문서/헤딩 기반 경로 요약 (검색 결과 설명용)';
COMMENT ON COLUMN criteria_units.unit_text IS '검색·RAG 응답에 사용할 대표 텍스트';
COMMENT ON COLUMN criteria_units.content_md5 IS '대표 텍스트 기반 중복 방지용 해시';
COMMENT ON COLUMN criteria_units.doc IS '업로드된 JSONL 원형 데이터 전체 (JSONB)';
COMMENT ON COLUMN criteria_units.embedding IS '벡터 임베딩 (KURE-v1 Korean model, 1024차원)';

-- 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_criteria_units_source_id ON criteria_units(source_id);
CREATE INDEX IF NOT EXISTS idx_criteria_units_record_type ON criteria_units(record_type);
CREATE INDEX IF NOT EXISTS idx_criteria_units_unit_type ON criteria_units(unit_type);
CREATE INDEX IF NOT EXISTS idx_criteria_units_content_md5 ON criteria_units(content_md5);

-- 벡터 검색 인덱스 (IVFFlat - matches main schema pattern)
CREATE INDEX IF NOT EXISTS idx_criteria_units_embedding_ivfflat
    ON criteria_units USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- 전문 검색 인덱스 (한국어)
CREATE INDEX IF NOT EXISTS idx_criteria_units_unit_text_gin
    ON criteria_units USING gin(to_tsvector('simple', unit_text));

-- JSONB 인덱스 (doc 내부 필드 검색용)
CREATE INDEX IF NOT EXISTS idx_criteria_units_doc_gin
    ON criteria_units USING gin(doc);

-- 복합 인덱스 (source_id + record_type 조합 검색)
CREATE INDEX IF NOT EXISTS idx_criteria_units_source_record
    ON criteria_units(source_id, record_type);

-- 계층 검색용 인덱스
CREATE INDEX IF NOT EXISTS idx_criteria_units_category_industry
    ON criteria_units(category, industry);
CREATE INDEX IF NOT EXISTS idx_criteria_units_item_group
    ON criteria_units(item_group);
CREATE INDEX IF NOT EXISTS idx_criteria_units_search_stage
    ON criteria_units(search_stage);
CREATE INDEX IF NOT EXISTS idx_criteria_units_dispute_type
    ON criteria_units(dispute_type);

-- 초기 데이터: criteria 원천 등록
INSERT INTO criteria (source_id, source_label, description) VALUES
    ('table1', '별표1 품목 분류', '소비자분쟁해결기준 대상품목 분류'),
    ('table2', '별표2 해결기준', '소비자분쟁해결기준 품목별 해결기준'),
    ('table3', '별표3 품질보증기간', '소비자분쟁해결기준 품목별 품질보증기간 및 부품보유기간'),
    ('table4', '별표4 내용연수', '소비자분쟁해결기준 품목별 내용연수'),
    ('ecommerce_guideline', '전자상거래 소비자보호 지침', '전자상거래 등에서의 소비자보호 지침'),
    ('content_guideline', '콘텐츠 소비자보호 지침', '콘텐츠 소비자보호 지침')
ON CONFLICT (source_id) DO NOTHING;

-- 트리거: criteria_units updated_at 자동 업데이트
CREATE TRIGGER update_criteria_units_updated_at
    BEFORE UPDATE ON criteria_units
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- 완료 메시지
-- ============================================
DO $$
BEGIN
    RAISE NOTICE '============================================';
    RAISE NOTICE '똑소리 프로젝트 데이터베이스 스키마 v2 + S1-D2 + S1-D3 생성 완료';
    RAISE NOTICE '============================================';
    RAISE NOTICE '생성된 RAG 테이블:';
    RAISE NOTICE '  - documents: 문서 메타데이터';
    RAISE NOTICE '  - chunks: 청크 및 임베딩 (drop 플래그 추가)';
    RAISE NOTICE '  - chunk_relations: 청크 간 관계 (법령 계층 타입 추가)';
    RAISE NOTICE '';
    RAISE NOTICE '생성된 법령 테이블 (S1-D2):';
    RAISE NOTICE '  - laws: 법령 메타데이터';
    RAISE NOTICE '  - law_node: 법령 계층 구조 (조/항/호/목)';
    RAISE NOTICE '  - law_version: 법령 버전 관리';
    RAISE NOTICE '  - law_citation_map: 사례-법령 연결';
    RAISE NOTICE '';
    RAISE NOTICE '생성된 분쟁조정기준 테이블 (S1-D3):';
    RAISE NOTICE '  - criteria: 분쟁조정기준 원천 (별표1~4, 지침)';
    RAISE NOTICE '  - criteria_units: 분쟁조정기준 단위 레코드 (계층 검색 지원)';
    RAISE NOTICE '';
    RAISE NOTICE '생성된 뷰:';
    RAISE NOTICE '  - v_chunks_with_documents: 통합 조회';
    RAISE NOTICE '  - v_data_statistics: 통계 정보';
    RAISE NOTICE '';
    RAISE NOTICE '생성된 함수:';
    RAISE NOTICE '  - search_similar_chunks(): 벡터 검색 (다중 필터 지원)';
    RAISE NOTICE '  - get_chunk_with_context(): 컨텍스트 확장';
    RAISE NOTICE '';
    RAISE NOTICE '주요 변경사항:';
    RAISE NOTICE '  [S1-D2] 법령 계층 구조 및 2단계 검색 지원';
    RAISE NOTICE '  [S1-D3] 분쟁조정기준 데이터 정형화 (별표1~4)';
    RAISE NOTICE '  [공통] KURE-v1 임베딩 (1024차원) 사용';
    RAISE NOTICE '============================================';
END $$;
