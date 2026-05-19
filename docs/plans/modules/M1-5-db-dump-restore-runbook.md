# M1-5 외부 DB dump/restore 경로 문서화 계획

- 작성일: 2026-05-19
- 모듈: `M1-5` 외부 DB dump/restore 경로 문서화
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`
- 선행 모듈: `M1-1` RAG DB inventory, `M1-2` vector DB smoke, `M1-3` schema compatibility 결정, `M1-4` `search_hybrid_rrf_2()` schema 복구
- 목표: `/home/maroco/data_collection_snippets`의 외부 Docker pgvector DB를 Ddoksori compose-owned DB volume으로 옮기기 전에, dump 생성/보관/restore/검증 절차를 재실행 가능한 runbook으로 고정한다.
- 이번 모듈에서 하지 않는 일: 실제 dump 생성, 실제 restore 실행, `docker-compose.yml` DB service 추가, DB volume 변경, seed fixture 작성, backend runtime 코드 수정.

## 1. 결론

M1-5는 **구현/마이그레이션이 아니라 runbook 모듈**이다.

현재 기준 DB는 외부 프로젝트의 Docker volume에 있으므로, 다음 구현 모듈들이 안전하게 진행되려면 먼저 아래를 문서로 고정해야 한다.

1. 어떤 DB를 source of truth로 dump할지
2. 어떤 dump format을 사용할지
3. dump artifact를 어디에 둘지
4. Ddoksori compose DB가 생긴 뒤 어떤 순서로 restore할지
5. restore 후 어떤 수치로 성공을 판단할지

## 2. Source DB 기준선

M1-5 runbook의 source DB는 아래로 고정한다.

| 항목 | 값 |
| --- | --- |
| Source repo | `/home/maroco/data_collection_snippets` |
| Compose file | `/home/maroco/data_collection_snippets/docker-compose.yml` |
| Container | `data_collection_snippets-postgres-1` |
| Image | `pgvector/pgvector:pg17` |
| Database | `ddoksori` |
| User/password | `postgres` / `postgres` |
| Host port | `5432` |

현재 검증된 DB baseline:

| Check | Expected |
| --- | ---: |
| `vector_chunks` rows | `40,285` |
| rows with embedding | `40,285` |
| rows with `text_tsv` | `40,285` |
| rows with `vector_dims(embedding)=1536` | `40,285` |
| `search_similar_chunks()` | exists and sample OK |
| `search_hybrid_rrf()` | exists and sample OK |
| `search_hybrid_rrf_2()` | exists and sample OK after M1-4 |
| legacy relations | `documents`, `chunks`, `law_units`, `mv_searchable_chunks` absent |

## 3. Runbook에서 정리할 작업

### M1-5.1 Source DB readiness check

문서화할 내용:

```bash
docker compose -f /home/maroco/data_collection_snippets/docker-compose.yml up -d postgres
docker exec data_collection_snippets-postgres-1 pg_isready -U postgres -d ddoksori
```

확인 기준:

- container가 running 상태
- `pg_isready` 성공
- `vector` extension과 `vector_chunks`가 존재
- M1-4 기준 `search_hybrid_rrf_2()`가 존재

### M1-5.2 Dump format 결정

권장 dump format:

```text
pg_dump --format=custom --no-owner --no-privileges
```

이유:

- custom format은 `pg_restore`에서 restore 대상 DB, 병렬 처리, section 선택이 유연하다.
- `--no-owner --no-privileges`는 다른 local role/owner 환경으로 옮길 때 충돌을 줄인다.
- 전체 `vector_chunks` data를 보존하므로 seed fixture가 아니라 실제 baseline 비교가 가능하다.

비채택:

- plain SQL only: review는 쉽지만 대용량 restore와 선택 복원이 불편하다.
- schema-only: 검색 baseline 수치 비교에 필요한 40,285 rows를 보존하지 못한다.
- data-only: extension/function/table 생성 순서가 별도 관리되어 초기 복원 runbook이 복잡해진다.

### M1-5.3 Dump artifact 위치/이름

runbook에는 artifact 위치를 repo 밖 또는 ignored 경로로 정리한다.

권장 위치:

```text
/home/maroco/Ddoksori-local-artifacts/db-dumps/
```

권장 파일명:

```text
ddoksori-vector-db-YYYYMMDD.pgcustom
```

주의:

- dump file은 git에 포함하지 않는다.
- dump에는 실제 수집 데이터와 embedding이 포함되므로 PR에 첨부하지 않는다.
- checksum만 문서에 남긴다.

### M1-5.4 Dump 생성 명령

runbook에 남길 명령:

```bash
mkdir -p /home/maroco/Ddoksori-local-artifacts/db-dumps

