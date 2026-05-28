# M1-8 Backend `/search` smoke 계획

- 작성일: 2026-05-28
- 모듈: `M1-8` Backend `/search` smoke
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`
- 선행 모듈: `M1-7` Ddoksori compose-owned `postgres_data` volume restore 및 DB-level smoke 완료
- 목표: M1-7에서 복원한 local compose DB를 기준으로 FastAPI backend가 `/health`와 `/search` 또는 equivalent retrieval endpoint를 통과하는지 확인한다.
- 이번 계획 문서에서 하지 않는 일: 실제 backend smoke 실행, endpoint 코드 변경, Redis cache read/write 검증, frontend UI 검증, LLM 답변 품질 평가, provider 전환.

## 1. 결론

M1-8 구현은 **복원된 local compose DB를 사용하는 backend API-level retrieval smoke**로 제한한다.

성공 기준은 다음과 같다.

| Check | Expected |
| --- | --- |
| `GET /health` | HTTP 200 and `status=healthy`, `database=connected` |
| `POST /search` | HTTP 200 |
| `/search` result count | `results_count > 0` for the smoke query |
| result payload shape | `query`, `results_count`, `results[]` present |
| result identity evidence | at least top chunk metadata such as `chunk_id`, `doc_type`/`chunk_type`, `similarity` captured |
| local DB binding | backend env/log evidence shows `DB_HOST=postgres`, `DB_PORT=5432`, restored compose DB credentials |
| M1-7 DB baseline | `check_vector_db_smoke.py` still passes or recent M1-7 evidence remains valid |

M1-8 does not validate final chatbot answer quality. It verifies that the backend API can read from the restored local RAG DB and return retrieval results.

## 2. Repo evidence for M1-8

### 2.1 API endpoints

- `backend/app/api/health.py` defines `GET /health`. It creates `HybridRetriever` when `RETRIEVAL_MODE=hybrid`, connects to DB, closes the connection, and returns `{"status": "healthy", "database": "connected"}` on success.
- `backend/app/api/search.py` defines `POST /search`. It accepts `SearchRequest`, runs `retriever.search(...)` when `RETRIEVAL_MODE=hybrid`, serializes `SearchResult` objects, and returns `query`, `results_count`, and `results`.
- `backend/app/api/models.py` defines `SearchRequest` with `query`, `top_k`, optional `chunk_types`, and optional `agencies`.
- `backend/app/api/dependencies.py` reads DB connection settings from `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, and reads retrieval mode from `RETRIEVAL_MODE`.

### 2.2 Compose behavior

- `docker-compose.yml` starts `postgres`, `redis`, and `backend` services.
- `backend` depends on healthy `postgres` and healthy `redis`.
- `backend` loads root `.env` if present, then uses Compose environment entries such as `DB_HOST=${DB_HOST:-postgres}` and `RETRIEVAL_MODE=${RETRIEVAL_MODE:-hybrid}`.
- Because local `.env` may contain an RDS placeholder from older workflows, M1-8 commands must explicitly force backend to use the compose network DB by setting `DB_HOST=postgres` and `DB_PORT=5432` in the shell invoking `docker compose`.

### 2.3 Search and embedding behavior

- In `RETRIEVAL_MODE=hybrid`, `/search` uses `HybridRetriever.search()`.
- `HybridRetriever` attempts dense vector search first. Dense search uses OpenAI embeddings and may require `OPENAI_API_KEY`.
- `HybridRetriever._dense_search()` catches embedding/API errors and returns an empty dense result list, then lexical FTS search still runs. Therefore, M1-8 can classify two valid smoke branches:
  - **Full hybrid branch**: `OPENAI_API_KEY` exists, dense + lexical contribute.
  - **Lexical fallback branch**: no valid OpenAI key, dense logs a failure, but `/search` still returns non-empty lexical/RRF results.
- If the project wants to prove dense embeddings specifically, that should be recorded as an extra M1-8 evidence item, but the minimum M1-8 acceptance is backend API retrieval against the restored local DB.

## 3. Preconditions

M1-8 implementation should start only after these are true:

| Precondition | Expected |
| --- | --- |
| PR #9 / M1-7 | merged into `develop` |
| Root branch | `develop` synced with `origin/develop` |
| Restored volume | Docker volume `ddoksori_postgres_data` exists |
| M1-7 DB baseline | `vector_chunks=40,285`, `dims_1536=40,285`, RRF functions present |
| Repo state | no unrelated tracked changes |

Recommended preflight:

```bash
git status --short --branch
docker volume ls --format '{{.Name}}' | grep '^ddoksori_postgres_data$'
```

If the volume is missing, stop and revisit M1-7 restore before running M1-8.

## 4. Implementation plan

### 4.1 Start backend stack against local compose DB

Run Docker/compose commands from the root worktree `/home/maroco/Ddoksori`, not from a feature worktree, so the compose project uses the restored root volume `ddoksori_postgres_data`.

```bash
cd /home/maroco/Ddoksori

DB_HOST=postgres \
DB_PORT=5432 \
RETRIEVAL_MODE=hybrid \
docker compose up -d postgres redis backend
```

Wait for service readiness:

```bash
docker compose ps postgres redis backend
curl -fsS http://localhost:8000/health
```

Expected `/health` response:

```json
{"status":"healthy","database":"connected"}
```

### 4.2 Confirm backend DB binding

Because root `.env` may point to an RDS placeholder, capture effective backend env for the non-secret connection fields.

```bash
docker compose exec -T backend sh -lc 'env | grep -E "^(DB_HOST|DB_PORT|DB_NAME|DB_USER|RETRIEVAL_MODE)=" | sort'
```

Expected:

