# DDOKSORI AWS MVP 배포 계획

## Context

### Original Request
DDOKSORI 프로젝트를 AWS에 단계별로 배포하는 계획 수립
- MVP 단계: Route53 + EC2 2대 + ALB + RDS + GHCR + Secrets Manager
- 추후 개선: CloudFront, Auto Scaling, 모니터링 강화 등 AWS 네이티브 통합

### Interview Summary
**Key Discussions**:
- EC2: 2대 + ALB (고가용성)
- DB: **기존 RDS PostgreSQL 사용** (`dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com`)
- **리전: us-east-1** (기존 RDS와 동일 리전으로 EC2 배치)
- DNS: Route53 ($0.50/월) - ALB와 Alias 레코드로 연동
- 컨테이너 레지스트리: GHCR (무료)
- 시크릿: AWS Secrets Manager
- RunPod: **EXAONE-4.0-1.2B** (임베딩은 OpenAI text-embedding-3-large 사용)
- S3: 게시판 이미지 저장

**Model Architecture** (AI_MEMO.md 기준):
| 역할 | 모델 | Fallback Chain |
|------|------|----------------|
| Supervisor | GPT-5.1 | Claude 3.5 Sonnet → Rule-based |
| Draft Agent | gpt-4o | gpt-4o-mini → rule_based |
| Review Agent | gpt-4o | - |
| Retrieval LLM | EXAONE-4.0-1.2B | gpt-4.1-nano → original query |
| Embedding | text-embedding-3-large (1536d) | - |

**Research Findings**:
- 현재 Dockerfile들은 개발용 (--reload, npm run dev)
- Nginx 설정 없음 - 생성 필요
- CI/CD 파이프라인 없음 - 생성 필요
- docker-compose.rds.yml로 RDS 연동 패턴 존재
- **기존 RDS에 `vector_chunks` 테이블 존재 (40,285 rows)**

### Metis Review
**Identified Gaps** (addressed):
- DuckDNS + ALB 호환성 문제 → Route53으로 해결
- 데이터 마이그레이션 전략 → Phase 3에서 다룸
- RunPod 연결 실패 시 fallback → OpenAI API fallback 정책 명시
- 비용 모니터링 → AWS Budget Alert 설정 포함

---

## Work Objectives

### Core Objective
DDOKSORI 프로젝트를 AWS 인프라에 배포하여 외부 사용자가 접근 가능한 서비스로 운영

### Concrete Deliverables
- Production-ready Dockerfile (backend, frontend)
- Nginx 설정 파일
- GitHub Actions CI/CD 워크플로우
- AWS 인프라 (VPC, EC2, RDS, ALB, S3, Route53)
- 운영 문서 (배포 가이드, 장애 대응)

### Definition of Done
- [ ] `https://[도메인]` 으로 서비스 접근 가능
- [ ] 채팅 기능 E2E 동작 확인
- [ ] main 브랜치 push 시 자동 배포
- [ ] 월 예상 비용 $130 이내

### Must Have
- HTTPS 적용 (ACM 인증서)
- Health check 기반 자동 복구
- 시크릿 암호화 저장 (Secrets Manager)
- 자동화된 CI/CD 파이프라인

### Must NOT Have (Guardrails)
- Production Dockerfile에 `--reload` 플래그 금지
- Frontend를 `npm run dev`로 서빙 금지
- .env 파일을 이미지에 포함 금지
- RDS를 public subnet에 배치 금지
- 0.0.0.0/0 에서 RDS 직접 접근 허용 금지
- 시크릿을 GitHub Actions 로그에 노출 금지
- root 사용자로 컨테이너 실행 금지

---

## Verification Strategy

### Test Decision
- **Infrastructure exists**: NO (신규 생성)
- **User wants tests**: Manual verification + Health checks
- **Framework**: curl, AWS CLI, 브라우저 테스트

### Manual QA Protocol
각 Phase 완료 시 검증 절차를 수행하고, 실패 시 해당 Phase 롤백

---

## Architecture Overview

```
                         ┌─────────────────────────────────────────┐
                         │            AWS Cloud (us-east-1)        │
                         └─────────────────────────────────────────┘

     [사용자] ──HTTPS──▶ Route53 ──▶ ALB (443) ──▶ Target Group
                         (Alias)     (ACM 인증서)       │
                                                   ┌────┴────┐
                                                   ▼         ▼
                                              ┌────────┐ ┌────────┐
                                              │ EC2 #1 │ │ EC2 #2 │
                                              │ (AZ-a) │ │ (AZ-b) │
                                              └───┬────┘ └───┬────┘
                                                  │          │
                         ┌────────────────────────┼──────────┼────┐
                         │                        │          │    │
                         │   ┌────────────────────┴──────────┴──┐ │
                         │   │  기존 RDS PostgreSQL (pgvector)  │ │
                         │   │  dsr-postgres.xxx.us-east-1.rds  │ │
                         │   │  vector_chunks: 40,285 rows      │ │
                         │   └──────────────────────────────────┘ │
                         └────────────────────────────────────────┘

     [EC2 내부]
     ┌─────────────────────────────────────────┐
     │  Docker Compose                         │
     │  ┌─────────┐  ┌─────────┐  ┌─────────┐ │
     │  │ Nginx   │  │ Backend │  │  Redis  │ │
     │  │  :80    │──│  :8000  │──│  :6379  │ │
     │  │(Frontend)│  │(FastAPI)│  │(Cache)  │ │
     │  └─────────┘  └─────────┘  └─────────┘ │
     └─────────────────────────────────────────┘
              │
              │ SSH Tunnel (systemd, port 19010)
              ▼
     ┌─────────────────┐     ┌─────────────────┐
     │  RunPod (GPU)   │     │   OpenAI API    │
     │  EXAONE-4.0-1.2B│     │  text-embedding │
     │  (Retrieval LLM)│     │  -3-large(1536d)│
     └─────────────────┘     └─────────────────┘

     [LLM 모델 할당]
     ┌─────────────────────────────────────────┐
     │  Supervisor: GPT-5.1                    │
     │  Draft Agent: gpt-4o                    │
     │  Review Agent: gpt-4o                   │
     │  Retrieval LLM: EXAONE-4.0-1.2B         │
     │  Retrieval Fallback: gpt-4.1-nano       │
     └─────────────────────────────────────────┘
```

