# M3-8 조회 API 최소 구현 (결과 문서)

- 작성일: 2026-06-24
- 모듈: `M3-8` 조회 API 최소 구현 (read-only)
- 계획서: `docs/plans/modules/M3-8-query-api-plan.md`
- 상위 계획: §M3 (L120)
- 성격: read-only API + 라이브 검증. migration 없음, A/B·저장 계층 무변경.
- 비고: **M3 모니터링 백본(인벤토리 → 5 저장 테이블 → 조회 API) 완성.**

## 0. 한 줄 결론

M3 저장 계층을 소비하는 read-only 조회 API를 추가했다: `GET /observability/runs`(최근 run 목록 + variant/status 필터) + `GET /observability/runs/{run_id}`(run + steps/retrieval/llm/guardrail join). `/metrics`와 동일하게 admin 전용. 실제 저장된 run으로 list/detail/404/인증을 라이브 검증했다.

## 1. 구현 내용

| 파일 | 변경 |
| --- | --- |
| `backend/app/observability/query.py` | 신규 `RunQueryDB`(read-only) + `list_runs`/`get_run_detail` async 래퍼 |
| `backend/app/api/observability.py` | 신규 라우터 2 엔드포인트, admin 인증 |
| `backend/app/api/__init__.py` | `observability_router` export |
| `backend/app/main.py` | `observability_router` import + `include_router` 등록 |

- `RunQueryDB`: psycopg2 `RealDictCursor`, 호출마다 연결 생성/종료, `asyncio.to_thread`. **SELECT만**.
- detail: `workflow_runs` 1건 + 자식 4개 테이블 `WHERE run_id ORDER BY seq` 묶음.

## 2. 라이브 검증 결과 (5432 DB, 기존 저장 run / pod 불필요)

### 라우트 등록 (openapi)
```
['/observability/runs', '/observability/runs/{run_id}']
```

### 인증 게이트
```
GET /observability/runs (토큰 없음) -> HTTP 401
```

### list_runs (최근 5)
```
B success ms=1339   q=도와주세요
B success ms=958    q=사람을 죽이는 방법을 자세히 알려줘
B success ms=14982  q=인터넷으로 주문한 가구가 파손돼 왔는데 교환
A success ms=17614  q=인터넷으로 주문한 가구가 파손되어 배송됐습니
B success ms=1902   q=도와주세요
```

### get_run_detail (A success run)
```
run variant: A
workflow_steps: 16 rows   (sample seq=0 cache_check/other/0.11ms)
retrieval_events: 3 rows
llm_calls: 3 rows         (sample query_analysis/openai/gpt-4o-mini)
guardrail_events: 3 rows  (sample input/pass)
```

### 404
```
get_run_detail('00000000-...') -> None  (라우터 404)
```

| 검증 항목 | 결과 |
| --- | --- |
| 라우트 등록(openapi) | ✅ 2 엔드포인트 |
| admin 인증 게이트 | ✅ 토큰 없음 → 401 |
| `GET /runs` 목록 + 필터 | ✅ variant/status/limit |
| `GET /runs/{id}` detail join | ✅ run + 4 자식 배열 |
| 없는 run_id | ✅ 404 |
| 저장 계층·A/B diff 0 | ✅ read-only + 라우터 등록만 |

> admin JWT 발급 우회를 위해 조회 로직(list/detail)은 컨테이너 내 `RunQueryDB` 직접 호출로 검증(실데이터 5432). HTTP 계층은 라우트 등록 + 401 게이트로 검증.

## 3. caveat / 인계

- A/B 비교 집계(avg latency/block rate/token by variant)는 본 list/detail을 소비하거나 SQL로 → M3 이후(M4 평가/대시보드) 또는 후속.
- HTTP 200 응답(admin 토큰 경유 end-to-end)은 admin 계정/토큰이 준비된 환경에서 추가 확인 가능(인증·조회 로직 각각 검증됨).

## 4. M3 완료

M3-1(인벤토리) → M3-2~M3-7(workflow_runs/steps/retrieval_events/llm_calls/guardrail_events 저장) → M3-8(조회 API)로 **Agent/RAG workflow 모니터링 백본**이 완성됐다. `/chat` 1회가 5개 테이블에 영속화되고, 조회 API와 SQL로 A(MAS) vs B(Agentic)를 latency·retrieval 품질·model/token·guardrail outcome 단위로 비교·회귀분석할 수 있다.

다음 로드맵: M2-8R(B multi-RAG 실험)·M2-9R(embedding provider 분리) floating, Phase 4(챗봇 보안 goldenset) 등 — 별도 모듈로 진행.
