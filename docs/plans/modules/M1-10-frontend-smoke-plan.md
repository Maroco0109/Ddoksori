# M1-10 Frontend local smoke 계획

- 작성일: 2026-05-28
- 모듈: `M1-10` Frontend 점검
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`
- 선행 모듈: `M1-9` Redis cache 복구 및 점검 완료
- 목표: local compose frontend가 local backend와 연결되고, frontend origin에서 최소 `health/search/chat` 요청 경로가 동작하는지 확인한다.
- 이번 계획 문서에서 하지 않는 일: 실제 frontend smoke 실행, frontend/backend 코드 수정, Docker volume 삭제, chatbot answer-quality 평가, Goldenset/security 평가, RunPod/provider migration.

## 1. 진행상황 요약

현재 `develop` 기준 M1-9까지 병합되어 있다.

| 항목 | 현재 상태 |
| --- | --- |
| Git 기준 | `develop` at `cf2767f` / PR #11 merge commit |
| M1-7 산출물 | `ddoksori_postgres_data` volume restored and preserved |
| M1-8 산출물 | backend `/health` HTTP 200, `/search` HTTP 200, `results_count=3` |
| M1-9 산출물 | authenticated Redis ping, answer/retrieval cache set-get-delete, `68 passed` targeted cache tests |
| Current gate | M1-10 frontend local UI smoke |

로드맵은 M1-10의 완료 기준을 `local UI에서 최소 chat/search 요청 확인`으로 정의한다 (`docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md:59-61`). M1-9 결과 문서는 Redis/cache validation이 완료되었고, M1-10으로 넘어가기 전 검토 게이트를 명시했다 (`docs/plans/modules/M1-9-redis-cache-smoke-plan.md:498-510`).

## 2. Repo evidence for M1-10

### 2.1 Compose stack has frontend/backend/postgres/redis services

- `docker-compose.yml:29-62`: backend service exposes `8000`, depends on healthy `postgres` and `redis`, and receives local DB/Redis env.
- `docker-compose.yml:64-77`: frontend service exposes `5173`, mounts `./frontend:/app`, sets `VITE_API_BASE_URL=http://localhost:8000`, and runs `npm run dev -- --host`.
- `docker-compose.yml:96-99`: named volumes include `postgres_data`, `redis_data`, and `frontend_node_modules`.

M1-10 should run compose with `COMPOSE_PROJECT_NAME=ddoksori` when using a feature worktree so the restored root volumes (`ddoksori_postgres_data`, `ddoksori_redis_data`) are reused.

### 2.2 Frontend API base and Vite proxy paths

- `frontend/src/shared/api/client.ts:7`: `API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'`.
- `frontend/src/shared/api/chat.service.ts:15-28`: `sendMessage()` posts to `/chat`; `healthCheck()` gets `/health`.
- `frontend/src/features/chat/hooks/useStreamingChat.ts:80-129`: current ChatPage sends streaming requests to `${API_BASE_URL}/chat/stream`.
- `frontend/vite.config.ts:41-60`: Vite dev proxy includes `/chat`, `/search`, `/api`, `/case`, and `/health` to backend `http://localhost:8000`.

Therefore M1-10 can validate frontend-backend connectivity through two complementary paths:

1. absolute backend URL from frontend runtime env (`http://localhost:8000`);
2. frontend-origin proxy path (`http://localhost:5173/search`, `http://localhost:5173/health`) to prove local UI/dev-server connectivity.

### 2.3 Chat UI route and selectors

- `frontend/src/shared/config/routes.ts:1-5`: chat route is `/chat`.
- `frontend/src/app/routes.tsx:18-28`: `/chat` renders `ChatPage` under `RootLayout`.
- `frontend/src/features/chat/ChatPage.tsx:567-570`: page heading is `AI 상담 챗봇`.
- `frontend/src/features/chat/ChatPage.tsx:750-801`: general chat input placeholder is `질문을 입력하세요...` and send button dispatches `handleGeneralSend()`.
- `frontend/src/features/chat/ChatPage.tsx:598-695`: dispute chat has a required onboarding form before sending.

For the smallest M1-10 UI smoke, prefer **general 상담** first because it does not require filling dispute onboarding fields. Use dispute form only as an optional secondary check.

