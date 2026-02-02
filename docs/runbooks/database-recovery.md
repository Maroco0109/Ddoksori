# DDOKSORI 데이터베이스 복구 런북

## 개요

이 문서는 RDS 데이터베이스 장애 시 복구 절차를 정의합니다.

**담당자:** DB 관리자
**최종 업데이트:** 2025-01-28

---

## 장애 유형별 대응

### 시나리오 1: 실수로 데이터 삭제 (최근 데이터 복구)

**상황:** 잘못된 DELETE/UPDATE 쿼리 실행, 몇 시간 전 상태로 복구 필요

**복구 방법:** RDS Point-in-Time Recovery (PITR)

```bash
# 1. 복구할 시점 확인 (UTC 기준)
# 예: 2025-01-28 10:00:00 KST → 2025-01-28 01:00:00 UTC

# 2. 새 인스턴스로 복구
aws rds restore-db-instance-to-point-in-time \
  --source-db-instance-identifier dsr-postgres \
  --target-db-instance-identifier dsr-postgres-restored \
  --restore-time "2025-01-28T01:00:00Z"

# 3. 복구 인스턴스 상태 확인 (약 10-30분 소요)
aws rds describe-db-instances \
  --db-instance-identifier dsr-postgres-restored \
  --query 'DBInstances[0].DBInstanceStatus'

# 4. 엔드포인트 확인
aws rds describe-db-instances \
  --db-instance-identifier dsr-postgres-restored \
  --query 'DBInstances[0].Endpoint.Address'

# 5. 애플리케이션 연결 전환
# backend/.env의 DB_HOST를 새 엔드포인트로 변경

# 6. 확인 후 기존 인스턴스 삭제 (선택)
aws rds delete-db-instance \
  --db-instance-identifier dsr-postgres \
  --skip-final-snapshot
```

**예상 복구 시간:** 10-30분

---

### 시나리오 2: RDS 완전 손실 (S3 백업에서 복구)

**상황:** RDS 인스턴스 삭제, 리전 장애 등

**복구 방법:** S3 백업 파일에서 복구

```bash
# 1. 환경변수 설정
export DB_HOST="new-rds-endpoint.rds.amazonaws.com"
export DB_USER="postgres"
export DB_NAME="ddoksori"
export DB_PASSWORD="your-password"

# 2. 사용 가능한 백업 확인
./backend/scripts/backup/restore_from_s3.sh --list

# 3. 드라이런으로 백업 파일 검증
./backend/scripts/backup/restore_from_s3.sh --dry-run

# 4. 복원 실행
./backend/scripts/backup/restore_from_s3.sh weekly/latest.sql.gz
# 또는 특정 백업:
./backend/scripts/backup/restore_from_s3.sh monthly/ddoksori_20250101_040000.sql.gz
```

**예상 복구 시간:** 30분 ~ 수 시간 (DB 크기에 따라)

---

### 시나리오 3: 스냅샷에서 복구

**상황:** 수동 스냅샷이 있는 경우

```bash
# 1. 사용 가능한 스냅샷 확인
aws rds describe-db-snapshots \
  --db-instance-identifier dsr-postgres \
  --query 'DBSnapshots[*].[DBSnapshotIdentifier,SnapshotCreateTime,Status]' \
  --output table

# 2. 스냅샷에서 복구
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier dsr-postgres-from-snapshot \
  --db-snapshot-identifier ddoksori-pre-deploy-20250128

# 3. 상태 확인 후 연결 전환
```

---

## 복구 후 검증 체크리스트

복구 완료 후 반드시 다음 항목을 확인하세요:

### 필수 검증

- [ ] **documents 테이블 개수**
  ```sql
  SELECT COUNT(*) FROM documents;
  -- 예상: 약 20,000개 이상
  ```

- [ ] **chunks 테이블 개수**
  ```sql
  SELECT COUNT(*) FROM chunks;
  -- 예상: 약 70,000개 이상
  ```

- [ ] **임베딩 존재 여부**
  ```sql
  SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL;
  -- 예상: chunks 개수와 동일하거나 비슷해야 함
  ```

- [ ] **conversations 테이블** (런타임 데이터)
  ```sql
  SELECT COUNT(*) FROM conversations;
  ```

- [ ] **oauth_users 테이블** (사용자 데이터)
  ```sql
  SELECT COUNT(*) FROM oauth_users;
  ```

### 통합 검증 쿼리

```sql
SELECT 'documents' as table_name, COUNT(*) as count FROM documents
UNION ALL SELECT 'chunks', COUNT(*) FROM chunks
UNION ALL SELECT 'chunks_with_embedding', COUNT(*) FROM chunks WHERE embedding IS NOT NULL
UNION ALL SELECT 'conversations', COUNT(*) FROM conversations
UNION ALL SELECT 'oauth_users', COUNT(*) FROM oauth_users
UNION ALL SELECT 'conversation_turns', COUNT(*) FROM conversation_turns;
```

### Agent별 데이터 소스 검증 (MAS v2)

v2 아키텍처에서 3개 Retrieval Agent (law, criteria, case)가 각각 다른 데이터를 검색합니다.
복구 후 각 데이터 소스의 무결성을 확인하세요:

```sql
-- 데이터 소스별 document/chunk 수 확인
SELECT d.doc_type, COUNT(DISTINCT d.doc_id) as doc_count, COUNT(c.*) as chunk_count,
       COUNT(c.embedding) as with_embedding
FROM documents d
LEFT JOIN chunks c ON c.doc_id = d.doc_id
GROUP BY d.doc_type
ORDER BY chunk_count DESC;
```

### API 검증

- [ ] **헬스체크**
  ```bash
  curl -s http://localhost:8000/health | jq
  ```

- [ ] **검색 테스트**
  ```bash
  curl -X POST http://localhost:8000/search \
    -H "Content-Type: application/json" \
    -d '{"query": "청약철회 기간", "top_k": 3}'
  ```

- [ ] **챗봇 테스트** (MAS v2: law, criteria, case 3개 Agent 병렬 검색)
  ```bash
  curl -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "환불 받을 수 있나요?", "chat_type": "dispute"}'
  ```

---

## 분기별 복구 테스트 기록

| 날짜 | 테스트 유형 | 결과 | 복구 시간 | 담당자 | 비고 |
|------|------------|------|----------|--------|------|
| 2025-01-28 | S3 복원 | - | - | - | 초기 설정 |
| | | | | | |
| | | | | | |

### 테스트 절차

1. **테스트 환경 준비**
   - 별도의 테스트용 RDS 인스턴스 생성
   - 또는 로컬 PostgreSQL 사용

2. **복원 실행**
   ```bash
   ./backend/scripts/backup/restore_from_s3.sh weekly/latest.sql.gz
   ```

3. **검증 체크리스트 수행**

4. **결과 기록**
   - 복구 시간
   - 발견된 문제
   - 개선 사항

---

## 연락처

| 역할 | 담당자 | 연락처 |
|------|--------|--------|
| DB 관리자 | - | - |
| 백엔드 개발 | - | - |
| AWS 관리 | - | - |

---

## 관련 문서

- [백업 스크립트 README](../../backend/scripts/backup/README.md)
- [MAS v2 아키텍처 설계](../plans/2026-01-28-mas-architecture-v2-design.md)
- [AWS RDS 문서](https://docs.aws.amazon.com/rds/)
- [PostgreSQL pg_dump 문서](https://www.postgresql.org/docs/current/app-pgdump.html)
