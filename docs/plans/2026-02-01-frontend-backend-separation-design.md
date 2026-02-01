# 프론트엔드-백엔드 독립 분리 + ALB 아키텍처 계획

## 현재 상태 (AS-IS)

```
사용자 → EC2:80 (nginx 컨테이너)
              ├── 정적 파일 (React SPA) 서빙
              └── /chat, /search, /auth 등 → backend:8000 프록시
         EC2:8000 (backend 컨테이너) → RDS (PostgreSQL)
         EC2:6379 (redis 컨테이너)
```

- 단일 EC2에 docker-compose로 3개 컨테이너 (frontend/nginx, backend/gunicorn, redis)
- nginx가 리버스 프록시 역할 (SPA 라우팅 + API 프록시)
- 프론트엔드 `VITE_API_BASE_URL`로 백엔드 주소 설정 (빌드 타임)

## 목표 상태 (TO-BE)

```
사용자 → CloudFront (CDN)
              ├── S3 Origin: React SPA 정적 파일
              └── ALB Origin: /api/* → Backend (모든 API에 /api prefix)
         ALB → EC2 (backend + redis만)
              └── Backend:8000 → RDS (PostgreSQL)
```

### 아키텍처 구성도

```
┌─────────────┐
│   사용자      │
└─────┬───────┘
      │ HTTPS
┌─────▼───────────────────────────┐
│       CloudFront Distribution    │
│  ┌────────────┬─────────────┐   │
│  │ Default(*) │ /api/*      │   │
│  │ → S3 버킷   │ → ALB Origin│   │
│  └────────────┴─────────────┘   │
└──────────────────────────────────┘
      │                    │
      ▼                    ▼
┌──────────┐    ┌──────────────────┐
│ S3 Bucket │    │       ALB        │
│ (React    │    │ (Target Group)   │
│  SPA)     │    └────────┬─────────┘
└──────────┘              │
                  ┌───────▼────────┐
                  │  EC2 Instance  │
                  │  ┌──────────┐  │
                  │  │ Backend  │  │
                  │  │ :8000    │  │
                  │  ├──────────┤  │
                  │  │ Redis    │  │
                  │  │ :6379    │  │
                  │  └──────────┘  │
                  └───────┬────────┘
                          │
                  ┌───────▼────────┐
                  │   AWS RDS      │
                  │  (PostgreSQL)  │
                  └────────────────┘
```

## 구현 단계

### Phase 1: 프론트엔드 + 백엔드 코드 변경

**1-1. 백엔드 API에 `/api` prefix 추가 (필수)**

> **[검토 결과 발견] 경로 충돌 문제**
> 현재 프론트엔드 SPA 라우트와 백엔드 API 경로가 충돌합니다:
> - `/chat` → 프론트엔드 ChatPage 라우트 **AND** 백엔드 chat API
> - `/admin/*` → 프론트엔드 AdminLayout **AND** 백엔드 admin API
>
> CloudFront Behavior에서 `/chat*`을 ALB로 보내면 브라우저의 `/chat` 페이지 탐색도
> ALB로 가서 SPA가 깨집니다. **반드시 백엔드 API에 `/api` prefix를 붙여야 합니다.**

**백엔드 변경할 파일:**

| 파일 | 현재 prefix | 변경 후 |
|------|------------|---------|
| `backend/app/api/chat.py` | `/chat` | `/api/chat` |
| `backend/app/api/search.py` | `/search` | `/api/search` |
| `backend/app/api/auth.py` | `/auth` | `/api/auth` |
| `backend/app/api/case.py` | `/case` | `/api/case` |
| `backend/app/api/health.py` | `/health` | `/api/health` |
| `backend/app/api/metrics.py` | `/metrics` | `/api/metrics` |
| `backend/app/api/admin.py` | `/api/admin` | `/api/admin` (이미 OK) |
| `backend/app/main.py` | 라우터 등록 | prefix 변경 또는 최상위 `/api` prefix 추가 |

**방법**: `main.py`에서 라우터 등록 시 최상위 prefix를 `/api`로 설정하거나, 각 라우터의 prefix를 개별 변경.

**1-2. 프론트엔드 API 클라이언트 수정**

