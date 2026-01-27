# 대화형 챗봇 운영 가이드

**작업 ID**: `feature/34-e2e`
**최종 업데이트**: 2026-01-28

---

## 📋 개요

이 문서는 대화형 챗봇 및 소셜 로그인 기능의 운영, 모니터링, 장애 대응 방법을 설명합니다.

---

## 🎛️ Feature Flag 관리

### 현재 설정 확인

```bash
# .env 파일 확인
grep -E "ANSWER_FORMAT_MODE|CONVERSATION_MEMORY_BACKEND|ENABLE_FOLLOWUP_QUESTIONS" backend/.env
```

### 점진적 롤아웃 전략

#### Phase 1: 후속 질문만 활성화 (저위험)

```bash
# backend/.env
ANSWER_FORMAT_MODE=fixed
CONVERSATION_MEMORY_BACKEND=memory
ENABLE_FOLLOWUP_QUESTIONS=true
```

**모니터링 (30분)**:
- 후속 질문 클릭률 확인
- API 에러율 < 1%
- 응답 시간 증가 < 10%

#### Phase 2: 유연한 형식 활성화

```bash
ANSWER_FORMAT_MODE=flexible
CONVERSATION_MEMORY_BACKEND=memory
ENABLE_FOLLOWUP_QUESTIONS=true
```

**모니터링 (1시간)**:
- 답변 품질 샘플링 (50개)
- 사용자 피드백 확인
- 섹션 구조 정상 렌더링 확인

#### Phase 3: DB 메모리 활성화 (최종)

```bash
ANSWER_FORMAT_MODE=flexible
CONVERSATION_MEMORY_BACKEND=db
ENABLE_FOLLOWUP_QUESTIONS=true
```

**모니터링 (2시간)**:
- DB 쿼리 지연시간 (p95 < 50ms)
- DB 커넥션 수 < 50
- 메모리 사용량 증가 확인
- Cleanup 서비스 정상 작동 확인

### 긴급 롤백

문제 발생 시 즉시 이전 설정으로 복구:

```bash
# 전체 비활성화 (기존 시스템으로 복귀)
ANSWER_FORMAT_MODE=fixed
CONVERSATION_MEMORY_BACKEND=memory
ENABLE_FOLLOWUP_QUESTIONS=false

# 백엔드 재시작 (재배포 불필요)
sudo systemctl restart ddoksori-backend
```

---

## 📊 모니터링

### 1. 핵심 메트릭

#### API 성능

**목표**:
- `/chat` p50: < 1초
- `/chat` p95: < 3초
- `/chat` p99: < 5초

**확인 방법** (Prometheus/Grafana):
```promql
# API 응답 시간 (p95)
histogram_quantile(0.95,
  rate(http_request_duration_seconds_bucket{endpoint="/chat"}[5m])
)

# 에러율
rate(http_requests_total{status=~"5.."}[5m]) /
rate(http_requests_total[5m])
```

**로그 확인**:
```bash
# 느린 요청 (> 5초)
grep "duration.*[5-9]\.[0-9]s\|duration.*[0-9][0-9]\." backend/logs/app.log | tail -20
```

#### DB 쿼리 성능

**목표**:
- `get_conversation_by_session`: p95 < 10ms
- `add_turn`: p95 < 15ms
- `get_conversation_history`: p95 < 20ms
- `delete_expired_conversations`: p95 < 100ms

**확인 방법**:
```sql
-- PostgreSQL slow query log
SELECT query, calls, total_time, mean_time, max_time
FROM pg_stat_statements
WHERE query LIKE '%conversations%'
  AND mean_time > 10
ORDER BY mean_time DESC
LIMIT 10;

-- 현재 실행 중인 쿼리
SELECT pid, now() - query_start as duration, query
FROM pg_stat_activity
WHERE state = 'active'
  AND query NOT LIKE '%pg_stat_activity%'
ORDER BY duration DESC;
```

**DB 커넥션**:
```sql
-- 현재 커넥션 수
SELECT count(*) FROM pg_stat_activity;

-- 최대 커넥션 설정 확인
SHOW max_connections;

-- 커넥션 상태별 카운트
SELECT state, COUNT(*)
FROM pg_stat_activity
GROUP BY state;
```

