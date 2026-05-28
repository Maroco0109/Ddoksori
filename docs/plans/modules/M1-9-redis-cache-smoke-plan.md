# M1-9 Redis cache 복구 및 점검 계획

- 작성일: 2026-05-28
- 모듈: `M1-9` Redis cache 복구 및 점검
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`
- 선행 모듈: `M1-8` Backend `/search` smoke 완료
- 목표: local compose Redis에 backend가 인증 포함으로 연결되고, answer cache와 retrieval cache가 실제 Redis에 read/write/delete 되는지 smoke로 검증한다.
- 이번 모듈에서 하지 않는 일: Docker volume 삭제, frontend UI smoke, chatbot answer-quality 평가, Goldenset/security 평가, provider 전환, broad cache architecture rewrite.

## 1. 진행상황 요약

현재 `develop` 기준 M1-8까지 병합되어 있다.

| 항목 | 현재 상태 |
| --- | --- |
| Git 기준 | `develop` at `22e7bba` / PR #10 merge commit |
| M1-7 산출물 | `ddoksori_postgres_data` volume restored and preserved |
| M1-8 산출물 | `/health` HTTP 200, `/search` HTTP 200, `results_count=3`, lexical fallback branch evidence |
| 현재 Docker state | `ddoksori_postgres_data`, `ddoksori_redis_data` volumes exist; no running `ddoksori_*` containers at planning time |
| 다음 gate | M1-9 Redis ping + answer/retrieval cache read/write |

로드맵은 M1-9의 완료 기준을 `Redis ping, answer/retrieval cache read/write 확인`으로 정의한다 (`docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md:58-60`). M1-8 결과 문서는 M1-9 전 게이트를 명시하고, M1-8이 local compose DB 기준으로 `/health`와 `/search`를 통과했음을 기록했다 (`docs/plans/modules/M1-8-backend-search-smoke-plan.md:413-423`).

## 2. Repo evidence for M1-9

### 2.1 Compose Redis service exists and requires auth

`docker-compose.yml`에는 Redis service가 이미 존재한다.

- `docker-compose.yml:74-89`: `redis:7-alpine`, container `ddoksori_redis`, host port `6379`, named volume `redis_data`, `REDIS_PASSWORD` default, `--requirepass`, authenticated healthcheck.
- `docker-compose.yml:50-54`: backend depends on healthy `postgres` and `redis`.
- `docker-compose.yml:40-48`: backend receives DB envs and `REDIS_HOST=redis`, but currently compose does **not** pass `REDIS_PASSWORD` to backend.

따라서 M1-9의 첫 번째 검증은 Redis container 자체 ping이고, 두 번째 검증은 backend Python cache clients가 같은 auth 설정으로 Redis에 접속하는지다.

### 2.2 `.env.example` documents cache enable flags, but not Redis password propagation

`.env.example`의 Redis/cache section은 아래 상태다.

- `.env.example:87-94`: `ENABLE_ANSWER_CACHE=false`, `REDIS_HOST=redis`, `REDIS_PORT=6379`, `REDIS_DB=0`.
- `.env.example:95-99`: supervisor/QA/answer cache TTL settings.
- `.env.example` currently does not expose a `REDIS_PASSWORD` example in the Redis section, even though compose Redis requires password.

M1-9 구현 중 password wiring이 필요하면 `.env.example`에 local default와 production warning을 같이 추가한다.

### 2.3 Current Redis clients likely fail against compose Redis auth until password wiring is restored

현재 Python Redis clients construct `redis.Redis(...)` without a password:

- `backend/app/common/cache/base.py:44-60`: `ENABLE_ANSWER_CACHE=true`일 때 shared Redis client를 만들지만 `password=` 인자를 넘기지 않는다.
- `backend/app/agents/answer_generation/cache.py:42-55`: `AnswerCache`도 `password=` 없이 Redis에 ping한다.
- `backend/app/common/cache/embedding_cache.py:87-99`: `EmbeddingCache`도 `ENABLE_EMBEDDING_CACHE=true`일 때 password 없이 ping한다.

반면 compose Redis는 `--requirepass`로 시작한다 (`docker-compose.yml:82-86`). 따라서 M1-9 implementation smoke에서 `NOAUTH Authentication required` 또는 `invalid username-password pair`가 나오면, 이는 M1-9 범위 안의 최소 복구 대상이다.

### 2.4 Cache classes to validate

M1-9의 최소 cache smoke는 full chat pipeline이 아니라 cache layer 자체의 real Redis read/write를 검증한다.

| Cache layer | Code | M1-9 validation target |
| --- | --- | --- |
| Raw Redis | `docker-compose.yml:74-89` | authenticated `PING -> PONG` |
| Answer cache | `backend/app/agents/answer_generation/cache.py:18-200` | `AnswerCache.set/get/invalidate`, metrics hit/miss/error |
| Supervisor/RAG answer cache | `backend/app/supervisor/cache.py:33-57` | optional: `SupervisorResponseCache.set/get/delete` with session split |
| Retrieval cache | `backend/app/supervisor/cache.py:128-178` | `RetrievalResultCache.set_by_session/get_by_session/invalidate_session` |
| Cache stats | `backend/app/supervisor/cache.py:262-292` | counts are available when Redis is connected |
| Reliability tests | `backend/scripts/testing/reliability/test_redis_failure.py:190-230` | disabled/import-error fallback already has unit coverage |
| Answer cache unit tests | `backend/scripts/testing/supervisor/test_answer_cache.py:17-218` | mock Redis behavior already has unit coverage |

## 3. M1-9 target outcome

M1-9 implementation should leave a repeatable local evidence record proving:

1. Redis container starts from Ddoksori compose and answers authenticated ping.
2. Backend cache clients receive the same Redis host/port/db/password as compose Redis.
3. Answer cache can write, read, count/measure, and delete a unique test answer payload.
4. Retrieval cache can write, read, and delete a unique test retrieval payload.
5. Smoke records numbers: ping latency, set/get latency, hit/miss/error counts, key names/prefixes or counts, cleanup count.
6. The restored `ddoksori_postgres_data` volume is preserved; no `docker compose down -v` is run.

## 4. Implementation plan

### 4.1 Preflight: repo, module, and Docker state

Run from the M1-9 feature worktree for code/doc changes, but use `COMPOSE_PROJECT_NAME=ddoksori` when interacting with Docker so the root compose project volumes are reused.

```bash
git status --short --branch
git log --oneline --decorate -5

