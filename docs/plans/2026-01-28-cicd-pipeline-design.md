# DDOKSORI CI/CD Pipeline Design

## Overview

DDOKSORI 프로젝트의 GitHub Actions 기반 CI/CD 파이프라인 설계 문서.

**목표**: PR/Push 시 자동 테스트 → main 머지 시 Staging 배포 → Tag 생성 시 Production 배포

**플랫폼**: GitHub Actions + AWS (EC2/ECS + ECR + RDS)

---

## Architecture

```
┌─────────────────── GitHub Actions CI/CD Pipeline ───────────────────┐
│                                                                      │
│  [PR/Push] ──→ ┌──────────┐    ┌──────────┐    ┌──────────┐         │
│                │  Lint    │ ─→ │  Test    │ ─→ │  Build   │         │
│                │ (ESLint, │    │ (pytest, │    │ (Docker  │         │
│                │  Black)  │    │  markers)│    │  images) │         │
│                └──────────┘    └──────────┘    └──────────┘         │
│                                                       │              │
│  [main merge] ──────────────────────────────────────→ ↓              │
│                                              ┌──────────────┐        │
│                                              │ Push to ECR  │        │
│                                              └──────────────┘        │
│                                                       │              │
│                                              ┌────────▼───────┐      │
│                                              │ Deploy Staging │      │
│                                              └────────────────┘      │
│                                                       │              │
│  [Tag: v*] ──────────────────────────────────────────▼              │
│                                              ┌─────────────────┐     │
│                                              │ Deploy Production│    │
│                                              └─────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Stage 1: CI 기본 (Lint & Test)

### 1.1 Lint Workflow (`.github/workflows/lint.yml`)

**트리거**: PR 생성, Push to main

**작업**:
- Backend: `black --check`, `isort --check`
- Frontend: `npm run lint` (ESLint)

```yaml
name: Lint

on:
  pull_request:
  push:
    branches: [main]

jobs:
  backend-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install black isort
      - run: black --check backend/
      - run: isort --check-only backend/

  frontend-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
        working-directory: frontend
      - run: npm run lint
        working-directory: frontend
```

### 1.2 Test Workflow (`.github/workflows/test.yml`)

**트리거**: PR 생성, Push to main

**서비스**: PostgreSQL + pgvector, Redis (3계층 캐싱용)

**테스트 전략** (리팩토링 반영):
- PR 시: `pytest -m "not skip_ci and not llm"` (빠른 피드백, LLM/skip_ci 제외)
- main 머지 시: `pytest -m "not skip_ci"` (전체 테스트, LLM 포함)

**활용 마커**: `unit`, `integration`, `skip_ci`, `llm`, `e2e`, `needs_db`

```yaml
name: Test

on:
  pull_request:
  push:
    branches: [main]

env:
  PYTHONPATH: backend

jobs:
  backend-test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg16
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
          POSTGRES_DB: ddoksori_test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
          cache-dependency-path: backend/requirements.txt

      - name: Install dependencies
        run: pip install -r backend/requirements.txt

      - name: Run tests (PR - fast)
        if: github.event_name == 'pull_request'
        run: pytest -c backend/pytest.ini -m "not skip_ci and not llm" backend/scripts/testing -v
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/ddoksori_test
          REDIS_HOST: localhost
          REDIS_PORT: 6379
          ENABLE_ANSWER_CACHE: false

      - name: Run tests (main - full)
        if: github.ref == 'refs/heads/main'
        run: pytest -c backend/pytest.ini -m "not skip_ci" backend/scripts/testing -v
        env:
          DATABASE_URL: postgresql://postgres:postgres@localhost:5432/ddoksori_test
          REDIS_HOST: localhost
          REDIS_PORT: 6379
          ENABLE_ANSWER_CACHE: true
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}

  frontend-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
        working-directory: frontend
      - run: npm run build
        working-directory: frontend
```

### 1.3 Dockerfile 프로덕션화

**현재 문제**:
- `backend/Dockerfile`: `--reload` 플래그 사용 (개발 모드)
- `frontend/Dockerfile`: `npm run dev` 실행 (개발 서버)

**수정 필요 파일**:

#### `backend/Dockerfile.prod` (신규 생성)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster pip (현재 Dockerfile과 동일한 방식)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy requirements first for layer caching
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy application
COPY app/ ./app/

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production server (gunicorn + uvicorn workers)
EXPOSE 8000
CMD ["gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000"]
```

