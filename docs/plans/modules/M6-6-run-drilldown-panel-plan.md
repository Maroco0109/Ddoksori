# M6-6 run 드릴다운 패널 (M3 DB 기반 e2e 분석 뷰) (계획서)

- 작성일: 2026-07-04
- 모듈: `M6-6` run 드릴다운 패널
- 선행: `M6-3`(Grafana + PostgreSQL datasource). 관련: M3(DB 백본 + `/observability` 조회 API), M6-4(운영 대시보드)
- 상위: §M6 라이브 모니터링 — Layer2(M3 DB 쿼리 분석)를 run 단위로 파고드는 뷰.
- 성격: **대시보드(JSON) 추가.** 앱 코드·스키마 변경 없음. 기존 M3 테이블/조회 API 재사용.

## 0. 한 줄 요약

M3 DB의 per-run 데이터를 **run 단위 e2e로 드릴다운**하는 Grafana 대시보드(Postgres datasource)를 추가한다: run 목록(필터: variant/status/기간) → `run_id` 선택 → 그 run의 **workflow_steps / retrieval_events / llm_calls / guardrail_events**를 한 화면에서 조회. 이미 있는 M3 스키마와 `/observability` API 철학을 그대로 시각화하는 것이라 신규 계측 없음.

## 1. 배경

- M3 백본이 per-run으로 `workflow_runs`(+ 자식 테이블 `workflow_steps`, `retrieval_events`, `llm_calls`, `guardrail_events`, `protocol_events`)를 적재. 조회 API `/observability/runs`, `/observability/runs/{run_id}`(run + 자식테이블 전체)가 이미 존재.
- 운영 대시보드(M6-4)는 집계(rate/p95)라 **개별 run의 원인 분석**은 못함 → run 드릴다운이 보완.

## 2. 범위

### 목표
- **드릴다운 대시보드 1개**("DDOKSORI Run Drilldown", Postgres datasource, M3 `ddoksori` DB):
  - **run 목록 패널**: `workflow_runs` 테이블 뷰 — `created_at, run_id, variant, status, total_time_ms, clarified, blocked, left(query,60)` (변수 필터: `variant`, `status`, 시간범위).
  - **`run_id` 템플릿 변수**: 목록에서 고른 run으로 하위 패널 필터.
  - **자식 패널**(선택 run 기준):
    - steps: `workflow_steps`(seq, step, duration_ms)
    - retrieval: `retrieval_events`(source, top_k, max/avg similarity, top_chunks)
    - llm: `llm_calls`(model, tokens, status)
    - guardrail: `guardrail_events`(stage, blocked, categories)
- 대시보드 JSON을 repo에 커밋.

### 비목표
- 운영 health/A/B 집계(M6-4), Prometheus 지표(M6-2), 스택(M6-3), 알림(M6-5).
- 새 조회 API/엔드포인트 추가 — Grafana Postgres datasource로 직접 SQL(기존 API는 참고). answer 원문 등 대용량 필드는 필요한 것만.

## 3. 설계 / 산출물

- `monitoring/grafana/dashboards/run_drilldown.json`: 위 패널 + `run_id`/`variant`/`status` 템플릿 변수.
- 데이터 접근: Grafana **PostgreSQL datasource**(M6-3에서 프로비저닝)로 `workflow_runs` 및 자식 테이블 직접 SQL. 자식 테이블은 `WHERE run_id = '$run_id' ORDER BY seq`.
- run_id 변수: `SELECT run_id FROM workflow_runs ORDER BY created_at DESC LIMIT 200` (또는 목록 패널 클릭 → 변수 연동, data link).

## 4. 작업 단계 (Impl)
1. Postgres datasource로 run 목록 SQL 패널 + `run_id`/`variant`/`status` 변수 구성.
2. 자식 테이블 4패널을 `$run_id` 필터로 구성.
3. JSON export → `run_drilldown.json`, provisioning 경로 등록, grafana 재기동 자동 로드.
4. 검증: 기존 goldenset run(예: `m5-5-*` session) 중 하나 선택 → 그 run의 steps/retrieval/llm/guardrail이 표시되는지 확인. variant/status 필터 동작 확인.

## 5. 완료 기준 / 검증
- [ ] run 목록 패널(필터 variant/status/기간) 렌더.
- [ ] `run_id` 선택 시 그 run의 steps/retrieval/llm/guardrail 4패널이 e2e로 표시.
- [ ] 대시보드 JSON repo 커밋(재현 가능).
- [ ] 새 앱 코드/엔드포인트/스키마 변경 없음(datasource SQL만).

## 6. caveat
- **datasource 의존**: M6-3의 PostgreSQL datasource 프로비저닝 전제. 순서상 M6-3 → M6-6.
- **top_chunks/categories는 JSONB**: Grafana 표에서 JSON 문자열로 표시(가독 위해 필요한 키만 SQL로 추출 가능).
- **대용량 필드**: `workflow_runs.answer`/retrieval text는 목록에선 생략, 상세에서 필요한 것만.
- **읽기 전용**: 조회만. 운영 read 계정 분리는 후속(운영화).

## 7. Next
M6-1~M6-4 + M6-6 완료 시 §M6(라이브 모니터링) 사실상 완성(M6-5 알림은 제외 결정). 이후 M4-A + 백엔드 버그(#67/#68) 측정된 before/after.