> **[검토 결과 발견] `VITE_API_BASE_URL` fallback 버그**
> 현재 코드: `import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'`
> - 빌드 시 `VITE_API_BASE_URL=""`로 설정하면 빈 문자열은 JS에서 **falsy**
> - `||` 연산자에 의해 `'http://localhost:8000'`으로 fallback됨
> - **프로덕션에서 localhost:8000으로 API를 호출하는 심각한 버그 발생**

| 파일 | 변경 내용 |
|------|----------|
| `frontend/src/shared/api/client.ts` | fallback을 `'/api'`로 변경: `VITE_API_BASE_URL \|\| '/api'` |
| `frontend/src/features/chat/hooks/useStreamingChat.ts` | 동일하게 fallback을 `'/api'`로 변경 |

변경 후 프론트엔드에서 API 호출: `fetch('/api/chat/stream', ...)` → CloudFront가 `/api/*` 패턴을 ALB로 라우팅

**1-3. OAuth 콜백 URL 업데이트**

| 파일 | 변경 내용 |
|------|----------|
| `backend/app/auth/service.py` | Google/Naver OAuth redirect_uri를 CloudFront 도메인으로 변경 |
| `backend/app/api/auth.py` | 콜백 성공 시 redirect URL의 `frontend_url`이 CloudFront 도메인인지 확인 |
| Google/Naver OAuth Console | Authorized redirect URI에 CloudFront 도메인 추가 |

### **선택: CloudFront Behavior 라우팅 (same-origin)**

이유:
1. CORS 설정 불필요 (same-origin)
2. SSE 스트리밍이 same-origin이라 브라우저 제한 없음
3. 사용자에게 단일 도메인 노출 (`ddoksori.com`)
4. CloudFront Behavior가 단 2개로 단순화 (`/api/*` → ALB, `*` → S3)

### Phase 2: AWS 인프라 구성

**2-1. S3 버킷 생성**

```
버킷명: ddoksori-frontend-{env}
설정:
  - 정적 웹사이트 호스팅: 비활성 (CloudFront OAC로 접근)
  - 퍼블릭 액세스: 차단
  - OAC (Origin Access Control): CloudFront만 접근 가능
```

**2-2. CloudFront Distribution**

> **[검토 결과] Behavior가 2개로 단순화됨**
> `/api` prefix 도입으로 경로별 Behavior 6개 → 단일 `/api/*` Behavior로 통합

```yaml
Origins:
  - S3Origin:
      DomainName: ddoksori-frontend-prod.s3.ap-northeast-2.amazonaws.com
      OriginAccessControl: OAC 설정 (Origin Access Control, OAI 대신 최신 방식)
  - ALBOrigin:
      DomainName: ALB DNS 이름
      Protocol: HTTP only (ALB → Backend은 내부 통신)
      CustomHeaders:
        X-Custom-Header: 시크릿값 (ALB가 CloudFront 외 접근 차단용)

Behaviors:
  # Behavior 1: 모든 API 요청 → ALB
  - /api/*:
      Origin: ALBOrigin
      CachePolicy: CachingDisabled
      OriginRequestPolicy: AllViewerExceptHostHeader
      AllowedMethods: GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE
      # SSE (/api/chat/stream)도 이 Behavior에 포함됨
      # CachingDisabled이면 CloudFront가 chunked response를 그대로 스트리밍

  # Behavior 2: 나머지 모두 → S3 (정적 파일 + SPA)
  - Default (*):
      Origin: S3Origin
      CachePolicy: CachingOptimized
      ViewerProtocolPolicy: redirect-to-https
      FunctionAssociations:
        - EventType: viewer-request
          FunctionARN: SPA-Routing-Function  # 아래 참조

# ⚠️ CustomErrorResponses 사용 금지!
# CustomErrorResponses는 Distribution 전역에 적용되어 ALB Origin의
# 에러 응답(401, 403, 404, 500)도 index.html로 덮어씁니다.
# 대신 CloudFront Function을 사용합니다.
```

**2-2-1. CloudFront Function (SPA 라우팅용)**

