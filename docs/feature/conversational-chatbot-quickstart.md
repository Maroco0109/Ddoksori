# 대화형 챗봇 & 소셜 로그인 - Quick Start Guide

**작업 ID**: `feature/34-e2e`
**최종 업데이트**: 2026-01-28

---

## 🎯 개요

이 가이드는 **대화형 챗봇 전환** 및 **소셜 로그인** 기능을 빠르게 시작하고 검증하는 방법을 설명합니다.

### 주요 변경사항

- ✅ **유연한 답변 형식**: 쿼리 타입별 동적 답변 구조 (3가지 형식)
- ✅ **장기 메모리 (30턴)**: PostgreSQL 기반 대화 영속화
- ✅ **후속 질문**: 템플릿 기반 맥락적 질문 생성 (29개 템플릿)
- ✅ **소셜 로그인**: Google, Naver OAuth 2.0 인증
- ✅ **게스트 세션 관리**: 24시간 TTL 자동 삭제

---

## ⚡ 5분 Quick Start

### 1. 환경 변수 설정

**Backend** (`.env`):
```bash
# JWT Secret (필수 - 32자 이상)
JWT_SECRET_KEY=change-this-to-random-32-char-string-in-production

# Feature Flags (활성화)
ANSWER_FORMAT_MODE=flexible
CONVERSATION_MEMORY_BACKEND=db
ENABLE_FOLLOWUP_QUESTIONS=true

# Memory Configuration
MAX_CONVERSATION_TURNS=30
SLIDING_WINDOW_SIZE=10
GUEST_SESSION_TTL_HOURS=24
CLEANUP_INTERVAL_HOURS=1

# OAuth (나중에 설정 가능)
GOOGLE_CLIENT_ID=your-client-id-here
GOOGLE_CLIENT_SECRET=your-secret-here
# NAVER_CLIENT_ID=...
```

### 2. 데이터베이스 마이그레이션

#### ⚠️ 중요: RDS vs 로컬 DB 환경 구분

**현재 환경 확인**:
```bash
# .env 파일에서 DB 설정 확인
grep -E "DB_HOST|DB_USER|USE_RDS_FOR_TESTS" .env
```

#### 옵션 A: 로컬 테스트 환경 (권장)

로컬 Docker PostgreSQL 사용:

```bash
# 1. 로컬 DB 시작
docker compose up -d postgres

# 2. .env 설정 변경
# DB_HOST=localhost
# USE_RDS_FOR_TESTS=false

# 3. 마이그레이션 실행
psql -h localhost -U postgres -d ddoksori -f backend/database/migrations/004_conversation_memory.sql

# 4. 테이블 생성 확인
psql -h localhost -U postgres -d ddoksori -c "\dt" | grep -E "conversations|users|oauth"
```

**예상 출력**:
```
 public | conversation_summaries | table | postgres
 public | conversation_turns     | table | postgres
 public | conversations          | table | postgres
 public | oauth_sessions         | table | postgres
 public | users                  | table | postgres
```

#### 옵션 B: RDS 사용 (프로덕션/스테이징)

**⚠️ 주의사항**:
1. **READ-ONLY 계정 확인**: `.env`의 `DB_USER`가 `ddoksori_ro`이면 마이그레이션 불가
2. **쓰기 권한 계정 필요**: DBA 또는 관리자 계정으로 실행
3. **백업 필수**: 마이그레이션 전 DB 스냅샷 생성
4. **기존 테이블 미접촉**: 새로운 5개 테이블만 생성

**RDS 마이그레이션 절차**:

```bash
# 1. 현재 계정 권한 확인
psql -h $DB_HOST -U $DB_USER -d ddoksori -c "\du $DB_USER"

# 출력 예시:
# ddoksori_ro | Cannot login, Cannot create DB, Cannot create roles
# ↑ READ-ONLY 계정이면 다음 단계 진행 불가

# 2. 쓰기 권한이 있는 계정으로 마이그레이션 실행
psql -h your-db-instance.ap-northeast-2.rds.amazonaws.com \
     -U ddoksori_admin \
     -d ddoksori \
     -f backend/database/migrations/004_conversation_memory.sql

# 3. 테이블 생성 확인
psql -h $DB_HOST -U $DB_USER -d ddoksori -c "\dt" | grep -E "conversations|users|oauth"
```

