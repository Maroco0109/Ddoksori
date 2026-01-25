# Docker 팀 개발 가이드

똑소리 프로젝트의 **팀 협업을 위한 Docker 환경 가이드**입니다. 신규 팀원 온보딩부터 RDS 연동까지 다룹니다.

---

## 목차

1. [개요](#1-개요)
2. [빠른 시작](#2-빠른-시작-quick-start)
3. [환경 구성](#3-환경-구성)
4. [팀원별 설정](#4-팀원별-설정)
5. [개발 워크플로우](#5-개발-워크플로우)
6. [모니터링](#6-모니터링-prometheus--grafana)
7. [트러블슈팅](#7-트러블슈팅)
8. [부록](#8-부록)

---

## 1. 개요

### 1-1. Docker가 팀 개발에서 해결하는 문제

| 문제 | Docker 해결책 |
|------|--------------|
| "내 PC에선 되는데?" | 컨테이너로 동일한 실행 환경 보장 |
| Python/Node 버전 충돌 | 컨테이너에 버전 고정 (Python 3.11, Node 20) |
| OS별 의존성 차이 | Linux 컨테이너로 통일 |
| DB 설치/설정 번거로움 | `docker compose up` 한 줄로 해결 |
| 복잡한 서비스 연동 | Compose로 네트워크 자동 구성 |

### 1-2. 필수 공유 파일 체크리스트

Git 저장소에 포함되어야 하는 Docker 관련 파일:

```
ddoksori_demo/
├── docker-compose.yml          # [필수] 서비스 오케스트레이션
├── docker-compose.rds.yml      # [선택] RDS용 override 파일
├── backend/
│   ├── Dockerfile              # [필수] 백엔드 빌드 정의
│   ├── .env.example            # [필수] 환경변수 템플릿
│   ├── requirements.txt        # [필수] Python 의존성
│   └── database/
│       ├── init.sql            # [필수] DB 초기화 (pgvector 확장)
│       └── schema_v2_final.sql # [필수] 테이블 스키마
├── frontend/
│   ├── Dockerfile              # [필수] 프론트엔드 빌드 정의
│   └── package.json            # [필수] Node 의존성
└── backend/monitoring/
    ├── prometheus.yml          # [필수] Prometheus 설정
    └── grafana/provisioning/   # [필수] Grafana 대시보드
```

> **중요**: `.env` 파일은 `.gitignore`에 포함되어 있습니다. API 키 등 민감 정보 보호를 위해 절대 커밋하지 마세요.

### 1-3. 서비스 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                     Docker Compose Network                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐     ┌──────────┐     ┌──────────┐                │
│  │ Frontend │────▶│ Backend  │────▶│    DB    │                │
│  │  :5173   │     │  :8000   │     │  :5432   │                │
│  └──────────┘     └────┬─────┘     └──────────┘                │
│                        │                                         │
│                        ▼                                         │
│                  ┌──────────┐                                   │
│                  │  Redis   │                                   │
│                  │  :6379   │                                   │
│                  └──────────┘                                   │
│                                                                  │
│  ┌──────────────────────────────────────────────┐               │
│  │              Monitoring Stack                 │               │
│  │  Prometheus :9090  ──▶  Grafana :3000        │               │
│  └──────────────────────────────────────────────┘               │
│                                                                  │
│  ┌──────────┐     ┌──────────┐                                 │
│  │CloudBeaver│     │ BGE-M3  │ (선택적)                         │
│  │  :8978   │     │  :8003   │                                 │
│  └──────────┘     └──────────┘                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. 빠른 시작 (Quick Start)

### 2-1. 사전 요구사항

| 도구 | 최소 버전 | 설치 확인 |
|------|----------|----------|
| Docker Desktop | 4.0+ | `docker --version` |
| Docker Compose | v2.0+ | `docker compose version` |
| Git | 2.0+ | `git --version` |

**Docker Desktop 설치**: https://www.docker.com/products/docker-desktop

### 2-2. 저장소 클론 및 환경 설정

```bash
# 1. 저장소 클론
git clone https://github.com/your-org/ddoksori_demo.git
cd ddoksori_demo

# 2. 환경변수 파일 생성
cp backend/.env.example backend/.env

# 3. 필수 API 키 설정 (편집기로 .env 파일 열기)
# OPENAI_API_KEY=sk-your-key-here
# ANTHROPIC_API_KEY=sk-ant-your-key-here
```

### 2-3. 서비스 실행

```bash
# 전체 서비스 빌드 및 실행 (첫 실행 시 ~5분 소요)
docker compose up --build

# 백그라운드 실행 (터미널 점유 X)
docker compose up --build -d

# 로그 확인 (백그라운드 실행 시)
docker compose logs -f
```

### 2-4. 헬스체크 확인

| 서비스 | URL | 예상 응답 |
|--------|-----|----------|
| Frontend | http://localhost:5173 | React 웹 UI |
| Backend API | http://localhost:8000/health | `{"status": "healthy"}` |
| API 문서 | http://localhost:8000/docs | Swagger UI |
| CloudBeaver | http://localhost:8978 | DB 관리 UI |
| Prometheus | http://localhost:9090 | 메트릭 대시보드 |
| Grafana | http://localhost:3000 | 모니터링 대시보드 |

```bash
# CLI로 헬스체크
curl http://localhost:8000/health
# 예상 출력: {"status":"healthy","version":"1.0.0",...}
```

---

## 3. 환경 구성

### 3-1. 로컬 DB 모드 (기본, 개발용)

**사용 시나리오**: 개인 개발, 테스트, 오프라인 작업

기본 `docker-compose.yml`이 로컬 PostgreSQL 컨테이너를 포함합니다:

```bash
# 기본 실행 (로컬 DB 포함)
docker compose up --build
```

**장점**:
- 인터넷 없이 개발 가능
- DB 초기화/리셋이 쉬움
- 비용 없음

**`.env` 설정** (기본값 사용):
```bash
DB_HOST=db          # Docker 내부 서비스명
DB_PORT=5432
DB_NAME=ddoksori
DB_USER=postgres
DB_PASSWORD=postgres
```

### 3-2. RDS 모드 (운영/스테이징)

**사용 시나리오**: 팀 공유 DB, 스테이징 환경, 프로덕션

AWS RDS(또는 다른 외부 DB)를 사용할 때의 설정:

#### Step 1: RDS override 파일 사용

```bash
# RDS 모드로 실행 (로컬 DB 컨테이너 제외)
docker compose -f docker-compose.yml -f docker-compose.rds.yml up --build
```

#### Step 2: `.env` 파일 수정

```bash
# backend/.env
DB_HOST=your-instance.xxxx.ap-northeast-2.rds.amazonaws.com
DB_PORT=5432
DB_NAME=ddoksori
DB_USER=admin
DB_PASSWORD=your-secure-password-here
```

#### Step 3: RDS 보안 그룹 설정

RDS 보안 그룹에서 개발자 IP 허용:
- **Type**: PostgreSQL
- **Port**: 5432
- **Source**: 개발자 IP 또는 VPN CIDR

### 3-3. 하이브리드 모드 (로컬 앱 + RDS)

**사용 시나리오**: Docker 없이 로컬에서 앱 실행하면서 공유 RDS 사용

```bash
# 1. .env에 RDS 정보 설정 (3-2 Step 2 참고)

# 2. Docker 없이 백엔드 실행
conda activate dsr
cd backend
uvicorn app.main:app --reload --port 8000

# 3. 프론트엔드 실행
cd frontend
npm run dev
```

### 3-4. 환경별 비교표

| 환경 | DB 위치 | 장점 | 단점 | 명령어 |
|------|---------|------|------|--------|
| **로컬 DB** | Docker 컨테이너 | 독립적, 빠름 | 데이터 공유 X | `docker compose up` |
| **RDS** | AWS Cloud | 팀 공유, 영속성 | 비용, 네트워크 필요 | `docker compose -f ... -f docker-compose.rds.yml up` |
| **하이브리드** | AWS Cloud | 핫 리로드 빠름 | 환경 불일치 가능 | `uvicorn` 직접 실행 |

---

## 4. 팀원별 설정

### 4-1. `.env` 파일 개인 설정

각 팀원은 자신만의 `.env` 파일을 관리합니다:

```bash
# 새 팀원 온보딩 시
cp backend/.env.example backend/.env

# .env 파일 편집
vim backend/.env  # 또는 선호하는 편집기
```

**개인화 항목**:
```bash
# 개인 API 키
OPENAI_API_KEY=sk-your-personal-key
ANTHROPIC_API_KEY=sk-ant-your-personal-key

# 개발 설정 (취향에 따라)
DEBUG=True
APP_ENV=development

# LangSmith (선택적, 트레이싱용)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your-langsmith-key
LANGCHAIN_PROJECT=ddoksori-yourname
```

### 4-2. API 키 관리

#### 방법 1: 개인 키 사용 (권장)
- 각자 OpenAI/Anthropic 계정에서 API 키 발급
- 사용량 추적 및 비용 관리 용이

#### 방법 2: 팀 공유 키 사용
- 팀 Slack/Notion에서 공유 키 수령
- 월간 사용량 한도 주의

**보안 주의사항**:
- `.env` 파일은 절대 Git에 커밋하지 않음
- API 키를 Slack/Discord에 평문으로 공유하지 않음
- 정기적으로 키 로테이션 (분기별 권장)

### 4-3. 충돌 방지

`.gitignore`에 이미 포함된 항목:
```gitignore
# 환경변수 (민감 정보)
backend/.env
.env

# Docker 볼륨 데이터
postgres_data/
redis_data/
```

---

## 5. 개발 워크플로우

### 5-1. 코드 변경 시 핫 리로드

Docker Compose 설정에 bind mount가 되어 있어 **재빌드 없이** 코드 변경이 반영됩니다:

| 서비스 | 핫 리로드 | 설명 |
|--------|----------|------|
| Backend | O | `--reload` 옵션으로 자동 감지 |
| Frontend | O | Vite HMR (Hot Module Replacement) |

```bash
# 코드 수정 후 저장하면 자동 반영
# 별도 명령어 필요 없음
```

### 5-2. 패키지 추가 시 재빌드

**Python 패키지 추가**:
```bash
# 1. requirements.txt에 패키지 추가
echo "new-package==1.0.0" >> backend/requirements.txt

# 2. 백엔드 컨테이너만 재빌드
docker compose up --build backend
```

**Node 패키지 추가**:
```bash
# 1. 컨테이너 내부에서 설치
docker compose exec frontend npm install new-package

# 또는 재빌드
docker compose up --build frontend
```

### 5-3. DB 스키마 변경 시

#### 방법 1: 볼륨 초기화 (개발 환경)
```bash
# 기존 데이터 삭제 후 새 스키마로 시작
docker compose down -v
docker compose up --build
```

#### 방법 2: 마이그레이션 스크립트 실행
```bash
# 컨테이너 내부에서 SQL 실행
docker compose exec db psql -U postgres -d ddoksori -f /path/to/migration.sql
```

### 5-4. 유용한 개발 명령어

```bash
# 특정 서비스만 재시작
docker compose restart backend

# 특정 서비스 로그 확인
docker compose logs -f backend

# 컨테이너 내부 접속 (디버깅)
docker compose exec backend bash
docker compose exec db psql -U postgres -d ddoksori

# 전체 중지 (데이터 유지)
docker compose down

# 전체 중지 + 볼륨 삭제 (초기화)
docker compose down -v
```

---

## 6. 모니터링 (Prometheus + Grafana)

### 6-1. 접속 정보

| 서비스 | URL | 기본 계정 |
|--------|-----|----------|
| Prometheus | http://localhost:9090 | 없음 |
| Grafana | http://localhost:3000 | admin / admin |

### 6-2. Prometheus 메트릭

Prometheus가 수집하는 주요 메트릭:

```yaml
# backend/monitoring/prometheus.yml 에서 정의
scrape_configs:
  - job_name: 'backend'
    static_configs:
      - targets: ['backend:8000']
```

**주요 메트릭**:
- `http_requests_total`: 총 HTTP 요청 수
- `http_request_duration_seconds`: 요청 처리 시간
- `python_gc_objects_collected_total`: Python GC 통계

### 6-3. Grafana 대시보드

1. http://localhost:3000 접속
2. 초기 비밀번호 변경 (admin → 새 비밀번호)
3. 좌측 메뉴 → Dashboards → Browse
4. 사전 구성된 대시보드 확인

**대시보드 추가 방법**:
```bash
# 대시보드 JSON 파일을 아래 경로에 추가
backend/monitoring/grafana/provisioning/dashboards/
```

---

## 7. 트러블슈팅

### 7-1. 포트 충돌

```bash
# 에러: "port is already allocated"

# 사용 중인 포트 확인
lsof -i :5432   # PostgreSQL
lsof -i :8000   # Backend
lsof -i :5173   # Frontend

# 프로세스 종료
kill -9 <PID>

# 또는 Docker 컨테이너 정리
docker compose down
docker system prune -f
```

### 7-2. 볼륨/캐시 문제

```bash
# 볼륨 완전 초기화
docker compose down -v
docker volume prune -f

# 이미지 캐시 삭제 (빌드 문제 시)
docker compose build --no-cache

# 전체 정리 (주의: 다른 프로젝트 데이터도 삭제됨)
docker system prune -a --volumes
```

### 7-3. 컨테이너 로그 확인

```bash
# 전체 로그
docker compose logs

# 특정 서비스 로그 (실시간)
docker compose logs -f backend

# 최근 100줄만
docker compose logs --tail=100 backend

# 에러만 필터링
docker compose logs backend 2>&1 | grep -i error
```

### 7-4. DB 연결 문제

```bash
# DB 컨테이너 상태 확인
docker compose ps db

# DB 컨테이너 내부에서 직접 연결 테스트
docker compose exec db psql -U postgres -d ddoksori -c "SELECT 1"

# 백엔드에서 DB 연결 테스트
docker compose exec backend python -c "
from app.common.database import engine
with engine.connect() as conn:
    print('DB Connected!')
"
```

### 7-5. RDS 연결 문제

```bash
# 로컬에서 RDS 직접 연결 테스트
psql -h your-instance.xxxx.rds.amazonaws.com -U admin -d ddoksori

# 연결 안 될 경우 체크리스트:
# 1. RDS 보안 그룹에 내 IP 추가됐는지
# 2. RDS가 publicly accessible 설정인지
# 3. VPN 연결 필요한지
# 4. .env의 DB_HOST가 정확한지
```

### 7-6. 메모리 부족

```bash
# Docker 리소스 사용량 확인
docker stats

# 불필요한 컨테이너/이미지 정리
docker system prune -a

# Docker Desktop 설정에서 메모리 증가
# Settings → Resources → Memory: 8GB 이상 권장
```

---

## 8. 부록

### 8-1. docker-compose 명령어 치트시트

| 명령어 | 설명 |
|--------|------|
| `docker compose up` | 서비스 시작 |
| `docker compose up -d` | 백그라운드 시작 |
| `docker compose up --build` | 빌드 후 시작 |
| `docker compose down` | 서비스 중지 |
| `docker compose down -v` | 중지 + 볼륨 삭제 |
| `docker compose ps` | 컨테이너 상태 |
| `docker compose logs -f` | 실시간 로그 |
| `docker compose exec <svc> bash` | 컨테이너 접속 |
| `docker compose restart <svc>` | 서비스 재시작 |
| `docker compose pull` | 이미지 업데이트 |

### 8-2. 환경별 Compose 파일 분리 전략

```bash
# 기본 구성
docker-compose.yml              # 공통 서비스 정의

# 환경별 override
docker-compose.rds.yml          # RDS 사용 시 (db 서비스 제외)
docker-compose.windows.yml      # Windows 특화 설정
docker-compose.prod.yml         # 프로덕션 설정

# 사용 예시
docker compose -f docker-compose.yml -f docker-compose.rds.yml up
```

### 8-3. VS Code 개발 환경 추천 설정

`.vscode/settings.json`:
```json
{
  "python.defaultInterpreterPath": "/opt/conda/envs/dsr/bin/python",
  "docker.composeUpServiceSubset": ["backend", "frontend", "db"],
  "docker.commands.build": "docker compose build"
}
```

추천 확장:
- Docker (ms-azuretools.vscode-docker)
- Remote - Containers (ms-vscode-remote.remote-containers)

### 8-4. 자주 묻는 질문 (FAQ)

**Q: Docker Desktop 없이 사용할 수 있나요?**
A: Linux에서는 Docker Engine만으로 가능합니다. Windows/Mac에서는 Docker Desktop이 필요합니다.

**Q: M1/M2 Mac에서 동작하나요?**
A: 네, `linux/arm64` 플랫폼으로 자동 빌드됩니다. 일부 이미지는 에뮬레이션으로 느릴 수 있습니다.

**Q: 회사 VPN 환경에서 빌드가 안 돼요**
A: Docker Desktop → Settings → Resources → Proxies에서 프록시 설정을 확인하세요.

**Q: 처음 빌드가 너무 오래 걸려요**
A: 첫 빌드 시 이미지 다운로드로 5-10분 소요됩니다. 이후 캐시되어 빠릅니다.

---

## 관련 문서

- [EASY_START_GUIDE_KR.md](./EASY_START_GUIDE_KR.md) - 상세 실행 가이드 (RunPod 포함)
- [runpod_gpu_ssh_guide.md](./runpod_gpu_ssh_guide.md) - RunPod GPU 연동 가이드
- [README.md](../../README.md) - 프로젝트 전체 개요