> **[검토 결과 발견] CustomErrorResponses의 치명적 문제**
> `CustomErrorResponses`는 CloudFront **전체 Distribution**에 적용됩니다.
> ALB Origin에서 반환하는 HTTP 에러 코드(401 Unauthorized, 404 Not Found 등)도
> `index.html + 200 OK`로 덮어쓰여서 프론트엔드 에러 핸들링이 완전히 깨집니다.
>
> **해결**: S3 Behavior의 Viewer Request에만 CloudFront Function을 연결하여
> 파일 확장자가 없는 경로를 `/index.html`로 rewrite합니다.

```javascript
// CloudFront Function: spa-routing
function handler(event) {
  var request = event.request;
  var uri = request.uri;

  // 파일 확장자가 있으면 그대로 (*.js, *.css, *.png 등)
  if (uri.includes('.')) {
    return request;
  }

  // 파일 확장자 없는 경로 → SPA index.html로 rewrite
  // 예: /chat, /procedure, /board, /mypage, /admin/dashboard
  request.uri = '/index.html';
  return request;
}
```

```yaml
# HTTPS
ViewerCertificate:
  # ⚠️ CloudFront용 ACM 인증서는 반드시 us-east-1 리전에서 발급!
  # ap-northeast-2가 아닌 us-east-1임에 주의
  ACMCertificateArn: us-east-1 리전의 ACM 인증서 (*.ddoksori.com)
  SSLSupportMethod: sni-only
  MinimumProtocolVersion: TLSv1.2_2021

Aliases:
  - ddoksori.com
  - www.ddoksori.com

# WAF (선택 사항, 권장)
WebACLId: AWS WAF 연결 시 rate limiting, IP blocking 등 가능
```

**2-3. ALB (Application Load Balancer)**

```yaml
ALB:
  Scheme: internet-facing  # CloudFront에서 접근 가능
  Listeners:
    - Port: 80
      Protocol: HTTP
      DefaultAction: forward to TargetGroup

  # 보안: CloudFront에서만 접근 허용
  SecurityGroup:
    Inbound:
      - CloudFront Managed Prefix List (com.amazonaws.global.cloudfront.origin-facing)
      - Port: 80

TargetGroup:
  Protocol: HTTP
  Port: 8000
  HealthCheck:
    Path: /api/health
    Interval: 30s
    Timeout: 10s
    HealthyThreshold: 2
    UnhealthyThreshold: 3
  Targets:
    - EC2 Instance (backend)
```

**2-4. EC2 변경 (백엔드 전용)**

```yaml
# docker-compose.prod.yml 에서 frontend 서비스 제거
# backend + redis만 남김

services:
  backend:
    image: ${ECR_REGISTRY}/ddoksori-backend:${IMAGE_TAG:-latest}
    restart: always
    ports:
      - "8000:8000"
    # ... (기존 환경변수 유지)
    # CORS 변경 필요:
    environment:
      - CORS_ORIGINS=https://ddoksori.com,https://www.ddoksori.com
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    depends_on:
      redis:
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

# frontend 서비스 완전 제거
```

### Phase 3: CI/CD 파이프라인 변경

**3-1. build.yml 변경**

```yaml
# 기존: 백엔드 ECR 빌드 + 프론트엔드 ECR 빌드
# 변경: 백엔드 ECR 빌드 + 프론트엔드 S3 업로드

jobs:
  build-backend:
    # ECR 빌드 (기존과 동일)

  build-frontend:
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci
        working-directory: ./frontend
      - run: npm run build
        working-directory: ./frontend
        env:
          VITE_API_BASE_URL: "/api"  # CloudFront /api/* → ALB 라우팅
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ap-northeast-2
      - name: Sync to S3
        run: |
          aws s3 sync ./frontend/dist s3://ddoksori-frontend-prod \
            --delete \
            --cache-control "public, max-age=31536000, immutable" \
            --exclude "index.html" \
            --exclude "*.json"
          # index.html은 캐시하지 않음
          aws s3 cp ./frontend/dist/index.html s3://ddoksori-frontend-prod/index.html \
            --cache-control "no-cache, no-store, must-revalidate"
      - name: Invalidate CloudFront
        run: |
          aws cloudfront create-invalidation \
            --distribution-id ${{ secrets.CLOUDFRONT_DISTRIBUTION_ID }} \
            --paths "/index.html" "/"
```

**3-2. deploy-production.yml 변경**