docker volume ls --format '{{.Name}}' | grep -E '^ddoksori_(postgres|redis)_data$'
docker ps -a --filter name=ddoksori --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
docker compose config --services
```

Expected:

- branch is `feature/m1-9-redis-cache-*` during implementation;
- `postgres`, `redis`, `backend`, `frontend` are compose services;
- `ddoksori_postgres_data` remains present from M1-7;
- `ddoksori_redis_data` may exist from prior compose runs but its contents are not trusted as evidence until this smoke runs.

### 4.2 Start Redis and prove container-level auth

Use an explicit local password value. The default compose fallback is acceptable for local smoke, but record whether `.env` overrode it.

```bash
COMPOSE_PROJECT_NAME=ddoksori \
REDIS_PASSWORD=${REDIS_PASSWORD:-dev_redis_password_change_in_production} \
docker compose up -d redis

COMPOSE_PROJECT_NAME=ddoksori docker compose ps redis

COMPOSE_PROJECT_NAME=ddoksori docker compose exec -T redis \
  sh -lc 'redis-cli -a "$REDIS_PASSWORD" --no-auth-warning ping'
```

Expected:

```text
PONG
```

Also prove unauthenticated access is rejected, without treating that rejection as a failure:

```bash
COMPOSE_PROJECT_NAME=ddoksori docker compose exec -T redis redis-cli ping || true
```

Expected shape:

```text
NOAUTH Authentication required.
```

### 4.3 Probe current backend cache connection before editing

Before changing code, run a minimal Python probe with cache enabled. This tells whether current code already supports auth through environment or needs M1-9 repair.

```bash
COMPOSE_PROJECT_NAME=ddoksori docker compose run --rm --no-deps \
  -e ENABLE_ANSWER_CACHE=true \
  -e REDIS_HOST=redis \
  -e REDIS_PORT=6379 \
  -e REDIS_DB=0 \
  -e REDIS_PASSWORD=${REDIS_PASSWORD:-dev_redis_password_change_in_production} \
  backend python - <<'PY'