#### `frontend/Dockerfile.prod` (신규 생성)

```dockerfile
# Build stage
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

#### `frontend/nginx.conf` (신규 생성)

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Stage 2: Docker 이미지 빌드 & ECR 푸시

### 2.1 Build Workflow (`.github/workflows/build.yml`)

**트리거**: Push to main, Tag 생성

**작업**:
- Backend/Frontend Docker 이미지 빌드
- AWS ECR에 이미지 푸시
- 태그: `latest`, `sha-{commit}`, `v{version}` (태그 시)

```yaml
name: Build and Push

on:
  push:
    branches: [main]
    tags: ['v*']

env:
  AWS_REGION: ap-northeast-2
  ECR_BACKEND: ddoksori-backend
  ECR_FRONTEND: ddoksori-frontend

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Login to Amazon ECR
        id: login-ecr
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push backend
        uses: docker/build-push-action@v5
        with:
          context: ./backend
          file: ./backend/Dockerfile.prod
          push: true
          tags: |
            ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_BACKEND }}:latest
            ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_BACKEND }}:sha-${{ github.sha }}

      - name: Build and push frontend
        uses: docker/build-push-action@v5
        with:
          context: ./frontend
          file: ./frontend/Dockerfile.prod
          push: true
          tags: |
            ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_FRONTEND }}:latest
            ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_FRONTEND }}:sha-${{ github.sha }}
```

### 2.2 AWS ECR 설정 (사전 작업)

```bash
# ECR 리포지토리 생성
aws ecr create-repository --repository-name ddoksori-backend
aws ecr create-repository --repository-name ddoksori-frontend

# OIDC Provider 설정 (GitHub Actions용)
# GitHub Actions에서 AWS 인증을 위한 IAM Role 생성 필요
```

---

## Stage 3: Staging 배포

### 3.1 Deploy Staging Workflow (`.github/workflows/deploy-staging.yml`)

**트리거**: main 브랜치에 Push 시 (테스트/빌드 성공 후)

```yaml
name: Deploy to Staging

on:
  workflow_run:
    workflows: ["Build and Push"]
    types: [completed]
    branches: [main]

env:
  AWS_REGION: ap-northeast-2
  EC2_HOST: staging.ddoksori.com

jobs:
  deploy:
    runs-on: ubuntu-latest
    if: ${{ github.event.workflow_run.conclusion == 'success' }}

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Deploy to Staging
        uses: appleboy/ssh-action@v1.0.0
        with:
          host: ${{ env.EC2_HOST }}
          username: ec2-user
          key: ${{ secrets.EC2_SSH_KEY }}
          script: |
            cd /home/ec2-user/ddoksori
            aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin ${{ secrets.ECR_REGISTRY }}
            docker compose -f docker-compose.prod.yml pull
            docker compose -f docker-compose.prod.yml up -d
            docker compose -f docker-compose.prod.yml ps

      - name: Health Check
        run: |
          sleep 30
          curl -f http://${{ env.EC2_HOST }}:8000/health || exit 1

      - name: Discord Notification
        uses: sarisia/actions-status-discord@v1
        if: always()
        with:
          webhook: ${{ secrets.DISCORD_WEBHOOK }}
          title: "Staging Deployment"
          description: |
            **Status**: ${{ job.status }}
            **Commit**: ${{ github.sha }}
            **Branch**: main
```

### 3.2 Production Compose File (`docker-compose.prod.yml`)

```yaml
version: '3.8'

services:
  backend:
    image: ${ECR_REGISTRY}/ddoksori-backend:latest
    restart: always
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    image: ${ECR_REGISTRY}/ddoksori-frontend:latest
    restart: always
    ports:
      - "80:80"
    depends_on:
      - backend

  redis:
    image: redis:7-alpine
    restart: always
    volumes:
      - redis-data:/data

volumes:
  redis-data:
```

---

## Stage 4: Production 배포

### 4.1 Deploy Production Workflow (`.github/workflows/deploy-production.yml`)

**트리거**: `v*` 태그 생성 시

```yaml
name: Deploy to Production

