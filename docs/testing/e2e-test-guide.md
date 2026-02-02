# E2E Testing Guide - Conversational Chatbot & Social Login

**Feature**: `feature/34-e2e`
**Last Updated**: 2026-01-28

---

## Prerequisites

### Environment Setup

#### 1. Database Connection (RDS)

```bash
# 현재 DB 설정 확인
grep -E "DB_HOST|DB_USER" backend/.env
```

**RDS 환경** (기본):
```bash
# backend/.env 설정 확인
# DB_HOST=<your-rds-endpoint>.ap-northeast-2.rds.amazonaws.com
# DB_USER=ddoksori_ro  (READ-ONLY)
# DB_PASSWORD=<your-password>
```

> 로컬 PostgreSQL 컨테이너는 더 이상 사용하지 않습니다.
> 모든 테스트는 RDS에 직접 연결합니다.

**READ-ONLY 계정 제약사항**:
- ✅ E2E-01 ~ E2E-06: 정상 실행 (조회만 사용)
- ❌ E2E-07 (Guest Session Cleanup): 수동 삭제 불가
  - 대안: Cleanup 서비스 로그 확인으로 대체

#### 2. Backend Running

```bash
cd backend
conda activate dsr
uvicorn app.main:app --reload
```

#### 3. Frontend Running

```bash
cd frontend
npm run dev
```

4. **Redis Running** (for answer caching):
   ```bash
   docker compose up -d redis
   ```

5. **Environment Variables Configured**:
   - Backend `.env` with OAuth credentials
   - Frontend `.env` with `VITE_API_BASE_URL`

6. **Database Migration Applied**:
   ```bash
   psql -U postgres -d ddoksori -f backend/database/migrations/004_conversation_memory.sql
   ```

---

## Test Suite Overview

| Test ID | Feature | Duration | Prerequisites |
|---------|---------|----------|---------------|
| E2E-01 | OAuth Login (Google) | 2 min | Google OAuth credentials |
| E2E-02 | OAuth Login (Kakao) | 2 min | Kakao OAuth credentials |
| E2E-03 | OAuth Login (Naver) | 2 min | Naver OAuth credentials |
| E2E-04 | Follow-up Questions | 3 min | Backend + Frontend running |
| E2E-05 | Memory Persistence (Logged In) | 5 min | OAuth login completed |
| E2E-06 | Memory Persistence (Guest) | 3 min | None |
| E2E-07 | Guest Session Cleanup | 30 sec | DB access |
| E2E-08 | Flexible Answer Formatting | 3 min | None |
| E2E-09 | JWT Authentication | 2 min | OAuth login completed |
| E2E-10 | Logout & Token Cleanup | 1 min | OAuth login completed |

**Total Duration**: ~25 minutes (all tests)

---

## Test Cases

### E2E-01: OAuth Login (Google)

**Objective**: Verify Google OAuth flow end-to-end

**Steps**:

1. Open frontend: `http://localhost:5173`
2. Click "로그인" button in header
3. **Expected**: Login modal appears with 3 social login buttons
4. Click "Google로 계속하기" button
5. **Expected**: Browser redirects to `https://accounts.google.com/o/oauth2/v2/auth?...`
6. Sign in with test Google account:
   - Email: `test@example.com` (use your test account)
   - Password: (your test password)
7. **Expected**: OAuth consent screen appears (first login only)
8. Click "Allow" to grant permissions
9. **Expected**: Browser redirects to `http://localhost:8000/api/auth/google/callback?code=...&state=...`
10. **Expected**: Backend exchanges code for token
11. **Expected**: Browser redirects to `http://localhost:5173/auth/callback?token=...`
12. **Expected**: Frontend stores JWT token
13. **Expected**: "로그인 중..." message appears briefly
14. **Expected**: Redirect to home page `/`
15. **Expected**: User name appears in header (e.g., "Test User")
16. **Expected**: Avatar image appears (if available)

**Verification Checklist**:
- [ ] Login modal opened correctly
- [ ] Google OAuth consent screen appeared
- [ ] Redirect back to frontend with token
- [ ] User name displayed in header
- [ ] Avatar image displayed (if available)
- [ ] No console errors

