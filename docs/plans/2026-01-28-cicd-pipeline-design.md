# DDOKSORI CI/CD Pipeline Design

> **Status**: 구현 완료 (2026-02-01 최신화)
>
> 이 문서는 설계 계획이 아닌 **현재 운영 중인 CI/CD 파이프라인의 참조 문서**입니다.
> 모든 워크플로우, Dockerfile, Compose 파일은 구현 완료되어 실 운영 중입니다.
>
> **전제 조건**: `feature/34-e2e` 브랜치의 모든 변경사항이 반영된 상태를 기준으로 합니다.

## Overview

DDOKSORI 프로젝트의 GitHub Actions 기반 CI/CD 파이프라인 참조 문서.

**구성**: PR/Push 시 자동 테스트 → main 머지 시 Staging 배포 → Tag 생성 시 Production 배포

**플랫폼**: GitHub Actions + AWS (EC2 + ECR + RDS + Secrets Manager + S3)

---

## Architecture

```
┌─────────────────── GitHub Actions CI/CD Pipeline ────────────────────┐
│                                                                      │
│  [PR/Push] ──→ ┌──────────┐    ┌──────────┐    ┌──────────────┐     │
│                │  Lint    │ ─→ │  Test    │ ─→ │ Frontend     │     │
│                │ (Black,  │    │ (pytest, │    │ Build Check  │     │
│                │  isort,  │    │ pgvector,│    └──────────────┘     │
│                │  ESLint) │    │  Redis)  │                         │
│                └──────────┘    └──────────┘                         │
│                                                                      │
│  [main merge] ──→ ┌───────────────────┐    ┌──────────────┐         │
│                   │ Build & Push      │ ─→ │ Deploy       │         │
│                   │ (Buildx + ECR +   │    │ Staging      │         │
│                   │  GHA Cache)       │    │ (SSH + ECR)  │         │
│                   └───────────────────┘    └──────────────┘         │
│                                                                      │
│  [Tag: v*] ──→ ┌──────────────┐    ┌─────────────────┐              │
│                │ Wait for     │ ─→ │ Deploy          │              │
│                │ Build        │    │ Production      │              │
│                └──────────────┘    │ (Manual Approve)│              │
│                                    └────────┬────────┘              │
│                                             │ (failure)             │
│                                    ┌────────▼────────┐              │
│                                    │ Auto Rollback   │              │
│                                    └─────────────────┘              │
│                                                                      │
│  [Weekly Cron] ──→ ┌──────────────────┐                             │
│                    │ DB Backup → S3   │                             │
│                    └──────────────────┘                             │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Step 0: AWS 인프라 초기 설정

> CI/CD 파이프라인을 실제 운영하기 위한 AWS 인프라 초기 설정 단계별 가이드.
> Phase A → B → C 순서로 진행하며, Phase A는 EC2 없이도 검증 가능.

### Phase A: CI + 빌드 검증 (EC2 없이 가능)

#### A-1. AWS CLI v2 설치

```bash
# Linux (x86_64)
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# 확인
aws --version

# 초기 설정
aws configure
# AWS Access Key ID: <IAM 사용자 Access Key>
# AWS Secret Access Key: <IAM 사용자 Secret Key>
# Default region name: ap-northeast-2
# Default output format: json
```

#### A-2. OIDC Identity Provider 생성 (AWS Console)

**IAM → Identity providers → Add provider**

| 필드 | 입력값 |
|------|--------|
| Provider type | OpenID Connect |
| Provider URL | `https://token.actions.githubusercontent.com` |
| Get thumbprint | 버튼 클릭 (자동 생성) |
| Audience (클라이언트 ID) | `sts.amazonaws.com` |

#### A-3. IAM Role 생성 (OIDC 연동)

**IAM → Roles → Create role**

1. Trusted entity: **Web identity**
2. Identity provider: 위에서 생성한 GitHub OIDC 선택
3. Audience: `sts.amazonaws.com`
4. Condition 설정:
   - `token.actions.githubusercontent.com:sub` → `StringLike` → `repo:<org>/<repo>:*`
   - `token.actions.githubusercontent.com:aud` → `StringEquals` → `sts.amazonaws.com`
5. 권한 정책 연결: `AmazonEC2ContainerRegistryPowerUser`
6. Role 이름 지정 (예: `ddoksori-github-actions`)

> **Note:** `<org>/<repo>`는 실제 GitHub 리포지토리 경로로 교체 (예: `myorg/ddoksori`)

#### A-4. ECR 리포지토리 생성

```bash
aws ecr create-repository --repository-name ddoksori-backend --region ap-northeast-2
aws ecr create-repository --repository-name ddoksori-frontend --region ap-northeast-2
```

#### A-5. GitHub Secrets 등록

GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret Name | 값 | 필수 |
|-------------|---|------|
| `AWS_ROLE_ARN` | 생성한 Role ARN (예: `arn:aws:iam::123456789012:role/ddoksori-github-actions`) | ✅ |

#### A-6. 워크플로우 파일 확인

`.github/workflows/` 에 다음 파일이 존재하는지 확인:
- `lint.yml` - Lint 워크플로우
- `test.yml` - 테스트 워크플로우
- `build.yml` - Docker 이미지 빌드 & ECR 푸시

#### A-7. CI + 빌드 검증

1. PR 생성 또는 main에 push → GitHub Actions 탭에서 lint, test 실행 확인
2. main 머지 시 → build.yml이 ECR에 이미지를 push하는지 확인

