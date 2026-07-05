# M6-2 핵심 지표 정리 + A/B variant 라벨 (계획서)

- 작성일: 2026-07-04
- 모듈: `M6-2` 핵심 지표 정리·라벨
- 선행: `M6-1`(/metrics scrape 엔드포인트). 관련: M3(DB 백본, per-run variant/tokens/guardrail 이미 적재)
- 상위: §M6 라이브 모니터링 — M6-4 대시보드가 소비할 지표를 정의.
- 성격: **경량 계측.** 새 프레임워크 없음. 기존 metric 정리 + A/B `variant` 라벨을 choke point에 추가.

## 0. 한 줄 요약

대시보드가 쓸 **핵심 운영 지표**(p95 지연 / 에러율 / 토큰율 / guardrail 차단율)를 확정하고, **A/B 비교가 가능하도록 `variant` 라벨**을 소수의 choke point(주로 `/chat` 경로)에 추가한다. 무거운 전면 계측은 지양하고, 토큰/가드레일의 풍부한 A/B 분석은 이미 적재 중인 **M3 DB**(Grafana Postgres datasource, M6-4)에 맡긴다.

## 1. 배경 (현재 계측 상태)

- 실제 증분되는 Prometheus metric: `agent_execution_seconds`/`agent_requests_total`(라벨 `agent_name`,`status`; `common/metrics.py`), `cache_hits/misses/errors_total`(`answer_generation/cache.py`).
- **정의만 되고 미증분**: `llm_tokens_total`, `agent_tool_usage_total`, `llm_cost_usd_total`, `embedding_cost_usd_total`.
- **`variant` 라벨이 전무** → 현재 Prometheus만으론 A/B 비교 불가.
- 반면 **M3 DB에는 per-run `variant`, `total_time_ms`, `status`, `llm_calls`(토큰), `guardrail_events`(차단)** 이 이미 적재됨 → A/B 분석의 1차 소스는 DB.

## 2. 범위

### 목표
- **핵심 지표 확정**(대시보드 계약):
  1. **요청/에러율**: `chat_requests_total{variant,status}` (요청 수 + status로 에러율 파생)
  2. **p95 지연**: `chat_request_latency_seconds{variant}` (Histogram → Grafana `histogram_quantile`)
  3. **guardrail 차단율**: `guardrail_blocks_total{variant,stage}` (stage=input/output)
  4. **토큰율**: `llm_tokens_total{variant,type}` (기존 정의 metric에 variant 추가·증분) — 단순 rate용
- 위 지표를 `/chat` 및 가드레일/LLM 집계 choke point에서 **variant 라벨과 함께 증분**.
- `/metrics`(M6-1)에 variant-라벨 시계열이 노출되어 A/B 분리가 가능함을 확인.

### 비목표
- 전 metric의 전면 라벨링·instrument(과계측). 정의만 된 `tool_usage`/`cost`는 이번에 강제 증분하지 않음(필요 시 후속).
- 대시보드/알림(M6-4/5), Prometheus/Grafana 스택(M6-3).
- **토큰/비용/가드레일의 상세 A/B 분석**은 M3 DB(Postgres datasource)에서 — Prometheus는 라이브 rate·health만.

## 3. 설계 (choke point 최소화)

- **`/chat` 핸들러**(variant를 아는 유일·단일 지점): 요청 시작/종료를 감싸 `chat_requests_total{variant,status}` inc + `chat_request_latency_seconds{variant}` observe. A/B 공통 경로라 한 곳에서 커버.
- **guardrail 차단**: 기존 guardrail 결과(blocked)가 집계되는 지점(예: variant_b `check_input/check_output`, A의 output_guardrail 노드)에서 `guardrail_blocks_total{variant,stage}` inc. 이미 M3 `guardrail_events` 적재 지점과 동일 위치 재사용.
- **토큰**: M3 `llm_calls` 집계(변형별 토큰 합)가 저장되는 지점에서 `llm_tokens_total{variant,type}` inc. (per-call model 라벨은 카디널리티 우려로 생략 가능 — type=prompt/completion만.)
- **원칙**: 계측은 "이미 A/B와 값을 아는 단일 저장/집계 지점"에만 얹어 중복·카디널리티를 억제.

## 4. 작업 단계 (Impl)

1. `common/metrics.py`에 신규 metric 정의: `chat_requests_total{variant,status}`, `chat_request_latency_seconds{variant}`, `guardrail_blocks_total{variant,stage}` + `llm_tokens_total`에 `variant` 라벨 반영(정의 갱신).
2. `/chat`(api/chat.py) A/B 양 경로에 requests/latency 계측 추가(단일 감쌈).
3. guardrail/토큰 집계 지점에 variant 라벨 inc 추가(M3 적재 지점과 동일 위치).
4. 검증: A·B `/chat` 각 1회 → `/metrics`에서 `chat_requests_total{variant="A"...}` / `{variant="B"...}`, latency bucket, guardrail/token 시계열 확인.

## 5. 산출물 (Impl PR)
- `backend/app/common/metrics.py` (metric 정의 + variant)
- `backend/app/api/chat.py` (requests/latency 계측)
- guardrail/token 집계 지점 파일 (variant inc)
- 결과 증빙은 PR 본문 `/metrics` 발췌.

## 6. 완료 기준 / 검증
- [ ] `/metrics`에 `variant` 라벨 붙은 핵심 지표(requests/latency/guardrail_blocks/llm_tokens) 노출.
- [ ] A·B 호출 후 variant별 시계열이 분리되어 증가.
- [ ] 카디널리티 통제(변수 라벨은 variant/status/stage/type 등 저카디널리티만).
- [ ] DB/스키마 변경 없음, 토큰/가드레일 M3 적재 로직 불변(계측만 추가).

## 7. caveat
- **카디널리티**: model/agent_name × variant는 폭발 위험 → variant는 요청 레벨 지표에만. 상세 model별은 M3 DB로.
- **A/B 중복**: 같은 값이 Prometheus(라이브)와 M3 DB(분석)에 이중 존재 — 의도된 2계층(M3-1). 대시보드에서 용도 분리(M6-4).
- 정의만 된 `tool_usage`/`cost`는 이번 비증분(후속에서 필요 시).

## 8. Next → M6-4
M6-4 대시보드가 본 모듈의 지표(p95·에러율·차단율·토큰율 + variant)를 패널로 시각화. M6-3(스택)과 병행 전제.