---

## Cost Estimation

| 서비스 | 스펙 | 시간당 | 월간 (730h) | 비고 |
|--------|------|--------|-------------|------|
| EC2 × 2 | t3.medium (us-east-1) | $0.0416 × 2 | $60.74 | |
| RDS | **기존 인스턴스 사용** | - | **$0** | 이미 운영 중 |
| ALB | 기본 + LCU | $0.028 | $20.44 | |
| Route53 | 1 hosted zone | - | $0.50 | |
| S3 | 10GB + 요청 | - | $1.00 | |
| Secrets Manager | 7 secrets | - | $2.80 | +models, +embedding |
| Data Transfer | 100GB 무료 | - | $0.00 | |
| **Total** | | **~$0.12/h** | **~$85/월** | RDS 제외 시 |

**⚠️ 참고**: 
- 기존 RDS(`dsr-postgres`)가 이미 us-east-1에서 운영 중이므로 신규 RDS 비용 없음
- 기존 RDS 비용은 별도 계정/예산에서 이미 지출 중
- Secrets Manager 시크릿 7개: db, api-keys, runpod, app, models, embedding + 여유

---

## Task Flow

```
Phase 1 (코드 준비)
    │
    ▼
Phase 2 (AWS 인프라) ──────────────────┐
    │                                  │
    ▼                                  ▼
Phase 3 (데이터 마이그레이션)      Phase 4 (시크릿 설정)
    │                                  │
    └──────────────┬───────────────────┘
                   ▼
            Phase 5 (배포 & 검증)
                   │
                   ▼
            Phase 6 (CI/CD 자동화)
                   │
                   ▼
            Phase 7 (추후 개선 - AWS 네이티브)
```

---

## TODOs

---

### Phase 1: Production 코드 준비

> 목표: 프로덕션 환경에서 실행 가능한 Docker 이미지 빌드 준비

---

- [ ] 1.1. Backend Production Dockerfile 작성

  **What to do**:
  - `backend/Dockerfile.prod` 생성
  - `--reload` 제거, gunicorn + uvicorn workers 사용
  - 비-root 사용자로 실행
  - Health check 명령어 포함

  **Must NOT do**:
  - `--reload` 플래그 사용 금지
  - root 사용자 실행 금지

  **Parallelizable**: YES (with 1.2, 1.3)

  **References**:
  - `backend/Dockerfile:1-27` - 현재 개발용 Dockerfile 구조
  - `backend/requirements.txt` - Python 의존성 목록
  - `backend/app/main.py` - FastAPI 앱 엔트리포인트

  **Acceptance Criteria**:
  - [ ] 파일 생성: `backend/Dockerfile.prod`
  - [ ] 빌드 성공: `docker build -f backend/Dockerfile.prod -t ddoksori-backend:test ./backend`
  - [ ] 컨테이너 실행: `docker run -d -p 8000:8000 ddoksori-backend:test`
  - [ ] Health check: `curl http://localhost:8000/health` → 200 OK
  - [ ] `--reload` 미포함 확인: `grep -c "reload" backend/Dockerfile.prod` → 0

  **Commit**: YES
  - Message: `feat(deploy): add production Dockerfile for backend`
  - Files: `backend/Dockerfile.prod`

---

- [ ] 1.2. Frontend Production Dockerfile 작성 (Multi-stage)

  **What to do**:
  - `frontend/Dockerfile.prod` 생성
  - Stage 1: Node.js로 빌드 (`npm run build`)
  - Stage 2: Nginx로 정적 파일 서빙
  - `VITE_API_BASE_URL` 빌드 인자 지원

  **Must NOT do**:
  - `npm run dev` 사용 금지
  - Node.js 런타임으로 서빙 금지

  **Parallelizable**: YES (with 1.1, 1.3)

  **References**:
  - `frontend/Dockerfile:1-14` - 현재 개발용 Dockerfile
  - `frontend/package.json` - build 스크립트 확인
  - `frontend/vite.config.ts` - Vite 빌드 설정

  **Acceptance Criteria**:
  - [ ] 파일 생성: `frontend/Dockerfile.prod`
  - [ ] 빌드 성공: `docker build -f frontend/Dockerfile.prod --build-arg VITE_API_BASE_URL=http://localhost:8000 -t ddoksori-frontend:test ./frontend`
  - [ ] 컨테이너 실행: `docker run -d -p 80:80 ddoksori-frontend:test`
  - [ ] 페이지 로드: `curl http://localhost:80` → HTML 응답
  - [ ] `npm run dev` 미포함: `grep -c "npm run dev" frontend/Dockerfile.prod` → 0

  **Commit**: YES
  - Message: `feat(deploy): add production Dockerfile for frontend with nginx`
  - Files: `frontend/Dockerfile.prod`

---

- [ ] 1.3. Nginx 설정 파일 작성

  **What to do**:
  - `frontend/nginx.conf` 생성
  - SPA 라우팅 처리 (`try_files $uri /index.html`)
  - API 프록시 (`/api/ → backend:8000`)
  - 정적 파일 캐싱 헤더
  - Health check 엔드포인트 (`/health`)
  - Gzip 압축 활성화

  **Must NOT do**:
  - 백엔드 포트 외부 노출 금지

  **Parallelizable**: YES (with 1.1, 1.2)

  **References**:
  - `frontend/src/shared/api/client.ts` - API 호출 패턴 확인
  - `frontend/vite.config.ts` - 개발 서버 프록시 설정 참고

  **Acceptance Criteria**:
  - [ ] 파일 생성: `frontend/nginx.conf`
  - [ ] 문법 검증: `docker run --rm -v $(pwd)/frontend/nginx.conf:/etc/nginx/conf.d/default.conf:ro nginx:alpine nginx -t` → syntax ok
  - [ ] SPA 라우팅: `/chat`, `/board` 경로가 index.html로 폴백
  - [ ] API 프록시: `/api/health` → backend `/health`

  **Commit**: YES
  - Message: `feat(deploy): add nginx configuration for frontend`
  - Files: `frontend/nginx.conf`