from app.common.cache.base import reset_redis_client, get_redis_client
reset_redis_client()
r = get_redis_client()
print('client_connected=', bool(r))
if r:
    print('ping=', r.ping())
PY
```

Decision rule:

| Probe result | Action |
| --- | --- |
| `client_connected=True`, `ping=True` | Proceed to smoke script/tests; no connection fix needed. |
| `client_connected=False` and logs show `NOAUTH`/auth failure | Implement minimal password propagation. |
| `client_connected=False` because `ENABLE_ANSWER_CACHE` not true | Fix invocation, not code. |
| Import or dependency error | Verify `redis==5.2.1` from `backend/requirements.txt:23`; classify separately. |

### 4.4 Minimal repair branch if auth fails

If the probe shows auth failure, M1-9 implementation should make the smallest coherent changes:

1. `docker-compose.yml`
   - pass `REDIS_PORT`, `REDIS_DB`, and `REDIS_PASSWORD` into `backend.environment` near `REDIS_HOST=redis`.
   - keep existing Redis `--requirepass` and healthcheck intact.
2. `.env.example`
   - add `REDIS_PASSWORD=dev_redis_password_change_in_production` under the Redis section;
   - add `ENABLE_EMBEDDING_CACHE=false` if embedding cache smoke/tests need a documented flag;
   - warn that production must override the local default.
3. `backend/app/common/cache/base.py`
   - read `REDIS_PASSWORD` and pass `password=os.getenv("REDIS_PASSWORD") or None` to `redis.Redis`.
4. `backend/app/agents/answer_generation/cache.py`
   - pass the same password into `AnswerCache`'s direct Redis client.
5. `backend/app/common/cache/embedding_cache.py`
   - pass the same password into the embedding cache Redis client.
6. Unit tests
   - add/adjust tests that assert `redis.Redis(..., password=<env password>)` receives the password when configured and `None` when blank.

This is still M1-9 scope because compose Redis already requires authentication and the module completion criteria require real cache read/write. Do not refactor cache architecture or replace Redis clients beyond password wiring.

### 4.5 Add or run a repeatable cache smoke script

Preferred implementation artifact:

```text
backend/scripts/testing/cache/check_redis_cache_smoke.py
```

The script should be safe, local, and self-cleaning:

- generate a unique run id, e.g. `m1-9:<timestamp>:<uuid>`;
- verify raw Redis ping through the same env variables as backend cache clients;
- reset singleton clients before testing so env changes are respected;
- perform `AnswerCache.set/get/invalidate` on a unique query;
- perform `RetrievalResultCache.set_by_session/get_by_session/invalidate_session` on a unique session id;
- optionally perform `SupervisorResponseCache.set/get/delete` as an additional answer-path check;
- print compact JSON metrics: `redis_ping_ms`, `answer_set_ms`, `answer_get_ms`, `retrieval_set_ms`, `retrieval_get_ms`, `answer_hit_count`, `answer_miss_count`, `error_count`, cleanup booleans;
- never call `flushdb` or delete broad production-like prefixes by default.

Example expected output shape:

```json
{
  "status": "ok",
  "redis": {"ping": true, "ping_ms": 1.23},
  "answer_cache": {"set": true, "hit": true, "deleted": true, "hit_count": 1, "error_count": 0},
  "retrieval_cache": {"set": true, "hit": true, "deleted": true, "error_count": 0},
  "cleanup": {"test_keys_remaining": 0}
}
```

### 4.6 Run container smoke with explicit cache env

Run against the compose Redis service. If backend depends on postgres in compose, starting `backend` may also require healthy `postgres`; this is acceptable as long as `ddoksori_postgres_data` is preserved.

```bash
COMPOSE_PROJECT_NAME=ddoksori \
REDIS_PASSWORD=${REDIS_PASSWORD:-dev_redis_password_change_in_production} \
docker compose up -d redis