### 2.4 Playwright exists but no e2e specs are present

- `frontend/package.json` defines `test:e2e = playwright test`.
- `frontend/playwright.config.ts:3-24` expects `testDir: './e2e'` and base URL `http://localhost:5173`.
- No tracked `frontend/e2e/*.spec.*` files exist at planning time.

M1-10 implementation can either run a manual/browser smoke and record evidence, or add a small `frontend/e2e/m1-10-local-smoke.spec.ts` if a repeatable UI smoke artifact is desired. Adding a minimal e2e spec is in-scope only if it remains focused on M1-10 connectivity and does not redesign frontend behavior.

## 3. M1-10 target outcome

M1-10 implementation should leave evidence proving:

1. `frontend`, `backend`, `postgres`, and `redis` run together under local compose.
2. `http://localhost:5173` serves the React app.
3. `http://localhost:5173/chat` renders the `AI 상담 챗봇` page.
4. Frontend-origin `/health` reaches backend and returns healthy DB status.
5. Frontend-origin `/search` reaches backend and returns `results_count > 0` against the restored local DB.
6. Chat UI sends at least one request to backend (`/chat/stream` preferred because current UI uses SSE) and records either a complete answer event or a clearly classified provider/config blocker.
7. Evidence includes status codes, result counts, latency, top result identifiers, request path, screenshots or console/network snippets, and cleanup/volume preservation.

## 4. Preconditions

| Precondition | Expected |
| --- | --- |
| PR #11 / M1-9 | merged into `develop` |
| Root branch | `develop` synced with `origin/develop` |
| Restored DB volume | `ddoksori_postgres_data` exists |
| Redis volume | `ddoksori_redis_data` exists or can be recreated without deleting DB volume |
| Backend baseline | M1-8 `/health` + `/search` evidence remains valid, or quick re-smoke passes |
| Redis baseline | M1-9 cache smoke evidence remains valid, or quick re-smoke passes |
| Repo state | no unrelated tracked changes |

Recommended preflight:

```bash
git status --short --branch
docker volume ls --format '{{.Name}}' | grep -E '^ddoksori_(postgres|redis)_data$'
COMPOSE_PROJECT_NAME=ddoksori docker compose config --services
```

If `ddoksori_postgres_data` is missing, stop and revisit M1-7 restore before claiming M1-10 complete.

## 5. Implementation plan

### 5.1 Start the local compose stack

Run from the M1-10 feature worktree if implementation changes are being tested. Use `COMPOSE_PROJECT_NAME=ddoksori` to reuse restored root volumes.

```bash
cd /home/maroco/Ddoksori-worktrees/m1-10-frontend-smoke-plan

COMPOSE_PROJECT_NAME=ddoksori \
DB_HOST=postgres \
DB_PORT=5432 \
RETRIEVAL_MODE=hybrid \
ENABLE_ANSWER_CACHE=true \
ENABLE_EMBEDDING_CACHE=false \
REDIS_PASSWORD=${REDIS_PASSWORD:-dev_redis_password_change_in_production} \
docker compose up -d postgres redis backend frontend

COMPOSE_PROJECT_NAME=ddoksori docker compose ps
```

Provider/env note:

- `/search` should work in the lexical fallback branch even without `OPENAI_API_KEY`, as proven in M1-8.
- `/chat/stream` may require generation provider configuration. If root `.env` has provider keys but the feature worktree lacks `.env`, either run the final UI smoke from the root worktree after merge or create a temporary untracked `.env` in the feature worktree from local secrets. Do not commit `.env` or print secret values.

### 5.2 Backend readiness through direct backend origin

Capture backend health first so frontend failures can be separated from backend readiness failures.

```bash
curl -o /tmp/m1-10-backend-health.json -sS \
  -w 'backend_health_http=%{http_code} backend_health_time_total=%{time_total}\n' \
  http://localhost:8000/health
cat /tmp/m1-10-backend-health.json
```

Expected:

```json
{"status":"healthy","database":"connected"}
```

Optional quick backend search baseline:

```bash
curl -o /tmp/m1-10-backend-search.json -sS \
  -w 'backend_search_http=%{http_code} backend_search_time_total=%{time_total}\n' \
  -H 'Content-Type: application/json' \
  -X POST http://localhost:8000/search \
  -d '{"query":"헬스장 계약 해지 환불 위약금", "top_k": 3}'
```