```yaml
# 프론트엔드: S3 + CloudFront invalidation (build에서 이미 처리)
# 백엔드: EC2 SSH 배포 (기존 유사하지만 frontend 컨테이너 없음)

deploy:
  steps:
    - name: Deploy Backend to EC2
      uses: appleboy/ssh-action@v1.0.0
      with:
        host: ${{ env.EC2_HOST }}
        script: |
          cd /home/ec2-user/ddoksori
          # ECR Login
          aws ecr get-login-password --region ap-northeast-2 | docker login ...
          # Pull & deploy (frontend 없이)
          export ECR_REGISTRY=...
          export IMAGE_TAG=...
          docker compose -f docker-compose.prod.yml pull
          docker compose -f docker-compose.prod.yml up -d --remove-orphans

    - name: Health Check via ALB
      run: |
        # ALB를 통한 헬스체크 (/api prefix 적용)
        curl -f https://ddoksori.com/api/health || exit 1
```

### Phase 4: SSE 스트리밍 지원 확인

**CloudFront에서 SSE가 동작하려면:**

1. **Cache Policy**: `CachingDisabled` (필수 - SSE는 캐시하면 안 됨)
2. **Origin Request Policy**: `AllViewerExceptHostHeader` 또는 커스텀
3. **CloudFront timeout**: Origin Response Timeout을 120초 이상으로 설정 (LLM 응답 대기)
4. **Transfer-Encoding**: CloudFront가 chunked encoding을 기본 지원

현재 `useStreamingChat.ts`의 `STREAM_TIMEOUT_MS = 120_000` (120초)와 맞춰서 CloudFront Origin Response Timeout도 120초로 설정.

### Phase 5: 보안 설정

| 항목 | 설정 |
|------|------|
| S3 | 퍼블릭 차단, OAC (Origin Access Control)로 CloudFront만 접근 |
| ALB | Security Group: CloudFront Managed Prefix List만 허용 |
| EC2 | Security Group: ALB SG만 8000포트 허용 |
| CloudFront | HTTPS 강제, TLS 1.2_2021+ |
| CORS | CloudFront가 same-origin이므로 불필요 |
| WAF (권장) | CloudFront에 AWS WAF 연결 - rate limiting, IP blocking, SQL injection 방지 |
| ACM 인증서 | **반드시 us-east-1 리전**에서 발급 (CloudFront 요구사항) |

### Phase 6: DNS 변경

```
현재: ddoksori.com → EC2 IP (A 레코드)
변경: ddoksori.com → CloudFront Distribution (CNAME 또는 Alias)
```

## 통신 방식 요약

```
[프론트엔드 (S3/CloudFront)]
    │
    ├── 정적 파일 요청 (*.js, *.css, images)
    │   → CloudFront Default(*) → S3 (캐시됨, 빠름)
    │   → SPA 라우트 (/chat, /board 등)는 CloudFront Function이 /index.html로 rewrite
    │
    ├── API 요청 (POST /api/chat, POST /api/search, GET /api/auth/*)
    │   → CloudFront /api/* Behavior → ALB → EC2:8000 (Backend/FastAPI)
    │       → RDS (PostgreSQL) : SQL 쿼리
    │       → Redis : 캐시 조회/저장
    │       → OpenAI API : LLM 호출
    │
    └── SSE 스트리밍 (POST /api/chat/stream)
        → CloudFront /api/* (CachingDisabled) → ALB → EC2:8000
            → 실시간 토큰 스트리밍 (text/event-stream)
            → heartbeat 15초 간격

[백엔드 (EC2)]
    │
    ├── PostgreSQL (RDS)
    │   연결: psycopg2, per-request connection
    │   DSN: postgresql://user:pass@rds-host:5432/ddoksori
    │
    ├── Redis (같은 EC2 내 컨테이너)
    │   연결: redis.Redis(host='redis', port=6379)
    │   3-tier 캐시: L1(응답), L2(쿼리분석), L3(의도분류)
    │
    └── External APIs
        ├── OpenAI (gpt-4o, text-embedding-3-large)
        ├── Anthropic (claude-3-haiku, fallback)
        └── OAuth (Google, Naver) - redirect_uri를 CloudFront 도메인으로 설정
```

## 변경해야 할 파일 목록

### 백엔드 (API `/api` prefix 추가)