**READ-ONLY 계정인 경우**:
- DBA에게 마이그레이션 실행 요청
- 또는 AWS Console에서 RDS 스냅샷 생성 후 관리자 계정으로 실행
- 또는 로컬 테스트 환경 사용 (옵션 A)

**마이그레이션 미실행 시**:
- 기능은 작동하지만 메모리가 DB에 저장되지 않음
- Feature flag를 `CONVERSATION_MEMORY_BACKEND=memory`로 설정하여 인메모리 모드 사용 가능

### 3. 백엔드 실행

```bash
cd backend
conda activate dsr
uvicorn app.main:app --reload
```

**로그 확인**:
```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     [Memory] Conversation cleanup service started (interval: 1h)
INFO:     Application startup complete.
```

### 4. 프론트엔드 실행

```bash
cd frontend
npm run dev
```

**브라우저 열기**: `http://localhost:5173`

---

## 🧪 기능 검증 (10분)

### Test 1: 후속 질문 기능

1. 채팅 페이지 접속: `http://localhost:5173/chat`
2. 메시지 전송: "노트북 환불 문의"
3. **확인사항**:
   - ✅ AI 답변에 구조화된 섹션 표시
   - ✅ 답변 하단에 "💡 이런 질문도 해보세요:" 섹션
   - ✅ 2-3개 클릭 가능한 질문 버튼
4. 후속 질문 클릭
5. **확인사항**:
   - ✅ 질문이 자동으로 전송됨
   - ✅ 새로운 AI 답변 표시
   - ✅ 새로운 후속 질문 표시

**✅ 성공**: 후속 질문이 정상 작동함

---

### Test 2: 메모리 영속화

1. 메시지 3개 전송
2. **브라우저 새로고침** (F5)
3. **확인사항**:
   - ✅ 이전 대화 내역 그대로 표시
4. 메시지 2개 더 전송 (총 5개)
5. **데이터베이스 확인**:
   ```sql
   -- 최근 대화 세션 확인
   SELECT conversation_id, session_id, user_id, turn_count, created_at
   FROM conversations
   ORDER BY created_at DESC
   LIMIT 1;

   -- 대화 턴 확인
   SELECT turn_number, role, LEFT(content, 50) as preview
   FROM conversation_turns
   WHERE conversation_id = 'your-conversation-id'
   ORDER BY turn_number;
   ```
6. **예상 출력**: 10개 턴 (5 user + 5 assistant)

**✅ 성공**: 메모리가 DB에 영속화됨

---

### Test 3: 유연한 답변 형식

**Test Case A - 인사 (simple_general)**:
- 전송: "안녕하세요"
- **예상**: 친근한 답변, 섹션 구조 없음

**Test Case B - 분쟁 상담 (full_dispute)**:
- 전송: "노트북 화면 깨짐, 환불 가능?"
- **예상**:
  ```
  ## 1. 유사 사례 분석
  (내용)

  ## 2. 관련 법령 및 기준
  (내용)

  ## 3. 추가 안내
  (내용)
  ```

**Test Case C - 제한 도메인 (info_only)**:
- 전송: "주식 투자 손실 환불 가능?"
- **예상**: 금융감독원 안내, 간결한 답변

**✅ 성공**: 쿼리 타입별로 다른 형식 적용됨

---

### Test 4: 게스트 세션 TTL

1. **시크릿/incognito 창** 열기
2. 메시지 2개 전송 (게스트 세션)
3. **DB 확인**:
   ```sql
   SELECT session_id, user_id, expires_at,
          EXTRACT(EPOCH FROM (expires_at - NOW())) / 3600 as hours_left
   FROM conversations
   WHERE user_id IS NULL
   ORDER BY created_at DESC
   LIMIT 1;
   ```
4. **예상**: `user_id = NULL`, `hours_left ≈ 24`

**✅ 성공**: 게스트 세션 24시간 만료 설정됨

---

## 🔐 OAuth 로그인 설정 (선택사항)

OAuth를 사용하지 않아도 모든 기능이 작동하지만, 로그인 기능을 테스트하려면:

### Google OAuth 설정 (10분)

1. **Google Cloud Console** 접속: https://console.cloud.google.com/
2. 프로젝트 생성 or 선택
3. **APIs & Services** → **OAuth consent screen**
   - User Type: External
   - App name: DDOKSORI
   - User support email: 본인 이메일
   - Developer contact: 본인 이메일
