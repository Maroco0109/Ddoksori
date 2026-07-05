# M3-8 조회 API 최소 구현 (계획서)

- 작성일: 2026-06-24
- 모듈: `M3-8` 조회 API 최소 구현 (read-only)
- 선행: `M3-3`~`M3-7` 저장 계층(`workflow_runs`/`workflow_steps`/`retrieval_events`/`llm_calls`/`guardrail_events`)
- 상위 계획: §M3 (L120)
- 성격: **read-only API.** 저장된 run을 꺼내본다. DB/스키마 변경 없음, A/B 코드 무변경. **M3 모니터링 백본 마무리.**

## 0. 한 줄 요약

M3 저장 계층을 소비하는 **read-only 조회 API**를 추가한다. `GET /observability/runs`(최근 run 목록, variant/status 필터) + `GET /observability/runs/{run_id}`(run 1건 + steps/retrieval/llm/guardrail join detail). `/metrics`와 동일하게 **admin 전용**. migration 없음.

## 1. 범위

### 목표 (완료 기준 = roadmap L120)
- 최근 run 목록 조회 + run detail(자식 테이블 join) 조회.

### 비목표
- A/B 집계·비교 엔드포인트(avg latency/block rate/token) — 후속/SQL로(범위 밖, scope creep).
- 대시보드 UI·시각화 — 범위 밖.
- 쓰기/수정/삭제 — read-only.
- 페이지네이션 고도화(커서 등) — limit/offset 최소만.

## 2. 엔드포인트 설계

### `GET /observability/runs`
- 쿼리 파라미터: `variant`(A|B, 선택), `status`(success/no_results/error, 선택), `limit`(기본 50, 최대 200), `offset`(기본 0).
- 응답: `workflow_runs` 행 목록(최신순). 각 항목 = run 요약
  `{run_id, variant, status, query, total_time_ms, clarified, blocked, started_at}`.
- 정렬: `started_at DESC`.

### `GET /observability/runs/{run_id}`
- 응답: run 1건 + 자식 배열
  ```json
  {
    "run": { ...workflow_runs row... },
    "steps": [ ...workflow_steps (seq순)... ],
    "retrieval_events": [ ...retrieval_events (seq순, top_chunks 포함)... ],
    "llm_calls": [ ...llm_calls (seq순)... ],
    "guardrail_events": [ ...guardrail_events (seq순)... ]
  }
  ```
- run_id 없으면 404.

## 3. 구현 설계

- **인증**: `/metrics` 관례 그대로 — `from app.admin.dependencies import get_current_admin`, `admin: Admin = Depends(get_current_admin)`.
- **라우터**: `backend/app/api/observability.py`, `APIRouter(prefix="/observability", tags=["Observability"])`. `main.py`에 `include_router` 등록.
- **조회 계층**: `backend/app/observability/query.py` 신규 — `RunQueryDB`(psycopg2 `RealDictCursor`, ConversationDB 패턴):
  - `list_runs(limit, offset, variant, status) -> List[dict]`
  - `get_run_detail(run_id) -> dict | None` (5개 테이블 `WHERE run_id=%s ORDER BY seq` 조회 후 묶음)
- **직렬화**: `RealDictCursor`로 dict 반환, `datetime`/`UUID`는 FastAPI JSON 인코더가 처리. `top_chunks`/`detail` JSONB는 그대로 dict/list.
- **읽기 전용**: SELECT만. 저장 경로(M3-3~7)·A/B 무변경.

## 4. 변경 대상 파일 (구현 시)

| 파일 | 변경 |
| --- | --- |
| `backend/app/observability/query.py` | 신규 `RunQueryDB`(list_runs/get_run_detail) |
| `backend/app/api/observability.py` | 신규 라우터(2 엔드포인트, admin 인증) |
| `backend/app/main.py` | `observability_router` import + `include_router` 등록 |

## 5. 완료 기준 / 검증 (구현 시)

- [ ] `GET /observability/runs` → 최근 run 목록(JSON), variant/status 필터 동작, admin 인증 요구.
- [ ] `GET /observability/runs/{run_id}` → run + steps/retrieval/llm/guardrail 묶음 반환.
- [ ] 존재하지 않는 run_id → 404.
- [ ] 비admin → 401/403.
- [ ] 저장 계층·A/B 코드 diff 0(read-only API + 라우터 등록만).
- [ ] 라이브: 실제 저장된 run으로 list/detail 응답 확인.

## 6. caveat / 인계

- A/B 비교 집계(avg latency/block rate/token by variant)는 본 API의 detail/list를 소비하거나 SQL로 수행 → **M3 이후(M4 평가/대시보드) 또는 후속**으로 분리.
- 페이지네이션은 limit/offset 최소. 대량 run 누적 시 인덱스(`started_at`)로 커버.

## 7. M3 마무리

M3-8 완료 시 **M3 모니터링 백본(인벤토리 → 5개 저장 테이블 → 조회 API)** 이 완성된다. `/chat` 1회가 runs/steps/retrieval/llm/guardrail로 영속화되고, 조회 API와 SQL로 A/B를 비교·회귀분석할 수 있는 기반이 마련된다. (다음 로드맵 단계: M2-8R/M2-9R floating, Phase 4 챗봇 보안 goldenset 등은 별도 모듈.)
