# M1-7 Ddoksori volume에 dump restore 계획

- 작성일: 2026-05-28
- 모듈: `M1-7` Ddoksori volume에 dump restore
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`
- 선행 모듈: `M1-1` RAG DB inventory, `M1-2` vector DB smoke baseline, `M1-3` schema compatibility 결정, `M1-4` `search_hybrid_rrf_2()` schema 복구, `M1-5` DB dump/restore runbook 및 dump artifact 생성, `M1-6` compose-owned pgvector service
- 목표: M1-5에서 만든 외부 DB dump artifact를 M1-6에서 만든 Ddoksori compose-owned PostgreSQL/pgvector `postgres_data` volume에 복원하고, active RAG 기준선 수치가 source DB와 일치하는지 검증한다.
- 이번 계획 문서에서 하지 않는 일: 실제 restore 실행, Docker volume 삭제, DB schema/data 수정, smoke script 수정, backend `/search` smoke, Redis/frontend/provider 전환.

## 1. 결론

M1-7 구현은 **Ddoksori compose-owned DB volume을 active RAG baseline으로 채우고 검증하는 모듈**로 제한한다.

M1-7의 성공은 아래 수치와 함수 계약이 source DB baseline과 동일해지는 것으로 판단한다.

| Check | Expected |
| --- | ---: |
| `vector_chunks` rows | `40,285` |
| rows with embedding | `40,285` |
| rows with `text_tsv` | `40,285` |
| rows with `vector_dims(embedding)=1536` | `40,285` |
| rows with non-1536 embedding | `0` |
| `search_similar_chunks()` | exists and sample OK |
| `search_hybrid_rrf()` | exists and sample OK |
| `search_hybrid_rrf_2()` | exists and sample OK |

M1-7은 DB restore와 DB-level smoke까지만 다룬다. Backend API `/search` end-to-end smoke는 `M1-8`로 분리한다.

## 2. 현재 입력 자산

### 2.1 Restore source artifact

M1-5 이후 생성된 dump artifact를 M1-7의 source of truth로 사용한다.

| 항목 | 값 |
| --- | --- |
| Dump path | `/home/maroco/Ddoksori-local-artifacts/db-dumps/ddoksori-vector-db-20260519-183814.pgcustom` |
| Checksum path | `/home/maroco/Ddoksori-local-artifacts/db-dumps/ddoksori-vector-db-20260519-183814.pgcustom.sha256` |
| Size | `304M` |
| SHA256 | `13f1335364dd98c79e6ce68c8023f11c3868fcfaecdadb7ed566bdc0ea4e21e0` |
| Dump format | PostgreSQL custom format, `--no-owner --no-privileges` |

M1-7 구현 시작 전에는 반드시 checksum을 다시 확인한다.

```bash
sha256sum /home/maroco/Ddoksori-local-artifacts/db-dumps/ddoksori-vector-db-20260519-183814.pgcustom
cat /home/maroco/Ddoksori-local-artifacts/db-dumps/ddoksori-vector-db-20260519-183814.pgcustom.sha256
```

### 2.2 Restore target

M1-6에서 Ddoksori root compose에 추가된 target은 아래와 같다.

| 항목 | 값 |
| --- | --- |
| Compose service | `postgres` |
| Container name | `ddoksori_postgres` |
| Image | `pgvector/pgvector:pg17` |
| Named volume | `postgres_data` |
| Database | `${DB_NAME:-ddoksori}` |
| User/password | `${DB_USER:-postgres}` / `${DB_PASSWORD:-postgres}` |
| Container port | `5432` |
| Host port default | `${POSTGRES_HOST_PORT:-5433}` |
| Init SQL | `backend/app/database/init/00_extensions.sql` |

Target DB is compose-owned but local-only. M1-7 must not touch the source DB container from `/home/maroco/data_collection_snippets` except for optional read-only comparison queries.

## 3. Implementation plan

### 3.1 Preflight: repo and artifact state

Run git checks from the M1-7 feature worktree. Run Docker/compose restore commands from the root worktree (`/home/maroco/Ddoksori`) so the target volume is the root compose project volume (`ddoksori_postgres_data`), not a feature-worktree compose project volume.

```bash
git status --short --branch
ls -lh /home/maroco/Ddoksori-local-artifacts/db-dumps/ddoksori-vector-db-20260519-183814.pgcustom
sha256sum /home/maroco/Ddoksori-local-artifacts/db-dumps/ddoksori-vector-db-20260519-183814.pgcustom
```

Success criteria:

- worktree is on `feature/m1-7-*`
- no unrelated local changes
- dump artifact exists outside the repo
- SHA256 matches `13f1335364dd98c79e6ce68c8023f11c3868fcfaecdadb7ed566bdc0ea4e21e0`

### 3.2 Preflight: compose target readiness

Start only the target DB first.

```bash
POSTGRES_HOST_PORT=5433 docker compose up -d postgres
docker compose ps postgres

