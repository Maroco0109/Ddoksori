# 모니터링 사용법 — Prometheus + Grafana (M6)

DDOKSORI의 라이브 모니터링 스택(§M6) 사용 가이드. "모니터링 데이터는 있으나 시스템은 없다"던 상태를
Prometheus scrape + Grafana 대시보드로 실제 감시 가능한 시스템으로 만든 결과물이다.

> 최종 업데이트: 2026-07-10 (M6-1~M6-4 + M6-6 기준. §1·§7에 WSL stale bind-mount, Grafana v11+ `jsonData.database`, Prometheus 카운터 리셋 트러블슈팅 추가. M6-5 알림은 제외)

## 0. 두 계층 (한눈에)

| 계층 | 저장소 | 용도 | Grafana datasource |
| --- | --- | --- | --- |
| **Layer 1** | Prometheus | 라이브 운영 health (rate/p95/에러율) | `Prometheus` |
| **Layer 2** | PostgreSQL (M3 DB) | run 단위 쿼리 분석·드릴다운 | `PostgreSQL` |

- Prometheus가 backend의 `/metrics`(M6-1)를 15초마다 scrape → 시계열 축적.
- Grafana가 Prometheus(집계 대시보드)와 M3 DB(드릴다운)를 둘 다 붙여 시각화.

## 1. 스택 올리기 / 내리기

```bash
# 전체 기동 (postgres/backend/redis + prometheus/grafana)
docker compose -p ddoksori up -d

# 모니터링만
docker compose -p ddoksori up -d prometheus grafana

# 내리기 (컨테이너 제거, 볼륨/데이터는 유지)
docker compose -p ddoksori down

# 상태 확인
docker compose -p ddoksori ps
```

> `-p ddoksori` 프로젝트명을 항상 붙인다(과거 `.env`의 `COMPOSE_PROJECT_NAME` 오염 이슈로 명시 권장).

> **WSL2/Docker Desktop stale bind-mount**: Docker Desktop 재시작이나 WSL 리셋 뒤 `up -d`가
> `error mounting ... /run/desktop/mnt/host/wsl/docker-desktop-bind-mounts/... : no such file or directory`
> 로 실패할 수 있다(소스 파일은 호스트에 멀쩡히 존재). 마운트 캐시가 깨진 것이므로 해당 서비스를
> 강제 재생성한다:
> ```bash
> docker compose -p ddoksori rm -sf <svc> && docker compose -p ddoksori up -d --force-recreate <svc>
> ```
> postgres·prometheus·grafana가 각각 당할 수 있으니 실패한 서비스마다 반복한다.

## 2. 접속

| 서비스 | URL | 계정 |
| --- | --- | --- |
| Grafana | http://localhost:3000 | `admin` / `admin` (기본) |
| Prometheus | http://localhost:9090 | 없음 |
| backend `/metrics` | http://localhost:8000/metrics | 없음(scrape용) |

- Grafana 비밀번호는 `.env`의 `GF_ADMIN_PASSWORD`로 바꾼다(미설정 시 `admin`). 실사용 전 반드시 변경.
- 포트는 `.env`의 `GRAFANA_HOST_PORT`(기본 3000) / `PROMETHEUS_HOST_PORT`(기본 9090)로 조정.

## 3. Grafana 대시보드

프로비저닝으로 자동 로드된다(폴더: **DDOKSORI**). 파일: `monitoring/grafana/dashboards/*.json`.

### 3.1 DDOKSORI Ops & A/B (uid `ddoksori-ops-ab`)

운영 health + A/B 비교. 상단 `variant` 드롭다운(All/A/B)으로 필터.

| 패널 | 소스 | 읽는 법 |
| --- | --- | --- |
| Request rate by variant/status | Prometheus | 초당 `/chat` 요청 수, variant·status별 |
| p95 latency by variant | Prometheus | variant별 p95 응답시간(초). A/B 지연 비교의 핵심 |
| Error rate by variant | Prometheus | variant별 에러 비율(0~1) |
| Guardrail block rate | Prometheus | variant·stage(input/output)별 차단율 |
| LLM token rate | Prometheus | variant·type(prompt/completion)별 토큰율. **A는 코드상 토큰 미표면화라 비어있음이 정상** |
| Cache hit ratio | Prometheus | 답변 캐시 적중률 |
| A/B summary (M3 DB) | PostgreSQL | `workflow_runs` variant별 runs/avg_ms/error%/block%/clarify% 누적 |

### 3.2 DDOKSORI Run Drilldown (uid `ddoksori-run-drilldown`)

개별 run e2e 원인 분석(집계 대시보드가 못 하는 것). 순서:

1. 상단에서 `variant`/`status`/시간범위로 필터.
2. **Runs** 표에서 원하는 `run_id`를 확인.
3. 상단 `run_id` 드롭다운에서 그 run 선택.
4. 하단 4패널이 그 run의 단계별 흐름을 보여줌:
   - **Steps**(`workflow_steps`): 노드 시퀀스 + 단계 지연
   - **Retrieval**(`retrieval_events`): 섹션별 top_k·유사도
   - **LLM calls**(`llm_calls`): 컴포넌트·모델·토큰
   - **Guardrail**(`guardrail_events`): stage·decision·사유

> 팁: goldenset run은 `session_id`가 `m5-5-*` 형태다(Runs 표의 query로 식별).

## 4. 지표에 데이터 채우기

새 Prometheus는 히스토리가 없어 **트래픽이 있어야 패널이 채워진다**(빈 패널은 정상).