#### LLM 토큰 사용량

**목표**: 30턴 메모리로 인해 20-30% 증가 예상

**확인 방법**:
```bash
# OpenAI API 사용량 확인
# https://platform.openai.com/usage

# 백엔드 로그에서 토큰 사용량 확인
grep "tokens" backend/logs/app.log | tail -100
```

**비용 계산**:
```python
# gpt-4o-mini 기준 (2024년 가격)
input_cost = (prompt_tokens / 1000) * 0.00015  # $0.15 per 1M tokens
output_cost = (completion_tokens / 1000) * 0.0006  # $0.60 per 1M tokens
total_cost = input_cost + output_cost
```

### 2. 대화 통계

```sql
-- 일일 대화 수
SELECT DATE(created_at), COUNT(*) as count
FROM conversations
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at)
ORDER BY DATE(created_at) DESC;

-- 평균 대화 턴 수
SELECT AVG(turn_count) as avg_turns,
       MAX(turn_count) as max_turns,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY turn_count) as median_turns
FROM conversations;

-- 30턴 이상 장기 대화 (압축 발생)
SELECT COUNT(*) as long_conversations
FROM conversations
WHERE turn_count >= 30;

-- 게스트 vs 인증 사용자 비율
SELECT
  CASE
    WHEN user_id IS NULL THEN 'guest'
    ELSE 'authenticated'
  END as user_type,
  COUNT(*) as count,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) as percentage
FROM conversations
GROUP BY user_type;
```

### 3. 후속 질문 성과

**목표**: 클릭률 > 10%

```sql
-- 후속 질문이 제공된 대화 수 (API 로그 분석 필요)
-- 이 정보는 현재 DB에 저장되지 않으므로, API 로그 또는 프론트엔드 analytics 필요

-- 대안: conversation_turns의 metadata 분석
SELECT
  COUNT(*) FILTER (WHERE metadata->>'has_followup' = 'true') as with_followup,
  COUNT(*) as total,
  ROUND(100.0 * COUNT(*) FILTER (WHERE metadata->>'has_followup' = 'true') / COUNT(*), 2) as percentage
FROM conversation_turns
WHERE role = 'assistant'
  AND created_at >= NOW() - INTERVAL '24 hours';
```

### 4. OAuth 로그인 성과

```sql
-- OAuth 제공자별 사용자 수
SELECT provider, COUNT(*) as user_count
FROM users
GROUP BY provider
ORDER BY user_count DESC;

-- 일일 신규 가입자
SELECT DATE(created_at), provider, COUNT(*) as new_users
FROM users
WHERE created_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE(created_at), provider
ORDER BY DATE(created_at) DESC, provider;

-- 최근 로그인 활동
SELECT DATE(last_login_at), COUNT(*) as active_users
FROM users
WHERE last_login_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE(last_login_at)
ORDER BY DATE(last_login_at) DESC;

-- 비활성 사용자 (30일 이상 미로그인)
SELECT COUNT(*) as inactive_users
FROM users
WHERE last_login_at < NOW() - INTERVAL '30 days'
   OR last_login_at IS NULL;
```

---

## 🧹 데이터 관리

### 게스트 세션 Cleanup

#### Cleanup 서비스 상태 확인

```bash
# 서비스 시작 로그
grep "Conversation cleanup service started" backend/logs/app.log

# 최근 cleanup 실행 로그
grep "Deleted.*expired guest conversations" backend/logs/app.log | tail -10

# 예상 출력:
# [2026-01-28 10:00:00] INFO: Deleted 5 expired guest conversations
# [2026-01-28 11:00:00] INFO: Deleted 3 expired guest conversations
```

#### 수동 Cleanup 실행

긴급 상황에서 수동으로 실행:

```python
# Python shell에서 실행
from app.supervisor.persistence.cleanup import ConversationCleanupService
import asyncio

cleanup = ConversationCleanupService()
deleted = asyncio.run(cleanup._cleanup_expired_conversations())
print(f"Deleted {deleted} conversations")
```

