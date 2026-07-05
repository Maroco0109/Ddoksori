# M6-3 compose에 Prometheus + Grafana 스택 (계획서)

- 작성일: 2026-07-04
- 모듈: `M6-3` 모니터링 스택 추가
- 선행: `M6-1`(/metrics scrape 대상 존재). 관련: M6-2(지표), M6-4(대시보드), M6-6(run 드릴다운)
- 상위: §M6 라이브 모니터링 — 대시보드(M6-4)·드릴다운(M6-6)이 올라갈 인프라.
- 성격: **인프라 추가.** 앱 코드 변경 없음. docker-compose에 서비스 2개 + 설정 파일.

## 0. 한 줄 요약

`docker-compose.yml`에 **Prometheus + Grafana** 서비스를 추가하고, Prometheus가 backend의 `/metrics`(M6-1)를 scrape하도록 설정한다. Grafana에는 **Prometheus + Postgres(M3 DB) 두 datasource**를 프로비저닝해, M6-4(대시보드)·M6-6(run 드릴다운)이 각각 Layer1(운영 health)·Layer2(쿼리 분석)를 그릴 토대를 만든다.

## 1. 배경

- 현재 compose 서비스: `postgres`(host 5433), `backend`(8000), `frontend`(5173), `redis`(6379). 모니터링 스택 없음.
- 두 계층(M3-1): Layer1 Prometheus(운영 health) + Layer2 M3 DB(쿼리 분석). 둘 다 Grafana에서 접근하게 datasource 2개 프로비저닝.

## 2. 범위

### 목표
- compose에 서비스 추가:
  - **prometheus** (`prom/prometheus`), host **9090**, `prometheus.yml`로 `backend:8000/metrics` scrape.
  - **grafana** (`grafana/grafana`), host **3000**, datasource/dashboard provisioning + admin 초기 계정(env).
- Grafana datasource 프로비저닝:
  - `Prometheus` → `http://prometheus:9090`
  - `PostgreSQL` → `postgres:5432` (M3 DB, read 계정) — M6-6/M6-4 A/B 분석용.
- 영속 볼륨(prometheus data, grafana data), compose 네트워크 공유.

### 비목표
- 대시보드 JSON(M6-4), run 드릴다운 패널(M6-6), 알림(M6-5).
- 지표 자체 정의·라벨(M6-2).
- 운영 보안(인증·TLS·외부 노출 정책) — dev 로컬 기준.

## 3. 설계 / 산출물 파일

- `docker-compose.yml`: `prometheus`, `grafana` 서비스 + volumes 추가. `depends_on: backend`.
- `monitoring/prometheus/prometheus.yml`:
  - `scrape_configs`: job `ddoksori-backend`, target `backend:8000`, path `/metrics`, interval 15s.
- `monitoring/grafana/provisioning/datasources/datasources.yml`:
  - Prometheus(default) + PostgreSQL(M3 `ddoksori` DB, read 계정, sslmode disable).
- `monitoring/grafana/provisioning/dashboards/dashboards.yml`: dashboard provider(파일 기반) — 실제 대시보드 JSON은 **M6-4/M6-6**에서 채움(빈 provider만 준비).
- env: Grafana admin 비번은 `.env`(`GF_SECURITY_ADMIN_PASSWORD`) 참조, 기본값 dev.

## 4. 작업 단계 (Impl)

1. `monitoring/` 디렉토리 + prometheus.yml + grafana provisioning(datasources, dashboards provider) 작성.
2. compose에 prometheus/grafana 서비스 + 볼륨 추가(host 9090/3000, 충돌 없음 확인됨).
3. `docker compose up -d prometheus grafana` → 기동.
4. 검증:
   - Prometheus `http://localhost:9090/targets` 에서 `ddoksori-backend` target = **UP**.
   - Grafana `http://localhost:3000` 로그인 → Data sources에 Prometheus·PostgreSQL 연결 OK(test).
   - Prometheus에서 `chat_requests_total`(M6-2 후) 또는 기존 `agent_requests_total` 쿼리 반환.

## 5. 완료 기준
- [ ] compose에 prometheus/grafana 서비스 기동, host 9090/3000 노출.
- [ ] Prometheus가 backend `/metrics` scrape(target UP).
- [ ] Grafana에 Prometheus + PostgreSQL datasource 프로비저닝(연결 성공).
- [ ] 앱 코드/DB 스키마 변경 없음.

## 6. caveat
- **scrape 대상 존재 전제**: M6-1의 `/metrics`가 있어야 target UP. 구현 순서상 M6-1 → M6-3.
- **backend 호스트명**: compose 네트워크 내부 `backend:8000`(host 매핑 아님). Prometheus는 컨테이너 네트워크로 접근.
- **Postgres datasource 계정**: 현 볼륨 superuser는 `your_db_user`(운영 노트). read 전용 계정 분리는 후속(운영화). dev는 기존 계정 사용.
- **Grafana 초기 대시보드 비어있음**: provider만 준비, JSON은 M6-4/M6-6에서.

## 7. Next → M6-4 / M6-6
스택이 서면 M6-4(운영 health + A/B 대시보드, Prometheus datasource)와 M6-6(run 드릴다운, PostgreSQL datasource)이 대시보드 JSON을 얹는다.