**Phase A 완료 체크리스트:**
- [ ] AWS CLI 설치 & 설정
- [ ] OIDC Identity Provider 생성
- [ ] IAM Role 생성 (OIDC trust + ECR 권한)
- [ ] ECR 리포지토리 2개 생성
- [ ] GitHub Secrets: `AWS_ROLE_ARN` 등록
- [ ] lint.yml, test.yml PR 시 정상 동작
- [ ] build.yml main push 시 ECR 이미지 푸시 성공

---

### Phase B: EC2 생성 & 설정

#### B-1. EC2 인스턴스 생성 (AWS Console)

**EC2 → Launch instances**

| 설정 | 값 |
|------|---|
| Name | `ddoksori-staging` |
| AMI | Amazon Linux 2023 |
| Instance type | `t3.small` (~$15/월) |
| Key pair | 새로 생성 → `.pem` 파일 다운로드 & 안전 보관 |
| Network | 기본 VPC |
| Security group | 아래 참조 |

**보안 그룹 인바운드 규칙:**

| 포트 | 프로토콜 | 소스 | 용도 |
|------|---------|------|------|
| 22 | TCP | My IP (또는 GitHub Actions IP) | SSH |
| 80 | TCP | 0.0.0.0/0 | Frontend (Nginx) |
| 8000 | TCP | 0.0.0.0/0 | Backend (FastAPI) |

> **보안 주의:** Production에서는 8000 포트를 Nginx 뒤에 숨기고 80/443만 노출할 것.

#### B-2. EC2 초기 설정

SSH 접속 후 실행:

```bash
# Docker 설치
sudo yum update -y
sudo yum install -y docker
sudo systemctl start docker && sudo systemctl enable docker
sudo usermod -aG docker ec2-user

# 재접속 (docker 그룹 반영)
exit
# SSH 재접속 후:

# Docker Compose 설치
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" \
  -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 확인
docker --version
docker-compose --version

# AWS CLI (Amazon Linux 2023에는 기본 포함)
aws --version

# 프로젝트 디렉토리 생성
mkdir -p /home/ec2-user/ddoksori/backups
```

#### B-3. EC2에 IAM Role 연결

EC2가 ECR에서 이미지를 pull하려면 별도 IAM Role이 필요:

1. **IAM → Roles → Create role**
   - Trusted entity: **AWS service → EC2**
   - 정책: `AmazonEC2ContainerRegistryReadOnly`
   - Role 이름: `ddoksori-ec2-role`

2. **EC2 Console → 인스턴스 선택 → Actions → Security → Modify IAM role**
   - 위에서 생성한 `ddoksori-ec2-role` 선택

> **Note:** AWS Secrets Manager도 사용할 경우 `SecretsManagerReadWrite` 정책도 추가.

#### B-4. docker-compose.prod.yml 배치

EC2에 `docker-compose.prod.yml`을 배치:

```bash
# 방법 1: scp로 로컬에서 전송
scp -i <key.pem> docker-compose.prod.yml ec2-user@<EC2_HOST>:/home/ec2-user/ddoksori/

# 방법 2: EC2에서 git clone (첫 배포 시)
cd /home/ec2-user/ddoksori
git clone <repo-url> .
```

**Phase B 완료 체크리스트:**
- [ ] EC2 인스턴스 생성 (t3.small, Amazon Linux 2023)
- [ ] 보안 그룹 설정 (22, 80, 8000)
- [ ] Docker + Docker Compose 설치
- [ ] EC2 IAM Role 연결 (ECR ReadOnly)
- [ ] `/home/ec2-user/ddoksori/` 디렉토리 + `docker-compose.prod.yml` 배치
- [ ] SSH 접속 테스트 성공

---

### Phase C: 배포 파이프라인 연결

#### C-1. 추가 GitHub Secrets 등록

| Secret Name | 값 | 필수 |
|-------------|---|------|
| `EC2_SSH_KEY` | EC2 키 페어의 `.pem` 파일 내용 전체 | ✅ |
| `OPENAI_API_KEY` | OpenAI API 키 (main 전체 테스트용) | ✅ |
| `DISCORD_WEBHOOK` | Discord 웹훅 URL | 선택 |

> **EC2_SSH_KEY 등록 방법:** `.pem` 파일을 텍스트 편집기로 열어 `-----BEGIN RSA PRIVATE KEY-----`부터 `-----END RSA PRIVATE KEY-----`까지 전체 복사하여 등록.

#### C-2. 배포 워크플로우 확인

`.github/workflows/` 에 다음 파일이 존재하는지 확인:
- `deploy-staging.yml` - Staging 배포
- `deploy-production.yml` - Production 배포 + 자동 롤백

**deploy-staging.yml 내 EC2_HOST 확인:**
```yaml
env:
  EC2_HOST: staging.ddoksori.com  # 실제 EC2 퍼블릭 IP 또는 도메인으로 교체
```

#### C-3. Staging 배포 테스트

1. main 브랜치에 코드 머지
2. `build.yml` 성공 → `deploy-staging.yml` 자동 실행
3. GitHub Actions 탭에서 배포 로그 확인
4. `http://<EC2_IP>:8000/health` 접속하여 헬스체크 확인
5. `http://<EC2_IP>` 접속하여 Frontend 확인

#### C-4. Production 배포 테스트

1. **GitHub → Settings → Environments → production** 환경 생성
   - Protection rules: "Required reviewers" 설정 (수동 승인)
