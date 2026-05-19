# M1-6 Ddoksori compose pgvector service 추가 계획

- 작성일: 2026-05-19
- 모듈: `M1-6` Ddoksori compose pgvector service 추가
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`
- 선행 모듈: `M1-1` RAG DB inventory, `M1-2` vector DB smoke baseline, `M1-3` schema compatibility 결정, `M1-4` `search_hybrid_rrf_2()` schema 복구, `M1-5` DB dump/restore runbook 및 dump artifact 생성
- 목표: Ddoksori repository 자체 `docker-compose.yml`에 local PostgreSQL/pgvector service를 추가해 M1-7 dump restore 대상 volume을 만든다.
- 이번 계획 문서에서 하지 않는 일: 실제 `docker-compose.yml` 수정, DB volume 생성, dump restore 실행, backend `/search` smoke, legacy schema 복구, provider/model 전환.

## 1. 결론

M1-6 구현은 **compose-owned 빈 pgvector database를 재현 가능하게 띄우는 모듈**로 제한한다.

구현 단계에서 권장하는 최소 변경은 다음 4개다.

1. `docker-compose.yml`에 `postgres` service 추가
2. `postgres_data` named volume 추가
3. 최초 DB 생성 시 `vector`/`pgcrypto` extension을 만들 init SQL 추가
4. backend container의 기본 DB host를 compose service명 `postgres`로 전환하되, `.env` override로 외부 DB 사용을 계속 허용

M1-6의 성공은 `vector_chunks` row count가 아니라 **DB container가 건강하게 올라오고 `vector` extension이 해당 DB에 생성되는 것**으로 판단한다. `vector_chunks`/RRF function/data 검증은 M1-7 restore 후 수행한다.

## 2. 리포 검토 근거

### 2.1 현재 compose에는 DB service가 없다

현재 `docker-compose.yml`은 `backend`, `frontend`, `redis`만 정의한다.

- `docker-compose.yml:6-31`: backend service
- `docker-compose.yml:33-46`: frontend service
- `docker-compose.yml:48-63`: redis service
- `docker-compose.yml:65-67`: volume은 `redis_data`, `frontend_node_modules`만 있음

실제 확인 명령:

```bash
docker compose config --services
```

현재 출력:

```text
redis
backend
frontend
```

### 2.2 backend는 환경변수 기반 DB 연결을 사용한다

현재 compose backend 환경변수는 외부 host DB를 기본값으로 둔다.

- `docker-compose.yml:16-23`: `DB_HOST=${DB_HOST:-host.docker.internal}`, `DB_PORT=5432`, `DB_NAME=ddoksori`, `DB_USER=postgres`, `DB_PASSWORD=postgres`, `RETRIEVAL_MODE=hybrid`
- `docker-compose.yml:24-28`: `host.docker.internal` extra host와 redis health dependency만 있음

backend 코드와 smoke script도 같은 DB env naming을 사용한다.

- `backend/app/api/dependencies.py:20-26`: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`로 API retriever DB config 구성
- `backend/scripts/testing/check_vector_db_smoke.py:34-41`: 같은 env로 smoke DB config 구성

따라서 M1-6에서는 새 env naming 체계를 만들기보다 기존 `DB_*` 변수와 PostgreSQL image의 `POSTGRES_*` 변수를 매핑하는 것이 가장 작은 변경이다.

### 2.3 pgvector image와 extension 초기화가 필요하다

이전 모듈과 문서는 `pgvector/pgvector:pg17`을 기준 이미지로 사용했다.

- `docs/plans/modules/M1-5-db-dump-restore-runbook.md:30-34`: source DB container는 `pgvector/pgvector:pg17`, DB/user/password는 `ddoksori` / `postgres` / `postgres`
- `docs/data/db/01_01_DB구축방법.md:149-165`: local postgres service 예시도 `pgvector/pgvector:pg17`과 host port 매핑을 사용
- `docs/data/db/01_01_DB구축방법.md:178-183`: `pg_isready` healthcheck 예시 존재

주의할 점은 image에 pgvector binary가 있어도 target database에 `CREATE EXTENSION vector;`가 필요하다는 점이다. M1-4에서 복구한 `search_hybrid_rrf_2()`도 `pgvector` 및 `vector_chunks.embedding vector(1536)`을 전제한다.

