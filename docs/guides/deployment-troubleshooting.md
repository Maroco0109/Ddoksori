# 배포 트러블슈팅 가이드

DDOKSORI 대화형 챗봇 배포 시 발생할 수 있는 일반적인 문제와 해결 방법을 정리합니다.

---

## 목차

1. [Docker 빌드 오류](#1-docker-빌드-오류)
2. [데이터베이스 연결 오류](#2-데이터베이스-연결-오류)
3. [환경 변수 관련 오류](#3-환경-변수-관련-오류)
4. [런타임 오류](#4-런타임-오류)
5. [성능 문제](#5-성능-문제)

---

## 1. Docker 빌드 오류

### 1.1 Python 패키지 의존성 해결 실패

#### 증상
```
× No solution found when resolving dependencies:
╰─▶ Because there is no version of anthropic==0.42.1 and you require
    anthropic==0.42.1, we can conclude that your requirements are
    unsatisfiable.
```

#### 원인
- `requirements.txt`에 존재하지 않는 패키지 버전 명시
- PyPI에서 해당 버전이 삭제되거나 never released된 경우

#### 해결 방법

**Step 1: 최신 버전 확인**
```bash
# 터미널에서 직접 확인
pip index versions anthropic

# 또는 PyPI 웹사이트 확인
open https://pypi.org/project/anthropic/
```

**Step 2: requirements.txt 수정**
```bash
# backend/requirements.txt 파일 편집
# 문제가 되는 패키지 버전 수정

# 예: anthropic==0.42.1 → anthropic==0.40.0
```

**Step 3: Docker 이미지 재빌드**
```bash
# 캐시 없이 완전히 새로 빌드
docker compose build --no-cache backend

# 또는 특정 서비스만 재빌드
docker compose up -d --build backend
```

#### 예방 방법
- **버전 범위 지정**: `anthropic>=0.40.0,<0.50.0` (특정 버전 대신)
- **정기적인 의존성 업데이트**: `pip list --outdated`로 확인
- **버전 고정 전 검증**: 새 버전 추가 전 PyPI에서 존재 여부 확인

---

### 1.2 Docker BuildKit 메모리 부족

#### 증상
```
ERROR: failed to solve: process "/bin/sh -c pip install -r requirements.txt"
did not complete successfully: signal: killed
```

#### 원인
- Docker BuildKit의 메모리 제한 초과 (특히 PyTorch, Transformers 설치 시)

#### 해결 방법

**Option 1: Docker 메모리 증설**
```bash
# Docker Desktop 설정에서 메모리 증설
# Settings → Resources → Memory: 8GB 이상 권장
```

**Option 2: 멀티스테이지 빌드 최적화**
```dockerfile
# Dockerfile에서 불필요한 빌드 도구 제거
RUN pip install --no-cache-dir -r requirements.txt
```

**Option 3: 의존성 분할 설치**
```dockerfile
# 대용량 패키지 먼저 설치
RUN pip install torch transformers
RUN pip install -r requirements.txt
```

---

### 1.3 uv 패키지 매니저 관련 오류

#### 증상
```
ERROR [stage-0 6/7] RUN uv pip install --system --no-cache -r requirements.txt
```

#### 원인
- `uv` 패키지 매니저의 의존성 해결 알고리즘이 더 엄격함
- 버전 충돌이나 호환되지 않는 패키지 조합

#### 해결 방법

**Option 1: 표준 pip으로 전환 (임시 해결)**
```dockerfile
# Dockerfile 수정
# 변경 전:
RUN uv pip install --system --no-cache -r requirements.txt

# 변경 후:
RUN pip install --no-cache-dir -r requirements.txt
```

**Option 2: uv 의존성 해결 로그 확인**
```bash
# 로컬에서 직접 테스트
conda activate dsr
uv pip install -r backend/requirements.txt --verbose
```

**Option 3: 충돌하는 패키지 버전 조정**
- `uv`는 의존성 트리를 정확하게 검증하므로, 실제 충돌을 발견한 것일 수 있음
- 관련 패키지들의 버전 호환성 매트릭스 확인

---

## 2. 데이터베이스 연결 오류

### 2.1 RDS 연결 실패

#### 증상
```
psycopg2.OperationalError: could not connect to server: Connection timed out
Is the server running on host "dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com"?
```

#### 원인
- Security Group 설정 (방화벽 규칙)
- 잘못된 DB 호스트/포트/credentials
- VPC 설정 (RDS가 private subnet에 있는 경우)

#### 해결 방법

**Step 1: 연결 정보 확인**
```bash
# .env 파일 확인
cat backend/.env | grep DB_

# 출력 예:
# DB_HOST=dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com
# DB_PORT=5432
# DB_NAME=ddoksori
# DB_USER=ddoksori_ro
# DB_PASSWORD=<password>
```

**Step 2: 네트워크 연결 테스트**
```bash
# Telnet으로 포트 확인
telnet dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com 5432

# 또는 netcat
nc -zv dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com 5432
```

**Step 3: psql CLI로 직접 연결 테스트**
```bash
psql -h dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com \
     -U ddoksori_ro \
     -d ddoksori \
     -c "SELECT 1;"
```

**Step 4: AWS Security Group 확인**
- RDS 인스턴스의 Security Group에 현재 서버 IP 허용 확인
- Inbound Rule: PostgreSQL (5432) TCP, Source: 0.0.0.0/0 (또는 특정 IP)

---

### 2.2 READ-ONLY 계정 권한 오류

#### 증상
```
psycopg2.errors.InsufficientPrivilege: permission denied for table conversations
```

#### 원인
- `ddoksori_ro` 계정은 SELECT만 가능
- INSERT/UPDATE/DELETE/CREATE TABLE 시도

#### 해결 방법

**Option 1: DBA에게 권한 요청**
```sql
-- DBA가 실행해야 하는 SQL
GRANT SELECT ON conversations, conversation_turns, conversation_summaries, users, oauth_sessions TO ddoksori_ro;

-- 또는 모든 테이블에 SELECT 권한
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ddoksori_ro;
```

**Option 2: 관리자 계정 사용 (마이그레이션 시)**
```bash
# .env 파일에 관리자 계정 임시 설정
DB_USER=<admin_user>
DB_PASSWORD=<admin_password>

# 마이그레이션 실행
psql -h ... -U <admin_user> -d ddoksori -f backend/database/migrations/004_conversation_memory.sql

# 마이그레이션 완료 후 READ-ONLY 계정으로 복구
DB_USER=ddoksori_ro
```

---

### 2.3 테이블이 존재하지 않음

#### 증상
```
psycopg2.errors.UndefinedTable: relation "conversations" does not exist
```

#### 원인
- 마이그레이션 미실행
- 잘못된 데이터베이스 연결 (다른 DB)

#### 해결 방법

**Step 1: 현재 테이블 목록 확인**
```sql
psql -h ... -U ddoksori_ro -d ddoksori -c "\dt"

-- 예상 출력:
--          List of relations
--  Schema |         Name          | Type  |  Owner
-- --------+-----------------------+-------+----------
--  public | chunks                | table | postgres
--  public | conversations         | table | postgres  ← 없으면 마이그레이션 필요
--  public | documents             | table | postgres
```

**Step 2: 마이그레이션 실행 확인**
```bash
# DBA에게 마이그레이션 실행 완료 여부 확인
# 또는 직접 실행 (관리자 권한 필요)
psql -h dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com \
     -U <admin_user> \
     -d ddoksori \
     -f backend/database/migrations/004_conversation_memory.sql
```

**Step 3: 마이그레이션 성공 검증**
```sql
-- 5개 테이블 생성 확인
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('conversations', 'conversation_turns', 'conversation_summaries', 'users', 'oauth_sessions');
```

---

## 3. 환경 변수 관련 오류

### 3.1 환경 변수 누락

#### 증상
```
pydantic_core._pydantic_core.ValidationError: 1 validation error for Config
jwt_secret_key
  Field required [type=missing, input_value={...}, input_type=dict]
```

#### 원인
- `.env` 파일에 필수 환경 변수 미설정
- 대소문자 오타 (`JWT_SECRET_KEY` vs `jwt_secret_key`)

#### 해결 방법

**Step 1: 필수 환경 변수 체크리스트**
```bash
# backend/.env 파일에 다음 항목 필수:
JWT_SECRET_KEY=<32자 이상 랜덤 문자열>
CONVERSATION_MEMORY_BACKEND=db
DB_HOST=dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com
DB_USER=ddoksori_ro
DB_PASSWORD=<password>
DB_NAME=ddoksori
```

**Step 2: 환경 변수 검증 스크립트**
```bash
# backend/.env 파일 검증
python3 << 'EOF'
import os
from pathlib import Path

env_file = Path("backend/.env")
if not env_file.exists():
    print("❌ .env 파일이 없습니다!")
    exit(1)

required_vars = [
    "JWT_SECRET_KEY",
    "DB_HOST",
    "DB_USER",
    "DB_PASSWORD",
    "DB_NAME",
    "CONVERSATION_MEMORY_BACKEND"
]

env_content = env_file.read_text()
missing = []

for var in required_vars:
    if f"{var}=" not in env_content:
        missing.append(var)

if missing:
    print(f"❌ 누락된 환경 변수: {', '.join(missing)}")
    exit(1)
else:
    print("✅ 모든 필수 환경 변수가 설정되었습니다.")
EOF
```

**Step 3: JWT_SECRET_KEY 생성**
```bash
# 32자 이상 랜덤 문자열 생성
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# 출력 예: yQ7XvZ3mN8kP2wR5tL9xU6bC4aJ1sH0e
# 이 값을 .env 파일에 복사
```

---

### 3.2 환경 변수 로드 실패 (Docker)

#### 증상
- Backend는 시작되지만 환경 변수가 기본값으로 설정됨
- `os.getenv("JWT_SECRET_KEY")` 반환값이 None

#### 원인
- Docker Compose에서 `.env` 파일 경로 오류
- 파일 권한 문제

#### 해결 방법

**Step 1: docker-compose.yml 확인**
```yaml
# docker-compose.yml
services:
  backend:
    env_file:
      - ./backend/.env  # ← 경로 확인
    environment:
      # 또는 직접 명시
      JWT_SECRET_KEY: ${JWT_SECRET_KEY}
```

**Step 2: 환경 변수 로드 확인**
```bash
# 컨테이너 내부에서 확인
docker compose exec backend env | grep JWT_SECRET_KEY

# 출력이 있으면 정상
```

**Step 3: 파일 권한 확인**
```bash
# .env 파일 읽기 권한 확인
ls -la backend/.env

# 출력 예: -rw-r--r-- (644 권한, 정상)
```

---

## 4. 런타임 오류

### 4.1 Cleanup 서비스 시작 실패

#### 증상
```
ERROR: [Memory] Failed to start conversation cleanup service: ...
```

#### 원인
- DB 연결 실패
- `CONVERSATION_MEMORY_BACKEND` 설정이 `db`가 아님

#### 해결 방법

**Step 1: Backend 로그 확인**
```bash
docker compose logs backend | grep -i "cleanup"

# 예상 출력:
# INFO: [Memory] Conversation cleanup service started (interval: 1h)
```

**Step 2: 환경 변수 확인**
```bash
# .env 파일 확인
grep CONVERSATION_MEMORY_BACKEND backend/.env

# 출력: CONVERSATION_MEMORY_BACKEND=db (정상)
```

**Step 3: DB 연결 테스트**
```python
# 테스트 스크립트 실행
cd backend
python3 << 'EOF'
from app.supervisor.persistence.db import ConversationDB

try:
    db = ConversationDB()
    result = db.test_connection()  # 연결 테스트 메서드
    print("✅ DB 연결 성공")
except Exception as e:
    print(f"❌ DB 연결 실패: {e}")
EOF
```

---

### 4.2 OAuth 콜백 리다이렉트 오류

#### 증상
- 소셜 로그인 클릭 후 404 Not Found
- "Redirect URI mismatch" 오류

#### 원인
- OAuth Provider 설정의 Redirect URI와 실제 URL 불일치
- `BACKEND_URL`, `FRONTEND_URL` 환경 변수 오류

#### 해결 방법

**Step 1: 환경 변수 확인**
```bash
# backend/.env
grep -E "BACKEND_URL|FRONTEND_URL" backend/.env

# 출력 예:
# BACKEND_URL=http://localhost:8000
# FRONTEND_URL=http://localhost:5173
```

**Step 2: OAuth Provider 설정 확인**

**Google OAuth (console.cloud.google.com)**:
- Redirect URI: `http://localhost:8000/api/auth/google/callback`
- 프로덕션: `https://your-domain.com/api/auth/google/callback`

**Kakao OAuth (developers.kakao.com)**:
- Redirect URI: `http://localhost:8000/api/auth/kakao/callback`

**Naver OAuth (developers.naver.com)**:
- Callback URL: `http://localhost:8000/api/auth/naver/callback`

**Step 3: 엔드포인트 테스트**
```bash
# OAuth 로그인 URL 확인
curl http://localhost:8000/api/auth/google/login

# 예상: Google OAuth 페이지로 리다이렉트 (302)
```

---

### 4.3 JWT 토큰 검증 실패

#### 증상
```
HTTPException: Invalid token
```

#### 원인
- `JWT_SECRET_KEY` 불일치 (서버 재시작 시 변경됨)
- 토큰 만료

#### 해결 방법

**Step 1: JWT_SECRET_KEY 고정**
```bash
# backend/.env 파일에 고정된 값 사용
JWT_SECRET_KEY=yQ7XvZ3mN8kP2wR5tL9xU6bC4aJ1sH0e  # 변경하지 말 것!
```

**Step 2: 토큰 만료 시간 확인**
```bash
# .env 파일
JWT_TOKEN_EXPIRE_DAYS=30  # 30일 유효
```

**Step 3: 브라우저 캐시 삭제**
- 개발자 도구 → Application → Local Storage → Clear
- 재로그인

---

## 5. 성능 문제

### 5.1 DB 쿼리 지연

#### 증상
- API 응답 시간 > 1초
- `SELECT * FROM conversations` 쿼리 느림

#### 원인
- 인덱스 누락
- 대량의 데이터 누적 (게스트 세션 미삭제)

#### 해결 방법

**Step 1: 느린 쿼리 확인**
```sql
-- pg_stat_statements 확장 활성화
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- 가장 느린 쿼리 TOP 10
SELECT
    query,
    calls,
    mean_time,
    max_time
FROM pg_stat_statements
WHERE query LIKE '%conversations%'
ORDER BY mean_time DESC
LIMIT 10;
```

**Step 2: 인덱스 검증**
```sql
-- 인덱스 목록 확인
\di

-- 예상 인덱스:
-- idx_conversations_session_id
-- idx_conversations_expires_at
-- idx_conversation_turns_conversation

-- 누락 시 수동 생성
CREATE INDEX IF NOT EXISTS idx_conversations_session_id ON conversations(session_id);
```

**Step 3: Cleanup 서비스 로그 확인**
```bash
# 만료된 게스트 세션 자동 삭제 확인
docker compose logs backend | grep "Deleted.*expired"

# 예상 출력:
# INFO: Deleted 15 expired guest conversations
```

**Step 4: VACUUM 실행 (필요 시)**
```sql
-- 삭제된 데이터 정리
VACUUM ANALYZE conversations;
VACUUM ANALYZE conversation_turns;
```

---

### 5.2 메모리 사용량 증가

#### 증상
- Backend 컨테이너 메모리 > 2GB
- OOMKilled (Out of Memory)

#### 원인
- 인메모리 대화 세션 누적
- LangGraph 상태 메모리 누적

#### 해결 방법

**Step 1: 메모리 사용량 모니터링**
```bash
# 컨테이너별 메모리 사용량
docker stats --no-stream

# 출력 예:
# CONTAINER         MEM USAGE / LIMIT     MEM %
# ddoksori_backend  1.8GiB / 4GiB         45%
```

**Step 2: 메모리 캐시 정리**
```python
# backend/app/api/chat.py 확인
# 인메모리 딕셔너리 사용 여부 확인
_session_memories: Dict = {}  # ← 이 부분 제거 필요 (DB 사용 시)
```

**Step 3: Docker 메모리 제한 설정**
```yaml
# docker-compose.yml
services:
  backend:
    deploy:
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 1G
```

---

## 6. 체크리스트

### 배포 전 체크리스트

- [ ] **requirements.txt**: 모든 패키지 버전이 PyPI에 존재하는지 확인
- [ ] **backend/.env**: 필수 환경 변수 모두 설정
- [ ] **DB 마이그레이션**: DBA가 004_conversation_memory.sql 실행 완료
- [ ] **DB 권한**: ddoksori_ro 계정에 SELECT 권한 부여 확인
- [ ] **OAuth 설정**: Google/Kakao/Naver OAuth Redirect URI 등록 (선택사항)
- [ ] **Docker 메모리**: 8GB 이상 할당

### 배포 후 체크리스트

- [ ] **Health Check**: `curl http://localhost:8000/health` → `{"status": "healthy"}`
- [ ] **DB 연결**: `SELECT * FROM conversations LIMIT 1;` 정상 실행
- [ ] **Cleanup 서비스**: Backend 로그에서 "Conversation cleanup service started" 확인
- [ ] **기본 채팅**: 프론트엔드에서 메시지 전송 → 후속 질문 표시 확인
- [ ] **성능**: API 응답 시간 < 1초

---

## 7. 긴급 롤백 절차

배포 후 심각한 문제 발생 시:

### Option 1: Feature Flags로 비활성화 (빠름)

```bash
# backend/.env 수정
ANSWER_FORMAT_MODE=fixed
CONVERSATION_MEMORY_BACKEND=memory
ENABLE_FOLLOWUP_QUESTIONS=false

# Backend 재시작
docker compose restart backend
```

### Option 2: Git Revert (중간)

```bash
# 이전 커밋으로 롤백
git log --oneline
git revert <commit_hash>

# 재배포
docker compose up -d --build
```

### Option 3: DB 마이그레이션 롤백 (최후의 수단)

```sql
-- DBA 실행 (주의: 데이터 손실)
DROP TABLE IF EXISTS oauth_sessions CASCADE;
DROP TABLE IF EXISTS conversation_summaries CASCADE;
DROP TABLE IF EXISTS conversation_turns CASCADE;
DROP TABLE IF EXISTS conversations CASCADE;
DROP TABLE IF EXISTS users CASCADE;
```

---

## 8. 추가 리소스

### 로그 위치
- Backend 로그: `docker compose logs -f backend`
- 또는: `backend/logs/app.log` (파일 로깅 설정 시)

### 모니터링 대시보드
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000

### 데이터베이스 GUI
- CloudBeaver: http://localhost:8978
- 또는 DBeaver, pgAdmin 4 사용

### 공식 문서
- FastAPI: https://fastapi.tiangolo.com/
- LangGraph: https://langchain-ai.github.io/langgraph/
- Anthropic API: https://docs.anthropic.com/
- PostgreSQL: https://www.postgresql.org/docs/

---

## 9. 추가 도움이 필요한 경우

1. **GitHub Issues**: 프로젝트 리포지토리에 이슈 등록
2. **로그 수집**: `docker compose logs backend > backend_logs.txt`
3. **환경 정보 수집**:
   ```bash
   docker --version
   docker compose version
   python --version
   conda --version
   ```

---

**마지막 업데이트**: 2026-01-28