DBU=$(docker compose exec -T postgres sh -lc 'printf %s "$POSTGRES_USER"')
DBN=$(docker compose exec -T postgres sh -lc 'printf %s "$POSTGRES_DB"')

docker compose exec -T postgres \
  pg_isready -U "$DBU" -d "$DBN"

docker compose exec -T postgres \
  psql -U "$DBU" -d "$DBN" \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'pgcrypto') ORDER BY extname;"
```

Success criteria:

- `postgres` service is healthy
- `pg_isready` succeeds
- `vector` and `pgcrypto` extensions exist before restore or will be present after restore

### 3.3 Inspect target before restore

Before destructive restore, record whether the target volume is empty or already has restored data.

```bash
docker compose exec -T postgres \
  psql -U "$DBU" -d "$DBN" \
  -c "SELECT to_regclass('public.vector_chunks') AS vector_chunks;"

# Run only if the table exists.
docker compose exec -T postgres \
  psql -U "$DBU" -d "$DBN" \
  -c "SELECT COUNT(*) AS vector_chunks_total FROM public.vector_chunks;"
```

Decision rule:

| Target state | Action |
| --- | --- |
| `vector_chunks` missing | proceed with restore |
| `vector_chunks` exists with `40,285` rows and smoke passes | treat as already restored; do not re-restore unless a clean replay is explicitly needed |
| `vector_chunks` exists with different count or smoke fails | use `pg_restore --clean --if-exists` into the same DB, after recording the before-state |

Do not run `docker compose down -v` as a default M1-7 step. Removing `postgres_data` is destructive and should only be used if the implementation explicitly needs a clean replay and the existing volume is known to be disposable.

### 3.4 Copy dump into the target container

```bash
docker cp \
  /home/maroco/Ddoksori-local-artifacts/db-dumps/ddoksori-vector-db-20260519-183814.pgcustom \
  ddoksori_postgres:/tmp/ddoksori-vector-db.pgcustom

# Optional size check inside container.
docker compose exec -T postgres \
  ls -lh /tmp/ddoksori-vector-db.pgcustom
```

The copied dump is a temporary container file. It must not be added to git.

### 3.5 Restore into Ddoksori compose DB

Recommended restore command:

```bash
docker compose exec -T postgres \
  pg_restore \
  --username="$DBU" \
  --dbname="$DBN" \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  /tmp/ddoksori-vector-db.pgcustom
```

Notes:

- `--clean --if-exists` makes reruns idempotent enough for local restore by dropping restored objects before recreating them.
- `--no-owner --no-privileges` matches the dump creation assumptions and avoids local role/permission drift.
- Do not use `--single-transaction` until verified with the custom dump, because extension/function/table drop/create ordering may need normal `pg_restore` behavior for clear diagnostics.
- If restore emits non-fatal warnings, capture the full output and classify them before claiming success.

### 3.6 Re-apply tracked schema only if restore lacks M1-4 function

Expected dump includes `search_hybrid_rrf_2()`. If post-restore function verification shows it missing, re-apply the tracked SQL from M1-4 rather than editing the DB manually.

```bash
docker compose exec -T postgres \
  psql -U "$DBU" -d "$DBN" \
  < backend/app/database/schema/search_hybrid_rrf_2.sql