on:
  push:
    tags: ['v*']

env:
  AWS_REGION: ap-northeast-2
  EC2_HOST: ddoksori.com

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production  # 수동 승인 필요 (GitHub 설정)

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Get version from tag
        id: version
        run: echo "VERSION=${GITHUB_REF#refs/tags/}" >> $GITHUB_OUTPUT

      - name: Deploy to Production
        uses: appleboy/ssh-action@v1.0.0
        with:
          host: ${{ env.EC2_HOST }}
          username: ec2-user
          key: ${{ secrets.EC2_SSH_KEY }}
          script: |
            cd /home/ec2-user/ddoksori

            # Backup current deployment
            docker compose -f docker-compose.prod.yml config > backup-$(date +%Y%m%d-%H%M%S).yml

            # Pull and deploy new version
            aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin ${{ secrets.ECR_REGISTRY }}
            export IMAGE_TAG=${{ steps.version.outputs.VERSION }}
            docker compose -f docker-compose.prod.yml pull
            docker compose -f docker-compose.prod.yml up -d
            docker compose -f docker-compose.prod.yml ps

      - name: Health Check
        run: |
          sleep 30
          curl -f http://${{ env.EC2_HOST }}:8000/health || exit 1

      - name: Discord Notification
        uses: sarisia/actions-status-discord@v1
        if: always()
        with:
          webhook: ${{ secrets.DISCORD_WEBHOOK }}
          title: "Production Deployment"
          description: |
            **Status**: ${{ job.status }}
            **Version**: ${{ steps.version.outputs.VERSION }}
```

### 4.2 Rollback 절차

Production 배포 실패 시 롤백:

```bash
# EC2에서 수동 롤백
cd /home/ec2-user/ddoksori

# 이전 이미지로 롤백
export IMAGE_TAG=v1.0.0  # 이전 버전
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d

# 또는 백업된 설정 사용
docker compose -f backup-YYYYMMDD-HHMMSS.yml up -d
```

---

## GitHub Secrets 설정

GitHub Repository → Settings → Secrets and variables → Actions

| Secret Name | Description |
|-------------|-------------|
| `AWS_ROLE_ARN` | AWS OIDC Role ARN (ECR 접근용) |
| `ECR_REGISTRY` | ECR 레지스트리 URL (예: 123456789.dkr.ecr.ap-northeast-2.amazonaws.com) |
| `EC2_SSH_KEY` | EC2 SSH 개인키 |
| `OPENAI_API_KEY` | OpenAI API 키 (테스트용) |
| `DISCORD_WEBHOOK` | Discord 웹훅 URL |

---

## 수정/생성 파일 목록

### 신규 생성

| 파일 | 설명 |
|------|------|
| `.github/workflows/lint.yml` | Lint 워크플로우 |
| `.github/workflows/test.yml` | 테스트 워크플로우 |
| `.github/workflows/build.yml` | 이미지 빌드 워크플로우 |
| `.github/workflows/deploy-staging.yml` | Staging 배포 워크플로우 |
| `.github/workflows/deploy-production.yml` | Production 배포 워크플로우 |
| `backend/Dockerfile.prod` | 프로덕션용 Backend Dockerfile |
| `frontend/Dockerfile.prod` | 프로덕션용 Frontend Dockerfile |
| `frontend/nginx.conf` | Nginx 설정 |
| `docker-compose.prod.yml` | 프로덕션 Compose 파일 |

### 수정 필요

| 파일 | 수정 내용 |
|------|-----------|
| `backend/requirements.txt` | `gunicorn` 추가 |

---

## 구현 우선순위 (권장)

배포 경험이 처음이시므로, 각 Stage를 순차적으로 구현하고 검증하는 것을 권장합니다:

1. **Stage 1**: CI 기본 (Lint + Test) - 가장 먼저 구현, PR마다 자동 검증
2. **Stage 2**: Docker 빌드 - ECR 설정 후 이미지 빌드 자동화
3. **Stage 3**: Staging 배포 - AWS 인프라 준비 후 자동 배포
4. **Stage 4**: Production 배포 - Staging 안정화 후 Production 자동화

각 Stage 완료 후 최소 며칠간 운영하여 안정성을 확인하세요.

---

## 비용 참고 (AWS)

아카이브된 비용 분석 (`docs/_archive/plans/deploy/02_cost_analysis.md`) 기준:
- EC2 t3.small: ~$15/월
- RDS db.t3.micro: ~$15/월
- ECR: ~$1/월 (스토리지)
- **예상 총 비용**: $25-60/월

---

## 참고 문서

- 아카이브된 배포 가이드: `docs/_archive/plans/deploy/`
- 현재 Docker 설정: `docker-compose.yml`
- 테스트 설정: `backend/pytest.ini`
- 환경변수 템플릿: `backend/.env.example`

---

## 리팩토링 반영 사항 (2026-01-28 업데이트)

Backend 리팩토링 Phase 4 완료 후 CI/CD 계획에 반영된 변경사항:

### 변경된 항목

| 항목 | 기존 | 변경 후 | 이유 |
|------|------|---------|------|
| **테스트 서비스** | PostgreSQL만 | PostgreSQL + Redis | 3계층 캐싱 테스트 지원 |
| **테스트 마커** | `unit or integration` | `not skip_ci and not llm` | 14개 마커 체계 활용 |
| **uv 설치** | `pip install uv` | `COPY --from=ghcr.io` | 현재 Dockerfile과 동일 |
| **환경변수** | 기본 | Redis 설정 추가 | 캐시 테스트용 |

### 리팩토링으로 추가된 모듈 (CI/CD 영향 없음)

- `backend/app/common/cache/` - BaseRedisCache
- `backend/app/llm/providers/` - LLM Provider Factory
- `backend/app/common/embedding/` - Embedding Provider 패턴
- `backend/app/common/config.py` - 통합 설정 (2,500+ LOC)

### 테스트 마커 참고

```bash
# CI에서 사용할 마커 조합
pytest -m "not skip_ci"           # skip_ci 제외한 모든 테스트
pytest -m "not skip_ci and not llm"  # LLM API 호출 제외 (빠른 테스트)
pytest -m "unit"                  # 유닛 테스트만
pytest -m "integration"           # DB 필요 테스트
pytest -m "e2e"                   # E2E 테스트