---

- [ ] 1.4. docker-compose.prod.yml 작성

  **What to do**:
  - 루트에 `docker-compose.prod.yml` 생성
  - GHCR 이미지 참조 (`ghcr.io/[owner]/ddoksori-backend:latest`)
  - 환경변수는 외부 주입 방식 (`${VAR}`)
  - Redis 컨테이너 포함
  - 네트워크 및 볼륨 정의
  - Health check 설정

  **Must NOT do**:
  - 하드코딩된 시크릿 금지
  - 로컬 빌드 컨텍스트 사용 금지 (이미지 pull 방식)

  **Parallelizable**: NO (depends on 1.1, 1.2, 1.3)

  **References**:
  - `docker-compose.yml:1-146` - 현재 개발용 구성
  - `docker-compose.rds.yml:1-68` - RDS 연동 패턴
  - `backend/.env.example:1-242` - 환경변수 목록

  **Acceptance Criteria**:
  - [ ] 파일 생성: `docker-compose.prod.yml`
  - [ ] 문법 검증: `docker compose -f docker-compose.prod.yml config` → 에러 없음
  - [ ] GHCR 이미지 참조 확인: `grep "ghcr.io" docker-compose.prod.yml` → 존재
  - [ ] 하드코딩 시크릿 없음: `grep -E "(password|secret|key)=" docker-compose.prod.yml` → 0개 또는 ${} 형식만

  **Commit**: YES
  - Message: `feat(deploy): add production docker-compose for AWS deployment`
  - Files: `docker-compose.prod.yml`

---

- [ ] 1.5. Secrets Manager 연동 스크립트 작성

  **What to do**:
  - `scripts/load-secrets.sh` 생성
  - AWS CLI로 Secrets Manager에서 시크릿 로드
  - 환경변수로 export
  - docker-compose 실행 전 호출

  **Must NOT do**:
  - 시크릿을 파일로 저장 금지
  - 로그에 시크릿 출력 금지

  **Parallelizable**: YES (with 1.4)

  **References**:
  - `backend/.env.example` - 필요한 환경변수 목록
  - `backend/app/common/config.py` - Pydantic Settings 패턴

  **Acceptance Criteria**:
  - [ ] 파일 생성: `scripts/load-secrets.sh`
  - [ ] 실행 권한: `chmod +x scripts/load-secrets.sh`
  - [ ] AWS CLI 의존성 체크 포함
  - [ ] 시크릿 키 목록 정의 (ddoksori/db, ddoksori/api-keys 등)

  **Commit**: YES
  - Message: `feat(deploy): add secrets manager loading script`
  - Files: `scripts/load-secrets.sh`

---

### Phase 1 완료 체크포인트

```bash
# 로컬에서 전체 빌드 테스트
docker build -f backend/Dockerfile.prod -t ddoksori-backend:test ./backend
docker build -f frontend/Dockerfile.prod --build-arg VITE_API_BASE_URL=http://localhost:8000 -t ddoksori-frontend:test ./frontend

# 컨테이너 실행 테스트 (로컬 DB 사용)
docker compose -f docker-compose.yml up -d db redis
docker run -d --network host -e DB_HOST=localhost ddoksori-backend:test
docker run -d -p 80:80 ddoksori-frontend:test

# 검증
curl http://localhost:8000/health  # → 200 OK
curl http://localhost:80           # → HTML 페이지
```

**Phase 1 완료 조건**:
- [ ] 모든 Dockerfile 빌드 성공
- [ ] 로컬에서 컨테이너 실행 및 통신 확인
- [ ] 코드 커밋 완료

---

### Phase 2: AWS 인프라 구성

> 목표: EC2, RDS, ALB, Route53 등 AWS 리소스 생성

---

- [ ] 2.1. VPC 및 네트워크 구성 (us-east-1)

  **What to do**:
  - VPC 생성 (CIDR: 10.0.0.0/16) - **리전: us-east-1** (기존 RDS와 동일)
  - Public Subnet 2개 (us-east-1a, us-east-1b) - EC2, ALB용
  - Private Subnet 2개 (us-east-1a, us-east-1b) - RDS 연결용
  - Internet Gateway 연결
  - NAT Gateway 생성 (Private Subnet 아웃바운드용)
  - Route Table 설정
  - **기존 RDS Security Group과 VPC Peering 또는 SG 규칙 추가**

  **Must NOT do**:
  - 단일 AZ에 모든 리소스 배치 금지
  - 기존 RDS가 있는 us-east-1 외 다른 리전 사용 금지

  **Parallelizable**: NO (다른 리소스의 기반)

  **References**:
  - AWS VPC 콘솔: https://console.aws.amazon.com/vpc
  - 기존 RDS: `dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com`

  **Acceptance Criteria**:
  - [ ] VPC 생성 확인: `aws ec2 describe-vpcs --filters "Name=tag:Name,Values=ddoksori-vpc" --region us-east-1`
  - [ ] Subnet 4개 생성 확인 (us-east-1a, us-east-1b)
  - [ ] Internet Gateway 연결 확인
  - [ ] Route Table 설정 확인

  **Commit**: NO (인프라 작업)

  **문서화**: `docs/infra/vpc-setup.md`에 생성 과정 기록

---

- [ ] 2.2. Security Groups 생성

  **What to do**:
  - `ddoksori-alb-sg`: 80, 443 인바운드 (0.0.0.0/0)
  - `ddoksori-ec2-sg`: ALB SG에서만 80 허용, 관리자 IP에서 22 허용
  - `ddoksori-rds-sg`: EC2 SG에서만 5432 허용

  **Must NOT do**:
  - RDS에 0.0.0.0/0 허용 금지
  - EC2에 0.0.0.0/0 에서 직접 80/443 허용 금지

  **Parallelizable**: YES (with 2.1 완료 후)

  **Acceptance Criteria**:
  - [ ] 3개 Security Group 생성 확인
  - [ ] 규칙 검증: `aws ec2 describe-security-groups --group-names ddoksori-rds-sg`
  - [ ] RDS SG에 0.0.0.0/0 없음 확인

  **Commit**: NO (인프라 작업)

---

