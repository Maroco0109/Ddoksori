-- Local compose bootstrap for the M1-6 pgvector service.
-- Data/schema restore is intentionally deferred to M1-7.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