Acceptance for this preflight: HTTP 200 and `results_count > 0`.

### 5.3 Frontend dev server readiness

```bash
curl -o /tmp/m1-10-frontend-root.html -sS \
  -w 'frontend_root_http=%{http_code} frontend_root_time_total=%{time_total}\n' \
  http://localhost:5173/

grep -E '<div id="root"|/src/main' /tmp/m1-10-frontend-root.html
```

Expected:

- HTTP 200;
- Vite-served HTML includes root mount or main script reference.

### 5.4 Frontend-origin proxy/API smoke

Use frontend origin to prove local frontend dev server can reach backend paths.

```bash
curl -o /tmp/m1-10-frontend-health.json -sS \
  -w 'frontend_health_http=%{http_code} frontend_health_time_total=%{time_total}\n' \
  http://localhost:5173/health

curl -o /tmp/m1-10-frontend-search.json -sS \
  -w 'frontend_search_http=%{http_code} frontend_search_time_total=%{time_total}\n' \
  -H 'Content-Type: application/json' \
  -X POST http://localhost:5173/search \
  -d '{"query":"헬스장 계약 해지 환불 위약금", "top_k": 3}'

python - <<'PY'
import json
from pathlib import Path
payload = json.loads(Path('/tmp/m1-10-frontend-search.json').read_text())
print('query=', payload.get('query'))
print('results_count=', payload.get('results_count'))
for idx, item in enumerate(payload.get('results', [])[:3], start=1):
    print(idx, item.get('chunk_id'), item.get('doc_type'), item.get('chunk_type'), item.get('similarity'))
PY
```

Acceptance:

- `/health` via `localhost:5173` returns HTTP 200 and healthy DB status.
- `/search` via `localhost:5173` returns HTTP 200 and `results_count > 0`.
- Record top 1-3 result identifiers and similarity values.

### 5.5 Browser UI smoke for `/chat`

Preferred path: Playwright one-off script or tracked focused e2e spec.

Manual/one-off Playwright shape:

```bash
cd frontend
npx playwright install chromium --with-deps  # only if browser deps are missing
npx playwright test e2e/m1-10-local-smoke.spec.ts --project=chromium --reporter=line
```

If adding a focused spec, keep it minimal:

1. navigate to `http://localhost:5173/chat`;
2. assert text `AI 상담 챗봇`, `일반 상담`, and input placeholder `질문을 입력하세요...` are visible;
3. intercept or observe request to `/chat/stream`;
4. fill `헬스장 계약 해지 환불 위약금` in the general input;
5. click the send button or press Enter;
6. wait for one of:
   - a successful SSE `complete` event and rendered AI answer; or
   - a classified backend/provider error surfaced in UI/logs, with the network request still proving frontend-to-backend path.

Full completion should prefer successful answer rendering. If provider configuration blocks answer generation, M1-10 should not silently pass; record the blocker and use `/search` frontend-origin smoke as the confirmed RAG connectivity evidence.

### 5.6 Optional dispute form smoke

Only after the general chat route is stable, optionally fill dispute onboarding:

| Field | Suggested value |
| --- | --- |
| 구매일자 | `2026-05-01` |
| 구매처 | `테스트 헬스장` |
| 플랫폼 | empty or `오프라인` |
| 구매품목 | `헬스장 회원권` |
| 구매금액 | `300000` |
| 분쟁 상세 내용 | `계약 해지와 환불 위약금 기준을 알고 싶습니다.` |

Acceptance: form submits, chat input appears, and a follow-up request can be sent or classified.

### 5.7 Cleanup

```bash
COMPOSE_PROJECT_NAME=ddoksori docker compose down
rm -f \
  /tmp/m1-10-backend-health.json \
  /tmp/m1-10-backend-search.json \
  /tmp/m1-10-frontend-root.html \
  /tmp/m1-10-frontend-health.json \
  /tmp/m1-10-frontend-search.json
```

Do not run:

```bash
docker compose down -v
```

## 6. Validation evidence to record

M1-10 implementation PR should append an `Implementation result` section to this file with these fields.