- [ ] 2.3. 기존 RDS PostgreSQL 연결 설정 (신규 생성 불필요)

  **What to do**:
  - **기존 RDS 사용**: `dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com`
  - 기존 RDS의 Security Group에 새 EC2 SG 인바운드 규칙 추가 (5432)
  - 또는 VPC Peering 설정 (새 VPC ↔ 기존 RDS VPC)
  - EC2에서 RDS 연결 테스트

  **기존 RDS 정보**:
  - Endpoint: `dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com`
  - 리전: us-east-1
  - 데이터: `vector_chunks` 테이블 40,285 rows (임베딩 포함)
  - pgvector 확장 이미 설치됨

  **Must NOT do**:
  - 신규 RDS 인스턴스 생성 (불필요)
  - 기존 데이터 삭제 또는 덮어쓰기

  **Parallelizable**: YES (with 2.2)

  **References**:
  - 기존 RDS 콘솔에서 Security Group 확인

  **Acceptance Criteria**:
  - [ ] 기존 RDS 상태 확인: `aws rds describe-db-instances --db-instance-identifier dsr-postgres --region us-east-1`
  - [ ] 상태: available
  - [ ] EC2에서 연결 테스트: `psql -h dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com -U admin -d ddoksori`
  - [ ] 데이터 확인: `SELECT COUNT(*) FROM vector_chunks;` → 40,285

  **Commit**: NO (인프라 작업)

---

- [ ] 2.4. 기존 RDS pgvector 및 데이터 검증 (신규 설치 불필요)

  **What to do**:
  - EC2에서 기존 RDS 연결 테스트
  - pgvector 확장 이미 설치되어 있음을 확인
  - 기존 데이터 무결성 확인 (vector_chunks, disputes 등)
  - **임베딩 차원 확인**: text-embedding-3-large = **1536 dimensions**

  **Must NOT do**:
  - 기존 데이터 삭제/수정
  - 스키마 재적용 (이미 존재)
  - 로컬에서 직접 RDS 접속 금지 (EC2 통해 접속)

  **Parallelizable**: NO (depends on 2.3)

  **References**:
  - 기존 데이터: 40,285 rows in vector_chunks

  **Acceptance Criteria**:
  - [ ] EC2에서 RDS 접속: `psql -h dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com -U admin -d ddoksori`
  - [ ] 확장 확인: `SELECT * FROM pg_extension WHERE extname = 'vector';` → 1 row
  - [ ] 테이블 확인: `\dt` → vector_chunks, disputes 등 존재
  - [ ] 데이터 확인: `SELECT COUNT(*) FROM vector_chunks;` → 40,285
  - [ ] 벡터 차원 확인: `SELECT vector_dims(embedding) FROM vector_chunks LIMIT 1;` → **1536**

  **Commit**: NO (인프라 작업)

---

- [ ] 2.5. EC2 인스턴스 2대 생성 (us-east-1)

  **What to do**:
  - AMI: Ubuntu 22.04 LTS
  - Instance Type: t3.medium
  - **리전: us-east-1** (기존 RDS와 동일)
  - 2대: us-east-1a, us-east-1b 각 1대
  - Key Pair 생성/선택
  - Security Group: ddoksori-ec2-sg
  - IAM Role: Secrets Manager 접근 권한 포함
  - User Data: Docker, Docker Compose 설치 스크립트

  **Must NOT do**:
  - Public IP 없이 생성 금지 (ALB 연결 전 테스트 필요)
  - us-east-1 외 다른 리전 사용 금지

  **Parallelizable**: YES (with 2.3, 2.4)

  **References**:
  - User Data 스크립트 예시 포함

  **Acceptance Criteria**:
  - [ ] 2대 인스턴스 running 상태 (us-east-1a, us-east-1b)
  - [ ] SSH 접속 성공: `ssh -i key.pem ubuntu@[public-ip]`
  - [ ] Docker 설치 확인: `docker --version`
  - [ ] Docker Compose 설치 확인: `docker compose version`
  - [ ] IAM Role 연결 확인: `aws sts get-caller-identity`
  - [ ] RDS 연결 테스트: `psql -h dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com -U admin -d ddoksori`

  **Commit**: NO (인프라 작업)

  **User Data Script**:
  ```bash
  #!/bin/bash
  apt-get update
  apt-get install -y docker.io docker-compose-v2 awscli jq postgresql-client
  systemctl enable docker
  systemctl start docker
  usermod -aG docker ubuntu
  ```

---

- [ ] 2.6. S3 버킷 생성 (us-east-1)

  **What to do**:
  - 버킷명: ddoksori-uploads-[account-id]
  - **리전: us-east-1** (EC2/RDS와 동일)
  - Public Access: Block all (Pre-signed URL 사용)
  - CORS 설정: 프론트엔드 도메인 허용
  - Lifecycle: 90일 후 IA 전환 (선택)

  **Must NOT do**:
  - Public read 정책 설정 금지
  - 다른 리전에 버킷 생성 금지

  **Parallelizable**: YES (독립적)

  **Acceptance Criteria**:
  - [ ] 버킷 생성: `aws s3 ls --region us-east-1 | grep ddoksori-uploads`
  - [ ] CORS 설정 확인: `aws s3api get-bucket-cors --bucket ddoksori-uploads-xxx`
  - [ ] Public Access Block 확인

  **Commit**: NO (인프라 작업)

---

- [ ] 2.7. ALB 및 Target Group 생성

  **What to do**:
  - ALB 생성 (Internet-facing, Public Subnets)
  - Target Group 생성 (HTTP:80, Health check: /health)
  - EC2 2대를 Target Group에 등록
  - Listener: HTTP:80 (임시, ACM 인증서 후 HTTPS 추가)

  **Must NOT do**:
  - Internal ALB 생성 금지

  **Parallelizable**: NO (depends on 2.5)

  **Acceptance Criteria**:
  - [ ] ALB 상태: active
  - [ ] Target Group: 2 targets healthy
  - [ ] ALB DNS로 접근: `curl http://[alb-dns]/health` → 200 OK

  **Commit**: NO (인프라 작업)

---