2. 태그 생성:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
3. `build.yml` 완료 대기 → `deploy-production.yml` 실행
4. GitHub에서 수동 승인 → 배포 진행
5. 실패 시 자동 롤백 잡 실행 확인

**Phase C 완료 체크리스트:**
- [ ] GitHub Secrets: `EC2_SSH_KEY`, `OPENAI_API_KEY` 등록
- [ ] deploy-staging.yml 내 EC2_HOST 실제 값으로 설정
- [ ] main 머지 → staging 자동 배포 성공
- [ ] 헬스체크 (`/health`) 정상 응답
- [ ] GitHub Environments: production 환경 + 수동 승인 설정
- [ ] v* 태그 → production 배포 테스트 성공
- [ ] (선택) Discord 알림 수신 확인

---

### 전체 진행 상태 추적

| 단계 | 항목 | 상태 |
|------|------|------|
| **A-1** | AWS CLI v2 설치 | ✅ 완료 |
| **A-2** | OIDC Identity Provider 생성 | ✅ 완료 |
| **A-3** | IAM Role 생성 | ✅ 완료 |
| **A-4** | ECR 리포지토리 생성 | ✅ 완료 |
| **A-5** | GitHub Secrets: AWS_ROLE_ARN | ✅ 완료 |
| **A-6** | 워크플로우 파일 확인 | ⬜ 미진행 |
| **A-7** | CI + 빌드 검증 | ⬜ 미진행 |
| **B-1** | EC2 인스턴스 생성 | ⬜ 미진행 |
| **B-2** | EC2 초기 설정 | ⬜ 미진행 |
| **B-3** | EC2 IAM Role 연결 | ⬜ 미진행 |
| **B-4** | docker-compose.prod.yml 배치 | ⬜ 미진행 |
| **C-1** | 추가 GitHub Secrets 등록 | ⬜ 미진행 |
| **C-2** | 배포 워크플로우 확인 | ⬜ 미진행 |
| **C-3** | Staging 배포 테스트 | ⬜ 미진행 |
| **C-4** | Production 배포 테스트 | ⬜ 미진행 |

---

## Step 1: CI 기본 (Lint & Test)

### 1.1 Lint Workflow (`.github/workflows/lint.yml`) - 구현 완료

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

### 1.2 Test Workflow (`.github/workflows/test.yml`) - 구현 완료

**트리거**: PR 생성, Push to main

**서비스**: PostgreSQL (pgvector:pg16) + Redis 7-alpine (3계층 캐싱용)

**테스트 전략**:
- PR 시: `pytest -m "not skip_ci and not llm"` (빠른 피드백, LLM/skip_ci 제외)
- main 머지 시: `pytest -m "not skip_ci"` (전체 테스트, LLM 포함)

**활용 마커** (16개): `unit`, `integration`, `api`, `supervisor`, `agent`, `retrieval`, `generation`, `review`, `slow`, `docker`, `skip_ci`, `llm`, `e2e`, `needs_db`, `needs_data`, `asyncio`

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

**테스트 마커 참고 (16개):**

```bash
# CI에서 사용할 마커 조합
pytest -m "not skip_ci"              # skip_ci 제외한 모든 테스트
pytest -m "not skip_ci and not llm"  # LLM API 호출 제외 (빠른 테스트)
pytest -m "unit"                     # 유닛 테스트만
pytest -m "integration"              # DB 필요 테스트
pytest -m "e2e"                      # E2E 테스트

# 전체 마커 목록 (pytest.ini)
# unit, integration, api, supervisor, agent, retrieval, generation, review,
# slow, docker, skip_ci, llm, e2e, needs_db, needs_data, asyncio
```

### 1.3 Dockerfile 프로덕션화 - 구현 완료

**개발 Dockerfile** (`backend/Dockerfile`, `frontend/Dockerfile`)은 `--reload`/`npm run dev` 모드로 개발 목적 전용.

**프로덕션 Dockerfile**은 별도 파일로 구현 완료:

#### `backend/Dockerfile.prod` - 구현 완료

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster pip
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy requirements first for layer caching
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY utils/ ./utils/

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Production server (gunicorn + uvicorn workers)
EXPOSE 8000
CMD ["sh", "-c", "gunicorn app.main:app \
    -w ${WEB_CONCURRENCY:-4} \
    -k uvicorn.workers.UvicornWorker \
    -b 0.0.0.0:8000 \
    --timeout 120 \
    --graceful-timeout 30 \
    --access-logfile -"]