COMPOSE_PROJECT_NAME=ddoksori docker compose run --rm --no-deps \
  -e ENABLE_ANSWER_CACHE=true \
  -e ENABLE_EMBEDDING_CACHE=false \
  -e REDIS_HOST=redis \
  -e REDIS_PORT=6379 \
  -e REDIS_DB=0 \
  -e REDIS_PASSWORD=${REDIS_PASSWORD:-dev_redis_password_change_in_production} \
  backend python scripts/testing/cache/check_redis_cache_smoke.py \
  | tee /tmp/m1-9-redis-cache-smoke.json
```

After M1-9 adds cache env entries to `backend.environment`, an additional service-level run can verify the long-running backend container receives the same non-secret Redis settings:

```bash
COMPOSE_PROJECT_NAME=ddoksori docker compose up -d backend
COMPOSE_PROJECT_NAME=ddoksori docker compose exec -T backend \
  sh -lc 'env | grep -E "^(ENABLE_ANSWER_CACHE|ENABLE_EMBEDDING_CACHE|REDIS_HOST|REDIS_PORT|REDIS_DB|REDIS_PASSWORD)=" | sed "s/^REDIS_PASSWORD=.*/REDIS_PASSWORD=***present***/" | sort'
```

The first smoke uses `docker compose run -e ...` intentionally, because shell variables are not automatically injected into a compose service unless they are listed in `environment:` or an `env_file`.

### 4.7 Run targeted tests

Targeted tests should cover connection wiring and existing cache semantics without running the full suite.

```bash
cd backend
PYTHONPATH=. pytest \
  scripts/testing/supervisor/test_answer_cache.py \
  scripts/testing/cache/test_embedding_cache.py \
  scripts/testing/cache/test_embedding_cache_integration.py \
  scripts/testing/cache/test_redis_password_config.py \
  scripts/testing/query_analysis/test_intent_cache.py \
  scripts/testing/reliability/test_redis_failure.py \
  -q