또는 SQL로 직접 삭제:
```sql
-- 만료된 게스트 세션 확인
SELECT conversation_id, session_id, expires_at,
       EXTRACT(EPOCH FROM (NOW() - expires_at)) / 3600 as hours_expired
FROM conversations
WHERE expires_at IS NOT NULL
  AND expires_at < NOW();

-- 수동 삭제 (주의: CASCADE로 turns, summaries도 함께 삭제됨)
DELETE FROM conversations
WHERE expires_at IS NOT NULL
  AND expires_at < NOW();
```

#### TTL 조정

게스트 세션 보관 기간 변경:

```bash
# backend/.env
GUEST_SESSION_TTL_HOURS=48  # 24시간 → 48시간으로 연장

# 백엔드 재시작
sudo systemctl restart ddoksori-backend
```

### 대화 이력 아카이브

디스크 공간 확보를 위해 오래된 대화 아카이브:

```sql
-- 90일 이상 오래된 대화 (사용자 동의 필요)
-- 1. 먼저 백업
\copy (SELECT * FROM conversations WHERE created_at < NOW() - INTERVAL '90 days') TO '/backup/conversations_archive_2026-01.csv' CSV HEADER;
\copy (SELECT * FROM conversation_turns WHERE conversation_id IN (SELECT conversation_id FROM conversations WHERE created_at < NOW() - INTERVAL '90 days')) TO '/backup/turns_archive_2026-01.csv' CSV HEADER;

-- 2. 확인 후 삭제
DELETE FROM conversations
WHERE created_at < NOW() - INTERVAL '90 days'
  AND user_id IS NULL;  -- 게스트만 삭제 (인증 사용자는 보존)
```

### DB 용량 모니터링

```sql
-- 테이블별 디스크 사용량
SELECT
  schemaname,
  tablename,
  pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN ('conversations', 'conversation_turns', 'conversation_summaries')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

-- 예상 출력:
--  schemaname |       tablename        |  size
-- ------------+------------------------+---------
--  public     | conversation_turns     | 512 MB
--  public     | conversations          | 128 MB
--  public     | conversation_summaries | 64 MB
```

**알림 임계값**: 각 테이블이 1GB 초과 시 아카이브 고려

---

## 🚨 장애 대응

### 시나리오 1: DB 연결 실패

**증상**:
```
psycopg2.OperationalError: could not connect to server
```

**원인**: DB 서버 다운 or 커넥션 제한 초과

**즉시 조치**:
1. Feature flag로 인메모리 모드 전환:
   ```bash
   CONVERSATION_MEMORY_BACKEND=memory
   sudo systemctl restart ddoksori-backend
   ```
2. DB 서버 상태 확인:
   ```bash
   docker compose ps postgres
   # 또는
   systemctl status postgresql
   ```
3. DB 재시작:
   ```bash
   docker compose restart postgres
   ```

**근본 원인 분석**:
```sql
-- 커넥션 수 확인
SELECT count(*) FROM pg_stat_activity;

-- 장시간 실행 쿼리 확인
SELECT pid, now() - query_start as duration, query
FROM pg_stat_activity
WHERE state = 'active'
  AND now() - query_start > interval '1 minute'
ORDER BY duration DESC;
```

### 시나리오 2: Cleanup 서비스 미작동

**증상**: 게스트 세션이 24시간 후에도 삭제되지 않음

**확인**:
```bash
# 서비스 시작 로그 확인
grep "Conversation cleanup service started" backend/logs/app.log

# 최근 cleanup 실행 확인
grep "Deleted.*expired" backend/logs/app.log | tail -5
```

**원인**:
1. DB 백엔드 비활성화 상태
2. Cleanup 서비스 크래시
3. 에러로 인한 중단

**조치**:
```bash
# 1. Feature flag 확인
grep CONVERSATION_MEMORY_BACKEND backend/.env

# 2. 백엔드 재시작
sudo systemctl restart ddoksori-backend

# 3. 수동 cleanup 실행 (위 "수동 Cleanup 실행" 참고)
```

### 시나리오 3: OAuth 로그인 실패