- [ ] 2.8. Route53 Hosted Zone 및 레코드 생성

  **What to do**:
  - 도메인 구매 또는 기존 도메인 사용
  - Hosted Zone 생성
  - A 레코드 (Alias) → ALB
  - 서브도메인 설정: `api.도메인` (선택)

  **Must NOT do**:
  - A 레코드에 IP 직접 입력 금지 (Alias 사용)

  **Parallelizable**: NO (depends on 2.7)

  **Acceptance Criteria**:
  - [ ] Hosted Zone 생성: `aws route53 list-hosted-zones`
  - [ ] A 레코드 확인: `dig [도메인]` → ALB IP 반환
  - [ ] 브라우저 접근: `http://[도메인]` → 서비스 응답

  **Commit**: NO (인프라 작업)

---

- [ ] 2.9. ACM 인증서 발급 및 HTTPS 설정

  **What to do**:
  - ACM에서 인증서 요청 (도메인)
  - DNS 검증 (Route53 자동 CNAME 추가)
  - ALB Listener에 HTTPS:443 추가
  - HTTP:80 → HTTPS 리다이렉트 설정

  **Must NOT do**:
  - HTTP만으로 운영 금지

  **Parallelizable**: NO (depends on 2.8)

  **Acceptance Criteria**:
  - [ ] 인증서 상태: Issued
  - [ ] HTTPS 접근: `curl -I https://[도메인]` → 200 OK
  - [ ] HTTP 리다이렉트: `curl -I http://[도메인]` → 301/302 to HTTPS

  **Commit**: NO (인프라 작업)

---

### Phase 2 완료 체크포인트

```bash
# 인프라 상태 확인 (us-east-1)
aws ec2 describe-instances --region us-east-1 --filters "Name=tag:Name,Values=ddoksori-*" --query 'Reservations[].Instances[].State.Name'
aws rds describe-db-instances --region us-east-1 --db-instance-identifier dsr-postgres --query 'DBInstances[0].DBInstanceStatus'
aws elbv2 describe-load-balancers --region us-east-1 --names ddoksori-alb --query 'LoadBalancers[0].State.Code'

# 연결 테스트
curl -I https://[도메인]  # → 200 또는 502 (앱 미배포 시)

# EC2에서 기존 RDS 연결 테스트
psql -h dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com -U admin -d ddoksori -c "SELECT COUNT(*) FROM vector_chunks;"
# → 40285
```

**Phase 2 완료 조건**:
- [ ] VPC, Subnet, SG 생성 완료 (us-east-1)
- [ ] EC2 2대 running (us-east-1a, us-east-1b)
- [ ] **기존 RDS 연결 성공** (dsr-postgres)
- [ ] HTTPS로 ALB 접근 가능
- [ ] 인프라 구성 문서화 완료

---

### Phase 3: 데이터 검증 (마이그레이션 불필요)

> 목표: **기존 RDS 데이터 무결성 확인** (신규 마이그레이션 불필요)

**⚠️ 중요**: 기존 RDS(`dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com`)에 이미 모든 데이터가 존재합니다.
- `vector_chunks`: 40,285 rows (임베딩 포함)
- 임베딩 모델: **text-embedding-3-large** (1536 dimensions)
- pgvector 확장 이미 설치됨

---

- [ ] 3.1. 기존 RDS 데이터 검증

  **What to do**:
  - EC2에서 기존 RDS 연결
  - 테이블 목록 및 row count 확인
  - 임베딩 데이터 무결성 확인
  - **벡터 차원 확인: 1536 (text-embedding-3-large)**

  **Must NOT do**:
  - 기존 데이터 삭제/수정
  - 로컬 데이터로 덮어쓰기
  - 스키마 DROP/재생성

  **Parallelizable**: NO

  **Acceptance Criteria**:
  - [ ] 테이블 목록 확인: `\dt` → vector_chunks, disputes 등 존재
  - [ ] 데이터 확인: `SELECT COUNT(*) FROM vector_chunks;` → 40,285
  - [ ] 벡터 차원 확인: `SELECT vector_dims(embedding) FROM vector_chunks LIMIT 1;` → **1536**
  - [ ] NULL 임베딩 없음: `SELECT COUNT(*) FROM vector_chunks WHERE embedding IS NULL;` → 0

  **Commit**: NO (검증 작업)

---

- [ ] 3.2. 벡터 검색 동작 테스트

  **What to do**:
  - 샘플 쿼리로 벡터 유사도 검색 테스트
  - **임베딩 차원: 1536** (text-embedding-3-large)
  - HNSW 인덱스 동작 확인

  **Must NOT do**:
  - 1024 차원(KURE-v1) 가정 금지 → **1536 차원(text-embedding-3-large) 사용**

  **Parallelizable**: NO (depends on 3.1)

  **Acceptance Criteria**:
  - [ ] 벡터 검색 테스트 (Python 또는 psql):
    ```sql
    -- 샘플 벡터로 유사도 검색 (1536차원)
    SELECT id, chunk_text, embedding <=> '[0.1, 0.2, ...]'::vector(1536) as distance
    FROM vector_chunks
    ORDER BY distance
    LIMIT 5;
    ```
  - [ ] 응답 시간 < 1초
  - [ ] 관련 결과 반환 확인

  **Commit**: NO (검증 작업)

---

### Phase 3 완료 체크포인트

```sql
-- RDS에서 실행 (dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com)

-- 1. 테이블 및 row count 확인
SELECT schemaname, relname, n_live_tup 
FROM pg_stat_user_tables 
ORDER BY n_live_tup DESC;

-- 2. 벡터 차원 확인 (1536 예상)
SELECT vector_dims(embedding) FROM vector_chunks LIMIT 1;

-- 3. pgvector 확장 확인
SELECT * FROM pg_extension WHERE extname = 'vector';

-- 4. HNSW 인덱스 확인
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'vector_chunks';
```

**Phase 3 완료 조건**:
- [ ] 기존 데이터 무결성 확인 (40,285 rows)
- [ ] 벡터 차원 1536 확인 (text-embedding-3-large)
- [ ] 벡터 검색 동작 확인

---

### Phase 4: 시크릿 설정

> 목표: AWS Secrets Manager에 시크릿 저장 및 연동

---