```

This is a recovery branch, not the happy path. If used, document why the dump did not contain the function.

## 4. Validation plan

### 4.1 SQL baseline checks

Run the direct SQL checks first to confirm the restored DB shape.

```bash
docker compose exec -T postgres \
  psql -U "$DBU" -d "$DBN" \
  -c "
SELECT
  COUNT(*) AS total,
  COUNT(*) FILTER (WHERE embedding IS NOT NULL) AS with_embedding,
  COUNT(*) FILTER (WHERE text_tsv IS NOT NULL) AS with_text_tsv,
  COUNT(*) FILTER (WHERE vector_dims(embedding) = 1536) AS dims_1536,
  COUNT(*) FILTER (WHERE vector_dims(embedding) IS DISTINCT FROM 1536) AS dims_not_1536
FROM public.vector_chunks;
"

docker compose exec -T postgres \
  psql -U "$DBU" -d "$DBN" \
  -c "
SELECT p.proname
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'public'
  AND p.proname IN ('search_similar_chunks', 'search_hybrid_rrf', 'search_hybrid_rrf_2')
ORDER BY p.proname;
"
```

Expected result:

- total: `40,285`
- with_embedding: `40,285`
- with_text_tsv: `40,285`
- dims_1536: `40,285`
- dims_not_1536: `0`
- all three search functions present

### 4.2 Backend-container DB smoke

Run the existing smoke script from the backend container against the compose DB.

```bash
docker compose run --rm \
  -e DB_HOST=postgres \
  -e DB_PORT=5432 \
  -e DB_NAME="$DBN" \
  -e DB_USER="$DBU" \
  -e DB_PASSWORD="$(docker compose exec -T postgres sh -lc 'printf %s "$POSTGRES_PASSWORD"')" \
  backend python scripts/testing/check_vector_db_smoke.py