| 파일 | 변경 내용 |
|------|----------|
| `backend/app/main.py` | 라우터 등록 시 `/api` prefix 추가 + CORS_ORIGINS에 CloudFront 도메인 |
| `backend/app/api/chat.py` | prefix `/chat` → `/api/chat` (또는 main.py에서 일괄 처리) |
| `backend/app/api/search.py` | prefix `/search` → `/api/search` |
| `backend/app/api/auth.py` | prefix `/auth` → `/api/auth` |
| `backend/app/api/case.py` | prefix `/case` → `/api/case` |
| `backend/app/api/health.py` | prefix `/health` → `/api/health` |
| `backend/app/api/metrics.py` | prefix `/metrics` → `/api/metrics` |
| `backend/app/auth/service.py` | OAuth redirect_uri를 CloudFront 도메인으로 변경 |

### 프론트엔드

| 파일 | 변경 내용 |
|------|----------|
| `frontend/src/shared/api/client.ts` | fallback `'http://localhost:8000'` → `'/api'` |
| `frontend/src/features/chat/hooks/useStreamingChat.ts` | 동일하게 fallback을 `'/api'`로 변경 |

### 인프라/CI/CD

| 파일 | 변경 내용 |
|------|----------|
| `docker-compose.prod.yml` | frontend 서비스 제거, CORS 환경변수 업데이트 |
| `.github/workflows/build.yml` | 프론트엔드: ECR 빌드 → S3 업로드 + CF invalidation |
| `.github/workflows/deploy-production.yml` | 프론트엔드 배포 로직 제거, 백엔드만 EC2 배포 |
| `.github/workflows/deploy-staging.yml` | 동일하게 변경 (staging용 S3/CF) |

### AWS 리소스 (신규 생성)

| 리소스 | 설명 |
|--------|------|
| S3 버킷 | `ddoksori-frontend-prod` (정적 파일 호스팅) |
| CloudFront Distribution | S3 + ALB Origin, CloudFront Function 연결 |
| CloudFront Function | SPA 라우팅용 (viewer-request에서 /index.html rewrite) |
| ALB + Target Group | Backend 로드밸런서 (EC2:8000) |
| ACM 인증서 | **us-east-1** 리전에서 `*.ddoksori.com` 발급 |
| Route53 | ddoksori.com → CloudFront Alias 레코드 |

## 비용 비교

### Option 1: S3 + CloudFront + ALB (고가용성 풀 구성)

| 항목 | 현재 (단일 EC2) | 변경 후 |
|------|----------------|---------|
| EC2 | t3.medium ~$30/월 | ~$30/월 (동일) |
| ALB | - | ~$18/월 (고정 $16.43 + LCU ~$2) |
| S3 | - | ~$0.5/월 미만 |
| CloudFront | - | Free tier 1TB/월, 이후 ~$0.085/GB |
| **합계** | **~$30/월** | **~$50/월** |

**선택: Option 1 (ALB 포함)** - ASG 연동 준비 완료 상태로 시작

## SSE 스트리밍 + CloudFront 호환성 분석

### 결론: 정상 동작함

**동작 원리:**
1. CloudFront는 HTTP/1.1 chunked transfer encoding 기본 지원
2. `CachingDisabled` 정책 → CloudFront가 단순 프록시 역할
3. 프론트엔드 코드가 `fetch()` + `ReadableStream` 사용 (EventSource API 아님) → 제한 없음

**주의사항 및 설정:**

| 항목 | 기본값 | 권장값 | 이유 |
|------|--------|--------|------|
| Origin Response Timeout | 30초 | 60초 | LLM 첫 응답까지 대기. heartbeat 15초이므로 30초도 OK이지만 안전 마진 |
| Keep-alive Timeout | 60초 (변경 불가) | - | heartbeat 15초 간격이므로 문제 없음 |
| Cache Policy | - | CachingDisabled | SSE는 절대 캐시하면 안 됨 |
| Origin Request Policy | - | AllViewerExceptHostHeader | POST body, headers 전달 필요 |