```

If M1-9 adds a new smoke script with unit-testable functions, add its focused tests to this command. If a test requires real Redis and is not deterministic in CI, mark it clearly and keep the local smoke command as the integration evidence.

### 4.8 Optional API-level cache observation

M1-9 minimum acceptance is cache-layer read/write. Full chat API cache hit behavior can be expensive or provider-dependent, so it is optional.

If performed, record it separately:

- enable `ENABLE_ANSWER_CACHE=true`;
- call the same chat/supervisor endpoint twice with a stable session id;
- confirm logs show cache miss then hit;
- record latency before/after and cache hit rate.

Do not block M1-9 on provider/API answer generation if cache-layer smoke already proves answer and retrieval cache read/write.

### 4.9 Cleanup

Preserve named volumes and stop containers only.

```bash
COMPOSE_PROJECT_NAME=ddoksori docker compose down
rm -f /tmp/m1-9-redis-cache-smoke.json
```

Do **not** run:

```bash
docker compose down -v
redis-cli FLUSHDB
```

## 5. Validation evidence to record

M1-9 implementation PR should append an `Implementation result` section to this file with the following table.

| Evidence | Required value / shape |
| --- | --- |
| Git commit/branch | feature branch and base `develop` commit |
| Compose services | `postgres`, `redis`, `backend`, `frontend` |
| Redis container | `ddoksori_redis`, healthy/running during smoke |
| Redis ping | authenticated `PONG`; unauthenticated rejection captured as expected |
| Backend Redis env | non-secret `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`, `ENABLE_ANSWER_CACHE`; password presence only, not value |
| Answer cache write/read | `set=True`, `get` returns same payload, `delete=True` |
| Retrieval cache write/read | `get_by_session` returns same retrieval payload, `invalidate=True` |
| Metrics | ping/set/get latency, hit/miss/error counts, key cleanup count |
| Tests | targeted pytest command and pass/fail count |
| Cleanup | `docker compose down`, volumes preserved |

## 6. Failure classification

| Symptom | Likely cause | M1-9 action |
| --- | --- | --- |
| Redis healthcheck fails | wrong `REDIS_PASSWORD`, port collision, stale container config | recreate Redis container without deleting volumes; record env used |
| `NOAUTH Authentication required` from backend cache client | Python clients did not pass `REDIS_PASSWORD` | implement password propagation in M1-9 scope |
| `client_connected=False` with no Redis error | `ENABLE_ANSWER_CACHE` or `ENABLE_EMBEDDING_CACHE` disabled | fix smoke env; do not edit code |
| `AnswerCache` works but `BaseRedisCache` layers fail | direct `AnswerCache` and shared cache client diverged | align password/env handling across both clients |
| Retrieval cache get returns `None` after set | singleton client initialized before env override, wrong DB, serialization issue | reset clients before smoke; inspect key prefix and DB |
| Host `6379` conflict | local Redis already uses host port | run compose network-only smoke or override host port only if needed |
| Full chat cache observation fails due LLM/provider | outside M1-9 minimum | record as optional gap; cache-layer smoke remains valid |

## 7. Explicit non-scope

M1-9 must not include:

- frontend local UI smoke; this is `M1-10`.
- chatbot answer-quality, retrieval ranking, or Goldenset evaluation.
- RunPod/local LLM provider migration.
- broad cache architecture rewrite or new external dependency.
- deleting `ddoksori_postgres_data` or `ddoksori_redis_data`.
- changing production secrets management beyond local env documentation.

## 8. M1-9 acceptance criteria

M1-9 implementation is complete when:

1. Authenticated Redis `PING` returns `PONG` from local compose Redis.
2. Backend cache clients can connect to compose Redis with cache enabled and password configured.
3. `AnswerCache` can set/get/delete a unique answer payload in real Redis.
4. `RetrievalResultCache` can set/get/invalidate a unique retrieval payload in real Redis.
5. Smoke output records latency and hit/miss/error metrics.
6. Targeted cache/reliability tests pass or any test gap is explicitly documented with a next-best validation.
7. Cleanup preserves existing Docker volumes.
8. Verification evidence is documented in the M1-9 PR.

## 9. Next module gate

After M1-9 is verified, stop before M1-10 and review the evidence.

The next module candidate is:

| Module | Goal | Completion criteria |
| --- | --- | --- |
| `M1-10` | Frontend 점검 | local UI에서 최소 chat/search 요청 확인 |


## 10. Implementation result

- 실행일: 2026-05-28
- 실행 위치: `/home/maroco/Ddoksori-worktrees/m1-9-redis-cache-plan`
- Feature branch: `feature/m1-9-redis-cache-plan`
- Base commit: `22e7bba` (`develop`, PR #10 merge)
- Target services/volumes: `ddoksori_redis`, `ddoksori_backend`, `ddoksori_postgres`; preserved `ddoksori_postgres_data` and `ddoksori_redis_data`

### 10.1 Pre-implementation evidence

Redis container-level auth worked, but backend cache clients failed before the M1-9 fix.

| Check | Result |
| --- | --- |
| Authenticated Redis ping | `PONG` |
| Backend shared cache probe before fix | `client_connected=False` |
| Failure message | `[Redis] Connection failed: Authentication required.` |
| Root cause | Compose Redis uses `--requirepass`, but backend cache clients did not pass `REDIS_PASSWORD` |

### 10.2 Implemented changes

| File | Change |
| --- | --- |
| `docker-compose.yml` | Added backend Redis env propagation for `REDIS_PORT`, `REDIS_DB`, `REDIS_PASSWORD`, `ENABLE_ANSWER_CACHE`, and `ENABLE_EMBEDDING_CACHE`. |
| `.env.example` | Documented `REDIS_PASSWORD` local default and `ENABLE_EMBEDDING_CACHE=false`. |
| `backend/app/common/cache/base.py` | Shared `BaseRedisCache` Redis client now passes `password=os.getenv("REDIS_PASSWORD") or None`. |
| `backend/app/agents/answer_generation/cache.py` | `AnswerCache` direct Redis client now passes `REDIS_PASSWORD`. |
| `backend/app/common/cache/embedding_cache.py` | `EmbeddingCache` Redis client now passes `REDIS_PASSWORD`. |
| `backend/scripts/testing/cache/check_redis_cache_smoke.py` | Added self-cleaning local smoke script for Redis ping, answer cache write/read/delete, retrieval cache write/read/delete, latency, hit/miss/error metrics, and cleanup counts. |
| `backend/scripts/testing/cache/test_redis_password_config.py` | Added focused password wiring unit coverage for shared `get_redis_client()`, `AnswerCache`, and `EmbeddingCache`. |

### 10.3 Post-fix connection evidence

Backend shared cache probe after the fix:

```text
client_connected= True
ping= True
```

Long-running backend service received the expected non-secret Redis settings:

```text
ENABLE_ANSWER_CACHE=true
ENABLE_EMBEDDING_CACHE=false
REDIS_DB=0
REDIS_HOST=redis
REDIS_PASSWORD=***present***
REDIS_PORT=6379
```

Unauthenticated Redis access remains rejected as expected:

```text
NOAUTH Authentication required.
```

### 10.4 Redis cache smoke result

Command shape:

```bash
COMPOSE_PROJECT_NAME=ddoksori docker compose run --rm --no-deps \
  -e ENABLE_ANSWER_CACHE=true \
  -e ENABLE_EMBEDDING_CACHE=false \
  -e REDIS_HOST=redis \
  -e REDIS_PORT=6379 \
  -e REDIS_DB=0 \
  -e REDIS_PASSWORD=${REDIS_PASSWORD:-dev_redis_password_change_in_production} \
  backend python scripts/testing/cache/check_redis_cache_smoke.py