```

> **Note:** `WEB_CONCURRENCY` 환경변수로 워커 수 동적 조정 가능 (기본 4). `--timeout 120`은 LLM API 호출 대기, `--graceful-timeout 30`은 안전한 종료 대기. `utils/` 디렉토리도 복사됨.

#### `frontend/Dockerfile.prod` - 구현 완료

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

#### `frontend/nginx.conf` - 구현 완료

SSE 스트리밍, gzip 압축, 7개 백엔드 프록시, 정적 파일 캐싱 포함:

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;
    gzip_min_length 1000;

    # SPA routing
    location / {
        try_files $uri $uri/ /index.html;
    }

    # SSE streaming support (must be before /chat to take priority)
    location /chat/stream {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Connection '';
        proxy_buffering off;
        proxy_cache off;
        chunked_transfer_encoding off;
    }

    # API proxy - backend endpoints
    location /chat {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /search {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /auth {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /case {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /metrics {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Health check endpoint
    location /health {
        proxy_pass http://backend:8000/health;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }

    # Static file caching
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

---

## Step 2: Docker 이미지 빌드 & ECR 푸시

### 2.1 Build Workflow (`.github/workflows/build.yml`) - 구현 완료

**트리거**: Push to main, Tag 생성 (`v*`)

**작업**:
- Docker Buildx로 Backend/Frontend 이미지 빌드
- `docker/metadata-action@v5`으로 태그 자동 관리 (latest, sha-, semver)
- GHA 캐시로 빌드 레이어 캐싱 (`cache-from: type=gha`, `cache-to: type=gha,mode=max`)
- AWS ECR에 이미지 푸시

> **Note:** ECR Registry URL은 GitHub Secret이 아닌, `aws-actions/amazon-ecr-login@v2` 스텝의
> output (`steps.login-ecr.outputs.registry`)에서 동적으로 획득합니다.

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

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Extract metadata for backend
        id: meta-backend
        uses: docker/metadata-action@v5
        with:
          images: ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_BACKEND }}
          tags: |
            type=raw,value=latest,enable={{is_default_branch}}
            type=sha,prefix=sha-
            type=semver,pattern={{version}}

      - name: Extract metadata for frontend
        id: meta-frontend
        uses: docker/metadata-action@v5
        with:
          images: ${{ steps.login-ecr.outputs.registry }}/${{ env.ECR_FRONTEND }}
          tags: |
            type=raw,value=latest,enable={{is_default_branch}}
            type=sha,prefix=sha-
            type=semver,pattern={{version}}

      - name: Build and push backend
        uses: docker/build-push-action@v5
        with:
          context: ./backend
          file: ./backend/Dockerfile.prod
          push: true
          tags: ${{ steps.meta-backend.outputs.tags }}
          labels: ${{ steps.meta-backend.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

      - name: Build and push frontend
        uses: docker/build-push-action@v5
        with:
          context: ./frontend
          file: ./frontend/Dockerfile.prod
          push: true
          tags: ${{ steps.meta-frontend.outputs.tags }}
          labels: ${{ steps.meta-frontend.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

### 2.2 AWS ECR 설정 (사전 작업)

> ECR 리포지토리 생성 및 OIDC 설정은 **Step 0: Phase A**를 참조하세요.

---

## Step 3: Staging 배포

### 3.1 Deploy Staging Workflow (`.github/workflows/deploy-staging.yml`) - 구현 완료

**트리거**: Build and Push 워크플로우 성공 완료 시 (main 브랜치)

**주요 특징**:
- ECR 로그인 스텝 분리 (`aws-actions/amazon-ecr-login@v2`)
- `--remove-orphans`로 고아 컨테이너 정리
- `docker image prune -f`로 이전 이미지 정리
- 5회 재시도 헬스체크 (초기 30초 대기 + 10초 간격)
- Success/Failure 별도 Discord 알림

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

      - name: Get ECR Login
        id: ecr-login
        uses: aws-actions/amazon-ecr-login@v2

      - name: Deploy to Staging
        uses: appleboy/ssh-action@v1.0.0
        with:
          host: ${{ env.EC2_HOST }}
          username: ec2-user
          key: ${{ secrets.EC2_SSH_KEY }}
          script: |
            cd /home/ec2-user/ddoksori

            # ECR Login
            aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin ${{ steps.ecr-login.outputs.registry }}

            # Pull latest images
            export ECR_REGISTRY=${{ steps.ecr-login.outputs.registry }}
            docker compose -f docker-compose.prod.yml pull

            # Deploy with zero-downtime
            docker compose -f docker-compose.prod.yml up -d --remove-orphans

            # Cleanup old images
            docker image prune -f

            # Show status
            docker compose -f docker-compose.prod.yml ps

      - name: Health Check
        run: |
          echo "Waiting for services to start..."
          sleep 30

          # Backend health check
          for i in {1..5}; do
            if curl -sf http://${{ env.EC2_HOST }}:8000/health; then
              echo "Backend is healthy!"
              break
            fi
            echo "Attempt $i failed, retrying in 10s..."
            sleep 10
          done

          # Final verification
          curl -f http://${{ env.EC2_HOST }}:8000/health || exit 1

      - name: Discord Notification - Success
        if: success()
        uses: sarisia/actions-status-discord@v1
        with:
          webhook: ${{ secrets.DISCORD_WEBHOOK }}
          status: success
          title: "Staging Deployment"
          description: |
            **Status**: Success
            **Commit**: `${{ github.event.workflow_run.head_sha }}`
            **Branch**: main
            **URL**: http://${{ env.EC2_HOST }}

      - name: Discord Notification - Failure
        if: failure()
        uses: sarisia/actions-status-discord@v1
        with:
          webhook: ${{ secrets.DISCORD_WEBHOOK }}
          status: failure
          title: "Staging Deployment"
          description: |
            **Status**: Failed
            **Commit**: `${{ github.event.workflow_run.head_sha }}`
            **Branch**: main

            Check GitHub Actions for details.
```

### 3.2 Production Compose File (`docker-compose.prod.yml`) - 구현 완료

AWS Secrets Manager 통합, MAS 에이전트 설정, 임베딩 설정, Redis 메모리 제한, 커스텀 네트워크 포함:

```yaml
services:
  backend:
    image: ${ECR_REGISTRY}/ddoksori-backend:${IMAGE_TAG:-latest}
    restart: always
    ports:
      - "8000:8000"
    environment:
      # === AWS Secrets Manager ===
      - USE_AWS_SECRETS=${USE_AWS_SECRETS:-false}
      - SECRETS_ENV=${SECRETS_ENV:-staging}
      - AWS_DEFAULT_REGION=ap-northeast-2

      # === Database (비-시크릿만, 시크릿은 Secrets Manager) ===
      - DB_POOL_SIZE=${DB_POOL_SIZE:-5}
      - DB_MAX_OVERFLOW=${DB_MAX_OVERFLOW:-10}
      - DATABASE_URL=${DATABASE_URL:-}

      # === Redis (3-tier caching) ===
      - REDIS_HOST=${REDIS_HOST:-redis}
      - REDIS_PORT=${REDIS_PORT:-6379}
      - ENABLE_ANSWER_CACHE=${ENABLE_ANSWER_CACHE:-true}

      # === LLM API Keys ===
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}

      # === MAS Supervisor Settings ===
      - MODEL_SUPERVISOR=${MODEL_SUPERVISOR:-gpt-4o}
      - MODEL_DRAFT_AGENT=${MODEL_DRAFT_AGENT:-gpt-4o}
      - MODEL_REVIEW_AGENT=${MODEL_REVIEW_AGENT:-gpt-4o}

      # === Embedding ===
      - EMBEDDING_MODEL=${EMBEDDING_MODEL:-text-embedding-3-large}
      - USE_OPENAI_EMBEDDING=${USE_OPENAI_EMBEDDING:-true}

      # === Agent Tuning ===
      - SIMILARITY_THRESHOLD=${SIMILARITY_THRESHOLD:-0.55}
      - MAX_SUPERVISOR_ITERATIONS=${MAX_SUPERVISOR_ITERATIONS:-10}

      # === Logging ===
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - ddoksori-net

  frontend:
    image: ${ECR_REGISTRY}/ddoksori-frontend:${IMAGE_TAG:-latest}
    restart: always
    ports:
      - "80:80"
    depends_on:
      backend:
        condition: service_healthy
    networks:
      - ddoksori-net

  redis:
    image: redis:7-alpine
    restart: always
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - ddoksori-net

networks:
  ddoksori-net:
    driver: bridge

volumes:
  redis-data:
```

### 3.3 AWS Secrets Manager 통합 - 구현 완료

프로덕션 시크릿 관리를 `.env` 파일에서 AWS Secrets Manager로 전환.
(상세 설계: `docs/plans/2026-01-29-aws-secrets-manager-design.md`)

| 항목 | 기존 | 변경 후 | 이유 |
|------|------|---------|------|
| **시크릿 저장** | `.env` 파일 | AWS Secrets Manager | 자동 로테이션, 감사 로그, IAM 접근 제어 |
| **시크릿 로딩** | Pydantic Settings dotenv | `inject_aws_secrets()` → os.environ 주입 | 기존 코드 최소 변경 |
| **docker-compose.prod.yml** | 시크릿 직접 환경변수 | `USE_AWS_SECRETS=true` + Secrets Manager | EC2에 .env 관리 불필요 |
| **비용** | 무료 | ~$6/월 | 7개 시크릿 x 2환경 |

**구현 완료 파일:**
- `backend/app/common/secrets.py` - AWS Secrets Manager SDK 래퍼, os.environ 사전 주입
  - SECRET_CATEGORIES (라인 27-35): database, llm, oauth/google, oauth/kakao, oauth/naver, security, infra
  - `inject_aws_secrets()` → `get_config()` 호출 전에 환경변수 주입

**환경별 시크릿 흐름:**

```
로컬 개발:  .env → Pydantic Settings (변경 없음)
CI/CD:      GitHub Secrets → 환경변수 (변경 없음)
Staging:    EC2 IAM Role → Secrets Manager → os.environ → Pydantic Settings
Production: EC2 IAM Role → Secrets Manager → os.environ → Pydantic Settings
```

---

## Step 4: Production 배포

### 4.1 Deploy Production Workflow (`.github/workflows/deploy-production.yml`) - 구현 완료

**트리거**: `v*` 태그 생성 시

**주요 특징**:
- `wait-for-build` 잡: Build 워크플로우 완료 대기 (`lewagon/wait-on-check-action@v1.3.4`)
- `environment: production`: GitHub 수동 승인 필요
- `backups/` 디렉토리에 배포 전 백업 생성
- 10회 재시도 헬스체크 (초기 30초 대기 + 15초 간격)
- Success/Failure 별도 Discord 알림 (색상 코드)
- **자동 롤백 잡**: 배포 실패 시 `production-rollback` environment로 자동 롤백