**Database Verification**:
```sql
-- Check user was created
SELECT user_id, email, name, provider, last_login_at
FROM users
WHERE email = 'test@example.com';

-- Expected: 1 row with provider='google'
```

**Failure Scenarios**:
- **Error: "Invalid state"** → OAuth state expired (10-min TTL), retry
- **Error: "Invalid credentials"** → Check `.env` CLIENT_ID/SECRET
- **Error: "Redirect URI mismatch"** → Check OAuth app settings in Google Cloud Console

---

### E2E-02: OAuth Login (Kakao)

**Objective**: Verify Kakao OAuth flow

**Steps**: (Same as E2E-01, but click "Kakao로 계속하기")

1. Click "Kakao로 계속하기"
2. **Expected**: Redirect to `https://kauth.kakao.com/oauth/authorize?...`
3. Sign in with Kakao account
4. Verify user name in header

**Database Verification**:
```sql
SELECT user_id, email, name, provider
FROM users
WHERE provider = 'kakao';
```

---

### E2E-03: OAuth Login (Naver)

**Objective**: Verify Naver OAuth flow

**Steps**: (Same as E2E-01, but click "Naver로 계속하기")

1. Click "Naver로 계속하기"
2. **Expected**: Redirect to `https://nid.naver.com/oauth2.0/authorize?...`
3. Sign in with Naver account
4. Verify user name in header

**Database Verification**:
```sql
SELECT user_id, email, name, provider
FROM users
WHERE provider = 'naver';
```

---

### E2E-04: Follow-up Questions

**Objective**: Verify contextual follow-up question generation and interaction

**Steps**:

1. Ensure you're on chat page: `http://localhost:5173/chat` (or click "똑소리 챗봇" in sidebar)
2. Send message: "노트북 화면이 깨져서 환불 받고 싶어요"
3. **Expected**: AI response appears within 5 seconds
4. **Expected**: Answer contains structured sections:
   - "## 1. 유사 사례 분석"
   - "## 2. 관련 법령 및 기준"
   - "## 3. 추가 안내"
5. **Expected**: Below the answer, follow-up questions section appears:
   - Title: "💡 이런 질문도 해보세요:"
   - 2-3 clickable question buttons
6. **Verify**: Questions are contextual, e.g.:
   - "환불 처리 기간은 얼마나 걸리나요?"
   - "분쟁 조정 신청 시 필요한 서류는 무엇인가요?"
   - "유사한 사례의 조정 결과는 어떻게 되었나요?"
7. Click the first follow-up question
8. **Expected**: Question appears as new user message in chat
9. **Expected**: AI response appears with new follow-up questions
10. Repeat for 2 more follow-up clicks
11. **Expected**: Each response has contextual follow-up questions

**Verification Checklist**:
- [ ] AI response appeared
- [ ] Follow-up questions section rendered with 💡 emoji
- [ ] 2-3 questions displayed
- [ ] Questions are contextually relevant
- [ ] Clicking question sends it as new message
- [ ] New response has new follow-up questions

**API Response Verification**:
```bash
# Send test request
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "노트북 환불 문의",
    "session_id": "test_session",
    "chat_type": "dispute"
  }' | jq '.followup_questions'

# Expected output:
# [
#   "환불 처리 기간은 얼마나 걸리나요?",
#   "분쟁 조정 신청 시 필요한 서류는 무엇인가요?",
#   "..."
# ]
```

**Edge Case Tests**:
- Send greeting: "안녕하세요"
  - **Expected**: Friendly response, NO structured sections
  - **Expected**: General follow-up questions (e.g., "어떤 도움이 필요하신가요?")
- Send vague query: "환불"
  - **Expected**: Clarifying questions appear (e.g., "구매하신 제품이나 서비스의 정확한 명칭을 알려주실 수 있나요?")

---

### E2E-05: Memory Persistence (Logged In)

**Objective**: Verify conversation history persists across sessions for authenticated users

**Prerequisites**: Complete E2E-01 (logged in with Google)

**Steps**:

1. Ensure you're logged in (user name visible in header)
2. Open chat page: `http://localhost:5173/chat`
3. Note the session ID (check network tab or localStorage)
4. Send 5 messages:
   - Message 1: "노트북 환불 문의"
   - Message 2: (Click follow-up question)
   - Message 3: "구매일은 2025년 1월 15일이에요"
   - Message 4: "구매 금액은 150만원입니다"
   - Message 5: "온라인 쇼핑몰에서 구매했어요"