| Evidence | Required value / shape |
| --- | --- |
| Git commit/branch | feature branch and base `develop` commit |
| Compose services | `postgres`, `redis`, `backend`, `frontend` running during smoke |
| Volumes | `ddoksori_postgres_data`, `ddoksori_redis_data` preserved |
| Backend direct health | HTTP code, latency, JSON status/database |
| Frontend root | HTTP code, latency, root/main script evidence |
| Frontend-origin health | HTTP code, latency, JSON status/database |
| Frontend-origin search | HTTP code, latency, `results_count > 0`, top result identifiers |
| Chat route UI | `/chat` loaded, visible heading/input evidence |
| Chat request | `/chat/stream` request observed, HTTP/SSE result classified |
| Browser console/network | zero unknown frontend errors, or classified known/provider error |
| Cleanup | `docker compose down`, no volume deletion |

## 7. Failure classification

| Symptom | Likely cause | M1-10 action |
| --- | --- | --- |
| Frontend `5173` not reachable | frontend container build/install/dev server failure | inspect `docker compose logs frontend`; fix only minimal local-run issue if in scope |
| Backend health fails | DB/Redis env or restored volume issue | revisit M1-7/M1-9 evidence before frontend debugging |
| Frontend-origin `/health` fails but backend direct `/health` passes | Vite proxy/env mismatch | inspect `vite.config.ts` and `VITE_API_BASE_URL`; fix minimal dev connectivity issue |
| Frontend-origin `/search` returns 0 results | restored DB missing/wrong compose project/query mismatch | rerun M1-7/M1-8 DB/search checks; do not claim M1-10 complete |
| `/chat/stream` request not sent | UI handler/selector/runtime error | inspect browser console and `ChatPage` send path; minimal M1-10 fix may be in scope |
| `/chat/stream` provider error | missing LLM provider env, not frontend connectivity | record as provider/config blocker; M2 provider work remains separate |
| CORS error | frontend calling backend absolute URL without allowed origin | capture browser console; fix local CORS only if backend config intends localhost:5173 |
| Playwright missing browsers/deps | local test environment issue | install browsers/deps or use manual browser/curl evidence; do not alter app code |

## 8. Explicit non-scope

M1-10 must not include:

- answer quality or retrieval ranking improvements;
- Goldenset/security evaluation;
- RunPod/local LLM provider migration;
- frontend redesign or broad UX changes;
- DB restore, Redis cache redesign, or Docker volume deletion;
- production deployment changes.

## 9. M1-10 acceptance criteria

M1-10 implementation is complete when:

1. Local compose stack runs `postgres`, `redis`, `backend`, and `frontend` together.
2. `http://localhost:5173` serves the frontend app.
3. `/chat` UI renders the chat page and general chat input.
4. Frontend-origin `/health` reaches backend and reports healthy DB status.
5. Frontend-origin `/search` returns HTTP 200 and `results_count > 0` for the canonical smoke query.
6. UI-initiated chat request to `/chat/stream` is observed and classified, preferably with a successful complete answer event.
7. Metrics/evidence include status codes, latency, result count, top result identifiers, and browser console/network status.
8. Cleanup preserves `ddoksori_postgres_data` and `ddoksori_redis_data`.
9. Verification evidence is documented in the M1-10 PR.

## 10. Next module gate

After M1-10 is verified, stop and review the full M1 local reproducibility evidence before moving to M2.

The next roadmap area is:

| Area | First module | Goal |
| --- | --- | --- |
| `M2` | `M2-1` | 현재 LLM 호출 경로 inventory |

## 11. Implementation result