4. **Credentials** → **Create OAuth 2.0 Client ID**
   - Application type: Web application
   - Name: DDOKSORI Development
   - **Authorized redirect URIs**:
     - `http://localhost:8000/api/auth/google/callback`
5. **Client ID**와 **Client Secret** 복사
6. `backend/.env` 업데이트:
   ```bash
   GOOGLE_CLIENT_ID=123456789-abc.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-abc123def456
   ```
7. 백엔드 재시작: `uvicorn app.main:app --reload`

### 로그인 테스트

1. 프론트엔드 접속: `http://localhost:5173`
2. "로그인" 버튼 클릭
3. "Google로 계속하기" 클릭
4. Google 계정으로 로그인
5. **확인사항**:
   - ✅ 홈으로 리다이렉트
   - ✅ 헤더에 사용자 이름 표시
   - ✅ 아바타 이미지 표시 (있는 경우)

**DB 확인**:
```sql
SELECT user_id, email, name, provider, last_login_at
FROM users
WHERE provider = 'google';
```

**✅ 성공**: OAuth 로그인 정상 작동

---

## 🎛️ Feature Flags

기능별로 켜고 끄기 가능합니다:

```bash
# backend/.env

# 1. 유연한 답변 형식 비활성화 (기존 3-섹션 고정 형식 사용)
ANSWER_FORMAT_MODE=fixed

# 2. 메모리 DB 저장 비활성화 (인메모리만 사용)
CONVERSATION_MEMORY_BACKEND=memory

# 3. 후속 질문 비활성화
ENABLE_FOLLOWUP_QUESTIONS=false
```

**재시작 후 적용**: `uvicorn app.main:app --reload`

---

## 🔍 RDS 계정 권한 확인

현재 사용 중인 DB 계정이 READ-ONLY인지 확인:

```bash
# 계정 권한 확인
psql -h $DB_HOST -U $DB_USER -d ddoksori -c "\du $DB_USER"

# 출력 예시:
# ddoksori_ro | Cannot login, Cannot create DB, Cannot create roles
```

**권한별 가능한 작업**:

| 권한 | SELECT | INSERT/UPDATE/DELETE | CREATE TABLE | DROP TABLE |
|------|--------|---------------------|--------------|------------|
| ddoksori_ro (READ-ONLY) | ✅ | ❌ | ❌ | ❌ |
| ddoksori_admin (WRITE) | ✅ | ✅ | ✅ | ✅ |

**READ-ONLY 계정으로 할 수 있는 것**:
- ✅ 기능 검증 (조회만 사용)
- ✅ 모니터링 쿼리 실행
- ✅ E2E 테스트 (E2E-07 제외)

**READ-ONLY 계정으로 할 수 없는 것**:
- ❌ DB 마이그레이션 실행
- ❌ 게스트 세션 수동 삭제
- ❌ 테스트 데이터 삽입

**대안**:
1. 로컬 Docker PostgreSQL 사용 (전체 권한)
2. DBA에게 마이그레이션 실행 요청
3. 관리자 계정으로 임시 접속

---

## 🐛 문제 해결

### 문제: "Conversation cleanup service started" 로그가 안 보임

**원인**: DB 백엔드가 활성화되지 않음

**해결**:
```bash
# .env 확인
grep CONVERSATION_MEMORY_BACKEND .env

# 출력이 db여야 함
CONVERSATION_MEMORY_BACKEND=db

# 백엔드 재시작
```

---

### 문제: 후속 질문이 안 나옴

**원인**: Feature flag 비활성화 or API 응답 오류

**해결**:
```bash
# 1. Feature flag 확인
grep ENABLE_FOLLOWUP_QUESTIONS backend/.env

# 2. API 응답 확인
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "환불 문의", "session_id": "test", "chat_type": "dispute"}' \
  | jq '.followup_questions'

# 예상 출력: ["질문1", "질문2", ...]
# 출력이 [] or null이면 문제 있음

# 3. 백엔드 로그 확인
tail -f backend/logs/app.log | grep followup
```

---

### 문제: DB 테이블이 없음

**증상**:
```
relation "conversations" does not exist
```

**해결**:
```bash
# 마이그레이션 재실행
psql -U postgres -d ddoksori -f backend/database/migrations/004_conversation_memory.sql

# 에러 확인
# 만약 "already exists" 에러면 정상 (이미 생성됨)
```

---

### 문제: OAuth 로그인 시 "Invalid state"

**원인**: State가 만료됨 (10분 TTL)