```

Expected result:

```text
[OK] Restored vector DB satisfies the M1-4 active retrieval baseline.
```

The JSON summary should include:

- `vector` extension
- `vector_chunks` relation
- `search_similar_chunks`, `search_hybrid_rrf`, `search_hybrid_rrf_2`
- `vector_chunks.total = 40285`
- dense/hybrid/RRF v2 sample rows

### 4.3 Optional host-side smoke

If host Python dependencies are available, run the smoke script via host port `5433`.

```bash
DB_HOST=127.0.0.1 \
DB_PORT=5433 \
DB_NAME=ddoksori \
DB_USER=postgres \
DB_PASSWORD=postgres \
python backend/scripts/testing/check_vector_db_smoke.py
```

This is optional because backend-container smoke is the canonical M1-7 verification path.

## 5. Evidence to capture in the M1-7 implementation document/PR

The implementation PR should record the following evidence, either in the module doc update or PR body.

| Evidence | Required value |
| --- | --- |
| Dump SHA256 | `13f1335364dd98c79e6ce68c8023f11c3868fcfaecdadb7ed566bdc0ea4e21e0` |
| Target compose service | `postgres` / `ddoksori_postgres` |
| Target DB | `ddoksori` |
| `vector_chunks` rows | `40,285` |
| embeddings present | `40,285` |
| `text_tsv` present | `40,285` |
| 1536 dimensions | `40,285` |
| non-1536 dimensions | `0` |
| functions | `search_similar_chunks`, `search_hybrid_rrf`, `search_hybrid_rrf_2` |
| smoke script | `backend/scripts/testing/check_vector_db_smoke.py` passes |

## 6. Rollback / cleanup plan

M1-7 changes local Docker state. Cleanup must be explicit and conservative.

| Need | Command | Notes |
| --- | --- | --- |
| Stop containers but keep restored DB | `docker compose down` | Preferred after successful verification; preserves `postgres_data` |
| Remove temporary dump copy | `docker compose exec -T postgres rm -f /tmp/ddoksori-vector-db.pgcustom` | Safe after restore and verification |
| Fully reset restored DB volume | `docker compose down -v` | Destructive; only if intentionally discarding local restore |

The implementation should not remove the M1-5 artifact under `/home/maroco/Ddoksori-local-artifacts/db-dumps/`.

## 7. Explicit non-scope

M1-7 must not include:

- backend `/search` endpoint smoke; this is `M1-8`
- Redis cache checks; this is `M1-9`
- frontend local UI checks; this is `M1-10`
- RunPod/local LLM provider routing; this is `M2`
- legacy `documents`, `chunks`, `law_units`, `mv_searchable_chunks` restoration beyond whatever the dump contains
- retrieval quality tuning or ranking changes
- schema redesign or new migrations
- committing the dump artifact or generated DB files
- deleting Docker volumes unless explicitly choosing a clean local replay path

## 8. M1-7 acceptance criteria

M1-7 implementation is complete when:

1. The dump checksum matches the M1-5 recorded checksum.
2. Ddoksori compose `postgres` service is healthy.
3. The dump restores into `ddoksori_postgres` / `postgres_data` without unresolved restore errors.
4. Direct SQL baseline checks match the source DB counts.
5. The existing backend-container smoke script passes against compose DB.
6. Verification evidence is documented.
7. No repo-tracked dump or generated DB artifact is added.

## 9. Next module gate

After M1-7 is verified, stop before M1-8 and review the evidence.

The next module candidate is:

| Module | Goal | Completion criteria |
| --- | --- | --- |
| `M1-8` | Backend `/search` smoke | `/health` and `/search` or equivalent retrieval endpoint work against the restored local compose DB |

## 10. Implementation result

- 실행일: 2026-05-28
- 실행 위치: Docker/compose restore는 root worktree `/home/maroco/Ddoksori`에서 실행했다. 이는 compose project name이 root 기준 `ddoksori`가 되어 실제 target volume이 `ddoksori_postgres_data`가 되도록 하기 위함이다. PR 문서 변경은 feature worktree `/home/maroco/Ddoksori-worktrees/m1-7-dump-restore-plan`에서만 수행했다.
- Restore target: `ddoksori_postgres` / Docker volume `ddoksori_postgres_data` / database `ddoksori`
- Local DB user observed from container env: `your_db_user` (`POSTGRES_USER`); plan commands now derive `POSTGRES_USER`/`POSTGRES_DB` from the running container instead of assuming `postgres`.

### 10.1 Preflight evidence

| Check | Result |
| --- | --- |
| Root branch | `develop...origin/develop`, clean |
| Feature branch | `feature/m1-7-dump-restore-plan...origin/feature/m1-7-dump-restore-plan`, clean before result update |
| PR #9 | `OPEN`, `MERGEABLE` before result update |
| Dump path | `/home/maroco/Ddoksori-local-artifacts/db-dumps/ddoksori-vector-db-20260519-183814.pgcustom` |
| Dump size | `304M` |
| SHA256 | `13f1335364dd98c79e6ce68c8023f11c3868fcfaecdadb7ed566bdc0ea4e21e0` |
| Sidecar SHA256 | `13f1335364dd98c79e6ce68c8023f11c3868fcfaecdadb7ed566bdc0ea4e21e0` |
| Target before restore | `public.vector_chunks` missing |
| Extensions before restore | `pgcrypto 1.3`, `vector 0.8.2` |

Initial `pg_isready -U postgres` was not the correct local command because the local `.env` initialized the DB with `POSTGRES_USER=your_db_user`. Verification continued with the actual container-derived user/database.

### 10.2 Restore evidence

```bash
docker cp /home/maroco/Ddoksori-local-artifacts/db-dumps/ddoksori-vector-db-20260519-183814.pgcustom \
  ddoksori_postgres:/tmp/ddoksori-vector-db.pgcustom

docker compose exec -T postgres pg_restore \
  --username="$DBU" \
  --dbname="$DBN" \
  --clean \
  --if-exists \
  --no-owner \
  --no-privileges \
  /tmp/ddoksori-vector-db.pgcustom