5. **Expected**: All 5 messages + AI responses visible in chat UI
6. **Refresh page** (F5 or Cmd+R)
7. **Expected**: Chat UI reloads
8. **Expected**: All 5 messages + AI responses are still visible
9. Send 2 more messages:
   - Message 6: "환불 신청 어떻게 하나요?"
   - Message 7: "감사합니다"
10. **Expected**: Total 7 user messages + 7 AI responses
11. **Close browser completely**
12. **Re-open browser** → Navigate to `http://localhost:5173/chat`
13. **Expected**: Previous conversation (7 messages) is still visible

**Verification Checklist**:
- [ ] 5 messages sent successfully
- [ ] Page refresh preserves conversation
- [ ] Additional messages can be sent
- [ ] Browser close + reopen preserves conversation
- [ ] Total turn count = 14 (7 user + 7 assistant)

**Database Verification**:
```sql
-- Get conversation ID
SELECT conversation_id, session_id, user_id, turn_count
FROM conversations
WHERE session_id = 'your-session-id';

-- Check turns
SELECT turn_number, role, LEFT(content, 50) as content_preview
FROM conversation_turns
WHERE conversation_id = 'your-conversation-id'
ORDER BY turn_number;

-- Expected: 14 rows (7 user + 7 assistant)

-- Check expires_at is NULL (logged in users don't expire)
SELECT expires_at
FROM conversations
WHERE conversation_id = 'your-conversation-id';

-- Expected: NULL
```

**Edge Case Test - 30-Turn Compaction**:

1. Continue conversation to 30 total turns (15 message pairs)
2. **Expected**: After 30th turn, compaction triggers
3. **Expected**: Chat UI still shows recent messages
4. **Verify in DB**:
   ```sql
   -- Check summary was created
   SELECT compacted_turn_count, dispute_type, key_facts
   FROM conversation_summaries
   WHERE conversation_id = 'your-conversation-id';

   -- Expected: 1 row with compacted_turn_count=30

   -- Check only recent turns in memory
   -- (DB should still have all turns for audit)
   SELECT COUNT(*)
   FROM conversation_turns
   WHERE conversation_id = 'your-conversation-id';

   -- Expected: 30 (all turns preserved in DB)
   ```

---

### E2E-06: Memory Persistence (Guest)

**Objective**: Verify guest session memory works but has 24-hour TTL

**Prerequisites**: None (use incognito/private window)

**Steps**:

1. Open **incognito/private window**
2. Navigate to `http://localhost:5173/chat`
3. **Expected**: Not logged in (no user name in header)
4. Send 3 messages:
   - Message 1: "안녕하세요"
   - Message 2: "노트북 환불 문의"
   - Message 3: "감사합니다"
5. **Expected**: All 3 messages visible
6. **Refresh page** (F5)
7. **Expected**: Messages still visible (same session)
8. **Close incognito window**
9. **Open NEW incognito window** → Navigate to `http://localhost:5173/chat`
10. **Expected**: Previous conversation is GONE (new session)

**Verification Checklist**:
- [ ] Guest can send messages
- [ ] Guest conversation persists on refresh (same session)
- [ ] New incognito window = new session (conversation lost)

**Database Verification**:
```sql
-- Find guest sessions
SELECT conversation_id, session_id, user_id, expires_at
FROM conversations
WHERE user_id IS NULL
ORDER BY created_at DESC
LIMIT 5;

-- Expected: user_id = NULL, expires_at ≈ NOW() + 24 hours

-- Check exact expiration
SELECT
  conversation_id,
  expires_at,
  EXTRACT(EPOCH FROM (expires_at - NOW())) / 3600 AS hours_until_expiry
FROM conversations
WHERE user_id IS NULL;

-- Expected: hours_until_expiry ≈ 24
```

---

### E2E-07: Guest Session Cleanup

**Objective**: Verify automatic deletion of expired guest sessions

**Prerequisites**: DB access (쓰기 권한 필요)