- `backend/app/database/schema/search_hybrid_rrf_2.sql:7-11`: pgvector extension, `public.vector_chunks`, `embedding vector(1536)`, `text_tsv` precondition
- `backend/scripts/testing/check_vector_db_smoke.py:70-82`: `vector` extension이 없으면 failure 처리
- `backend/app/database/migrations/004_conversation_memory.sql:12-13`: conversation memory migration은 `pgcrypto` extension을 사용

따라서 M1-6에서 init SQL은 최소한 아래를 포함해야 한다.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

### 2.4 M1-6은 restore/data 검증 모듈이 아니다

M1-5는 restore 대상 service/container 이름을 M1-6에서 확정한다고 남겨두었다.

- `docs/plans/modules/M1-5-db-dump-restore-runbook.md:138-168`: M1-6 이후 Ddoksori compose DB service가 생겼다고 가정한 restore command와 `<ddoksori-postgres-container>` placeholder
- `docs/plans/modules/M1-5-db-dump-restore-runbook.md:170-205`: `vector_chunks` row count/RRF function/smoke 검증은 M1-7 restore 후 검증 기준
- `docs/plans/modules/M1-5-db-dump-restore-runbook.md:207-218`: M1-5의 명시적 비범위에 compose service 추가, 실제 restore, `/search` smoke가 분리됨

M1-6도 같은 분리를 유지한다. DB service는 만들지만 M1-5 dump를 복원하지 않는다.

## 3. 권장 구현 범위

### 3.1 `docker-compose.yml` 변경안

권장 service name은 roadmap 완료 기준과 M1-5 placeholder를 만족하도록 `postgres`로 둔다.

권장 container name은 외부 source DB의 `data_collection_snippets-postgres-1` 및 과거 문서의 `ddoksori_db`와 충돌하지 않도록 `ddoksori_postgres`로 둔다.

권장 host port default는 `5433` 또는 `55432` 중 하나를 선택한다. 이유는 M1-5 source DB가 host `5432`를 사용하므로, 두 DB를 동시에 띄워 비교/restore할 때 host port collision을 피하기 위해서다. compose network 내부에서는 항상 `postgres:5432`를 사용하므로 backend container에는 영향이 없다.

초안:

```yaml
  postgres:
    image: pgvector/pgvector:pg17
    container_name: ddoksori_postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${DB_NAME:-ddoksori}
      POSTGRES_USER: ${DB_USER:-postgres}
      POSTGRES_PASSWORD: ${DB_PASSWORD:-postgres}
      POSTGRES_INITDB_ARGS: "--encoding=UTF-8 --locale=C"
      TZ: Asia/Seoul
    ports:
      - "${POSTGRES_HOST_PORT:-5433}:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backend/app/database/init/00_extensions.sql:/docker-entrypoint-initdb.d/00_extensions.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-postgres} -d ${DB_NAME:-ddoksori}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
```

Backend service 변경안:

```yaml
    environment:
      - DB_HOST=${DB_HOST:-postgres}
      - DB_PORT=${DB_PORT:-5432}
      - DB_NAME=${DB_NAME:-ddoksori}
      - DB_USER=${DB_USER:-postgres}
      - DB_PASSWORD=${DB_PASSWORD:-postgres}
      - RETRIEVAL_MODE=${RETRIEVAL_MODE:-hybrid}
      - REDIS_HOST=redis
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
```

Volume 변경안:

```yaml
volumes:
  postgres_data:
  redis_data:
  frontend_node_modules:
```

### 3.2 init SQL 추가안

새 파일 후보:

```text
backend/app/database/init/00_extensions.sql
```

내용:

```sql
-- Local compose bootstrap for the M1-6 pgvector service.
-- Data/schema restore is intentionally deferred to M1-7.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
```

주의: `.gitignore:75`가 `backend/app/database`를 ignore하지만, 기존 `backend/app/database/migrations/004_conversation_memory.sql`와 `backend/app/database/schema/search_hybrid_rrf_2.sql`는 tracked 상태다. 구현 PR에서는 새 init SQL을 `git add -f`로 명시 추가해야 한다.