```bash
# variant A (OpenAI만 필요)
curl -s -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"message":"온라인 쇼핑몰 환불 기간은?","variant":"A","chat_type":"dispute"}' -o /dev/null -w "%{http_code}\n"

# variant B — VARIANT_B_MODEL_SPEC에 따라 frontier(OpenAI) 또는 exaone(RunPod pod 필요)
curl -s -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"message":"온라인 쇼핑몰 환불 기간은?","variant":"B","chat_type":"dispute"}' -o /dev/null -w "%{http_code}\n"
```

- 호출 후 ~15초(scrape 주기) 지나면 Ops 대시보드에 반영.
- **B-exaone** 패널까지 채우려면 RunPod EXAONE pod + `EXAONE_RUNPOD_URL`이 살아있어야 한다(`docs/infrastructure/runpod-vllm-setup.md`). pod 없이 A/B를 보려면 `.env`에 `VARIANT_B_MODEL_SPEC=frontier`.

## 5. Prometheus 직접 쓰기

http://localhost:9090

- **Status → Targets**: `ddoksori-backend`가 **UP**이어야 scrape 정상.
- **Graph** 탭에서 PromQL 쿼리:

```promql
# variant별 요청율
sum by (variant, status) (rate(chat_requests_total[5m]))

# variant별 p95 지연
histogram_quantile(0.95, sum by (le, variant) (rate(chat_request_latency_seconds_bucket[5m])))

# variant별 에러율
sum by (variant) (rate(chat_requests_total{status="error"}[5m]))
  / clamp_min(sum by (variant) (rate(chat_requests_total[5m])), 0.001)

# scrape 성공 여부
up{job="ddoksori-backend"}
```

### 주요 metric (M6-2 + 기존)

| metric | 라벨 | 의미 |
| --- | --- | --- |
| `chat_requests_total` | variant, status | `/chat` 요청 수 |
| `chat_request_latency_seconds` | variant | `/chat` 지연(Histogram, `_bucket`/`_count`/`_sum`) |
| `guardrail_blocks_total` | variant, stage | 가드레일 차단 수 |
| `llm_tokens_total` | variant, type | LLM 토큰(현재 B만) |
| `cache_hits_total`/`cache_misses_total` | — | 답변 캐시 |
| `agent_requests_total`/`agent_execution_seconds` | agent_name, status | 에이전트 단위(기존 S3) |

## 6. 설정 파일 위치

```
monitoring/
├── prometheus/prometheus.yml                     # scrape 설정(backend:8000/metrics)
└── grafana/
    ├── provisioning/datasources/datasources.yml  # Prometheus + PostgreSQL
    ├── provisioning/dashboards/dashboards.yml     # 파일 provider
    └── dashboards/
        ├── ops_ab.json                            # M6-4 운영/A-B
        └── run_drilldown.json                     # M6-6 run 드릴다운
```

- 대시보드를 Grafana UI에서 수정했으면 **JSON을 다시 export**해 `dashboards/`에 커밋해야 재현된다.

## 7. Troubleshooting

| 증상 | 원인/조치 |
| --- | --- |
| Targets에서 backend **DOWN** | backend 미기동 또는 `/metrics` 부재. `curl localhost:8000/metrics` 확인. 컨테이너 네트워크에선 `backend:8000`으로 접근 |
| 대시보드 패널이 **비어있음** | 트래픽 없음(정상). §4로 `/chat` 호출 후 15초 대기 |
| PostgreSQL datasource 연결 실패 | `.env`의 `DB_USER`/`DB_PASSWORD`가 볼륨 계정과 불일치. 현재 dev 볼륨 계정은 `your_db_user`. Grafana 컨테이너 env로 주입됨 |
| Postgres 패널만 **"no default database configured"** 에러(헬스체크는 OK) | Grafana `:latest`가 v11+로 드리프트해 신 `grafana-postgresql-datasource` 플러그인이 DB명을 `jsonData.database`에서 읽음. provisioning의 legacy top-level `database:`만으론 백엔드는 붙지만(헬스 OK) 프론트엔드 패널 쿼리가 터짐. `datasources.yml`의 `jsonData`에 `database: ${DB_NAME}` 추가(PR #106, v1.1.1). 확인: `curl -s -u admin:admin localhost:3000/api/datasources/uid/ddoksori-postgres`의 `jsonData.database` |
| Prometheus 패널이 backend 재시작 후 **리셋/빈 값** | `prometheus_client` 카운터는 프로세스 in-memory라 backend 재기동 시 0으로 리셋됨(정상). §4로 트래픽 재생성. 누적 분석은 Postgres 기반 "A/B summary from M3 DB" 표(재시작 무관)를 사용 |
| B/토큰 패널만 비어있음 | A는 토큰 미표면화(정상). B-exaone은 pod 필요 |
| Grafana 대시보드가 안 보임 | provider 경로/JSON 오류. `docker logs ddoksori_grafana | grep provision` 확인. UI 수정본은 export 후 커밋 |
| 이미지 버전 고정 | compose가 `:latest` 사용 중. 운영 재현성 위해 태그 pin 권장 |

## 8. 범위 밖 (후속)

- **M6-5 알림**(임계 초과 알림): 제외 결정. 필요 시 Prometheus alerting rule + Alertmanager로 추가.
- **인증/TLS/외부 노출**: 현재 dev 로컬 기준(Grafana admin/admin, Prometheus 비인증). 운영은 reverse-proxy·network policy로 제한.
- **multiprocess metrics**: 단일 uvicorn 프로세스 기준. gunicorn 다중 워커는 `prometheus_client` multiprocess 모드 필요.
- **Postgres read 전용 계정**: 현재 dev는 볼륨 superuser 사용. 운영은 read-only 계정 분리 권장.
