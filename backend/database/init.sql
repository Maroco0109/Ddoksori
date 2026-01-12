-- Database initialization script
-- This script runs when the PostgreSQL container is first created
-- PostgreSQL은 /docker-entrypoint-initdb.d/ 디렉토리의 .sql, .sh 파일을 알파벳 순서로 자동 실행합니다.

-- Create database if not exists
SELECT 'CREATE DATABASE ddoksori'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'ddoksori')\gexec

-- Connect to ddoksori database
\c ddoksori

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 한국어 검색 설정 생성 (Fallback: simple)
-- 'korean' 설정이 없어서 발생하는 오류를 방지하기 위해 simple 설정을 복사하여 생성합니다.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_ts_config
        WHERE cfgname = 'korean'
    ) THEN
        CREATE TEXT SEARCH CONFIGURATION public.korean (COPY = simple);
    END IF;
END
$$;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE ddoksori TO postgres;

-- Note: 실제 테이블 스키마(schema_v2_final.sql)는 별도로 실행해야 합니다.
-- Docker 컨테이너 내에서 실행:
--   docker exec -i ddoksori_db psql -U postgres -d ddoksori < /path/to/schema_v2_final.sql
-- 또는 로컬에서 실행:
--   psql -h localhost -p 5432 -U postgres -d ddoksori -f backend/database/schema_v2_final.sql
