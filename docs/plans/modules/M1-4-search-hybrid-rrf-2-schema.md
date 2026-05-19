# M1-4 `search_hybrid_rrf_2()` Schema 복구

- 작성일: 2026-05-19
- 모듈: `M1-4` `search_hybrid_rrf_2()` schema 복구
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`
- 선행 모듈: `docs/plans/modules/M1-1-rag-db-inventory.md`, `docs/plans/modules/M1-2-vector-db-smoke.md`, `docs/plans/modules/M1-3-rag-schema-compatibility-plan.md`
- 목표: `search_hybrid_rrf_2()`를 재현 가능한 schema asset으로 복구하고 smoke check에서 active RAG 기준선으로 검증한다.
- 이번 모듈에서 하지 않는 일: compose PostgreSQL service 추가, dump/restore 자동화, legacy schema 복구, retrieval 품질 튜닝, provider/model 전환.

## 1. 결론

M1-4는 완료 기준을 만족한다.

- 추가: `backend/app/database/schema/search_hybrid_rrf_2.sql`
- 수정: `backend/scripts/testing/check_vector_db_smoke.py`
- local restored DB 적용: 성공
- smoke 검증: 성공

`search_hybrid_rrf_2()`는 이제 repository-tracked SQL file로 복구되었고, smoke script에서 optional object가 아니라 required function으로 검증된다.

## 2. `/home/maroco/data_collection_snippets` 점검 결과

외부 데이터 수집 repo를 점검했다.

확인 명령 범위:

- checked-out files에서 `search_hybrid_rrf_2` 검색
- git 전체 refs에서 `search_hybrid_rrf_2` 검색
- `DB/01_00_unified_schema.sql`의 `vector_chunks`, `search_hybrid_rrf()` 확인
- `DB/migrations/fix_search_hybrid_rrf_ambiguous_column.py` 확인

결과:

- `/home/maroco/data_collection_snippets`에는 `search_hybrid_rrf_2()` exact DDL이 없다.
- git history / all refs에도 `search_hybrid_rrf_2` 문자열은 없다.
- 다만 복구에 필요한 기준 정보는 있다.
  - `DB/01_00_unified_schema.sql`: `vector_chunks`, `text_tsv`, `search_hybrid_rrf()` 기준 schema
  - `DB/migrations/fix_search_hybrid_rrf_ambiguous_column.py`: RRF function에서 `vc.*` alias를 명시해야 하는 migration 근거
  - `docker-compose.yml`: `pgvector/pgvector:pg17`, DB `ddoksori`, user/password `postgres`

따라서 M1-4 복구 SQL은 다음을 조합해 작성했다.

1. 외부 repo의 `vector_chunks`/`search_hybrid_rrf()` schema shape
2. 외부 migration의 ambiguous column 회피 패턴
3. 현재 Ddoksori에 남아 있던 `backend/app/agents/retrieval/docs/rds_internal_function.md`의 `search_hybrid_rrf_2()` 계약

## 3. 복구한 DB function 계약

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

반환 column:

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

이 계약은 `backend/app/agents/retrieval/tools/rds_internal_retriever.py`의 existing row mapping과 맞춘다.

## 4. 적용 및 검증 결과

Local restored DB container가 중지되어 있어 외부 compose의 postgres만 재기동했다.

```bash
docker compose -f /home/maroco/data_collection_snippets/docker-compose.yml up -d postgres
```

적용 전 함수 존재 여부:

```text
search_hybrid_rrf_2 count = 0
```

적용 명령:

```bash
docker exec -i data_collection_snippets-postgres-1 \
  psql -U postgres -d ddoksori \
  < backend/app/database/schema/search_hybrid_rrf_2.sql
```

적용 결과:

```text
CREATE FUNCTION
search_hybrid_rrf_2 count = 1
```

Smoke 검증:

```bash
python -m py_compile backend/scripts/testing/check_vector_db_smoke.py
DB_HOST=host.docker.internal \
DB_PORT=5432 \
DB_NAME=ddoksori \
DB_USER=postgres \
DB_PASSWORD=postgres \
docker compose run --rm backend python scripts/testing/check_vector_db_smoke.py
```

핵심 결과:

| Check | Result |
| --- | --- |
| `vector` extension | OK, `0.8.2` |
| `vector_chunks` rows | `40,285` |
| embeddings present | `40,285` |
| `text_tsv` present | `40,285` |
| vector dimensions | all `1536` |
| `search_similar_chunks()` | OK |
| `search_hybrid_rrf()` | OK |
| `search_hybrid_rrf_2()` | OK |
| `search_hybrid_rrf_2` sample rows | 3 rows returned |

Sample `search_hybrid_rrf_2()` result included rows such as:

- `민법_제912조`
- `약관의 규제에 관한 법률_제31조`
- `민법_제1조`

## 5. 남은 비범위 / 다음 gate

M1-4에서는 아래를 일부러 하지 않았다.

- Ddoksori compose에 PostgreSQL/pgvector service 추가
- 외부 DB dump 생성 또는 restore 자동화
- `documents`, `chunks`, `law_units`, `mv_searchable_chunks` 생성
- retrieval ranking 로직 변경
- law/criteria retriever 품질 튜닝
- OpenAI embedding 호출 경로 변경
- RunPod/local LLM provider 전환
- `/search` API end-to-end smoke

다음 후보는 별도 모듈로만 진행한다.

| 후보 모듈 | 목표 | 완료 기준 |
| --- | --- | --- |
| `M1-5` | 외부 DB dump/restore 경로 문서화 | 재실행 가능한 dump 명령과 산출물 위치 확정 |
| `M1-6` | Ddoksori compose에 pgvector service 추가 | `docker compose up postgres`와 extension 확인 |
| `M1-7` | Ddoksori volume에 dump restore | `vector_chunks` row count와 1536 dimension 재확인 |
| `M1-8` | backend `/search` smoke | `/search`가 local compose DB로 검색 결과 반환 |
