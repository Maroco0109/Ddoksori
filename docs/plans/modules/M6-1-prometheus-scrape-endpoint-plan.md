# M6-1 Prometheus scrape 엔드포인트 (계획서)

- 작성일: 2026-07-04
- 모듈: `M6-1` Prometheus 노출 엔드포인트 (M3-1 갭 해소)
- 선행: 없음(독립). 관련: M3-1(Prometheus metric 정의만 하고 노출 보류), M6 전체(라이브 모니터링)
- 상위: §M6 라이브 서비스 모니터링 — 첫 모듈. M6-2(지표 정리)·M6-3(compose Prometheus)·M6-4(Grafana)의 전제.
- 성격: **노출 전용.** 새 계측·라벨 없음, DB/스키마 변경 없음. 기존 metric을 scrape 포맷으로 내보내는 라우트 1개.

## 0. 한 줄 요약

이미 default registry에 등록된 Prometheus metric(`common/metrics.py` + `legal_review/metrics.py`)을 `generate_latest`로 내보내는 **`GET /metrics` scrape 엔드포인트**를 추가한다. 이것만으로 "모니터링 데이터는 있으나 시스템은 없다"의 첫 갭(M3-1)이 닫히고, M6-3의 Prometheus가 backend를 scrape할 대상이 생긴다.

## 1. 배경 (M3-1 갭)

- Prometheus metric은 **정의·등록만** 돼 있고 scrape 엔드포인트가 없다(M3-1에서 "노출은 M3 범위 밖"으로 보류).
- 확인된 기존 metric (default global `REGISTRY`에 eager 등록):
  - `common/metrics.py`: `agent_execution_seconds`(Histogram), `agent_requests_total`, `llm_tokens_total`, `agent_tool_usage_total`, `cache_hits/misses/errors_total`, `llm_cost_usd_total`, `embedding_cost_usd_total`.
  - `legal_review/metrics.py`(지연 초기화): `legal_review_violations_total`, `..._hallucination_detected_total`, `..._legal_judgment_detected_total`, `..._confidence_score`, `..._llm_calls_total`, `..._processing_seconds`, `..._reviews_total`, `..._relevance_score`.
- `prometheus_client`는 이미 하드 의존성(`common/metrics.py` 최상단 import). 기존 `/metrics/*` 라우터는 **커스텀 JSON(admin 전용 DB 조회)** 이라 Prometheus 포맷과 무관.

## 2. 범위

### 목표
- **`GET /metrics`** 라우트 추가: `generate_latest(REGISTRY)`를 `CONTENT_TYPE_LATEST`(`text/plain; version=0.0.4`) 로 반환.
- 응답 본문에 기존 metric family 이름이 노출되어 Prometheus가 scrape 가능함을 확인.

### 비목표
- **새 계측·라벨 추가**(예: `variant` 라벨, p95 정리) = **M6-2**.
- Prometheus/Grafana docker service = **M6-3**, 대시보드 = **M6-4**, 알림 = **M6-5**, run 드릴다운 = **M6-6**.
- 인증·mTLS·multiprocess(gunicorn) registry 병합 = 범위 밖(§6 caveat).
- 계측 커버리지 개선(metric이 실제로 증가하도록 instrument하는 것) — 노출만 하고, 실제 증분 여부 점검은 M6-2.

## 3. 설계

- **경로**: bare `GET /metrics` (Prometheus 관례). 기존 `/metrics/agents` 등은 `prefix="/metrics"` 라우터의 하위 경로라 **exact-match `/metrics`와 충돌하지 않음**(FastAPI가 정확 경로 우선 매칭). 따라서 `/metrics` 프리픽스 라우터에 얹지 말고 **별도 라우트**(no-prefix)로 추가한다.
  - 산출물: `backend/app/api/prometheus.py`(작은 라우터, `@router.get("/metrics")`) → `main.py`에 include. 또는 `main.py`에 직접 `@app.get("/metrics")`. **전자(별도 모듈)** 권장(관심사 분리).
- **레지스트리**: default global `prometheus_client.REGISTRY`. 기존 metric이 모듈 로드시 등록되므로 그대로 노출.
- **인증**: scrape 엔드포인트는 **비인증**(Prometheus 서버가 내부 네트워크에서 scrape). 기존 `/metrics/*` JSON의 admin-only와 분리. 노출 정보는 운영 지표(요청수/지연/토큰/비용)로 PII 없음.
- **응답**: `fastapi.Response(content=generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)`.

## 4. 작업 단계 (Impl)

1. `backend/app/api/prometheus.py` 생성: `generate_latest`/`CONTENT_TYPE_LATEST` import, `GET /metrics` 라우트 반환.
2. `main.py`(및 `api/__init__.py` 필요시)에 라우터 include.
3. 기존 `/metrics/*`(admin JSON) 라우터와 공존 확인(경로 충돌 없음).
4. 검증: 서버 기동 → `curl -s localhost:8000/metrics` → 200 + `text/plain; version=0.0.4` + 본문에 `agent_requests_total`, `llm_tokens_total` 등 family 존재. `/chat` 1회 호출 후 해당 카운터 증가 노출 확인(선택).

## 5. 산출물 (Impl PR 예정)

- `backend/app/api/prometheus.py` (신규 라우트)
- `backend/app/main.py` (+ `api/__init__.py`) 라우터 등록
- (선택) `docs/plans/modules/M6-1-...-results.md` 또는 결과는 PR 본문에 curl 증빙

## 6. 완료 기준 / 검증

- [ ] `GET /metrics`가 200 반환, `Content-Type: text/plain; version=0.0.4`.
- [ ] 본문에 기존 metric family(예: `agent_requests_total`, `llm_tokens_total`, `agent_execution_seconds`) 노출.
- [ ] 기존 `/metrics/agents`(admin JSON)와 공존(경로 충돌 없음).
- [ ] 새 계측·라벨·DB/스키마 변경 없음.
- 검증 방법: `curl` 헤더·본문 확인 + `/chat` 후 카운터 증분 스팟체크.

## 7. caveat

- **multiprocess**: 현재 dev는 uvicorn 단일 프로세스라 default registry로 충분. 운영에서 gunicorn 다중 워커 시 `prometheus_client` multiprocess 모드(`PROMETHEUS_MULTIPROC_DIR`)가 필요 — 범위 밖, M6-3/운영화 시 재검토.
- **legal_review metric 지연 초기화**: 해당 metric은 첫 사용 시 등록되므로, 아직 호출 전이면 `/metrics`에 안 보일 수 있음(정상). 노출 자체는 문제 없음.
- **비인증 노출**: 내부 네트워크 scrape 전제. 외부 노출 시 network policy/reverse-proxy로 제한(운영 과제).

## 8. Next → M6-2

- M6-2: p95 지연/에러율/토큰율/guardrail 차단율 등 **핵심 지표 정리 + A/B `variant` 라벨** 추가(실제 증분 instrument 포함). M6-1이 노출 통로를 열었으니 M6-2는 "무엇을 어떤 라벨로" 채우는 단계.