- [ ] 4.1. Secrets Manager에 시크릿 생성

  **What to do**:
  - `ddoksori/db`: DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
    - DB_HOST: `dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com`
  - `ddoksori/api-keys`: OPENAI_API_KEY, ANTHROPIC_API_KEY
  - `ddoksori/runpod`: EXAONE_RUNPOD_URL, EXAONE_RUNPOD_API_KEY
    - EXAONE_RUNPOD_URL: `http://localhost:19010/v1` (SSH 터널 통해 접근)
  - `ddoksori/app`: SECRET_KEY, CORS_ORIGINS
  - **`ddoksori/models`**: 모델 설정 (AI_MEMO.md 기준)
    - SUPERVISOR_MODEL: `gpt-5.1`
    - SUPERVISOR_FALLBACK_1: `claude-3-5-sonnet`
    - DRAFT_MODEL: `gpt-4o`
    - DRAFT_FALLBACK: `gpt-4o-mini`
    - REVIEW_MODEL: `gpt-4o`
    - RETRIEVAL_LLM_MODEL: `exaone-4.0-1.2b`
    - RETRIEVAL_FALLBACK: `gpt-4.1-nano`
  - **`ddoksori/embedding`**: 임베딩 설정
    - EMBEDDING_MODEL: `text-embedding-3-large`
    - EMBEDDING_DIMENSION: `1536`

  **Must NOT do**:
  - 평문으로 시크릿 전송 금지 (HTTPS 사용)
  - 잘못된 모델명/차원 입력 금지

  **Parallelizable**: YES (독립적)

  **Acceptance Criteria**:
  - [ ] 시크릿 생성 확인: `aws secretsmanager list-secrets --region us-east-1 --filter Key=name,Values=ddoksori`
  - [ ] 시크릿 조회 테스트: `aws secretsmanager get-secret-value --region us-east-1 --secret-id ddoksori/db`
  - [ ] 모델 설정 확인: `aws secretsmanager get-secret-value --region us-east-1 --secret-id ddoksori/models`
  - [ ] 임베딩 설정 확인: `aws secretsmanager get-secret-value --region us-east-1 --secret-id ddoksori/embedding`

  **Commit**: NO (인프라 작업)

---