```

- Restore started: `2026-05-28T11:24:22+09:00`
- Restore finished: `2026-05-28T11:24:58+09:00`
- Restore command exit code: `0`
- Restore log: `/tmp/m1-7-pg-restore-20260528-112421.log` (local ephemeral log, not committed)
- Restore output lines: `2` timestamp lines only; no warning/error output from `pg_restore`

### 10.3 Direct SQL validation

| Check | Actual | Expected | Result |
| --- | ---: | ---: | --- |
| `vector_chunks` total | `40,285` | `40,285` | PASS |
| rows with embedding | `40,285` | `40,285` | PASS |
| rows with `text_tsv` | `40,285` | `40,285` | PASS |
| rows with `vector_dims(embedding)=1536` | `40,285` | `40,285` | PASS |
| rows with non-1536 embedding | `0` | `0` | PASS |
| `pgcrypto` extension | `1.3` | present | PASS |
| `vector` extension | `0.8.2` | present | PASS |
| `search_similar_chunks` | present | present | PASS |
| `search_hybrid_rrf` | present | present | PASS |
| `search_hybrid_rrf_2` | present | present | PASS |

Function signatures after restore:

| Function | Arguments |
| --- | --- |
| `search_similar_chunks` | `query_embedding vector, filter_dataset character varying, filter_category character varying, filter_law_name character varying, filter_year integer, result_limit integer` |
| `search_hybrid_rrf` | `query_text text, query_embedding vector, filter_dataset character varying, filter_category character varying, filter_document_type character varying, filter_year integer, result_limit integer, rrf_k integer` |
| `search_hybrid_rrf_2` | `query_text text, query_embedding vector, filter_dataset character varying, filter_category character varying, filter_document_type character varying[], filter_chunk_type character varying[], filter_year_from integer, filter_year_to integer, result_limit integer, rrf_k integer` |

A manually written ad-hoc sample SQL using `search_similar_chunks(vector, integer)` failed because that was not the restored function signature. This did not indicate restore failure; the canonical smoke script below used the correct signatures and passed.

### 10.4 Backend-container smoke validation

First smoke attempt without overrides failed because root `.env` pointed `DB_HOST` at `your-instance.xxxx.ap-northeast-2.rds.amazonaws.com`. The canonical M1-7 smoke was rerun with explicit compose DB overrides:

```bash
docker compose run --rm \
  -e DB_HOST=postgres \
  -e DB_PORT=5432 \
  -e DB_NAME="$DBN" \
  -e DB_USER="$DBU" \
  -e DB_PASSWORD="$(docker compose exec -T postgres sh -lc 'printf %s "$POSTGRES_PASSWORD"')" \
  backend python scripts/testing/check_vector_db_smoke.py
```

Result: PASS

```text
[OK] Restored vector DB satisfies the M1-4 active retrieval baseline.
```

Smoke summary highlights:

| Metric | Value |
| --- | ---: |
| `vector_chunks.total` | `40,285` |
| `vector_chunks.with_embedding` | `40,285` |
| `vector_chunks.with_text_tsv` | `40,285` |
| `vector_chunks.dims_1536` | `40,285` |
| `vector_chunks.dims_not_1536` | `0` |
| `case / 조정` rows | `20,992` |
| `case / 상담` rows | `11,342` |
| `law_guide / 법률` rows | `3,448` |
| `case / 해결` rows | `1,874` |
| `law_guide / 별표` rows | `1,692` |
| `law_guide / 시행령` rows | `611` |
| `law_guide / 행정규칙` rows | `326` |

The smoke output included non-empty `dense_sample`, `hybrid_sample`, and `hybrid_rrf_2_sample` arrays. Optional legacy relations remained absent: `documents`, `chunks`, `law_units`, `mv_searchable_chunks`.

### 10.5 Cleanup after verification

- Removed temporary container dump copy: `/tmp/ddoksori-vector-db.pgcustom`
- Ran `docker compose down` from root worktree to stop/remove containers and network while preserving named volumes.
- Preserved volumes observed after cleanup: `ddoksori_postgres_data`, `ddoksori_redis_data`
- No repo-tracked dump or generated DB artifact was added.

### 10.6 M1-7 status and next gate

M1-7 restore and DB-level validation are complete. Stop before M1-8 until the restore evidence is reviewed/accepted. M1-8 remains backend `/health` plus `/search` or equivalent retrieval endpoint smoke against the restored local compose DB.