- 실행일: 2026-05-28
- 실행 위치: `/home/maroco/Ddoksori-worktrees/m1-10-frontend-smoke-plan`
- Feature branch: `feature/m1-10-frontend-smoke-plan`
- Base commit before implementation: `cf2767f` (`develop`, PR #11 merged)
- Target compose project: `COMPOSE_PROJECT_NAME=ddoksori`
- Target services: `ddoksori_postgres`, `ddoksori_redis`, `ddoksori_backend`, `ddoksori_frontend`
- Target volumes preserved: `ddoksori_postgres_data`, `ddoksori_redis_data`
- Canonical query: `헬스장 계약 해지 환불 위약금`

### 11.1 Implementation changes

M1-10 smoke exposed two local frontend connectivity issues and fixed them minimally:

| File | Change | Why |
| --- | --- | --- |
| `docker-compose.yml` | Added `VITE_PROXY_TARGET=http://backend:8000` to the frontend service. | Inside the frontend container, Vite proxy target `localhost:8000` points at the frontend container itself, not the backend container. |
| `frontend/vite.config.ts` | Reads `process.env.VITE_PROXY_TARGET` with `http://localhost:8000` fallback. | Host `npm run dev` keeps the old default; Docker compose uses the backend service DNS name. |
| `frontend/vite.config.ts` | Bypasses proxy for `GET` document requests with `Accept: text/html`, returning `/index.html`. | `/chat` is both a frontend SPA route and a backend API prefix; browser navigation to `/chat` must render the SPA instead of being proxied to backend `POST /chat`. |
| `.gitignore` | Stopped ignoring `frontend/e2e`. | The repo already has Playwright config; M1-10 needs a tracked repeatable smoke spec. |
| `frontend/e2e/m1-10-local-smoke.spec.ts` | Added focused Playwright smoke for frontend-origin `/health`, `/search`, `/chat`, and `/chat/stream`. | Preserves repeatable evidence for future before/after comparisons. |

### 11.2 Preflight and environment evidence

The first compose run intentionally reused `ddoksori` volumes but no feature-worktree `.env` existed. That run classified the expected credential/env issue before the final run:

```text
backend_health_http=200 backend_health_time_total=0.024733
{"status":"unhealthy","error":"서비스 연결 실패"}
backend_search_http=500 backend_search_time_total=0.006290
```

Backend logs showed the cause was DB credentials mismatch against the restored volume:

```text
psycopg2.OperationalError: connection to server at "postgres" ... failed: FATAL:  password authentication failed for user "postgres"
```

Final smoke used the root local `.env` as a temporary untracked symlink in the feature worktree so compose could reuse the restored DB credentials and provider settings without committing secrets. Effective non-secret backend env:

```text
DB_HOST=postgres
DB_NAME=ddoksori
DB_PORT=5432
DB_USER=***present***
ENABLE_ANSWER_CACHE=true
ENABLE_EMBEDDING_CACHE=false
OPENAI_API_KEY=***present***
REDIS_DB=0
REDIS_HOST=redis
REDIS_PASSWORD=***present***
REDIS_PORT=6379
RETRIEVAL_MODE=hybrid
```

Compose services during the successful smoke:

```text
ddoksori_backend    Up 6 minutes             0.0.0.0:8000->8000/tcp
ddoksori_frontend   Up About a minute        0.0.0.0:5173->5173/tcp
ddoksori_postgres   Up 6 minutes (healthy)   0.0.0.0:5433->5432/tcp
ddoksori_redis      Up 6 minutes (healthy)   0.0.0.0:6379->6379/tcp
```

Observed named volumes:

```text
ddoksori_frontend_node_modules
ddoksori_postgres_data
ddoksori_redis_data
```

### 11.3 Direct backend smoke evidence

`GET /health` against backend origin passed:

```text
backend_health_http=200 backend_health_time_total=0.026301
```

Response:

```json
{"status":"healthy","database":"connected"}
```

`POST /search` against backend origin passed:

```text
backend_search_http=200 backend_search_time_total=2.354274
backend_results_count=3
```

Top result evidence:

| Rank | `chunk_id` | `doc_id` | `doc_type` | `chunk_type` | `similarity` |
| ---: | --- | --- | --- | --- | ---: |
| 1 | `crawl_semantic_상담_10490_full_1` | `10490` | `counsel_case` | `case` | `0.01639344262295082` |
| 2 | `crawl_semantic_조정_2182_judgment_3` | `2182` | `mediation_case` | `case` | `0.01639344262295082` |
| 3 | `crawl_semantic_상담_10617_full_1` | `10617` | `counsel_case` | `case` | `0.016129032258064516` |

### 11.4 Frontend-origin smoke evidence

Frontend root served Vite HTML:

```text
frontend_root_http=200 frontend_root_time_total=0.028182
<div id="root"></div>
<script type="module" src="/src/main.jsx"></script>
```

Browser-style `GET /chat` with `Accept: text/html` served SPA HTML after the proxy bypass fix:

```text
HTTP/1.1 200 OK
Content-Type: text/html
<div id="root"></div>
<script type="module" src="/src/main.jsx"></script>
```

Frontend-origin `/health` through Vite proxy passed:

```text
frontend_health_http=200 frontend_health_time_total=0.024562
```

Response:

```json
{"status":"healthy","database":"connected"}
```

Frontend-origin `/search` through Vite proxy passed:

```text
frontend_search_http=200 frontend_search_time_total=1.021957
frontend_results_count=3
```

Top result evidence matched the direct backend smoke:

| Rank | `chunk_id` | `doc_id` | `doc_type` | `chunk_type` | `similarity` |
| ---: | --- | --- | --- | --- | ---: |
| 1 | `crawl_semantic_상담_10490_full_1` | `10490` | `counsel_case` | `case` | `0.01639344262295082` |
| 2 | `crawl_semantic_조정_2182_judgment_3` | `2182` | `mediation_case` | `case` | `0.01639344262295082` |
| 3 | `crawl_semantic_상담_10617_full_1` | `10617` | `counsel_case` | `case` | `0.016129032258064516` |

### 11.5 Browser UI and chat stream smoke evidence

Command shape:

```bash
docker run --rm --network host \
  -v "$PWD/frontend:/work/frontend" \
  -v m1_10_playwright_node_modules:/work/frontend/node_modules \
  -w /work/frontend \
  -e M1_10_REQUIRE_CHAT_COMPLETE=true \
  mcr.microsoft.com/playwright:v1.58.1-noble \
  sh -lc 'npm ci && npx playwright test e2e/m1-10-local-smoke.spec.ts --project=chromium --reporter=line --output=/tmp/m1-10-playwright-results'
```

Result:

```text
Running 2 tests using 2 workers
m1-10 frontend-origin search: {"results_count":3,"top_results":[...]}
m1-10 chat stream: {"status":200,"hasCompleteEvent":true,"hasErrorEvent":false,"bodyBytes":9210}
2 passed (21.3s)
```

This proves:

1. `/chat` rendered the browser-visible `AI 상담 챗봇` and `일반 상담` headings.
2. The general chat input `질문을 입력하세요...` was visible.
3. UI input submitted the canonical smoke query.
4. Browser observed a `POST /chat/stream` response with HTTP 200.
5. The SSE stream contained a `complete` event, not an error event.
6. The Playwright console-error assertion passed.

### 11.6 Build verification

Frontend production build passed after the Vite config change:

```text
COMPOSE_PROJECT_NAME=ddoksori docker compose exec -T frontend npm run build
✓ 2784 modules transformed.
✓ built in 5.05s
```

Vite emitted the existing large-chunk warning for the bundled app; no build error was produced.

### 11.7 Cleanup after verification

Cleanup command:

```bash
COMPOSE_PROJECT_NAME=ddoksori docker compose down
rm -f .env
```

Do not run `docker compose down -v`; M1-10 depends on preserving the restored local DB and Redis volumes.

### 11.8 Local self-test guide

After this PR is merged, a local tester can reproduce M1-10 from the repo root.

1. Confirm the restored volumes exist:

   ```bash
   docker volume ls --format '{{.Name}}' | grep -E '^ddoksori_(postgres|redis)_data$'
   ```

2. Start the local stack. If root `.env` contains restored DB credentials and provider keys, keep it local and do not print secret values:

   ```bash
   COMPOSE_PROJECT_NAME=ddoksori \
   DB_HOST=postgres \
   DB_PORT=5432 \
   RETRIEVAL_MODE=hybrid \
   ENABLE_ANSWER_CACHE=true \
   ENABLE_EMBEDDING_CACHE=false \
   docker compose --env-file .env up -d postgres redis backend frontend
   ```

   If no provider key is available, `/health` and `/search` can still be tested, but `/chat/stream` may return a classified provider/config error instead of a complete answer.

3. Quick curl checks:

   ```bash
   curl http://localhost:8000/health
   curl http://localhost:5173/health

   curl -H 'Content-Type: application/json' \
     -X POST http://localhost:5173/search \
     -d '{"query":"헬스장 계약 해지 환불 위약금", "top_k": 3}'
   ```

   Expected: health JSON is `{"status":"healthy","database":"connected"}` and search returns `results_count > 0`.

4. Manual browser check:

   - Open `http://localhost:5173/chat`.
   - Confirm `AI 상담 챗봇` and `일반 상담` are visible.
   - Enter `헬스장 계약 해지 환불 위약금` into `질문을 입력하세요...`.
   - Send with Enter or the send button.
   - In browser DevTools Network, confirm `POST http://localhost:8000/chat/stream` returns HTTP 200 and the UI renders an answer. If provider env is missing, record the visible/backend error as provider-config blocked rather than frontend-connectivity failed.

5. Repeatable Playwright check:

   ```bash
   docker run --rm --network host \
     -v "$PWD/frontend:/work/frontend" \
     -v m1_10_playwright_node_modules:/work/frontend/node_modules \
     -w /work/frontend \
     -e M1_10_REQUIRE_CHAT_COMPLETE=true \
     mcr.microsoft.com/playwright:v1.58.1-noble \
     sh -lc 'npm ci && npx playwright test e2e/m1-10-local-smoke.spec.ts --project=chromium --reporter=line --output=/tmp/m1-10-playwright-results'
   ```

   Use `-e M1_10_REQUIRE_CHAT_COMPLETE=false` only when intentionally testing a no-provider environment where chat-stream request connectivity should be classified but not required to complete.

6. Stop containers while preserving volumes:

   ```bash
   COMPOSE_PROJECT_NAME=ddoksori docker compose down
   ```

### 11.9 M1-10 status and next gate

M1-10 is complete for local frontend/backend smoke:

1. `postgres`, `redis`, `backend`, and `frontend` ran together under local compose.
2. `http://localhost:5173` served the frontend app.
3. Browser-style `/chat` navigation rendered the SPA.
4. Frontend-origin `/health` returned healthy DB status.
5. Frontend-origin `/search` returned HTTP 200 and `results_count=3`.
6. UI-initiated `/chat/stream` returned HTTP 200 with SSE `complete` event.
7. Evidence includes status codes, latency, result counts, top result identifiers, browser/Playwright status, and build status.
8. Cleanup preserved `ddoksori_postgres_data` and `ddoksori_redis_data`.

Stop here for user review before moving to M2-1 (`현재 LLM 호출 경로 inventory`).
### 11.10 Troubleshooting notes from local rerun

A follow-up local rerun reproduced two common failure modes:

1. If the stack is started without the intended local compose project/env shape while `.env` contains an old external DB host, backend can report HTTP 200 with an unhealthy payload:

   ```text
   DB_HOST=your-instance.xxxx.ap-northeast-2.rds.amazonaws.com
   {"status":"unhealthy","error":"서비스 연결 실패"}
   ```

   To prevent this in local compose, `docker-compose.yml` now pins backend container network DB routing to:

   ```text
   DB_HOST=postgres
   DB_PORT=5432
   ```

   Keep using `COMPOSE_PROJECT_NAME=ddoksori` so the restored `ddoksori_postgres_data` and `ddoksori_redis_data` volumes are reused.

2. Opening `http://localhost:8000/chat/stream` directly in a browser address bar sends a `GET` request. The endpoint is intentionally a streaming `POST` endpoint, so this response is expected and does not indicate UI failure:

   ```text
   get_chat_stream_http=405
   {"detail":"Method Not Allowed"}
   ```

   The equivalent API/UI call must be `POST` with JSON and `Accept: text/event-stream`:

   ```bash
   curl -N \
     -H 'Content-Type: application/json' \
     -H 'Accept: text/event-stream' \
     -X POST http://localhost:8000/chat/stream \
     -d '{"message":"헬스장 계약 해지 환불 위약금","chat_type":"general","top_k":3}'
   ```

   Follow-up verification after the compose DB routing fix:

   ```text
   backend /health:  HTTP 200, {"status":"healthy","database":"connected"}
   frontend /health: HTTP 200, {"status":"healthy","database":"connected"}
   GET /chat/stream:  HTTP 405 Method Not Allowed (expected for address-bar GET)
   POST /chat/stream: HTTP 200, SSE status events + complete event
   Playwright M1-10 smoke: 2 passed (17.4s), chat stream complete event, no error event
   ```