# v2 아키텍처 테스트 (MAS v2 그래프 전용)
pytest backend/scripts/testing/test_mas_v2_architecture.py -v
```

---

## MAS v2 아키텍처 반영 사항 (2026-01-29 업데이트)

MAS v2 아키텍처 개편 후 CI/CD 계획에 반영된 변경사항:
(상세 설계: `docs/plans/2026-01-28-mas-architecture-v2-design.md`)

### 변경된 항목

| 항목 | 기존 (v1) | 변경 후 (v2) | 이유 |
|------|----------|-------------|------|
| **Retrieval Agent 수** | 4개 (law, criteria, case, counsel) | 3개 (law, criteria, case) | counsel → case에 통합 |
| **QueryAnalyst 모델** | 규칙 기반 | gpt-4o-mini (LLM 기반) | 쿼리 확장 품질 향상 |
| **Supervisor 모델** | gpt-4o | gpt-4o-mini | 비용 최적화 |
| **Agent Registry** | 없음 | 동적 에이전트 등록 | 확장성 향상 |
| **재생성 루프** | 없음 | LegalReviewer → AnswerDrafter (max 1회) | 품질 보증 |
| **프로토콜** | protocols.py (v1) | protocols.py (v2 통합) | 메타데이터 필터, CitedCase 등 |

### v2로 추가된 모듈 (CI/CD 영향 없음)

- `backend/app/agents/query_analysis/llm_expander.py` - LLM 기반 쿼리 확장
- `backend/app/agents/registry/agent_registry.py` - Agent Registry (동적 에이전트 등록)
- `backend/app/supervisor/nodes/` - Supervisor 노드 분리 (supervisor.py, retrieval_merge.py, clarify.py)
- `backend/scripts/testing/test_mas_v2_architecture.py` - v2 통합 테스트

### v2로 삭제된 파일

- `backend/app/agents/retrieval/counsel_agent.py` - case_agent에 통합 (상담사례 검색을 CaseRetrievalAgent가 처리)