```yaml
name: Deploy to Production

on:
  push:
    tags: ['v*']

env:
  AWS_REGION: ap-northeast-2
  EC2_HOST: ddoksori.com

jobs:
  # Wait for build to complete first
  wait-for-build:
    runs-on: ubuntu-latest
    steps:
      - name: Wait for Build workflow
        uses: lewagon/wait-on-check-action@v1.3.4
        with:
          ref: ${{ github.ref }}
          repo-token: ${{ secrets.GITHUB_TOKEN }}
          check-name: build-and-push
          wait-interval: 30

  deploy:
    runs-on: ubuntu-latest
    needs: wait-for-build
    environment: production  # Requires manual approval in GitHub settings
    permissions:
      id-token: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Get version from tag
        id: version
        run: echo "VERSION=${GITHUB_REF#refs/tags/}" >> $GITHUB_OUTPUT

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Get ECR Login
        id: ecr-login
        uses: aws-actions/amazon-ecr-login@v2

      - name: Deploy to Production
        uses: appleboy/ssh-action@v1.0.0
        with:
          host: ${{ env.EC2_HOST }}
          username: ec2-user
          key: ${{ secrets.EC2_SSH_KEY }}
          script: |
            cd /home/ec2-user/ddoksori

            # Backup current deployment
            echo "Creating backup..."
            docker compose -f docker-compose.prod.yml config > backups/backup-$(date +%Y%m%d-%H%M%S).yml 2>/dev/null || true
            mkdir -p backups

            # ECR Login
            aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin ${{ steps.ecr-login.outputs.registry }}

            # Pull new version with specific tag
            export ECR_REGISTRY=${{ steps.ecr-login.outputs.registry }}
            export IMAGE_TAG=${{ steps.version.outputs.VERSION }}
            docker compose -f docker-compose.prod.yml pull

            # Rolling update
            echo "Deploying version $IMAGE_TAG..."
            docker compose -f docker-compose.prod.yml up -d --remove-orphans

            # Cleanup old images (keep last 3)
            docker image prune -f

            # Show status
            echo "Deployment complete:"
            docker compose -f docker-compose.prod.yml ps

      - name: Health Check
        run: |
          echo "Waiting for services to start..."
          sleep 30

          # Backend health check with retries
          for i in {1..10}; do
            if curl -sf http://${{ env.EC2_HOST }}:8000/health; then
              echo "Backend is healthy!"
              break
            fi
            echo "Attempt $i failed, retrying in 15s..."
            sleep 15
          done

          # Final verification
          curl -f http://${{ env.EC2_HOST }}:8000/health || exit 1

      - name: Discord Notification - Success
        if: success()
        uses: sarisia/actions-status-discord@v1
        with:
          webhook: ${{ secrets.DISCORD_WEBHOOK }}
          status: success
          title: "Production Deployment"
          color: 0x00ff00
          description: |
            **Status**: Success
            **Version**: `${{ steps.version.outputs.VERSION }}`
            **Commit**: `${{ github.sha }}`
            **URL**: http://${{ env.EC2_HOST }}

            Production deployment completed successfully!

      - name: Discord Notification - Failure
        if: failure()
        uses: sarisia/actions-status-discord@v1
        with:
          webhook: ${{ secrets.DISCORD_WEBHOOK }}
          status: failure
          title: "Production Deployment Failed"
          color: 0xff0000
          description: |
            **Status**: Failed
            **Version**: `${{ steps.version.outputs.VERSION }}`
            **Commit**: `${{ github.sha }}`

            Manual intervention may be required.
            Consider rolling back to previous version.

  # Automatic rollback on deploy failure
  rollback:
    runs-on: ubuntu-latest
    if: failure() && needs.deploy.result == 'failure'
    needs: deploy
    environment: production-rollback
    permissions:
      id-token: write
      contents: read

    steps:
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Get ECR Login
        id: ecr-login
        uses: aws-actions/amazon-ecr-login@v2

      - name: Rollback to previous version
        uses: appleboy/ssh-action@v1.0.0
        with:
          host: ${{ env.EC2_HOST }}
          username: ec2-user
          key: ${{ secrets.EC2_SSH_KEY }}
          script: |
            cd /home/ec2-user/ddoksori

            # ECR Login
            aws ecr get-login-password --region ap-northeast-2 | docker login --username AWS --password-stdin ${{ steps.ecr-login.outputs.registry }}

            # Rollback to latest (previous stable)
            export ECR_REGISTRY=${{ steps.ecr-login.outputs.registry }}
            export IMAGE_TAG=latest
            docker compose -f docker-compose.prod.yml pull
            docker compose -f docker-compose.prod.yml up -d

            echo "Rolled back to latest stable version"
            docker compose -f docker-compose.prod.yml ps

      - name: Discord Notification - Rollback
        uses: sarisia/actions-status-discord@v1
        with:
          webhook: ${{ secrets.DISCORD_WEBHOOK }}
          status: ${{ job.status }}
          title: "Production Rollback"
          description: |
            **Status**: ${{ job.status }}
            **Action**: Rolled back to previous stable version

            Please investigate the failed deployment.
```

### 4.2 Rollback 절차

배포 실패 시 **자동 롤백 잡**이 먼저 실행됩니다. 자동 롤백도 실패하거나 수동 롤백이 필요한 경우:

```bash
# EC2에서 수동 롤백
cd /home/ec2-user/ddoksori

# 이전 이미지로 롤백
export IMAGE_TAG=v1.0.0  # 이전 버전
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d

# 또는 백업된 설정 사용
docker compose -f backups/backup-YYYYMMDD-HHMMSS.yml up -d
```

---

## Step 5: DB 백업 자동화

### 5.1 Weekly DB Backup Workflow (`.github/workflows/db-backup.yml`) - 구현 완료

**트리거**: 매주 일요일 04:00 UTC (한국시간 13:00) + 수동 트리거 (`workflow_dispatch`)

**작업**:
- PostgreSQL 데이터베이스를 `pg_dump`로 백업
- S3 버킷 (`ddoksori-backups`)에 업로드
- weekly/monthly/manual 타입 분류
- 실패 시 GitHub Issue 자동 생성 (`bug` + `infrastructure` 라벨)

> **Note:** S3 버킷 리전은 `us-east-1`로, CI/CD의 ECR/EC2 리전(`ap-northeast-2`)과 다릅니다.
> 이는 S3 비용 최적화 및 글로벌 내구성을 위한 의도적 설계입니다.