**증상**: "Invalid state" or "Invalid client" 에러

**확인**:
```bash
# OAuth 에러 로그
grep -i "oauth.*error\|Invalid state\|Invalid client" backend/logs/app.log | tail -20
```

**원인별 조치**:

| 에러 | 원인 | 조치 |
|------|------|------|
| Invalid state | State 만료 (10분) | 사용자에게 재시도 안내 |
| Invalid client | Client ID/Secret 오류 | `.env` 재확인 |
| Redirect URI mismatch | OAuth 앱 설정 오류 | OAuth 앱에서 URI 확인 |
| Access denied | 테스트 사용자 미등록 (Google) | OAuth 앱에 테스트 사용자 추가 |

**긴급 조치** (OAuth 완전 비활성화):
```bash
# 프론트엔드에서 로그인 버튼 숨기기 (임시)
# 또는 백엔드에서 OAuth 엔드포인트 비활성화
```

### 시나리오 4: 후속 질문 미표시

**증상**: 후속 질문이 표시되지 않음

**확인**:
```bash
# Feature flag 확인
grep ENABLE_FOLLOWUP_QUESTIONS backend/.env

# API 응답 확인
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "환불 문의", "session_id": "test", "chat_type": "dispute"}' \
  | jq '.followup_questions'
```

**조치**:
1. Feature flag가 `false`면 `true`로 변경
2. API 응답에서 `followup_questions`가 비어있으면 백엔드 로그 확인
3. 템플릿 매칭 로직 확인

### 시나리오 5: 메모리 사용량 급증

**증상**: 서버 메모리 > 80%

**확인**:
```bash
# 메모리 사용량
free -h
# 또는
top -o %MEM

# 백엔드 프로세스 메모리
ps aux | grep uvicorn
```

**원인**:
- 대화 이력이 메모리에 누적 (DB 백엔드 미사용 시)
- 슬라이딩 윈도우 미작동

**조치**:
1. DB 백엔드 활성화:
   ```bash
   CONVERSATION_MEMORY_BACKEND=db
   sudo systemctl restart ddoksori-backend
   ```
2. 슬라이딩 윈도우 크기 축소:
   ```bash
   SLIDING_WINDOW_SIZE=5  # 10 → 5
   ```
3. 백엔드 재시작으로 메모리 해제

---

## 🔧 유지보수

### 주간 점검 (매주 월요일)

```bash
# 1. DB 용량 확인
psql -U postgres -d ddoksori -c "
SELECT tablename, pg_size_pretty(pg_total_relation_size('public.'||tablename))
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename LIKE 'conversation%'
ORDER BY pg_total_relation_size('public.'||tablename) DESC;
"

# 2. Cleanup 서비스 로그 확인
grep "Deleted.*expired" backend/logs/app.log | tail -20

# 3. 에러 로그 확인
grep -i "error\|exception" backend/logs/app.log | grep -v "404\|401" | tail -50

# 4. 느린 쿼리 확인
psql -U postgres -d ddoksori -c "
SELECT query, calls, mean_time, max_time
FROM pg_stat_statements
WHERE mean_time > 50
ORDER BY mean_time DESC
LIMIT 10;
"
```

### 월간 점검 (매월 1일)

```bash
# 1. 월간 통계 리포트
psql -U postgres -d ddoksori -f scripts/monthly_report.sql > reports/2026-01.txt

# 2. DB 백업
pg_dump -U postgres ddoksori > backups/ddoksori_2026-01-01.sql

# 3. 90일 이상 오래된 게스트 대화 아카이브 (위 "대화 이력 아카이브" 참고)

# 4. OAuth credentials 로테이션 검토

# 5. JWT_SECRET_KEY 로테이션 검토 (선택사항)
```

### 인덱스 유지보수

```sql
-- 인덱스 bloat 확인
SELECT
  schemaname,
  tablename,
  indexname,
  pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes
WHERE schemaname = 'public'
  AND tablename LIKE 'conversation%'
ORDER BY pg_relation_size(indexrelid) DESC;

-- 인덱스 재구축 (bloat 발생 시)
REINDEX TABLE conversations;
REINDEX TABLE conversation_turns;
```