**현재 코드와의 호환성:**
- `useStreamingChat.ts`: `STREAM_TIMEOUT_MS = 120_000` (120초) - CloudFront timeout(60초) 내에 heartbeat이 15초마다 도착하므로 문제 없음
- `backend/app/api/chat.py`: heartbeat 15초 간격 - CloudFront keep-alive 60초 이내
- nginx의 SSE 설정(`proxy_buffering off`, `chunked_transfer_encoding off`)은 CloudFront에서 불필요 (CloudFront 자체가 처리)

**데이터 흐름:**
```
브라우저 ←(SSE)→ CloudFront ←(HTTP chunked)→ EC2:8000
         │                    │
         └─ heartbeat 15초   └─ Origin timeout 60초
            client timeout     keep-alive 60초
            120초
```

## 마이그레이션 순서 (무중단)

1. **백엔드 `/api` prefix 추가** (기존 nginx 프록시에서도 동작하도록 양쪽 지원)
2. **프론트엔드 API_BASE_URL 수정** (`'/api'` fallback)
3. S3 버킷 생성 + 프론트엔드 빌드 업로드 (테스트)
4. ALB 생성 + Target Group에 기존 EC2 등록
5. CloudFront Function 생성 (SPA 라우팅용)
6. CloudFront Distribution 생성 (임시 도메인으로 테스트)
7. 테스트: CloudFront 임시 도메인으로 전체 기능 검증 (SSE, OAuth, SPA 라우팅 포함)
8. **OAuth Console**: Google/Naver에 CloudFront 도메인 redirect URI 추가
9. DNS 전환: ddoksori.com → CloudFront (TTL 짧게 설정 후 전환)
10. EC2에서 nginx(frontend) 컨테이너 제거
11. CI/CD 파이프라인 업데이트
12. 안정화 확인 후 ECR에서 frontend 이미지 정리

---

## 검토 결과 요약 (Review Findings)

본 계획은 실제 프로덕션 서비스 패턴 검증 및 프로젝트 코드 적합성 검토를 거쳐 아래 사항이 반영되었습니다.

### 발견된 문제 3건 (수정 완료)

| # | 문제 | 심각도 | 해결 |
|---|------|--------|------|
| 1 | **경로 충돌**: `/chat`, `/admin/*`이 프론트엔드 SPA 라우트와 백엔드 API 경로에서 동시 사용됨. CloudFront Behavior로 구분 불가 | Critical | 백엔드 모든 API에 `/api` prefix 추가 → CloudFront Behavior를 `/api/*` 단일 패턴으로 통합 |
| 2 | **CustomErrorResponses 전역 적용**: 403/404를 index.html로 rewrite하면 ALB Origin의 HTTP 에러 코드(401, 404, 500 등)도 덮어씀 → 프론트엔드 에러 핸들링 불능 | Critical | `CustomErrorResponses` 제거 → S3 Behavior에만 **CloudFront Function** (viewer-request) 연결 |
| 3 | **`VITE_API_BASE_URL=""` falsy 버그**: JS에서 빈 문자열은 falsy → `\|\|` 연산자로 `'http://localhost:8000'` fallback 실행 → 프로덕션에서 localhost 호출 | High | fallback을 `'/api'`로 변경, 빌드 시 `VITE_API_BASE_URL="/api"` 설정 |

### 추가 보안/설정 권장사항

| 항목 | 설명 |
|------|------|
| ACM 인증서 리전 | CloudFront용 인증서는 **반드시 us-east-1** (N. Virginia)에서 발급해야 함 |
| WAF | CloudFront에 AWS WAF 연결 권장 (rate limiting, IP blocking, OWASP 보호) |
| OAC vs OAI | S3 접근 제어에 **OAC** (Origin Access Control) 사용 (OAI는 레거시) |
| OAuth redirect_uri | Google/Naver OAuth Console에 CloudFront 도메인 등록 필요 |

### 검증된 사항

- S3 + CloudFront + ALB 패턴은 AWS 공식 아키텍처이며 다수의 프로덕션 서비스에서 검증됨
- SSE (Server-Sent Events)는 `CachingDisabled` 정책으로 CloudFront에서 정상 동작 (chunked transfer encoding 지원)
- 15초 heartbeat이 CloudFront 60초 keep-alive timeout 내에 있어 연결 유지 가능
- 프론트엔드가 `fetch()` + `ReadableStream` 사용 (EventSource API 아님) → CloudFront 호환성 문제 없음