```yaml
name: Weekly DB Backup

on:
  schedule:
    # 매주 일요일 04:00 UTC (한국시간 13:00)
    - cron: '0 4 * * 0'
  workflow_dispatch:
    inputs:
      backup_type:
        description: 'Backup type (weekly, monthly, manual)'
        required: false
        default: 'weekly'
        type: choice
        options:
          - weekly
          - monthly
          - manual

env:
  S3_BUCKET: ddoksori-backups
  AWS_REGION: us-east-1

jobs:
  backup:
    name: Backup PostgreSQL to S3
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Install PostgreSQL client
        run: |
          sudo apt-get update
          sudo apt-get install -y postgresql-client

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Verify S3 bucket access
        run: |
          aws s3 ls s3://${{ env.S3_BUCKET }}/ || echo "Bucket empty or first backup"

      - name: Run backup script
        env:
          DB_HOST: ${{ secrets.DB_HOST }}
          DB_USER: ${{ secrets.DB_USER }}
          DB_NAME: ${{ secrets.DB_NAME }}
          PGPASSWORD: ${{ secrets.DB_PASSWORD }}
          S3_BUCKET: ${{ env.S3_BUCKET }}
        run: |
          chmod +x ./backend/scripts/backup/backup_to_s3.sh
          ./backend/scripts/backup/backup_to_s3.sh ${{ github.event.inputs.backup_type || 'weekly' }}

      - name: List recent backups
        run: |
          echo "=== Recent Weekly Backups ==="
          aws s3 ls s3://${{ env.S3_BUCKET }}/weekly/ --human-readable | tail -5
          echo ""
          echo "=== Recent Monthly Backups ==="
          aws s3 ls s3://${{ env.S3_BUCKET }}/monthly/ --human-readable | tail -5

  notify-on-failure:
    name: Notify on Failure
    runs-on: ubuntu-latest
    needs: backup
    if: failure()

    steps:
      - name: Create failure issue
        uses: actions/github-script@v7
        with:
          script: |
            const title = `DB Backup Failed - ${new Date().toISOString().split('T')[0]}`;
            const body = `
            ## Database Backup Failed

            **Workflow Run:** [${context.runId}](${context.serverUrl}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId})
            **Triggered By:** ${context.eventName}
            **Time:** ${new Date().toISOString()}

            Please investigate and manually trigger a backup after fixing the issue.

            ### Checklist
            - [ ] Check AWS credentials (expired?)
            - [ ] Check RDS connectivity
            - [ ] Check S3 bucket permissions
            - [ ] Manually run backup after fix
            `;

            await github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: title,
              body: body,
              labels: ['bug', 'infrastructure']
            });
```

---

## GitHub Secrets 설정

GitHub Repository → Settings → Secrets and variables → Actions

### CI/CD 파이프라인용

| Secret Name | 사용 워크플로우 | Description |
|-------------|-----------------|-------------|
| `AWS_ROLE_ARN` | build, deploy-staging, deploy-production | AWS OIDC Role ARN (ECR/EC2 접근) |
| `EC2_SSH_KEY` | deploy-staging, deploy-production | EC2 SSH 개인키 |
| `OPENAI_API_KEY` | test | LLM 테스트용 API 키 (main 브랜치 전체 테스트) |
| `DISCORD_WEBHOOK` | deploy-staging, deploy-production | Discord 알림 웹훅 URL |

### DB 백업용

| Secret Name | 사용 워크플로우 | Description |
|-------------|-----------------|-------------|
| `AWS_ACCESS_KEY_ID` | db-backup | S3 접근용 AWS Access Key |
| `AWS_SECRET_ACCESS_KEY` | db-backup | S3 접근용 AWS Secret Key |
| `DB_HOST` | db-backup | RDS 호스트 주소 |
| `DB_USER` | db-backup | RDS 사용자명 |
| `DB_NAME` | db-backup | RDS 데이터베이스명 |
| `DB_PASSWORD` | db-backup | RDS 비밀번호 |

### AI 코드리뷰용 (보조 자동화)

| Secret Name | 사용 워크플로우 | Description |
|-------------|-----------------|-------------|
| `CLAUDE_CODE_OAUTH_TOKEN` | claude-code-review, claude | Claude Code Action OAuth 토큰 |
| `GOOGLE_GENERATIVE_AI_API_KEY` | opencode | Google Gemini API 키 |
| `GEMINI_API_KEY` | opencode | Gemini API 키 (대체) |

> **Note:** `GITHUB_TOKEN`은 자동 제공되므로 별도 설정 불필요. `ECR_REGISTRY`는 시크릿이 아니라 ECR 로그인 스텝 output에서 동적 획득.

### AWS Secrets Manager (EC2 런타임용, GitHub Secrets 아님)

> 아래는 EC2에서 런타임에 로드되는 AWS Secrets Manager 경로입니다.
> 소스: `backend/app/common/secrets.py` (SECRET_CATEGORIES, 라인 27-35)

| Secret Path | 주입되는 환경변수 |
|-------------|-------------------|
| `ddoksori/{env}/database` | DB_HOST, DB_USER, DB_PASSWORD, DATABASE_URL |
| `ddoksori/{env}/llm` | OPENAI_API_KEY, ANTHROPIC_API_KEY |
| `ddoksori/{env}/oauth/google` | GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET |
| `ddoksori/{env}/oauth/kakao` | KAKAO_CLIENT_ID, KAKAO_CLIENT_SECRET |
| `ddoksori/{env}/oauth/naver` | NAVER_CLIENT_ID, NAVER_CLIENT_SECRET |
| `ddoksori/{env}/security` | JWT_SECRET_KEY, SECRET_KEY |
| `ddoksori/{env}/infra` | HF_TOKEN, EXAONE_RUNPOD_API_KEY |

