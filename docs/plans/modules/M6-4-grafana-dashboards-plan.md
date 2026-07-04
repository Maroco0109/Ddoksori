# M6-4 Grafana 대시보드 (운영 health + A/B 비교) (계획서)

- 작성일: 2026-07-04
- 모듈: `M6-4` Grafana 대시보드
- 선행: `M6-2`(핵심 지표 + variant 라벨), `M6-3`(Grafana + datasource). 관련: M6-6(run 드릴다운 별도 대시보드)
- 상위: §M6 라이브 모니터링 — "감시 가능한 시스템"의 시각화 층.
- 성격: **대시보드 정의(JSON) 추가.** 앱 코드 변경 없음. 프로비저닝 파일 기반.

## 0. 한 줄 요약

M6-2 지표(Prometheus)와 M3 DB(Postgres)를 **프로비저닝된 Grafana 대시보드**로 시각화한다: (A) 운영 health 패널(p95 지연·에러율·guardrail 차단율·토큰율·cache) + (B) **A/B 비교 패널**(variant별 분리). 대시보드 JSON을 repo에 커밋해 재현·버전관리한다.

## 1. 범위

### 목표
- **대시보드 1개**("DDOKSORI Ops & A/B"), 파일 프로비저닝(M6-3의 dashboards provider가 로드):
  - **운영 health(Prometheus)**:
    - p95 지연: `histogram_quantile(0.95, rate(chat_request_latency_seconds_bucket[5m]))`
    - 에러율: `rate(chat_requests_total{status="error"}[5m]) / rate(chat_requests_total[5m])`
    - guardrail 차단율: `rate(guardrail_blocks_total[5m])` (stage별)
    - 토큰율: `rate(llm_tokens_total[5m])` (type별)
    - cache hit율: `rate(cache_hits_total[5m]) / (rate(cache_hits_total[5m])+rate(cache_misses_total[5m]))`
  - **A/B 비교(variant로 분리)**: 위 지표들을 `by (variant)`로 나눈 패널(요청수/p95/에러율/차단율/토큰). Prometheus 라벨 기반.
  - **(보강) M3 DB 기반 A/B 요약(Postgres datasource)**: `workflow_runs`에서 variant별 평균 지연·에러율·건수 SQL 패널(라이브 rate로 안 잡히는 누적/정합 비교).
- 대시보드 JSON + provider 설정을 repo에 커밋.

### 비목표
- 지표 자체 정의·계측(M6-2), 스택 구성(M6-3), 알림(M6-5), **run 단위 e2e 드릴다운(M6-6)** — 별도 대시보드.
- 품질 지표(M5 faithfulness/coverage 등)는 오프라인 평가라 본 라이브 대시보드 범위 밖(원하면 후속 정적 패널).

## 2. 설계 / 산출물

- `monitoring/grafana/dashboards/ops_ab.json`: 위 패널 정의(Prometheus + Postgres 혼합 datasource).
- (필요 시) `monitoring/grafana/provisioning/dashboards/dashboards.yml`에 경로 등록(M6-3에서 provider 생성했다면 파일만 추가).
- 대시보드 변수: `variant`(All/A/B) 템플릿 변수로 필터.

## 3. 작업 단계 (Impl)
1. Grafana UI에서 패널 구성 후 JSON export → `ops_ab.json`으로 저장(또는 직접 JSON 작성).
2. provisioning에 대시보드 경로 연결, `docker compose up -d grafana` 재기동으로 자동 로드.
3. 검증: A·B `/chat` 트래픽 발생 후 Grafana에서 p95/에러율/차단율/토큰/cache 패널이 값 표시, variant 분리 패널이 A/B 각각 렌더.

## 4. 완료 기준 / 검증
- [ ] 프로비저닝된 대시보드가 Grafana에 자동 로드.
- [ ] 운영 health 패널(p95·에러율·차단율·토큰율·cache) 렌더.
- [ ] A/B 비교 패널이 `variant`별로 분리 표시.
- [ ] 대시보드 JSON이 repo에 커밋(재현 가능).
- [ ] 앱 코드/스키마 변경 없음.

## 5. caveat
- **M6-2 라벨 의존**: variant 분리 패널은 M6-2의 variant 라벨 전제. 순서상 M6-2 → M6-4.
- **데이터 유무**: 새 Prometheus는 히스토리 없음 → 검증 시 트래픽을 만들어야 패널이 채워짐(빈 패널은 정상).
- **혼합 datasource**: 한 대시보드에서 Prometheus·Postgres 패널 공존 — datasource UID를 프로비저닝 값과 일치.
- p95 histogram은 M6-2가 Histogram으로 정의해야 `_bucket` 존재.

## 6. Next → M6-6
run 단위 e2e 드릴다운은 별 대시보드(Postgres datasource, M3 테이블)로 M6-6에서 추가.