```text
DB_HOST=postgres
DB_PORT=5432
DB_NAME=ddoksori
RETRIEVAL_MODE=hybrid
```

`DB_USER` may reflect the local `.env` value that initialized M1-7's restored compose DB. Do not print `DB_PASSWORD`.

### 4.3 Run `/search` smoke

Use a stable Korean consumer-dispute query likely to match restored data.

```bash
curl -fsS \
  -H 'Content-Type: application/json' \
  -X POST http://localhost:8000/search \
  -d '{"query":"헬스장 계약 해지 환불 위약금", "top_k": 3}' \
  | tee /tmp/m1-8-search-response.json
```

Inspect compact metrics:

```bash
python - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path('/tmp/m1-8-search-response.json').read_text())
print('query=', payload.get('query'))
print('results_count=', payload.get('results_count'))
for idx, item in enumerate(payload.get('results', [])[:3], start=1):
    print(idx, item.get('chunk_id'), item.get('doc_type'), item.get('chunk_type'), item.get('similarity'))
PY
```

Acceptance:

- HTTP status is 200.
- `results_count > 0`.
- At least one result includes a stable identifier such as `chunk_id`.
- Capture the top 1-3 result identifiers and similarity values.

### 4.4 Optional mode comparison

If `OPENAI_API_KEY` is valid and cost/time are acceptable, record whether dense embeddings participate. Otherwise, explicitly mark this as lexical fallback branch evidence.

Useful observations:

```bash
# Recent backend logs around search execution.
docker compose logs --tail=120 backend
```

Classify the branch:

| Branch | Evidence |
| --- | --- |
| Full hybrid | no embedding failure; `/search` returns results |
| Lexical fallback | backend logs show dense/embedding failure but `/search` returns results |
| Failure | `/search` HTTP 500 or `results_count=0`; capture error and do not claim M1-8 complete |

## 5. Validation evidence to record

The M1-8 implementation PR should record these numbers and facts.

| Evidence | Required value / shape |
| --- | --- |
| Root commit | current `develop` commit after PR #9 merge |
| Docker volume | `ddoksori_postgres_data` exists |
| Backend env | `DB_HOST=postgres`, `DB_PORT=5432`, `RETRIEVAL_MODE=hybrid` |
| `/health` status | HTTP 200, `status=healthy`, `database=connected` |
| `/search` status | HTTP 200 |
| `/search` query | exact query string used |
| `/search` result count | integer, must be `>0` |
| Top result evidence | `chunk_id`, `doc_type`/`chunk_type`, `similarity` for top 1-3 |
| Latency | at least rough wall-clock or `curl` timing for `/health` and `/search` |
| Retrieval branch | full hybrid or lexical fallback |
| Known local env caveat | whether root `.env` required explicit DB override |

Recommended latency capture:

```bash
curl -o /tmp/m1-8-health.json -sS -w 'health_http=%{http_code} health_time_total=%{time_total}\n' \
  http://localhost:8000/health

curl -o /tmp/m1-8-search-response.json -sS -w 'search_http=%{http_code} search_time_total=%{time_total}\n' \
  -H 'Content-Type: application/json' \
  -X POST http://localhost:8000/search \
  -d '{"query":"헬스장 계약 해지 환불 위약금", "top_k": 3}'
```

## 6. Failure classification

| Symptom | Likely cause | M1-8 action |
| --- | --- | --- |
| `/health` unhealthy | backend points to wrong DB host, DB credentials mismatch, or restored volume absent | capture env/compose state; fix invocation/restore state before retrying |
| `/search` 500 with DB connection error | backend env still using RDS placeholder or wrong port | rerun compose with `DB_HOST=postgres DB_PORT=5432` |
| `/search` 500 with embedding error in dense mode | `RETRIEVAL_MODE=dense` and no OpenAI key | rerun with `RETRIEVAL_MODE=hybrid` or provide key if dense-specific proof is required |
| `/search` 200 but `results_count=0` | query/filter mismatch or FTS path not finding data | retry with the canonical smoke query and inspect DB baseline; do not claim complete until non-empty |
| Redis dependency blocks backend startup | Redis service/health issue | only resolve enough to start backend; cache behavior remains M1-9 |

## 7. Cleanup plan

After M1-8 smoke, keep the restored DB volume but stop containers unless continued local testing is needed.

```bash
docker compose down
```

Do not run `docker compose down -v`; that would remove `ddoksori_postgres_data` and discard M1-7's restored baseline.

Remove only temporary local response files if desired:

```bash
rm -f /tmp/m1-8-health.json /tmp/m1-8-search-response.json
```

## 8. Explicit non-scope

M1-8 must not include:

- Redis cache read/write validation; this is `M1-9`.
- Frontend UI smoke; this is `M1-10`.
- Chatbot answer-quality/goldenset evaluation.
- Schema migrations, retrieval ranking changes, or endpoint behavior changes.
- Provider migration or RunPod/local LLM setup.
- Deleting Docker volumes.

## 9. M1-8 acceptance criteria

M1-8 implementation is complete when:

1. Backend stack starts against the restored local compose DB.
2. `GET /health` returns healthy DB status.
3. `POST /search` returns HTTP 200 and `results_count > 0` for the canonical smoke query.
4. Result identifiers and latency/result-count metrics are recorded.
5. Retrieval branch is classified as full hybrid or lexical fallback.
6. Cleanup preserves `ddoksori_postgres_data`.
7. Verification evidence is documented in the M1-8 PR.

## 10. Next module gate

After M1-8 is verified, stop before M1-9 and review the evidence.

The next module candidate is:

| Module | Goal | Completion criteria |
| --- | --- | --- |
| `M1-9` | Redis cache 복구 및 점검 | Redis ping, answer/retrieval cache read/write 확인 |