**⚠️ RDS READ-ONLY 계정 제약사항**:
- `ddoksori_ro` 계정으로는 수동 UPDATE/DELETE 불가
- **대안**: Cleanup 서비스 로그 확인으로 검증

**Steps (쓰기 권한 있는 경우)**:

1. Open **incognito window** → Send 1 message (creates guest session)
2. **Get conversation ID from DB**:
   ```sql
   SELECT conversation_id, session_id, expires_at
   FROM conversations
   WHERE user_id IS NULL
   ORDER BY created_at DESC
   LIMIT 1;
   ```
3. **Manually expire the session** (simulate 24 hours passed):
   ```sql
   -- ⚠️ 쓰기 권한 필요
   UPDATE conversations
   SET expires_at = NOW() - INTERVAL '1 hour'
   WHERE conversation_id = 'your-conversation-id';
   ```
4. **Wait for cleanup service** (runs every hour)
   - OR manually trigger:
     ```bash
     # Check backend logs
     tail -f backend/logs/app.log | grep "cleanup"
     ```
5. **Check DB again**:
   ```sql
   SELECT * FROM conversations WHERE conversation_id = 'your-conversation-id';
   -- Expected: 0 rows (deleted)
   ```
6. **Verify cascade delete** (turns and summary also deleted):
   ```sql
   SELECT * FROM conversation_turns WHERE conversation_id = 'your-conversation-id';
   -- Expected: 0 rows

   SELECT * FROM conversation_summaries WHERE conversation_id = 'your-conversation-id';
   -- Expected: 0 rows
   ```

**Verification Checklist**:
- [ ] Guest session created with expires_at
- [ ] Manual expiration successful
- [ ] Cleanup service detected and deleted session
- [ ] Cascade delete removed turns and summary
- [ ] Backend logs show: "Deleted N expired guest conversations"

**Cleanup Service Logs** (expected output):
```
[2026-01-28 10:00:00] INFO: [Memory] Conversation cleanup service started (interval: 1h)
[2026-01-28 11:00:00] INFO: [Memory] Deleted 3 expired guest conversations
```

---

### E2E-08: Flexible Answer Formatting

**Objective**: Verify dynamic answer formatting based on query type

**Steps**:

#### Test Case 1: Greeting (simple_general format)

1. Send message: "안녕하세요"
2. **Expected**: Friendly response, e.g., "안녕하세요! 무엇을 도와드릴까요?"
3. **Expected**: NO structured sections (no "## 1. ...")
4. **Expected**: NO legal disclaimer
5. **Expected**: Follow-up questions: "어떤 도움이 필요하신가요?" etc.

#### Test Case 2: Dispute Query (full_dispute format)

1. Send message: "노트북 화면이 깨져서 환불 받고 싶어요"
2. **Expected**: Structured response with sections:
   - "## 1. 유사 사례 분석"
   - "## 2. 관련 법령 및 기준"
   - "## 3. 추가 안내"
3. **Expected**: Legal disclaimer at bottom
4. **Expected**: Formal tone

#### Test Case 3: Restricted Domain (info_only format)

1. Send message: "주식 투자로 손해 봤는데 환불 받을 수 있나요?"
2. **Expected**: Brief response referring to specialized agency
3. **Expected**: "금융감독원" or "금융소비자보호센터" mentioned
4. **Expected**: Agency contact info provided
5. **Expected**: NO detailed legal analysis

#### Test Case 4: General Info Query (simple_general format)

1. Send message: "소비자 분쟁이란 무엇인가요?"
2. **Expected**: Informative but friendly response
3. **Expected**: NO strict section structure
4. **Expected**: Educational tone

**Verification Checklist**:
- [ ] Greeting → friendly, no sections
- [ ] Dispute → structured sections, formal
- [ ] Restricted → agency referral, brief
- [ ] General info → informative, no sections

**API Verification**:
```bash
# Test format selection
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "안녕하세요", "session_id": "test", "chat_type": "general"}' \
  | jq -r '.answer' | grep "##"

# Expected: No matches (no sections)
```

---

### E2E-09: JWT Authentication

**Objective**: Verify JWT is sent with all API requests and authenticated routes work

**Prerequisites**: Complete E2E-01 (logged in)

**Steps**:

1. Ensure you're logged in (user name visible)
2. **Open browser DevTools** → Network tab
3. Send a chat message
4. **Find POST request** to `/chat` in Network tab
5. **Click request** → Headers tab
6. **Verify**: Authorization header present:
   ```
   Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
   ```
7. **Copy JWT token** → Go to [jwt.io](https://jwt.io/)
8. **Paste token** → Verify payload:
   ```json
   {
     "sub": "google:123456789",
     "email": "test@example.com",
     "provider": "google",
     "exp": 1738000000,
     "iat": 1735000000
   }
   ```
9. **Test authenticated endpoint**:
   ```bash
   # Get your JWT from DevTools or localStorage
   JWT="your-jwt-token-here"

   # Call /auth/me
   curl -X GET http://localhost:8000/auth/me \
     -H "Authorization: Bearer $JWT"

   # Expected: User info returned
   # {
   #   "user_id": "google:123456789",
   #   "email": "test@example.com",
   #   "name": "Test User",
   #   "avatar_url": "...",
   #   "provider": "google"
   # }
   ```
10. **Test invalid token**:
    ```bash
    curl -X GET http://localhost:8000/auth/me \
      -H "Authorization: Bearer invalid_token"

    # Expected: 401 Unauthorized
    # {"detail": "Invalid token"}
    ```

**Verification Checklist**:
- [ ] Authorization header present in all requests
- [ ] JWT payload contains correct user info
- [ ] /auth/me returns user data
- [ ] Invalid token returns 401
- [ ] No console errors

---

### E2E-10: Logout & Token Cleanup

**Objective**: Verify logout clears token and redirects to home

**Prerequisites**: Complete E2E-01 (logged in)

**Steps**:

1. Ensure you're logged in (user name visible)
2. **Open browser DevTools** → Application tab → Local Storage
3. **Verify**: Token exists in localStorage:
   - Key: `auth-storage`
   - Value: `{"state": {..., "token": "eyJ..."}}`
4. Click user avatar/name in header
5. **Expected**: Dropdown menu appears with "로그아웃" option
6. Click "로그아웃"
7. **Expected**: Token removed from localStorage
8. **Expected**: User name disappears from header
9. **Expected**: Redirect to home page `/`
10. **Refresh page** (F5)
11. **Expected**: Still logged out (token not restored)
12. Try sending a chat message
13. **Expected**: Message sent as guest (no Authorization header)

**Verification Checklist**:
- [ ] Logout button visible
- [ ] Token removed from localStorage
- [ ] User name removed from UI
- [ ] Redirect to home
- [ ] Refresh doesn't restore login
- [ ] Subsequent requests are guest requests

**API Verification**:
```bash
# After logout, try authenticated endpoint
curl -X GET http://localhost:8000/auth/me

# Expected: 401 or 403 (no token)
```

---

## Automated E2E Testing (Future)

### Playwright Script Example

```typescript
// e2e/oauth-login.spec.ts
import { test, expect } from '@playwright/test';

test('OAuth login flow (Google)', async ({ page }) => {
  await page.goto('http://localhost:5173');

  // Open login modal
  await page.click('text=로그인');
  await expect(page.locator('text=Google로 계속하기')).toBeVisible();

  // Click Google login
  await page.click('text=Google로 계속하기');

  // Wait for Google OAuth page
  await page.waitForURL(/accounts\.google\.com/);

  // Fill in test credentials (use test account)
  await page.fill('input[type="email"]', 'test@example.com');
  await page.click('text=Next');
  await page.fill('input[type="password"]', 'test_password');
  await page.click('text=Next');

  // Wait for redirect back to app
  await page.waitForURL(/localhost:5173\/auth\/callback/);

  // Wait for final redirect to home
  await page.waitForURL('http://localhost:5173/');

  // Verify logged in
  await expect(page.locator('text=Test User')).toBeVisible();
});
```

**Run Playwright tests**:
```bash
cd frontend
npm run test:e2e
```

---

## Performance Benchmarks

### Response Time Targets

| Endpoint | p50 | p95 | p99 |
|----------|-----|-----|-----|
| POST /chat | < 1s | < 3s | < 5s |
| GET /auth/me | < 50ms | < 100ms | < 200ms |
| POST /chat (with memory) | < 1.2s | < 3.5s | < 6s |

### Database Query Targets

| Query | p50 | p95 | p99 |
|-------|-----|-----|-----|
| get_conversation_by_session | < 5ms | < 10ms | < 20ms |
| add_turn | < 8ms | < 15ms | < 30ms |
| get_conversation_history | < 10ms | < 20ms | < 40ms |
| delete_expired_conversations | < 50ms | < 100ms | < 200ms |

### Load Testing

**Test Scenario**: 100 concurrent users sending 10 messages each

```bash
# Using Locust
cd backend/scripts/load_testing
locust -f locustfile.py --host=http://localhost:8000

# Open: http://localhost:8089
# Set: 100 users, 10 spawn rate
# Run for 5 minutes
```

**Success Criteria**:
- 0% error rate
- p95 response time < 5s
- DB connections < 50

---

## Troubleshooting

### Issue: "Invalid state" on OAuth callback

**Cause**: OAuth state expired (10-minute TTL)

**Fix**:
1. Retry login
2. If persists, check backend logs: `grep "Invalid state" backend/logs/app.log`
3. Verify state storage is working (not cleared on restart)

---

### Issue: 401 on authenticated requests

**Cause**: JWT expired or invalid

**Fix**:
1. Check JWT expiration: Paste token at [jwt.io](https://jwt.io/) → Check `exp` field
2. If expired, logout and login again
3. If not expired, check `JWT_SECRET_KEY` matches between backend and frontend

---

### Issue: Follow-up questions not appearing

**Cause**: Feature flag disabled or query type mismatch

**Fix**:
1. Check `.env`: `ENABLE_FOLLOWUP_QUESTIONS=true`
2. Restart backend
3. Check backend logs: `grep "followup" backend/logs/app.log`
4. Verify API response: `curl ... | jq '.followup_questions'`

---

### Issue: Memory not persisting

**Cause**: DB backend disabled or session mismatch

**Fix**:
1. Check `.env`: `CONVERSATION_MEMORY_BACKEND=db`
2. Restart backend
3. Verify DB table exists:
   ```sql
   SELECT COUNT(*) FROM conversations;
   ```
4. Check backend logs: `grep "conversation_id" backend/logs/app.log`

---

### Issue: Guest sessions not expiring

**Cause**: Cleanup service not running

**Fix**:
1. Check backend startup logs: `grep "Conversation cleanup service started" backend/logs/app.log`
2. Verify config: `GUEST_SESSION_TTL_HOURS=24`
3. Manually trigger cleanup:
   ```python
   from app.supervisor.persistence.cleanup import ConversationCleanupService
   cleanup = ConversationCleanupService()
   await cleanup._cleanup_expired_conversations()
   ```

---

## Test Report Template

### Test Execution Summary

**Date**: YYYY-MM-DD
**Tester**: Name
**Environment**: Dev / Staging / Production
**Build**: Commit hash

| Test ID | Test Name | Status | Notes |
|---------|-----------|--------|-------|
| E2E-01 | OAuth Login (Google) | ✅ PASS | - |
| E2E-02 | OAuth Login (Kakao) | ✅ PASS | - |
| E2E-03 | OAuth Login (Naver) | ❌ FAIL | 401 error, credentials issue |
| E2E-04 | Follow-up Questions | ✅ PASS | 3 questions displayed |
| E2E-05 | Memory Persistence (Logged In) | ✅ PASS | 30 turns tested |
| E2E-06 | Memory Persistence (Guest) | ✅ PASS | - |
| E2E-07 | Guest Session Cleanup | ✅ PASS | Deleted after 24h |
| E2E-08 | Flexible Answer Formatting | ✅ PASS | All 4 formats tested |
| E2E-09 | JWT Authentication | ✅ PASS | - |
| E2E-10 | Logout & Token Cleanup | ✅ PASS | - |

**Overall**: 9/10 PASS (90%)

**Blockers**: Naver OAuth credentials need to be reconfigured

**Next Steps**: Fix Naver OAuth, re-test E2E-03

---

## Contact

For questions or issues with E2E testing:
- Slack: #ddoksori-dev
- Email: dev@ddoksori.ai
- GitHub Issues: [anthropics/ddoksori/issues](https://github.com/anthropics/ddoksori/issues)