docker exec data_collection_snippets-postgres-1 \
  pg_dump \
  --username=postgres \
  --dbname=ddoksori \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file=/tmp/ddoksori-vector-db.pgcustom

docker cp \
  data_collection_snippets-postgres-1:/tmp/ddoksori-vector-db.pgcustom \
  /home/maroco/Ddoksori-local-artifacts/db-dumps/ddoksori-vector-db-YYYYMMDD.pgcustom

sha256sum /home/maroco/Ddoksori-local-artifacts/db-dumps/ddoksori-vector-db-YYYYMMDD.pgcustom
```

완료 기준:

- dump file이 repo 밖 artifact directory에 생성됨
- sha256 checksum 기록 가능
- dump 생성 명령이 source DB container에만 read-only 성격으로 작동함

### M1-5.5 Restore 준비 명령

M1-6 이후 Ddoksori compose DB service가 생겼다고 가정한 restore 절차를 문서화한다.

예상 restore target:

```text
service/container: Ddoksori compose postgres service
DB: ddoksori
user/password: postgres/postgres for local dev
```

예상 restore command:

```bash
docker cp \
  /home/maroco/Ddoksori-local-artifacts/db-dumps/ddoksori-vector-db-YYYYMMDD.pgcustom \
  <ddoksori-postgres-container>:/tmp/ddoksori-vector-db.pgcustom

docker exec <ddoksori-postgres-container> \
  pg_restore \
  --username=postgres \
  --dbname=ddoksori \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  /tmp/ddoksori-vector-db.pgcustom
```

M1-5에서는 `<ddoksori-postgres-container>`를 실제 이름으로 확정하지 않는다. 이 이름은 M1-6에서 compose service가 추가된 뒤 확정한다.

### M1-5.6 Restore 검증 기준

M1-7에서 restore 후 실행할 검증 기준을 문서화한다.

필수 검증:

```bash
docker compose run --rm backend python scripts/testing/check_vector_db_smoke.py
```

추가 SQL 검증:

```sql
SELECT COUNT(*) FROM vector_chunks;
SELECT COUNT(*) FROM vector_chunks WHERE embedding IS NOT NULL;
SELECT COUNT(*) FROM vector_chunks WHERE text_tsv IS NOT NULL;
SELECT COUNT(*) FROM vector_chunks WHERE vector_dims(embedding) = 1536;

SELECT p.proname
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public'
  AND p.proname IN (
    'search_similar_chunks',
    'search_hybrid_rrf',
    'search_hybrid_rrf_2'
  )
ORDER BY p.proname;
```

성공 기준:

- `vector_chunks` row count가 source baseline `40,285`와 일치
- embedding/text_tsv/1536 dimension count가 source baseline과 일치
- 세 search function이 모두 존재
- smoke script sample query가 통과

## 4. 명시적 비범위

M1-5에서는 아래를 하지 않는다.

- Ddoksori `docker-compose.yml`에 postgres service 추가
- 실제 dump 파일 생성/커밋
- 실제 restore 수행
- DB schema migration 수정
- `documents`, `chunks`, `law_units`, `mv_searchable_chunks` 복구
- 최소 seed fixture 작성
- `/search` API smoke 수행

## 5. Verification plan

M1-5 문서 PR 검증은 아래로 제한한다.

```bash
git diff --check
git status --short
```

실제 dump/restore 명령은 M1-5 문서의 runbook으로만 남기고, 실행은 M1-6/M1-7에서 별도 모듈로 진행한다.

## 6. 다음 모듈 gate

M1-5가 merge되면 바로 restore를 실행하지 않는다. 다음 중 하나를 별도 모듈로 시작한다.

| 후보 모듈 | 목표 | 완료 기준 |
| --- | --- | --- |
| `M1-6` | Ddoksori compose에 pgvector service 추가 | `docker compose up postgres`와 `vector` extension 확인 |
| `M1-7` | M1-5 dump를 Ddoksori volume에 restore | `vector_chunks` row count와 1536 dimension 재확인 |
| `M1-8` | backend `/search` smoke | `/search`가 local compose DB로 검색 결과 반환 |