### 3.3 `.env.example` 문서 변경안

현재 `.env.example`은 RDS/external DB 중심 설명이다.

- `.env.example:4-13`: production/RDS, local Python, backend container external DB host를 설명하고 기본 `DB_HOST`는 RDS placeholder

M1-6 구현 시 아래를 추가한다.

```env
# Ddoksori Docker Compose default:
# - Backend container -> DB_HOST=postgres, DB_PORT=5432
# - Host psql/Python -> DB_HOST=127.0.0.1, DB_PORT=${POSTGRES_HOST_PORT:-5433}
# - External baseline DB override -> DB_HOST=host.docker.internal, DB_PORT=5432
POSTGRES_HOST_PORT=5433
```

단, `.env.example`의 실제 `DB_HOST` 기본값을 `postgres`로 바꿀지는 신중히 결정한다. host에서 Python script를 직접 실행하면 `postgres` DNS가 해석되지 않기 때문이다. 권장안은 설명을 추가하고 compose defaults는 `docker-compose.yml`에서 처리하는 것이다.

### 3.4 README 변경안

현재 README는 Docker Compose stack이 Backend/Frontend/Redis만 포함하고 DB는 AWS RDS라고 설명한다.

- `README.md:284-298`: Docker Compose 설명에서 DB는 AWS RDS를 사용해 로컬에서 실행되지 않는다고 명시

M1-6 구현 PR에서는 해당 문장을 “local compose postgres service가 추가되었지만 restore는 M1-7 이후”라는 상태로 갱신해야 한다. 다만 문서 변경은 최소화한다.

## 4. 구현하지 않을 것

M1-6에서는 아래를 하지 않는다.

- M1-5 dump artifact restore
- `vector_chunks` table/data 생성 또는 seed fixture 작성
- `search_similar_chunks()`, `search_hybrid_rrf()`, `search_hybrid_rrf_2()` 적용
- `backend/scripts/testing/check_vector_db_smoke.py`의 M1-7 기준 완화/변경
- backend `/search` 또는 retrieval endpoint smoke
- legacy `documents`, `chunks`, `law_units`, `mv_searchable_chunks` 복구
- Redis cache 복구/점검
- RunPod/local LLM provider 전환
- production compose 변경

## 5. Acceptance criteria

M1-6 구현 완료 기준은 아래처럼 좁힌다.

1. `docker compose config --services`에 `postgres`가 포함된다.
2. `docker compose up -d postgres`가 성공한다.
3. `docker compose ps postgres`가 healthy 상태를 보여준다.
4. 아래 SQL이 `vector` extension을 반환한다.

   ```bash
   docker compose exec -T postgres \
     psql -U postgres -d ddoksori \
     -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
   ```

5. `pgcrypto` extension도 생성되어 conversation memory migration 전제와 충돌하지 않는다.
6. `docker compose down` 후 `postgres_data` named volume이 보존된다. 단, `down -v`는 M1-6 검증 중 실행하지 않는다.
7. `git diff --check`가 통과한다.

## 6. Verification commands

구현 PR에서 실행할 검증 명령:

```bash
# Compose config parse
POSTGRES_HOST_PORT=5433 docker compose config --services

# Start only postgres for M1-6
POSTGRES_HOST_PORT=5433 docker compose up -d postgres

docker compose ps postgres

# Extension checks
docker compose exec -T postgres \
  psql -U postgres -d ddoksori \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'pgcrypto') ORDER BY extname;"

# Health check by pg_isready
docker compose exec -T postgres \
  pg_isready -U postgres -d ddoksori

# Static/doc checks
git diff --check
git status --short
```

명시적 비검증:

```bash
# M1-7 전에는 실패가 정상일 수 있음: vector_chunks/RRF/data가 아직 없음
docker compose run --rm backend python scripts/testing/check_vector_db_smoke.py
```

