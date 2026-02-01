# DDOKSORI 대화형 챗봇 배포 실행 가이드

이 문서는 DDOKSORI 대화형 챗봇 시스템(Track 1-4: 유연한 형식, DB 메모리, 후속 질문, 소셜 로그인)을 처음부터 배포하는 전체 과정을 안내합니다.

---

## 📑 목차

1. [사전 요구사항](#1-사전-요구사항)
2. [초기 환경 설정](#2-초기-환경-설정)
3. [배포 실행 단계](#3-배포-실행-단계)
4. [검증 및 테스트](#4-검증-및-테스트)
5. [일상적인 운영](#5-일상적인-운영)
6. [모니터링 및 유지보수](#6-모니터링-및-유지보수)
7. [응답 모드 A/B 테스트 (Progressive Disclosure)](#7-응답-모드-ab-테스트-progressive-disclosure)

---

## 1. 사전 요구사항

### 1.1 시스템 요구사항

#### 하드웨어
- **CPU**: 4코어 이상
- **메모리**: 8GB 이상 (16GB 권장)
- **디스크**: 50GB 이상 여유 공간
- **네트워크**: 인터넷 연결 (Docker 이미지 다운로드, RDS 접속)

#### 소프트웨어
```bash
# 필수 소프트웨어 버전 확인
docker --version          # Docker 20.10+ 필요
docker compose version    # Docker Compose v2.0+ 필요
python --version          # Python 3.11+ 필요
conda --version           # Miniconda/Anaconda 설치 필요
git --version             # Git 2.0+ 필요
```

**설치되지 않은 경우:**
- [Docker Desktop 설치](https://docs.docker.com/get-docker/)
- [Miniconda 설치](https://docs.conda.io/en/latest/miniconda.html)
- [Git 설치](https://git-scm.com/downloads)

---

### 1.2 계정 및 권한

#### AWS RDS 접근 권한
- **READ-ONLY 계정** (`ddoksori_ro`): Backend 운영용
- **관리자 계정**: DB 마이그레이션 실행용 (DBA 요청)

```bash
# RDS 연결 테스트
psql -h ["rds address"] \
     -U ddoksori_ro \
     -d ddoksori \
     -c "SELECT 1;"

# 출력:
#  ?column?
# ----------
#         1
# (1 row)
```

#### GitHub 접근 권한 (선택사항)
- 프로젝트 리포지토리에 대한 읽기 권한
- SSH 키 또는 Personal Access Token 설정

---

### 1.3 OAuth Credentials (소셜 로그인 사용 시)

소셜 로그인을 사용하려면 각 Provider에서 Client ID/Secret 발급 필요:

| Provider | 콘솔 URL | Redirect URI |
|----------|---------|-------------|
| Google | [console.cloud.google.com](https://console.cloud.google.com/) | `http://localhost:8000/api/auth/google/callback` |
| Kakao | [developers.kakao.com](https://developers.kakao.com/) | `http://localhost:8000/api/auth/kakao/callback` |
| Naver | [developers.naver.com](https://developers.naver.com/) | `http://localhost:8000/api/auth/naver/callback` |

**OAuth 설정은 선택사항입니다.** 소셜 로그인 없이도 게스트 모드로 시스템 사용 가능합니다.

---

## 2. 초기 환경 설정

### 2.1 프로젝트 클론

```bash
# 작업 디렉토리로 이동
cd /home/maroco

# 프로젝트 클론 (이미 있으면 스킵)
git clone <repository-url> LLM
cd LLM

# 브랜치 확인
git checkout feature/34-e2e
git pull origin feature/34-e2e
```

---

### 2.2 Conda 환경 생성

```bash
# Conda 환경 생성 (처음 한 번만)
conda create -n dsr python=3.11 -y

# 환경 활성화
conda activate dsr

# 패키지 설치
cd backend
conda run -n dsr pip install -r requirements.txt
```

**⏱️ 예상 소요 시간**: 10-15분 (PyTorch, Transformers 등 대용량 패키지 포함)

---

### 2.3 환경 변수 설정

#### Backend 환경 변수 (`backend/.env`)

```bash
# backend/.env 파일 생성
cd /home/maroco/LLM/backend
cp .env.example .env
nano .env  # 또는 vi, code 등 선호하는 에디터 사용
```

**필수 환경 변수**:
```bash
# ============================================================================
# Database (RDS)
# ============================================================================
DB_HOST=your_rds_dir.us-east-1.rds.amazonaws.com
DB_PORT=5432
DB_NAME=ddoksori
DB_USER=ddoksori_ro
DB_PASSWORD=<READ-ONLY 계정 비밀번호>

# ============================================================================
# JWT Authentication (필수)
# ============================================================================
# 32자 이상 랜덤 문자열 생성:
# python3 -c "import secrets; print(secrets.token_urlsafe(32))"
JWT_SECRET_KEY=<생성된_랜덤_문자열>
JWT_ALGORITHM=HS256
JWT_TOKEN_EXPIRE_DAYS=30

# ============================================================================
# Memory Configuration
# ============================================================================
CONVERSATION_MEMORY_BACKEND=db  # 'db' 또는 'memory'
MAX_CONVERSATION_TURNS=30
SLIDING_WINDOW_SIZE=10
GUEST_SESSION_TTL_HOURS=24
CLEANUP_INTERVAL_HOURS=1

# ============================================================================
# Feature Flags (점진적 활성화 가능)
# ============================================================================
ENABLE_FOLLOWUP_QUESTIONS=true
ANSWER_FORMAT_MODE=flexible  # 'fixed' 또는 'flexible'

# ============================================================================
# Response Mode (A/B 테스트 - Progressive Disclosure)
# ============================================================================
# legacy: 기존 동작 100% 유지 (기본값)
# minimal: 규칙 기반 Progressive Disclosure (요약 응답 + 후속 질문)
# adaptive: LLM 판단 기반 (향후 구현)
RESPONSE_MODE=legacy
SUMMARY_MAX_LENGTH=200
FOLLOWUP_SIMILARITY_THRESHOLD=0.8

# ============================================================================
# OAuth Credentials (선택사항)
# ============================================================================
# Google OAuth (없으면 주석 처리 또는 빈 값)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# Kakao OAuth
KAKAO_CLIENT_ID=
KAKAO_CLIENT_SECRET=

# Naver OAuth
NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=

# ============================================================================
# URLs
# ============================================================================
BACKEND_URL=http://localhost:8000
FRONTEND_URL=http://localhost:5173

# ============================================================================
# LLM API Keys
# ============================================================================
OPENAI_API_KEY=<OpenAI API 키>
ANTHROPIC_API_KEY=<Anthropic API 키>  # 선택사항
```

#### Frontend 환경 변수 (`frontend/.env`)

```bash
cd /home/maroco/LLM/frontend
nano .env
```

```bash
# Backend API URL
VITE_API_BASE_URL=http://localhost:8000
```

---

### 2.4 JWT_SECRET_KEY 생성

```bash
# 32자 이상 랜덤 문자열 생성
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# 출력 예시:
# yQ7XvZ3mN8kP2wR5tL9xU6bC4aJ1sH0eGfKpMqNr

# 이 값을 복사하여 backend/.env 파일의 JWT_SECRET_KEY에 붙여넣기
```

---

## 3. 배포 실행 단계

### 3.1 Step 1: 데이터베이스 마이그레이션 (DBA 요청 필수)

#### 3.1.1 마이그레이션 파일 확인

```bash
# 마이그레이션 파일 위치 확인
ls -lh migrations/004_conversation_memory.sql

# 파일 내용 미리보기 (선택사항)
head -50 migrations/004_conversation_memory.sql
```

#### 3.1.2 DBA에게 마이그레이션 실행 요청

**이메일 템플릿**:
```
제목: [DDOKSORI] 대화형 챗봇 DB 마이그레이션 실행 요청

안녕하세요,

DDOKSORI 대화형 챗봇 시스템 배포를 위해 데이터베이스 마이그레이션 실행을 요청드립니다.

### 실행 정보
- 파일: backend/database/migrations/004_conversation_memory.sql
- RDS 호스트: your_rds_dir.us-east-1.rds.amazonaws.com
- 데이터베이스: ddoksori

### 실행 명령어
psql -h your_rds_dir.us-east-1.rds.amazonaws.com \
     -U <관리자_계정> \
     -d ddoksori \
     -f backend/database/migrations/004_conversation_memory.sql

### 실행 후 권한 부여 (필수)
GRANT SELECT ON conversations, conversation_turns, conversation_summaries, users, oauth_sessions TO ddoksori_ro;

### 생성될 테이블 (총 5개)
1. conversations - 대화 세션
2. conversation_turns - 대화 턴
3. conversation_summaries - 압축 요약
4. users - 사용자
5. oauth_sessions - OAuth 토큰

### 안전성
✅ 기존 테이블(documents, chunks 등)에 영향 없음
✅ CASCADE DELETE로 참조 무결성 유지
✅ CHECK 제약조건으로 데이터 검증

완료 후 알려주시면 감사하겠습니다.
```

#### 3.1.3 마이그레이션 완료 검증

DBA로부터 완료 통보 받은 후:

```bash
# 테이블 생성 확인
psql -h your_rds_dir.us-east-1.rds.amazonaws.com \
     -U ddoksori_ro \
     -d ddoksori \
     -c "\dt"

# 예상 출력:
#              List of relations
#  Schema |         Name              | Type  |  Owner
# --------+---------------------------+-------+----------
#  public | vector_chunks             | table | postgres
#  public | conversation_summaries    | table | postgres  ← 신규
#  public | conversation_turns        | table | postgres  ← 신규
#  public | conversations             | table | postgres  ← 신규
#  public | search_quality_logs       | table | postgres
#  public | oauth_sessions            | table | postgres  ← 신규
#  public | users                     | table | postgres  ← 신규
```

**5개 신규 테이블 확인 완료 시 → Step 2로 진행**

---

### 3.2 Step 2: CloudBeaver로 스키마 시각적 확인 (선택사항, 권장)

```bash
# CloudBeaver 시작
cd /home/maroco/LLM
docker compose up -d cloudbeaver

# 로그 확인
docker compose logs -f cloudbeaver

# 브라우저에서 접속
open http://localhost:8978
```

#### CloudBeaver 초기 설정

1. **첫 접속 시 관리자 계정 생성**
   - Username: `admin`
   - Password: 안전한 비밀번호 입력

2. **RDS 데이터베이스 연결**
   - Connection Name: `DDOKSORI RDS`
   - Host: `your_rds_dir.us-east-1.rds.amazonaws.com`
   - Port: `5432`
   - Database: `ddoksori`
   - Username: `ddoksori_ro`
   - Password: READ-ONLY 계정 비밀번호

3. **Test Connection 클릭** → "Connection is valid" 확인

4. **스키마 확인**
   - 왼쪽 Database Navigator → ddoksori → public → Tables
   - 신규 테이블 5개 표시 확인:
     - conversations
     - conversation_turns
     - conversation_summaries
     - users
     - oauth_sessions

---

### 3.3 Step 3: Docker 이미지 빌드

```bash
cd /home/maroco/LLM

# Backend 이미지 빌드 (캐시 없이)
docker compose build --no-cache backend

# Frontend 이미지 빌드
docker compose build --no-cache frontend
```

**⏱️ 예상 소요 시간**: Backend 5-10분, Frontend 2-3분

#### 빌드 중 예상 출력
```
[+] Building 600.0s (10/10) FINISHED
 => [stage-0 1/7] FROM docker.io/library/python:3.11-slim
 => [stage-0 3/7] RUN apt-get update && apt-get install -y gcc postgresql-client
 => [stage-0 6/7] RUN uv pip install --system --no-cache -r requirements.txt
 => [stage-0 7/7] COPY . .
 => => exporting to image
```

**에러 발생 시** → [트러블슈팅 가이드](./deployment-troubleshooting.md) 참고

---

### 3.4 Step 4: 컨테이너 시작

```bash
cd /home/maroco/LLM

# 모든 서비스 시작
docker compose up -d

# 서비스 목록 확인
docker compose ps

# 예상 출력:
# NAME                    STATUS    PORTS
# ddoksori_backend        Up        0.0.0.0:8000->8000/tcp
# ddoksori_frontend       Up        0.0.0.0:5173->5173/tcp
# ddoksori_redis          Up        6379/tcp
# ddoksori_cloudbeaver    Up        0.0.0.0:8978->8978/tcp
# ddoksori_prometheus     Up        9090/tcp
# ddoksori_grafana        Up        3000/tcp
```

---

### 3.5 Step 5: 서비스 상태 확인

#### Backend Health Check

```bash
# Health 엔드포인트 확인
curl http://localhost:8000/health

# 예상 출력:
# {"status":"healthy"}
```

#### Backend 로그 확인

```bash
# Backend 컨테이너 로그
docker compose logs -f backend

# 예상 출력 (일부):
# INFO:     Started server process [1]
# INFO:     Waiting for application startup.
# INFO:     [Memory] Conversation cleanup service started (interval: 1h)
# INFO:     Application startup complete.
# INFO:     Uvicorn running on http://0.0.0.0:8000
```

**중요**: "Conversation cleanup service started" 메시지 확인 필수

#### Frontend 접속 확인

```bash
# 브라우저에서 접속
open http://localhost:5173
```

---

## 4. 검증 및 테스트

### 4.1 기본 채팅 기능 테스트

#### 테스트 시나리오 1: 분쟁 상담 쿼리

1. **프론트엔드 접속**: http://localhost:5173
2. **메시지 입력**: "노트북을 구매했는데 화면이 깨져서 도착했어요. 환불 가능한가요?"
3. **예상 응답 확인**:
   - ✅ 답변이 3-섹션 구조가 아닌 자연스러운 대화체
   - ✅ 하단에 "💡 이런 질문도 해보세요:" 섹션 표시
   - ✅ 후속 질문 2-3개 표시 (예: "환불 처리 기간은 얼마나 걸리나요?")

4. **후속 질문 클릭 테스트**:
   - 후속 질문 중 하나 클릭
   - 자동으로 메시지 전송 및 새 응답 표시 확인

---

#### 테스트 시나리오 2: 일반 대화 쿼리

1. **메시지 입력**: "안녕하세요"
2. **예상 응답 확인**:
   - ✅ 간단하고 친근한 톤의 인사말
   - ✅ 3-섹션 구조 강제 없음
   - ✅ 후속 질문 표시 ("무엇을 도와드릴까요?" 등)

---

### 4.2 메모리 영속화 확인

#### 브라우저 새로고침 테스트

1. **여러 메시지 주고받기** (5-10턴)
2. **브라우저 새로고침** (F5 또는 Ctrl+R)
3. **대화 이력 복구 확인**:
   - ✅ 이전 대화가 그대로 표시됨
   - ✅ 세션 ID 유지됨

---

#### 데이터베이스 확인

```bash
# RDS 접속
psql -h your_rds_dir.us-east-1.rds.amazonaws.com \
     -U ddoksori_ro \
     -d ddoksori

# 대화 세션 확인
\x  -- Expanded display 활성화
SELECT * FROM conversations ORDER BY created_at DESC LIMIT 1;

# 예상 출력:
# -[ RECORD 1 ]------+-------------------------------------
# conversation_id    | 550e8400-e29b-41d4-a716-446655440000
# session_id         | abc123xyz789
# user_id            | [null]  (게스트 세션)
# chat_type          | dispute
# turn_count         | 10
# created_at         | 2026-01-28 12:34:56
# expires_at         | 2026-01-29 12:34:56  (24시간 후)

# 대화 턴 확인
SELECT turn_number, role, LEFT(content, 50) as preview
FROM conversation_turns
WHERE conversation_id = '<위에서 확인한 conversation_id>'
ORDER BY turn_number;

# 예상 출력:
#  turn_number | role      | preview
# -------------+-----------+--------------------------------------------------
#            1 | user      | 노트북을 구매했는데 화면이 깨져서 도착했어요...
#            2 | assistant | 소비자보호법에 따르면 불량품에 대해서는 7일 이내...
#            3 | user      | 환불 처리 기간은 얼마나 걸리나요?
```

---

### 4.3 게스트 세션 TTL 확인

```sql
-- 게스트 세션 확인
SELECT
    conversation_id,
    session_id,
    expires_at,
    EXTRACT(EPOCH FROM (expires_at - NOW())) / 3600 as hours_until_expiry
FROM conversations
WHERE user_id IS NULL
ORDER BY created_at DESC
LIMIT 5;

-- 예상 출력:
#  hours_until_expiry
# --------------------
#  23.8  (거의 24시간)
```

**예상 동작**:
- 게스트 세션은 생성 후 정확히 24시간 뒤 `expires_at` 설정
- Cleanup 서비스가 1시간마다 만료된 세션 자동 삭제

---

### 4.4 OAuth 로그인 테스트 (선택사항)

**OAuth Credentials 설정이 완료된 경우에만 테스트**

#### Google OAuth 테스트

1. **프론트엔드에서 "로그인" 버튼 클릭**
2. **"Google로 계속하기" 클릭**
3. **Google 계정 로그인**
   - Google OAuth 동의 화면 표시
   - 이메일, 프로필 권한 요청
4. **리다이렉트 확인**
   - `http://localhost:5173/auth/callback?token=...` 로 리다이렉트
   - 프론트엔드에서 "로그인 중..." 표시 후 홈으로 이동
5. **로그인 상태 확인**
   - 우측 상단에 사용자 이름/아바타 표시
   - "로그인" 버튼 → "로그아웃" 버튼으로 변경

#### 데이터베이스 확인

```sql
-- 사용자 생성 확인
SELECT user_id, email, name, provider, last_login_at
FROM users
ORDER BY last_login_at DESC
LIMIT 5;

-- 예상 출력:
#  user_id         | email               | name     | provider | last_login_at
# -----------------+---------------------+----------+----------+-------------------
#  google:12345678 | user@gmail.com      | John Doe | google   | 2026-01-28 12:45:00
```

---

## 5. 일상적인 운영

### 5.1 서비스 재시작

#### 전체 서비스 재시작

```bash
cd /home/maroco/LLM

# 모든 서비스 재시작
docker compose restart

# 또는 특정 서비스만 재시작
docker compose restart backend
docker compose restart frontend
```

#### 환경 변수 변경 후 재시작

```bash
# .env 파일 수정
nano backend/.env

# Backend만 재시작 (환경 변수 다시 로드)
docker compose restart backend
```

---

### 5.2 로그 확인

#### 실시간 로그 모니터링

```bash
# Backend 로그
docker compose logs -f backend

# Frontend 로그
docker compose logs -f frontend

# 모든 서비스 로그
docker compose logs -f
```

#### 특정 시간 범위 로그 조회

```bash
# 최근 100줄
docker compose logs --tail=100 backend

# 최근 1시간
docker compose logs --since 1h backend
```

#### Cleanup 서비스 로그 필터링

```bash
# 게스트 세션 자동 삭제 로그만 보기
docker compose logs backend | grep -i "cleanup\|deleted.*expired"

# 예상 출력:
# INFO: [Memory] Conversation cleanup service started (interval: 1h)
# INFO: Deleted 15 expired guest conversations
```

---

### 5.3 데이터베이스 관리

#### 일상적인 쿼리

```sql
-- RDS 접속
psql -h your_rds_dir.us-east-1.rds.amazonaws.com \
     -U ddoksori_ro \
     -d ddoksori

-- 대화 통계
SELECT
    COUNT(*) as total_conversations,
    COUNT(*) FILTER (WHERE user_id IS NULL) as guest_sessions,
    COUNT(*) FILTER (WHERE user_id IS NOT NULL) as authenticated_sessions,
    AVG(turn_count) as avg_turns_per_session
FROM conversations;

-- 사용자 통계
SELECT
    provider,
    COUNT(*) as user_count
FROM users
GROUP BY provider;

-- 최근 활동
SELECT
    c.conversation_id,
    c.session_id,
    u.email,
    c.turn_count,
    c.updated_at
FROM conversations c
LEFT JOIN users u ON c.user_id = u.user_id
ORDER BY c.updated_at DESC
LIMIT 10;
```

---

### 5.4 Feature Flags 조정

#### 점진적 기능 활성화

```bash
# backend/.env 파일 수정
nano backend/.env

# 단계별 활성화 예시:

# Step 1: 후속 질문만 활성화 (저위험)
ENABLE_FOLLOWUP_QUESTIONS=true
ANSWER_FORMAT_MODE=fixed
CONVERSATION_MEMORY_BACKEND=memory

# Step 2: 유연한 형식 활성화 (Step 1 안정 확인 후)
ENABLE_FOLLOWUP_QUESTIONS=true
ANSWER_FORMAT_MODE=flexible
CONVERSATION_MEMORY_BACKEND=memory

# Step 3: DB 메모리 활성화 (최종, Step 2 안정 확인 후)
ENABLE_FOLLOWUP_QUESTIONS=true
ANSWER_FORMAT_MODE=flexible
CONVERSATION_MEMORY_BACKEND=db

# 재시작
docker compose restart backend
```

#### 긴급 롤백 (문제 발생 시)

```bash
# 모든 신규 기능 비활성화
ENABLE_FOLLOWUP_QUESTIONS=false
ANSWER_FORMAT_MODE=fixed
CONVERSATION_MEMORY_BACKEND=memory

# 재시작
docker compose restart backend
```

---

## 6. 모니터링 및 유지보수

### 6.1 성능 모니터링

#### Prometheus 메트릭 확인

```bash
# 브라우저에서 접속
open http://localhost:9090

# 주요 메트릭 쿼리:
# - http_request_duration_seconds (API 응답 시간)
# - process_resident_memory_bytes (메모리 사용량)
# - process_cpu_seconds_total (CPU 사용량)
```

#### Grafana 대시보드

```bash
# 브라우저에서 접속
open http://localhost:3000

# 기본 로그인:
# Username: admin
# Password: admin
```

---

### 6.2 데이터베이스 성능 모니터링

```sql
-- 느린 쿼리 확인 (pg_stat_statements 필요)
SELECT
    query,
    calls,
    mean_time,
    max_time
FROM pg_stat_statements
WHERE query LIKE '%conversations%'
  AND mean_time > 100  -- 100ms 이상
ORDER BY mean_time DESC
LIMIT 10;

-- 테이블 크기 확인
SELECT
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE tablename IN ('conversations', 'conversation_turns', 'conversation_summaries', 'users')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

---

### 6.3 정기 유지보수

#### 주간 체크리스트

- [ ] **로그 확인**: Backend 에러 로그 검토
- [ ] **DB 통계**: 대화 통계, 사용자 증가 추이 확인
- [ ] **디스크 공간**: Docker 볼륨 사용량 확인 (`df -h`)
- [ ] **Cleanup 서비스**: 게스트 세션 자동 삭제 정상 동작 확인

```bash
# 디스크 공간 확인
df -h /var/lib/docker

# Docker 불필요한 리소스 정리
docker system prune -a --volumes -f
```

#### 월간 체크리스트

- [ ] **패키지 업데이트**: requirements.txt 의존성 최신 버전 확인
- [ ] **보안 패치**: Docker 이미지, OS 패키지 업데이트
- [ ] **백업 검증**: 데이터베이스 백업 복구 테스트
- [ ] **성능 리뷰**: Prometheus 메트릭 분석, 병목 지점 확인

---

### 6.4 백업 및 복구

#### 데이터베이스 백업 (DBA 요청)

```bash
# DBA에게 요청할 백업 명령어
pg_dump -h your_rds_dir.us-east-1.rds.amazonaws.com \
        -U <관리자_계정> \
        -d ddoksori \
        -t conversations \
        -t conversation_turns \
        -t conversation_summaries \
        -t users \
        -t oauth_sessions \
        --clean --if-exists \
        -f ddoksori_conversation_backup_$(date +%Y%m%d).sql
```

#### 설정 파일 백업

```bash
# 환경 변수 백업 (민감 정보 포함, 안전하게 보관)
cp backend/.env backend/.env.backup.$(date +%Y%m%d)
cp frontend/.env frontend/.env.backup.$(date +%Y%m%d)

# 암호화하여 보관 (선택사항)
tar -czf env_backup_$(date +%Y%m%d).tar.gz backend/.env frontend/.env
gpg --symmetric --cipher-algo AES256 env_backup_$(date +%Y%m%d).tar.gz
```

---

## 7. 응답 모드 A/B 테스트 (Progressive Disclosure)

### 7.1 개요

`RESPONSE_MODE` 환경변수를 통해 답변 생성 방식을 전환할 수 있습니다. 단일 Docker 인스턴스에서 환경변수만 변경하여 테스트합니다.

| 모드 | 설명 | 적용 기능 |
|------|------|-----------|
| `legacy` (기본) | 기존 동작 100% 유지 | 변경 없음 |
| `minimal` | 규칙 기반 Progressive Disclosure | 요약 응답 + 후속 질문 + 메타 쿼리 가이드 |
| `adaptive` | LLM 판단 기반 (향후 구현) | minimal + LLM 분류 |

**환경변수 설정은 [Section 2.3](#23-환경-변수-설정)의 Backend 환경 변수를 참고하세요.**

### 7.2 A/B 테스트 실행 방법

#### 방법 1: .env 파일 직접 수정

```bash
# backend/.env 파일 수정
nano backend/.env

# RESPONSE_MODE=minimal 로 변경 후 저장

# Backend 재시작
docker compose restart backend

# 로그에서 모드 확인
docker compose logs backend | grep -i "response_mode"
```

#### 방법 2: Docker Compose 환경변수 오버라이드

```bash
# A 모드: 기존 동작 (기본)
RESPONSE_MODE=legacy docker compose up -d backend

# B 모드: Progressive Disclosure
RESPONSE_MODE=minimal docker compose up -d backend
```

#### 방법 3: 로컬 개발 서버에서 테스트

```bash
cd /home/maroco/LLM/backend
conda activate dsr

# legacy 모드 (기본)
RESPONSE_MODE=legacy uvicorn app.main:app --reload

# minimal 모드
RESPONSE_MODE=minimal uvicorn app.main:app --reload
```

### 7.3 모드별 테스트 시나리오

#### 시나리오 1: 분쟁 상담 쿼리 비교

```bash
# legacy 모드 - 전체 답변 한 번에 출력
curl -s -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"노트북 환불하고 싶어요","chat_type":"dispute"}' | head -5

# 기대 결과 (legacy):
# - 법령 + 기준 + 사례 모두 포함된 긴 답변
# - response_depth: "full" (또는 미포함)
```

```bash
# minimal 모드 - 요약 + 후속 질문
RESPONSE_MODE=minimal docker compose restart backend

curl -s -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"노트북 환불하고 싶어요","chat_type":"dispute"}' | head -5

# 기대 결과 (minimal):
# - 200자 이내 핵심 요약 답변
# - response_depth: "summary"
# - available_details: {"laws": {...}, "cases": {...}}
# - followup_questions: ["관련 법령을 자세히 알려드릴까요?", ...]
```

#### 시나리오 2: 메타 쿼리 비교

```bash
# legacy 모드
curl -s -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"뭘 물어봐야 할까?","chat_type":"dispute"}'

# 기대 결과 (legacy): RAG 검색 실행 → 유사도 낮은 결과 → 부적절한 답변

# minimal 모드
# 기대 결과 (minimal): RAG 미실행 → 가이드 템플릿 응답
#   "똑소리에서는 다음과 같은 도움을 드릴 수 있습니다:
#    1. 구매 품목 관련 환불/교환 규정
#    2. 분쟁 해결 절차 안내 ..."
```

#### 시나리오 3: 후속 질문 클릭 비교

```bash
# 1단계: 첫 질문 (minimal 모드)
curl -s -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"노트북 환불하고 싶어요","chat_type":"dispute"}'
# → 후속 질문 반환: "관련 법령을 자세히 알려드릴까요?"

# 2단계: 후속 질문 클릭 (같은 세션에서)
curl -s -X POST http://localhost:8000/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message":"관련 법령을 자세히 알려드릴까요?","chat_type":"dispute"}'

# legacy 모드: 새로 RAG 검색 실행 → 이전 맥락 없이 답변
# minimal 모드: 이전 턴 retrieval 재사용 → 법령 섹션만 상세 답변
#   response_depth: "detail", detail_type: "laws"
```

### 7.4 비교 평가 기준

| 평가 항목 | legacy | minimal 기대 |
|-----------|--------|-------------|
| 첫 응답 길이 | 500~1500자 | 100~200자 |
| 응답 시간 (첫 턴) | 동일 | 동일 (RAG 동일 실행) |
| 응답 시간 (후속 턴) | 2~5초 (새 RAG) | <1초 (캐시 재사용) |
| 메타 쿼리 처리 | 부적절한 RAG 결과 | 가이드 템플릿 |
| 후속 질문 유용성 | 일반적 | 컨텍스트 기반 구체적 |
| 정보 완결성 (첫 턴) | 높음 | 낮음 (요약만) |
| 정보 완결성 (멀티턴) | 높음 | 높음 (누적 상세) |

### 7.5 단계별 롤아웃 권장

```bash
# Step 1: 개발 환경에서 minimal 모드 테스트
RESPONSE_MODE=minimal docker compose up -d backend
# → 위 시나리오 1~3 검증

# Step 2: 내부 QA 테스트 (1주일)
# → 답변 품질, 후속 질문 유용성, 응답 시간 측정

# Step 3: 프로덕션 전환
# backend/.env에서 RESPONSE_MODE=minimal 설정
docker compose restart backend

# 긴급 롤백 (문제 발생 시)
# backend/.env에서 RESPONSE_MODE=legacy 설정
docker compose restart backend
```

### 7.6 관련 환경변수 전체 목록

RESPONSE_MODE 관련 환경변수는 [Section 2.3](#23-환경-변수-설정)을 참고하세요.

추가 관련 환경변수:
```bash
# ============================================================================
# Sufficiency Check (PR-A)
# ============================================================================
SUFFICIENCY_MIN_SIMILARITY=0.5    # 충분성 기준 유사도
SUFFICIENCY_MIN_DOCUMENTS=2       # 충분성 기준 문서 수
SUFFICIENCY_LOW_THRESHOLD=0.3     # 부족 판정 임계치
SUFFICIENCY_MEDIUM_THRESHOLD=0.6  # 보통 판정 임계치

# ============================================================================
# Conversation Memory (PR-B)
# ============================================================================
CONVERSATION_MEMORY_WINDOW=5      # RAG 대화 히스토리 윈도우 크기
```

**상세 구현 문서**: [Progressive Disclosure 구현 문서](../feature/2026-01-31-progressive-disclosure-implementation.md)

---

## 8. 문제 해결

### 8.1 자주 발생하는 문제

#### 문제: "Backend 컨테이너가 계속 재시작됨"

```bash
# 로그 확인
docker compose logs backend | tail -50

# 일반적인 원인:
# - 환경 변수 누락 (JWT_SECRET_KEY, DB_PASSWORD 등)
# - DB 연결 실패 (잘못된 호스트/포트/credentials)
# - 포트 충돌 (8000번 포트가 이미 사용 중)

# 해결:
# 1. .env 파일 검증
# 2. DB 연결 테스트 (psql CLI)
# 3. 포트 사용 확인: netstat -tlnp | grep 8000
```

#### 문제: "대화 이력이 저장되지 않음"

```bash
# Cleanup 서비스 로그 확인
docker compose logs backend | grep -i "cleanup"

# 환경 변수 확인
docker compose exec backend env | grep CONVERSATION_MEMORY_BACKEND

# 예상 출력: CONVERSATION_MEMORY_BACKEND=db

# DB 테이블 확인
psql -h ... -U ddoksori_ro -d ddoksori -c "SELECT COUNT(*) FROM conversations;"
```

#### 문제: "후속 질문이 표시되지 않음"

```bash
# Feature Flag 확인
docker compose exec backend env | grep ENABLE_FOLLOWUP_QUESTIONS

# 예상 출력: ENABLE_FOLLOWUP_QUESTIONS=true

# Backend 로그에서 에러 확인
docker compose logs backend | grep -i "followup\|error"
```

---

### 8.2 추가 리소스

- **트러블슈팅 가이드**: [deployment-troubleshooting.md](./deployment-troubleshooting.md)
- **E2E 테스트 가이드**: [e2e-test-guide.md](../testing/e2e-test-guide.md)
- **OAuth 설정 가이드**: [oauth-setup-guide.md](./oauth-setup-guide.md)
- **운영 가이드**: [conversational-chatbot-operations.md](./conversational-chatbot-operations.md)

---

## 9. 체크리스트 요약

### 배포 전 체크리스트

- [ ] Docker, Docker Compose, Conda 설치 확인
- [ ] RDS 연결 테스트 (ddoksori_ro 계정)
- [ ] 프로젝트 클론 및 브랜치 확인 (feature/34-e2e)
- [ ] Conda 환경 생성 및 패키지 설치
- [ ] backend/.env 파일 설정 (JWT_SECRET_KEY, DB_PASSWORD 필수)
- [ ] frontend/.env 파일 설정

### 배포 실행 체크리스트

- [ ] DBA에게 마이그레이션 실행 요청 및 완료 확인
- [ ] CloudBeaver로 신규 테이블 5개 생성 확인 (선택사항)
- [ ] Docker 이미지 빌드 (backend, frontend)
- [ ] 컨테이너 시작 (docker compose up -d)
- [ ] Backend Health Check (`curl http://localhost:8000/health`)
- [ ] Backend 로그에서 "Conversation cleanup service started" 확인
- [ ] Frontend 접속 확인 (http://localhost:5173)

### 검증 체크리스트

- [ ] 기본 채팅 기능 테스트 (분쟁 상담 쿼리)
- [ ] 후속 질문 표시 및 클릭 동작 확인
- [ ] 브라우저 새로고침 후 대화 이력 복구 확인
- [ ] DB에 conversations 데이터 생성 확인
- [ ] 게스트 세션 expires_at 확인 (24시간)
- [ ] OAuth 로그인 테스트 (선택사항)

---

## 10. 다음 단계

배포 완료 후:

1. **모니터링 설정**: Prometheus, Grafana 대시보드 구성
2. **알림 설정**: 에러율, 응답 시간 임계값 설정
3. **부하 테스트**: 동시 접속 100명 시뮬레이션
4. **사용자 피드백 수집**: 답변 품질, 후속 질문 유용성 평가
5. **성능 최적화**: 병목 지점 분석 및 개선

---

**문서 작성일**: 2026-01-28
**버전**: 1.0
**작성자**: DDOKSORI Development Team