**해결**: 다시 로그인 시도 (처음부터)

---

### 문제: 401 Unauthorized on /chat

**원인**: JWT가 만료되었거나 잘못됨

**해결**:
1. 로그아웃 후 재로그인
2. localStorage 확인:
   ```javascript
   // 브라우저 콘솔
   localStorage.getItem('auth-storage')
   ```
3. JWT 검증: https://jwt.io/ 에서 토큰 붙여넣기

---

## 📊 모니터링

### 주요 메트릭

**DB 쿼리 성능**:
```sql
-- 느린 쿼리 확인 (PostgreSQL)
SELECT query, calls, total_time, mean_time
FROM pg_stat_statements
WHERE query LIKE '%conversations%'
ORDER BY mean_time DESC
LIMIT 10;
```

**목표**:
- `get_conversation_by_session`: < 10ms (p95)
- `add_turn`: < 15ms (p95)
- `get_conversation_history`: < 20ms (p95)

**대화 통계**:
```sql
-- 총 대화 수
SELECT COUNT(*) FROM conversations;

-- 게스트 vs 로그인 사용자
SELECT
  CASE WHEN user_id IS NULL THEN 'guest' ELSE 'authenticated' END as user_type,
  COUNT(*) as count
FROM conversations
GROUP BY user_type;

-- 평균 턴 수
SELECT AVG(turn_count) FROM conversations;

-- 30턴 이상 대화 (압축 발생)
SELECT COUNT(*) FROM conversations WHERE turn_count >= 30;
```

**Cleanup 서비스 로그**:
```bash
# 실행 확인
grep "Conversation cleanup service started" backend/logs/app.log

# 삭제 기록
grep "Deleted.*expired guest conversations" backend/logs/app.log

# 예상 출력:
# [2026-01-28 10:00:00] INFO: Deleted 5 expired guest conversations
```

---

## 🚀 프로덕션 배포 체크리스트

### 배포 전

- [ ] `JWT_SECRET_KEY` 변경 (최소 32자, cryptographically secure)
- [ ] OAuth Client ID/Secret 발급 (Google, Naver)
- [ ] Production Redirect URI 등록:
  - Google: `https://your-domain.com/api/auth/google/callback`
  - Naver: `https://your-domain.com/api/auth/naver/callback`
- [ ] `.env` BACKEND_URL/FRONTEND_URL 변경
- [ ] DB 마이그레이션 실행 (production DB)
- [ ] DB 인덱스 생성 확인
- [ ] Feature flags 설정 (점진적 활성화 권장)

### 배포 순서

1. **Feature flags 비활성화 상태로 배포**:
   ```bash
   ANSWER_FORMAT_MODE=fixed
   CONVERSATION_MEMORY_BACKEND=memory
   ENABLE_FOLLOWUP_QUESTIONS=false
   ```
2. 배포 완료 후 smoke test
3. **단계별 활성화** (각 단계마다 30분-1시간 모니터링):
   ```bash
   # Step 1
   ENABLE_FOLLOWUP_QUESTIONS=true

   # Step 2 (Step 1 정상 확인 후)
   ANSWER_FORMAT_MODE=flexible

   # Step 3 (Step 2 정상 확인 후)
   CONVERSATION_MEMORY_BACKEND=db
   ```

### 배포 후 모니터링 (24시간)

- [ ] DB 쿼리 latency (p95 < 50ms 목표)
- [ ] LLM token 사용량 (30% 증가 예상)
- [ ] 후속 질문 클릭률 (> 10% 목표)
- [ ] OAuth 성공률 (> 95% 목표)
- [ ] 에러율 (< 1% 목표)
- [ ] 답변 품질 샘플링 (첫 50개 수동 검토)

---

## 📚 추가 문서

- **전체 아키텍처 & 상세 구현**: `/docs/feature/conversational-chatbot-transformation.md`
- **E2E 테스트 가이드**: `/docs/testing/e2e-test-guide.md`
- **MAS Supervisor 아키텍처**: `/docs/guides/MAS_SUPERVISOR_ARCHITECTURE.md`

---

## 💬 지원

- GitHub Issues: [anthropics/ddoksori/issues](https://github.com/anthropics/ddoksori/issues)
- Slack: #ddoksori-dev
- Email: dev@ddoksori.ai

---

**마지막 업데이트**: 2026-01-28
**작성자**: Claude Code
**버전**: 1.0