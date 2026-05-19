# M1-4 `search_hybrid_rrf_2()` Schema 복구 계획

- 작성일: 2026-05-19
- 모듈: `M1-4` `search_hybrid_rrf_2()` schema 복구
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`
- 선행 모듈: `docs/plans/modules/M1-1-rag-db-inventory.md`, `docs/plans/modules/M1-2-vector-db-smoke.md`, `docs/plans/modules/M1-3-rag-schema-compatibility-plan.md`
- 목표: 현재 복원 DB에는 없는 `search_hybrid_rrf_2()`를 재현 가능한 schema asset으로 복구하고, 이후 smoke check에서 active RAG 기준선으로 검증할 수 있게 한다.
- 이번 문서에서 하지 않는 일: SQL 실행, DB volume 변경, `docker-compose.yml` 수정, backend retrieval 코드 수정, 검색 품질 튜닝, legacy schema 복구.

## 1. 결론 요약

M1-4의 실행 범위는 하나로 제한한다.

> `backend/app/agents/retrieval/docs/rds_internal_function.md`에 문서 형태로 남아 있는 `search_hybrid_rrf_2()` DDL을 repository-tracked SQL/schema file로 승격하고, local restored DB와 smoke script에서 검증 가능한 상태로 만든다.

M1-4가 끝나면 다음이 가능해야 한다.

- 새 worktree나 context reset 이후에도 `search_hybrid_rrf_2()` DDL 위치를 찾을 수 있다.
- local restored DB에 같은 함수를 반복 적용할 수 있다.
- `check_vector_db_smoke.py`가 `search_hybrid_rrf_2()`를 optional missing이 아니라 required OK 대상으로 검증한다.
- 법령/기준 specialized retrieval이 사용하는 DB function 계약이 문서와 코드에서 같은 이름과 signature로 고정된다.

## 2. 현재 기준선

M1-2와 M1-3 기준 현재 상태는 다음과 같다.

| 항목 | 상태 | M1-4 판단 |
| --- | --- | --- |
| `vector` extension | 존재 | 유지 |
| `vector_chunks` | 존재, 40,285 rows | active table로 유지 |
| embedding dimension | 전체 `1536` | `vector(1536)` 기준 유지 |
| `text_tsv` | 존재 | BM25/RRF 검색 필수 |
| `search_similar_chunks()` | 존재 | dense smoke 기준 유지 |
| `search_hybrid_rrf()` | 존재 | case/counsel 계열 hybrid 기준 유지 |
| `search_hybrid_rrf_2()` | 없음 | M1-4에서 복구 |
| `documents`, `chunks`, `law_units`, `mv_searchable_chunks` | 없음 | M1-4에서 복구하지 않음 |
| compose DB service | 없음 | M1-4에서 추가하지 않음 |

## 3. 구현 모듈별 해야 할 일

M1-4는 아래 하위 작업을 순서대로 수행한다. 각 하위 작업은 같은 feature branch/worktree 안에서 처리하되, 범위는 `search_hybrid_rrf_2()` 복구에만 묶는다.

### M1-4.1 Schema asset 추가

해야 할 일:

- `search_hybrid_rrf_2()`만 담은 tracked SQL/schema file을 추가한다.
- 원본 DDL은 `backend/app/agents/retrieval/docs/rds_internal_function.md`의 `CREATE OR REPLACE FUNCTION search_hybrid_rrf_2(...)` 블록을 기준으로 한다.
- SQL file에는 최소한 아래 전제 조건을 주석으로 남긴다.
  - PostgreSQL + `pgvector` extension 필요
  - `public.vector_chunks` 필요
  - `embedding vector(1536)` 필요
  - `text_tsv` 필요
- 기존 `search_similar_chunks()`나 `search_hybrid_rrf()` DDL은 M1-4에서 다시 옮기지 않는다.

권장 파일 위치:

```text
backend/app/database/schema/search_hybrid_rrf_2.sql
```

완료 기준:

- repository 안에서 `search_hybrid_rrf_2()` DDL이 문서가 아니라 실행 가능한 `.sql` 파일로 존재한다.
- 파일은 idempotent하게 `CREATE OR REPLACE FUNCTION`을 사용한다.

### M1-4.2 Function signature 고정

해야 할 일:

- 현재 runtime caller와 호환되는 signature를 유지한다.
- 필터 계약은 아래를 기준으로 고정한다.

```sql
search_hybrid_rrf_2(
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
```

반환 column 계약:

- `chunk_id`
- `dataset_type`
- `text`
- `rrf_score`
- `bm25_score`
- `vector_similarity`
- `law_name`
- `chunk_type`
- `category`
- `document_type`
- `source_url`
- `source_file`
- `printed_page`
- `source_year`
- `metadata`

완료 기준:

- `backend/app/agents/retrieval/tools/rds_internal_retriever.py`와 `specialized_retrievers.py`의 기존 호출 방식을 바꾸지 않아도 된다.
- 반환 column 이름이 기존 `SimilarChunkResult` 매핑과 충돌하지 않는다.

### M1-4.3 Local restored DB 적용 검증

해야 할 일:

- M1-2에서 사용한 local restored DB에 SQL file을 적용한다.
- 적용 명령은 문서나 PR 본문에 재실행 가능하게 남긴다.

권장 검증 명령:

```bash
PGPASSWORD=postgres psql \
  "postgresql://postgres@127.0.0.1:5432/ddoksori" \
  -f backend/app/database/schema/search_hybrid_rrf_2.sql
```

또는 backend container에서 실행한다.

```bash
docker compose run --rm backend \
  psql "postgresql://postgres:postgres@host.docker.internal:5432/ddoksori" \
  -f app/database/schema/search_hybrid_rrf_2.sql
```

완료 기준:

- SQL 적용이 에러 없이 완료된다.
- 아래 query가 `1` 이상의 값을 반환한다.

```sql
SELECT COUNT(*) AS function_count
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public'
  AND p.proname = 'search_hybrid_rrf_2';
```

### M1-4.4 Smoke script 확장

해야 할 일:

- `backend/scripts/testing/check_vector_db_smoke.py`에서 `search_hybrid_rrf_2`를 optional object에서 critical function으로 승격한다.
- summary JSON에는 기존처럼 function 목록과 sample 결과가 남아야 한다.
- sample query는 existing `vector_chunks.embedding`을 사용해서 OpenAI API 없이 실행한다.

권장 sample query:

```sql
WITH q AS (
  SELECT embedding
  FROM vector_chunks
  WHERE dataset_type = 'law_guide'
    AND embedding IS NOT NULL
  LIMIT 1
)
SELECT chunk_id,
       dataset_type,
       chunk_type,
       document_type,
       rrf_score,
       bm25_score,
       vector_similarity
FROM search_hybrid_rrf_2(
  '소비자 분쟁 해결 기준',
  (SELECT embedding FROM q),
  'law_guide',
  NULL,
  ARRAY['법률', '시행령']::VARCHAR(20)[],
  NULL,
  NULL,
  NULL,
  3,
  60
);
```

완료 기준:

- 함수가 없으면 smoke script가 실패한다.
- 함수가 있으면 sample query가 SQL error 없이 실행된다.
- matching row가 없을 가능성은 실패로 보지 않는다. 단, current restored DB에서는 결과 반환을 기대한다.

### M1-4.5 Regression guard

해야 할 일:

- 기존 M1-2 smoke 검증 항목은 유지한다.
- `search_similar_chunks()`와 `search_hybrid_rrf()` sample이 계속 통과해야 한다.
- `vector_chunks` row count, embedding count, `text_tsv`, 1536 dimension 검증을 약화하지 않는다.

완료 기준:

- M1-4 이후에도 M1-2 active retrieval baseline이 깨지지 않는다.
- 새 검증은 `search_hybrid_rrf_2()`만 추가한다.

## 4. 명시적 비범위

M1-4에서는 아래를 하지 않는다.

- Ddoksori `docker-compose.yml`에 PostgreSQL/pgvector service 추가
- 외부 DB dump 생성 또는 restore 자동화
- `documents`, `chunks`, `law_units`, `mv_searchable_chunks` 생성
- retrieval ranking 로직 변경
- law/criteria retriever 품질 튜닝
- OpenAI embedding 호출 경로 변경
- RunPod/local LLM provider 전환
- `/search` API end-to-end smoke

이 항목들은 M1-5 이후 별도 모듈로 진행한다.

## 5. 검증 계획

M1-4 구현 PR에서 실행할 검증은 다음 순서로 고정한다.

```bash
git diff --check
```

```bash
docker compose config
```

```bash
docker compose run --rm backend python -m py_compile scripts/testing/check_vector_db_smoke.py
```

```bash
docker compose run --rm backend python scripts/testing/check_vector_db_smoke.py
```

DB에 SQL을 적용한 뒤에는 아래를 추가로 확인한다.

```bash
docker compose run --rm backend python scripts/testing/check_vector_db_smoke.py
```

성공 기준:

- `search_hybrid_rrf_2`가 function 목록에 표시된다.
- `search_hybrid_rrf_2` sample query가 crash 없이 실행된다.
- 기존 dense/hybrid sample query도 계속 통과한다.

## 6. PR 완료 기준

M1-4 구현 PR은 아래가 모두 만족되면 완료로 본다.

- tracked SQL/schema file이 추가됨
- smoke script가 `search_hybrid_rrf_2()`를 required check로 검증함
- local restored DB에 함수 적용 후 smoke 통과 evidence가 PR에 남음
- diff가 `search_hybrid_rrf_2()` 복구 범위를 넘지 않음
- legacy schema/compose/dump restore 변경이 포함되지 않음

## 7. 다음 모듈 gate

M1-4 완료 후 바로 다음 구현으로 넘어가지 않는다. PR merge와 사용자 검토 후 다음 중 하나를 별도 모듈로 시작한다.

| 후보 모듈 | 목표 | 완료 기준 |
| --- | --- | --- |
| `M1-5` | 외부 DB dump/restore 경로 문서화 | 재실행 가능한 dump 명령과 산출물 위치 확정 |
| `M1-6` | Ddoksori compose에 pgvector service 추가 | `docker compose up postgres`와 extension 확인 |
| `M1-7` | Ddoksori volume에 dump restore | `vector_chunks` row count와 1536 dimension 재확인 |
| `M1-8` | backend `/search` smoke | `/search`가 local compose DB로 검색 결과 반환 |