## 7. Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Host port `5432` collision with M1-5 source DB | `docker compose up postgres` 실패 또는 잘못된 DB 접속 | default host port를 `5433`/`55432`로 두고 backend는 internal `postgres:5432` 사용 |
| `pgvector/pgvector:pg17` image에는 binary가 있지만 DB extension이 자동 생성되지 않음 | M1-6 완료 기준 실패 | `docker-entrypoint-initdb.d/00_extensions.sql`로 `CREATE EXTENSION` 실행 |
| init SQL은 새 volume 최초 생성 때만 실행됨 | 기존 volume이 있으면 extension 수정이 반영되지 않을 수 있음 | 검증 실패 시 volume 상태를 문서화하고, destructive `down -v`는 사용자 승인 또는 명시적 local-only cleanup 단계에서만 실행 |
| backend default를 `postgres`로 바꾸면 외부 DB smoke 흐름이 달라짐 | M1-4/M1-5식 external DB smoke 재현 혼란 | `.env` override로 `DB_HOST=host.docker.internal` 가능하다고 README/.env.example에 명시 |
| `.gitignore`가 `backend/app/database`를 ignore | init SQL이 PR에 누락될 수 있음 | `git add -f backend/app/database/init/00_extensions.sql` 사용, PR diff에서 확인 |
| Empty DB에 backend가 연결됨 | M1-7 전 `/search`는 실패 가능 | M1-6 acceptance를 extension/healthcheck로 제한하고 `/search`는 M1-8로 유지 |

## 8. Recommended implementation sequence

1. Add `backend/app/database/init/00_extensions.sql` with `vector` and `pgcrypto` extension creation.
2. Add `postgres` service and `postgres_data` volume to `docker-compose.yml`.
3. Change backend compose default `DB_HOST` from `host.docker.internal` to `postgres`, add `depends_on.postgres.condition=service_healthy`.
4. Update `.env.example` comments with compose DB/default host-port guidance.
5. Update README Docker Compose section to reflect local postgres service and M1-7 restore separation.
6. Run M1-6 verification commands.
7. Commit with Lore commit protocol and open PR to `develop`.

## 9. Next-module gate

M1-6가 merge되어도 바로 restore하지 않는다.

다음 단계는 사용자 논의 후 별도 모듈로 진행한다.

| Next module | Goal | Completion criteria |
| --- | --- | --- |
| `M1-7` | M1-5 dump를 M1-6 `postgres_data` volume에 restore | `vector_chunks=40,285`, embedding/text_tsv/1536 dims, RRF functions, smoke 통과 |
| `M1-8` | backend `/search` smoke | local compose DB 기준 `/health` 및 search/retrieval endpoint 통과 |
| M1-6 수정 | plan/implementation feedback 반영 | compose service acceptance 재검증 |

## 10. Implementation result

M1-6 implementation completed the planned compose-owned pgvector baseline without restoring data.

Changed files:

- `docker-compose.yml`
  - added `postgres` service using `pgvector/pgvector:pg17`
  - added `postgres_data` named volume
  - changed backend compose default `DB_HOST` to `postgres`
  - added backend dependency on healthy `postgres`
- `backend/app/database/init/00_extensions.sql`
  - creates `vector` and `pgcrypto` extensions on first DB volume initialization
- `.env.example`
  - documents compose DB defaults, host access port, external baseline override, and production/RDS override
- `README.md`
  - documents local pgvector service and M1-7 restore separation

Verification evidence:

```text
POSTGRES_HOST_PORT=5433 docker compose config --services
=> frontend, postgres, redis, backend

docker compose up -d postgres
=> ddoksori_postgres started

docker compose ps postgres
=> Up ... (healthy), 0.0.0.0:5433->5432/tcp

docker compose exec -T postgres \
  psql -U postgres -d ddoksori \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'pgcrypto') ORDER BY extname;"
=> pgcrypto 1.3, vector 0.8.2

docker compose exec -T postgres pg_isready -U postgres -d ddoksori
=> /var/run/postgresql:5432 - accepting connections

docker compose down
=> container/network removed, postgres_data volume preserved
```

Explicitly not run in M1-6:

- M1-5 dump restore
- `check_vector_db_smoke.py` against the empty compose DB
- backend `/search` smoke
- legacy schema/data restoration

Next gate remains M1-7: restore the M1-5 dump into the Ddoksori `postgres_data` volume and then validate `vector_chunks`, embeddings, `text_tsv`, dimensions, and RRF functions.