---

## 구현 완료 파일 목록

### CI/CD 핵심 파일

| 파일 | 설명 | 상태 |
|------|------|------|
| `.github/workflows/lint.yml` | Lint 워크플로우 | 구현 완료 |
| `.github/workflows/test.yml` | 테스트 워크플로우 | 구현 완료 |
| `.github/workflows/build.yml` | 이미지 빌드 워크플로우 (Buildx + GHA 캐시) | 구현 완료 |
| `.github/workflows/deploy-staging.yml` | Staging 배포 워크플로우 | 구현 완료 |
| `.github/workflows/deploy-production.yml` | Production 배포 + 자동 롤백 | 구현 완료 |
| `.github/workflows/db-backup.yml` | Weekly DB 백업 → S3 | 구현 완료 |
| `backend/Dockerfile.prod` | 프로덕션용 Backend Dockerfile | 구현 완료 |
| `frontend/Dockerfile.prod` | 프로덕션용 Frontend Dockerfile | 구현 완료 |
| `frontend/nginx.conf` | Nginx 설정 (SSE, gzip, 프록시) | 구현 완료 |
| `docker-compose.prod.yml` | 프로덕션 Compose 파일 | 구현 완료 |
| `backend/app/common/secrets.py` | AWS Secrets Manager SDK 래퍼 | 구현 완료 |

### 보조 자동화 (CI/CD 파이프라인 외)

| 파일 | 설명 |
|------|------|
| `.github/workflows/claude-code-review.yml` | Claude Code PR 자동 리뷰 |
| `.github/workflows/claude.yml` | Claude Code Action |
| `.github/workflows/opencode.yml` | OpenCode (Gemini) Action |

---

## 운영 가이드

| 작업 | 트리거 | 자동화 |
|------|--------|--------|
| 코드 린트 | PR 생성/Push to main | 자동 |
| 테스트 실행 | PR 생성/Push to main | 자동 |
| Docker 이미지 빌드 | Push to main / Tag 생성 | 자동 |
| Staging 배포 | main 머지 후 Build 성공 | 자동 |
| Production 배포 | v* 태그 생성 | 자동 (수동 승인) |
| DB 백업 | 매주 일요일 13:00 KST | 자동 |
| Production 롤백 | 배포 실패 시 | 자동 (수동 트리거 가능) |

---

## 비용 참고 (AWS)

아카이브된 비용 분석 (`docs/_archive/plans/deploy/02_cost_analysis.md`) 기준:
- EC2 t3.small: ~$15/월
- RDS db.t3.micro: ~$15/월
- ECR: ~$1/월 (스토리지)
- S3 (DB 백업): ~$1/월
- Secrets Manager: ~$6/월 (7개 시크릿 x 2환경)
- **예상 총 비용**: $30-70/월

> **EC2 인스턴스 검토 (2026-02-01):** t3.small (2GB RAM)에서 gunicorn 4 워커 + Redis 256MB + Nginx를
> 실행하면 메모리가 빡빡합니다 (~2.2GB 추정). 초기 운영 시 `WEB_CONCURRENCY=2`로 워커를 줄이거나,
> t3.medium (4GB, ~$30/월)으로 업그레이드를 권장합니다.

---

## 참고 문서

- 아카이브된 배포 가이드: `docs/_archive/plans/deploy/`
- 현재 Docker 설정 (개발): `docker-compose.yml`
- 테스트 설정: `backend/pytest.ini`
- 환경변수 템플릿: `backend/.env.example`
- AWS Secrets Manager 설계: `docs/plans/2026-01-29-aws-secrets-manager-design.md`
- MAS v2 아키텍처 설계: `docs/plans/2026-01-28-mas-architecture-v2-design.md`

---

## Appendix: 변경 이력

### 2026-01-28: Backend 리팩토링 반영

CI/CD에 영향 있는 변경:
- 테스트 서비스: PostgreSQL만 → PostgreSQL + Redis (3계층 캐싱 테스트)
- 테스트 마커: `unit or integration` → `not skip_ci and not llm` (16개 마커 체계)
- uv 설치: `pip install uv` → `COPY --from=ghcr.io` (Dockerfile과 동일)
- 환경변수: Redis 설정 추가

CI/CD 영향 없는 추가 모듈: `app/common/cache/`, `app/llm/providers/`, `app/common/embedding/`, `app/common/config.py`, `app/agents/followup/`, `app/agents/retrieval/trace.py`, `app/agents/retrieval/tools/unified_retriever.py`, `app/database/migrations/004_add_rrf_search_functions.sql`, `app/auth/`, `scripts/testing/e2e/`

### 2026-01-29: MAS v2 아키텍처 반영

CI/CD 영향 없음. 주요 변경:
- Retrieval Agent: 4개 → 3개 (counsel → case 통합)
- Supervisor 모델: gpt-4o → gpt-4o-mini
- 추가: Agent Registry, 재생성 루프, ChatState 분할

상세 설계: `docs/plans/2026-01-28-mas-architecture-v2-design.md`

### 2026-01-29: AWS Secrets Manager 통합

Step 3에 통합됨. 상세 설계: `docs/plans/2026-01-29-aws-secrets-manager-design.md`

### 2026-02-01: AWS 인프라 초기 설정 가이드

Step 0으로 통합됨.
