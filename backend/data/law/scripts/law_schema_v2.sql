-- law_schema_v2.sql
-- 법령 데이터 스키마 (실제 DB 명세서 기준)

CREATE EXTENSION IF NOT EXISTS vector;

-- =========================
-- 1) laws (법령 기본 정보)
-- =========================
CREATE TABLE IF NOT EXISTS laws (
  law_id              TEXT PRIMARY KEY,
  law_name            TEXT NOT NULL,
  law_type            TEXT,
  ministry            TEXT,
  promulgation_date   DATE,
  enforcement_date    DATE,
  revision_type       TEXT,
  domain              TEXT DEFAULT 'statute'
);

-- =========================
-- 2) law_units (법령 조문 단위)
-- =========================
CREATE TABLE IF NOT EXISTS law_units (
  doc_id                 TEXT PRIMARY KEY,
  law_id                 TEXT NOT NULL REFERENCES laws(law_id) ON DELETE CASCADE,
  parent_id              TEXT REFERENCES law_units(doc_id),

  level                  TEXT NOT NULL,
  is_indexable           BOOLEAN NOT NULL DEFAULT TRUE,

  article_no             TEXT,
  article_title          TEXT,
  paragraph_no           TEXT,
  item_no                TEXT,
  subitem_no             TEXT,

  path                   TEXT,
  text                   TEXT NOT NULL,
  amendment_note         TEXT,

  -- 섹션 정보 (계층적 검색용)
  section_path           JSONB NOT NULL DEFAULT '[]'::jsonb,
  chapter_no             TEXT,
  chapter_name           TEXT,
  section_no             TEXT,
  section_name           TEXT,
  search_stage           TEXT,  -- 'stage1' (article) or 'stage2' (paragraph/item/subitem)

  ref_citations_internal JSONB NOT NULL DEFAULT '[]'::jsonb,
  ref_citations_external JSONB NOT NULL DEFAULT '[]'::jsonb,
  mentioned_laws         JSONB NOT NULL DEFAULT '[]'::jsonb
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_law_units_law_id ON law_units(law_id);
CREATE INDEX IF NOT EXISTS idx_law_units_parent_id ON law_units(parent_id);
CREATE INDEX IF NOT EXISTS idx_law_units_level ON law_units(level);
CREATE INDEX IF NOT EXISTS idx_law_units_is_indexable ON law_units(is_indexable);
CREATE INDEX IF NOT EXISTS idx_law_units_law_article ON law_units(law_id, article_no);
CREATE INDEX IF NOT EXISTS idx_law_units_section_path ON law_units USING GIN (section_path);
CREATE INDEX IF NOT EXISTS idx_law_units_chapter_no ON law_units(chapter_no);
CREATE INDEX IF NOT EXISTS idx_law_units_search_stage ON law_units(search_stage);

-- =========================
-- 3) statute_chunk_vectors (Vector 인덱스)
-- =========================
CREATE TABLE IF NOT EXISTS statute_chunk_vectors (
  unit_id         TEXT NOT NULL,
  embedding_model TEXT NOT NULL,
  law_id          TEXT NOT NULL,
  unit_level      TEXT,
  path            TEXT,
  node_refs       JSONB NOT NULL DEFAULT '[]'::jsonb,
  index_text      TEXT,
  embedding       VECTOR(1024) NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (unit_id, embedding_model)
);

-- 필터/조인용 인덱스
CREATE INDEX IF NOT EXISTS idx_statute_chunk_vectors_law_id
  ON statute_chunk_vectors(law_id);

CREATE INDEX IF NOT EXISTS idx_statute_chunk_vectors_unit_level
  ON statute_chunk_vectors(unit_level);

CREATE INDEX IF NOT EXISTS idx_statute_chunk_vectors_embedding_model
  ON statute_chunk_vectors(embedding_model);

-- 벡터 인덱스 (HNSW + cosine)
CREATE INDEX IF NOT EXISTS idx_statute_chunk_vectors_embedding_hnsw
  ON statute_chunk_vectors
  USING hnsw (embedding vector_cosine_ops);