---

## 📈 성능 튜닝

### DB 커넥션 풀 조정

현재는 per-method connection 사용:
```python
# app/supervisor/persistence/db.py
def _get_connection(self):
    return psycopg2.connect(...)  # 매번 새 연결
```

**대안**: 커넥션 풀 사용 (성능 개선)
```python
from psycopg2 import pool

# 초기화 시
self.connection_pool = pool.ThreadedConnectionPool(
    minconn=1,
    maxconn=20,
    dsn=connection_string
)

# 사용 시
conn = self.connection_pool.getconn()
try:
    # ... 쿼리 실행
finally:
    self.connection_pool.putconn(conn)
```

### 슬라이딩 윈도우 크기 조정

토큰 비용 vs 컨텍스트 품질 균형:

```bash
# 토큰 비용 절감 (컨텍스트 감소)
SLIDING_WINDOW_SIZE=5

# 컨텍스트 품질 향상 (비용 증가)
SLIDING_WINDOW_SIZE=15
```

**권장**: 10 (현재 설정)

### 캐싱 전략

기존 answer cache 활용:
```bash
# backend/.env
ENABLE_ANSWER_CACHE=true
REDIS_HOST=localhost
REDIS_PORT=6379
```

**효과**: 동일 쿼리 반복 시 LLM 호출 생략 (응답 시간 90% 단축)

---

## 📝 로그 관리

### 로그 로테이션

```bash
# logrotate 설정 생성
sudo nano /etc/logrotate.d/ddoksori

# 내용:
/home/maroco/LLM/backend/logs/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    missingok
    create 0644 maroco maroco
    postrotate
        systemctl reload ddoksori-backend > /dev/null 2>&1 || true
    endscript
}
```

### 로그 레벨 조정

개발/디버깅 시:
```python
# app/common/logging/config.py
LOG_LEVEL = "DEBUG"  # 기본: INFO
```

프로덕션:
```python
LOG_LEVEL = "INFO"  # 또는 WARNING
```

---

## 🔐 보안 점검

### 주기적 보안 점검 (분기별)

```bash
# 1. JWT Secret 로테이션 (선택사항, 모든 사용자 로그아웃됨)
# 새로운 32자 이상 랜덤 문자열 생성
openssl rand -base64 32

# 2. OAuth Client Secret 로테이션
# 각 OAuth 제공자 콘솔에서 새 Secret 발급

# 3. DB 비밀번호 변경
# .env 업데이트 후 DB 재시작

# 4. 취약점 스캔
pip-audit  # Python 패키지 취약점 확인
npm audit  # Node 패키지 취약점 확인
```

### 접근 로그 분석

```bash
# 의심스러운 로그인 시도
grep "401\|403" backend/logs/app.log | grep "/auth/" | tail -50

# 비정상적인 API 호출 패턴
awk '{print $1}' backend/logs/access.log | sort | uniq -c | sort -rn | head -20
```

---

## 📞 에스컬레이션

### Level 1: 즉시 대응 (운영팀)

- DB 연결 실패 → 인메모리 모드 전환
- OAuth 로그인 실패 → 사용자 재시도 안내
- Cleanup 서비스 실패 → 수동 cleanup 실행

### Level 2: 긴급 대응 (개발팀)

- API 응답 시간 > 10초
- 에러율 > 5%
- DB 디스크 사용량 > 90%

### Level 3: 중대 사고 (전체 팀)

- 서비스 완전 다운
- 데이터 유실
- 보안 침해

**연락처**:
- Slack: #ddoksori-ops
- PagerDuty: (설정 필요)
- Email: ops@ddoksori.ai

---

## 📚 참고 문서

- **Quick Start**: `/docs/guides/conversational-chatbot-quickstart.md`
- **OAuth 설정**: `/docs/guides/oauth-setup-guide.md`
- **E2E 테스트**: `/docs/testing/e2e-test-guide.md`
- **전체 아키텍처**: `/docs/feature/conversational-chatbot-transformation.md`

---

**마지막 업데이트**: 2026-01-28
**작성자**: Claude Code
**버전**: 1.0