```

Smoke output summary:

| Metric | Value |
| --- | ---: |
| `status` | `ok` |
| `run_id` | `m1-9:1779940126:6620f4a9` |
| Redis `ping` | `true` |
| Redis `ping_ms` | `1.243` |
| Answer cache `set/get/delete` | `true / true / true` |
| Answer cache `set_ms/get_ms/delete_ms` | `0.365 / 0.207 / 0.194` |
| Answer cache `hit_count/miss_count/error_count` | `1 / 0 / 0` |
| Retrieval cache `set/get/delete` | `true / true / true` |
| Retrieval cache `set_ms/get_ms/delete_ms` | `1.061 / 0.194 / 0.126` |
| Retrieval cache `hit_count/miss_count/error_count` | `1 / 0 / 0` |
| Cleanup `test_keys_remaining` | `0` |

### 10.5 Targeted tests

Executed in the backend container because the host Python environment did not have `pytest` installed.

```bash
COMPOSE_PROJECT_NAME=ddoksori docker compose run --rm --no-deps \
  -e PYTHONDONTWRITEBYTECODE=1 \
  backend python -m pytest \
  scripts/testing/supervisor/test_answer_cache.py \
  scripts/testing/cache/test_embedding_cache.py \
  scripts/testing/cache/test_embedding_cache_integration.py \
  scripts/testing/cache/test_redis_password_config.py \
  scripts/testing/query_analysis/test_intent_cache.py \
  scripts/testing/reliability/test_redis_failure.py \
  -q
```

Result:

```text
68 passed in 5.38s
```

Additional syntax check:

```text
syntax_ok backend/app/common/cache/base.py
syntax_ok backend/app/agents/answer_generation/cache.py
syntax_ok backend/app/common/cache/embedding_cache.py
syntax_ok backend/scripts/testing/cache/check_redis_cache_smoke.py
```

### 10.6 Cleanup after verification

Ran:

```bash
COMPOSE_PROJECT_NAME=ddoksori docker compose down
```

Post-cleanup state:

| Check | Result |
| --- | --- |
| Running `ddoksori_*` containers | none |
| Preserved volume | `ddoksori_postgres_data` |
| Preserved volume | `ddoksori_redis_data` |
| Broad Redis deletion | not run |
| Docker volume deletion | not run |

### 10.7 M1-9 status and next gate

M1-9 is complete for Redis cache recovery and smoke validation:

1. Authenticated Redis `PING` returned `PONG`.
2. Backend cache clients connect to compose Redis with password configured.
3. `AnswerCache` set/get/delete succeeded against real Redis.
4. `RetrievalResultCache` set/get/invalidate succeeded against real Redis.
5. Latency, hit/miss/error metrics, and cleanup counts were recorded.
6. Targeted cache/reliability tests passed (`68 passed`).
7. Cleanup preserved existing Docker volumes.

Stop before M1-10 until this evidence is reviewed/accepted. M1-10 remains frontend local UI smoke against the local backend.