- [ ] 4.2. EC2 IAM Role 권한 확인

  **What to do**:
  - EC2에 연결된 IAM Role에 SecretsManagerReadWrite 정책 확인
  - 필요시 인라인 정책 추가 (ddoksori/* 리소스만 허용)

  **Parallelizable**: NO (depends on 4.1)

  **Acceptance Criteria**:
  - [ ] EC2에서 시크릿 조회: `aws secretsmanager get-secret-value --secret-id ddoksori/db`
  - [ ] 권한 오류 없음

  **Commit**: NO (인프라 작업)

---

### Phase 4 완료 체크포인트

```bash
# EC2에서 실행
aws secretsmanager get-secret-value --secret-id ddoksori/db --query SecretString --output text | jq
aws secretsmanager get-secret-value --secret-id ddoksori/api-keys --query SecretString --output text | jq
```

**Phase 4 완료 조건**:
- [ ] 모든 시크릿 Secrets Manager에 저장
- [ ] EC2에서 시크릿 조회 가능

---

### Phase 5: 배포 및 검증

> 목표: 실제 서비스 배포 및 E2E 테스트

---

- [ ] 5.1. GHCR에 이미지 푸시

  **What to do**:
  - GitHub Personal Access Token 생성 (packages:write)
  - 로컬에서 이미지 빌드 및 푸시
  - 태그: `v1.0.0`, `latest`

  **Parallelizable**: NO

  **References**:
  - `backend/Dockerfile.prod`
  - `frontend/Dockerfile.prod`

  **Acceptance Criteria**:
  - [ ] 로그인 성공: `echo $PAT | docker login ghcr.io -u [username] --password-stdin`
  - [ ] 푸시 성공: `docker push ghcr.io/[owner]/ddoksori-backend:v1.0.0`
  - [ ] GitHub Packages에서 이미지 확인

  **Commit**: NO (이미지 푸시)

---

- [ ] 5.2. EC2에서 수동 배포

  **What to do**:
  - EC2에 SSH 접속
  - GHCR 로그인
  - docker-compose.prod.yml 복사
  - 시크릿 로드 스크립트 실행
  - docker compose up -d

  **Parallelizable**: NO (depends on 5.1)

  **Acceptance Criteria**:
  - [ ] 컨테이너 실행: `docker compose ps` → 3 services running
  - [ ] 로그 확인: `docker compose logs backend` → 에러 없음
  - [ ] Health check: `curl http://localhost/api/health` → 200 OK

  **Commit**: NO (배포 작업)

---

- [ ] 5.3. RunPod SSH 터널 설정 (systemd)

  **What to do**:
  - EC2에 RunPod SSH 키 배치
  - systemd 서비스 파일 생성
  - **터널 포트: 19010** (EXAONE-4.0-1.2B)
  - 터널 자동 시작 및 재연결 설정

  **Must NOT do**:
  - 포트 19080 사용 금지 (구버전) → **19010 사용**

  **Parallelizable**: YES (with 5.2)

  **References**:
  - `scripts/start_laptop.sh:1-85` - SSH 터널 패턴
  - AI_MEMO.md - RunPod 포트 19010

  **systemd 서비스 예시**:
  ```ini
  [Unit]
  Description=RunPod SSH Tunnel for EXAONE
  After=network.target

  [Service]
  Type=simple
  User=ubuntu
  ExecStart=/usr/bin/ssh -N -L 19010:localhost:8000 root@[runpod-ip] -i /home/ubuntu/.ssh/runpod_key
  Restart=always
  RestartSec=10

  [Install]
  WantedBy=multi-user.target
  ```

  **Acceptance Criteria**:
  - [ ] 서비스 파일 생성: `/etc/systemd/system/runpod-tunnel.service`
  - [ ] 서비스 시작: `sudo systemctl start runpod-tunnel`
  - [ ] 터널 확인: `curl http://localhost:19010/health` → RunPod 응답
  - [ ] EXAONE API 테스트: `curl http://localhost:19010/v1/models` → 모델 목록

  **Commit**: NO (인프라 작업)

---

- [ ] 5.4. E2E 테스트 (Fallback Chain 포함)

  **What to do**:
  - 브라우저에서 `https://[도메인]` 접속
  - 채팅 기능 테스트 (분쟁 상담, 일반 상담)
  - 출처 인용 확인
  - 게시판 기능 테스트
  - **Fallback Chain 테스트**

  **Fallback Chain 테스트 시나리오** (AI_MEMO.md 기준):
  1. **Supervisor Fallback**: GPT-5.1 실패 시 → Claude 3.5 Sonnet → Rule-based
  2. **Draft Agent Fallback**: gpt-4o 실패 시 → gpt-4o-mini → rule_based
  3. **Retrieval LLM Fallback**: EXAONE 실패 시 → gpt-4.1-nano → original query

  **테스트 방법**:
  - RunPod 터널 중지 후 채팅 테스트 → Retrieval fallback 동작 확인
  - 로그에서 fallback 전환 메시지 확인

  **Parallelizable**: NO (depends on 5.2, 5.3)

  **Acceptance Criteria**:
  - [ ] 홈페이지 로드 확인
  - [ ] 채팅 메시지 전송 및 응답 수신
  - [ ] 출처 [N] 클릭 시 모달 표시
  - [ ] 이미지 업로드 (S3) 동작 확인
  - [ ] **Fallback 테스트**: RunPod 중지 시에도 응답 생성 (gpt-4.1-nano fallback)
  - [ ] **로그 확인**: `docker compose logs backend | grep -i fallback`

  **Commit**: NO (테스트)

---

### Phase 5 완료 체크포인트

```bash
# 서비스 상태 확인
curl -I https://[도메인]                    # → 200 OK
curl https://[도메인]/api/health            # → {"status": "healthy"}
curl -X POST https://[도메인]/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "환불 규정 알려줘"}'       # → 응답 수신
```

**Phase 5 완료 조건**:
- [ ] 외부에서 HTTPS 접근 가능
- [ ] 채팅 기능 정상 동작
- [ ] 2대 EC2 모두 healthy

---

### Phase 6: CI/CD 자동화

> 목표: main 브랜치 push 시 자동 배포

---

- [ ] 6.1. GitHub Actions 워크플로우 작성

  **What to do**:
  - `.github/workflows/deploy.yml` 생성
  - Trigger: push to main
  - Jobs: build-backend, build-frontend, deploy
  - GHCR 푸시 및 EC2 SSH 배포

  **Must NOT do**:
  - 시크릿을 로그에 출력 금지
  - latest 태그만 사용 금지 (SHA 태그 병행)

  **Parallelizable**: NO

  **References**:
  - `.github/workflows/opencode.yml` - 기존 워크플로우 패턴

  **Acceptance Criteria**:
  - [ ] 파일 생성: `.github/workflows/deploy.yml`
  - [ ] 워크플로우 문법 검증: GitHub Actions 탭에서 에러 없음
  - [ ] 테스트 실행: 수동 workflow_dispatch로 트리거

  **Commit**: YES
  - Message: `feat(ci): add GitHub Actions deployment workflow`
  - Files: `.github/workflows/deploy.yml`

---

- [ ] 6.2. GitHub Secrets 설정

  **What to do**:
  - Repository Settings → Secrets → Actions
  - `EC2_HOST`: EC2 Public IP 또는 도메인
  - `EC2_SSH_KEY`: SSH 프라이빗 키
  - `GHCR_PAT`: GitHub Personal Access Token

  **Must NOT do**:
  - AWS Access Key 사용 금지 (EC2 IAM Role 사용)

  **Parallelizable**: YES (with 6.1)

  **Acceptance Criteria**:
  - [ ] 3개 Secrets 등록 확인
  - [ ] 워크플로우에서 시크릿 참조 가능

  **Commit**: NO (GitHub 설정)

---

- [ ] 6.3. 자동 배포 테스트

  **What to do**:
  - README.md에 사소한 변경 후 main에 push
  - GitHub Actions 실행 확인
  - 배포 완료 후 서비스 동작 확인

  **Parallelizable**: NO (depends on 6.1, 6.2)

  **Acceptance Criteria**:
  - [ ] Actions 탭: 워크플로우 성공 (녹색 체크)
  - [ ] 배포 시간: 5분 이내
  - [ ] 서비스 무중단 확인

  **Commit**: YES (테스트용 커밋)

---

### Phase 6 완료 체크포인트

```bash
# 커밋 후 자동 배포 확인
git add . && git commit -m "test: trigger auto deploy" && git push origin main

# GitHub Actions 모니터링
# https://github.com/[owner]/[repo]/actions

# 배포 완료 후 버전 확인
curl https://[도메인]/api/health  # → 새 버전 배포 확인
```

**Phase 6 완료 조건**:
- [ ] main push 시 자동 배포 동작
- [ ] 배포 실패 시 알림 (GitHub Actions)
- [ ] 롤백 절차 문서화

---

### Phase 7: 추후 개선 (AWS 네이티브 통합)

> 목표: MVP 이후 확장성, 보안, 모니터링 강화

---

- [ ] 7.1. CloudFront CDN 도입

  **Why**: 정적 자산 캐싱, 글로벌 지연시간 감소, DDoS 보호

  **What to do**:
  - CloudFront Distribution 생성
  - Origin: ALB
  - 캐시 정책: 정적 파일 장기 캐싱
  - Route53 레코드를 CloudFront로 변경

  **Expected Benefit**:
  - 정적 자산 로딩 속도 50%+ 향상
  - ALB 부하 감소
  - 기본 DDoS 방어

  **Estimated Cost**: ~$5-10/월 (트래픽에 따라)

---

- [ ] 7.2. Auto Scaling Group 도입

  **Why**: 트래픽 증가 시 자동 확장, 비용 최적화

  **What to do**:
  - Launch Template 생성 (현재 EC2 설정 기반)
  - Auto Scaling Group 생성
  - Scaling Policy: CPU 70% 초과 시 확장
  - 최소 2대, 최대 4대

  **Expected Benefit**:
  - 트래픽 급증 대응
  - 장애 시 자동 복구
  - 비용 최적화 (야간 축소)

  **Estimated Cost**: 사용량 기반 (기존과 유사하거나 절감)

---

- [ ] 7.3. CloudWatch 모니터링 강화

  **Why**: 실시간 모니터링, 알림, 로그 중앙화

  **What to do**:
  - CloudWatch Agent 설치 (EC2)
  - 커스텀 메트릭: 응답시간, 에러율
  - 알람 설정: CPU > 80%, 5xx 에러 > 10
  - 로그 그룹: /ddoksori/backend, /ddoksori/frontend

  **Expected Benefit**:
  - 실시간 장애 감지
  - 성능 추이 분석
  - 로그 검색 용이

  **Estimated Cost**: ~$3-5/월

---

- [ ] 7.4. WAF (Web Application Firewall) 적용

  **Why**: SQL Injection, XSS 등 웹 공격 방어

  **What to do**:
  - WAF Web ACL 생성
  - AWS Managed Rules 적용 (Core Rule Set)
  - ALB에 연결
  - Rate Limiting 설정

  **Expected Benefit**:
  - 웹 취약점 공격 차단
  - 악성 봇 차단
  - 규정 준수 (보안 감사)

  **Estimated Cost**: ~$5-10/월

---

- [ ] 7.5. RDS Multi-AZ 및 Read Replica

  **Why**: 데이터베이스 고가용성, 읽기 성능 향상

  **What to do**:
  - Multi-AZ 활성화 (장애 시 자동 failover)
  - Read Replica 추가 (읽기 쿼리 분산)
  - 애플리케이션에서 읽기/쓰기 엔드포인트 분리

  **Expected Benefit**:
  - DB 장애 시 자동 복구 (30초 이내)
  - 읽기 성능 2배 향상

  **Estimated Cost**: +$17/월 (Multi-AZ), +$17/월 (Read Replica)

---

- [ ] 7.6. ElastiCache Redis 도입

  **Why**: 세션/캐시 공유, EC2 간 상태 동기화

  **What to do**:
  - ElastiCache Redis 클러스터 생성
  - 애플리케이션에서 Redis 엔드포인트 변경
  - 세션 저장소로 활용

  **Expected Benefit**:
  - EC2 간 세션 공유
  - 캐시 히트율 향상
  - 관리형 서비스로 운영 부담 감소

  **Estimated Cost**: ~$15/월 (cache.t3.micro)

---

- [ ] 7.7. Terraform IaC 전환

  **Why**: 인프라 버전 관리, 재현 가능성, 협업

  **What to do**:
  - 현재 수동 생성 리소스를 Terraform import
  - 모듈화: vpc, rds, ec2, alb, route53
  - GitHub에 terraform/ 디렉토리 추가
  - CI에서 terraform plan 자동 실행

  **Expected Benefit**:
  - 인프라 변경 이력 추적
  - 환경 복제 용이 (staging, production)
  - 코드 리뷰로 변경 검증

  **Estimated Cost**: $0 (Terraform 무료)

---

## Success Criteria

### Verification Commands

```bash
# Phase 5 완료 후 MVP 검증
curl -I https://[도메인]                           # → 200 OK
curl https://[도메인]/api/health                   # → {"status": "healthy"}
curl -X POST https://[도메인]/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "환불 규정 알려줘"}'             # → 채팅 응답

# Phase 6 완료 후 CI/CD 검증
# GitHub Actions에서 녹색 체크 확인
# main push → 5분 이내 배포 완료
```

### Final Checklist

- [ ] 외부에서 HTTPS로 서비스 접근 가능
- [ ] 채팅 기능 (분쟁/일반) 정상 동작
- [ ] 출처 인용 표시 정상
- [ ] main 브랜치 push 시 자동 배포
- [ ] 월 비용 $130 이내
- [ ] EC2 1대 장애 시 서비스 지속 (ALB failover)
- [ ] 시크릿이 코드/로그에 노출되지 않음
- [ ] 배포/롤백 문서 완성

---

## Commit Strategy

| Phase | Task | Commit Message | Files |
|-------|------|----------------|-------|
| 1 | 1.1 | `feat(deploy): add production Dockerfile for backend` | `backend/Dockerfile.prod` |
| 1 | 1.2 | `feat(deploy): add production Dockerfile for frontend with nginx` | `frontend/Dockerfile.prod` |
| 1 | 1.3 | `feat(deploy): add nginx configuration for frontend` | `frontend/nginx.conf` |
| 1 | 1.4 | `feat(deploy): add production docker-compose for AWS deployment` | `docker-compose.prod.yml` |
| 1 | 1.5 | `feat(deploy): add secrets manager loading script` | `scripts/load-secrets.sh` |
| 6 | 6.1 | `feat(ci): add GitHub Actions deployment workflow` | `.github/workflows/deploy.yml` |

---

## Rollback Procedures

### Phase 5 롤백 (배포 실패 시)
```bash
# EC2에서 실행
docker compose -f docker-compose.prod.yml down
docker pull ghcr.io/[owner]/ddoksori-backend:[previous-tag]
docker pull ghcr.io/[owner]/ddoksori-frontend:[previous-tag]
# docker-compose.prod.yml에서 이미지 태그 수정
docker compose -f docker-compose.prod.yml up -d
```

### Phase 3 롤백 (데이터 손실 시)
```bash
# 백업에서 복원
psql -h [rds-endpoint] -U admin -d ddoksori < backend/backups/ddoksori_backup_[date].sql
```

### Phase 2 롤백 (인프라 문제 시)
- AWS 콘솔에서 리소스 삭제
- 로컬 개발 환경으로 복귀
- 문제 원인 분석 후 재시도

---

## Risk Mitigation

| 리스크 | 확률 | 영향 | 대응 |
|--------|------|------|------|
| RDS 연결 실패 | 중 | 높음 | Security Group 확인, 로컬 테스트 |
| GHCR 접근 불가 | 낮 | 중 | PAT 갱신, 로컬 이미지 캐시 |
| RunPod 연결 끊김 | 중 | 중 | systemd 자동 재시작, OpenAI fallback |
| 비용 초과 | 낮 | 중 | AWS Budget Alert 설정 |
| SSL 인증서 만료 | 낮 | 높음 | ACM 자동 갱신 (관리형) |
