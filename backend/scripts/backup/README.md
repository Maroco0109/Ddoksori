# DDOKSORI Database Backup Scripts

PostgreSQL 데이터베이스를 S3에 백업하고 복원하는 스크립트입니다.

## 사전 요구사항

1. **PostgreSQL 클라이언트**
   ```bash
   # Ubuntu/Debian
   sudo apt-get install postgresql-client

   # macOS
   brew install postgresql
   ```

2. **AWS CLI** (설정 완료 상태)
   ```bash
   aws configure
   # 또는 환경변수: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY
   ```

3. **S3 버킷 생성**
   ```bash
   aws s3 mb s3://ddoksori-backups
   ```

## 환경변수

```bash
export DB_HOST="your-rds-endpoint.rds.amazonaws.com"
export DB_USER="postgres"
export DB_NAME="ddoksori"
export DB_PASSWORD="your-password"  # 또는 PGPASSWORD
export S3_BUCKET="ddoksori-backups"  # 선택사항, 기본값 사용 가능
```

## 사용법

### 백업

```bash
# 주간 백업 (기본)
./backup_to_s3.sh

# 월간 백업
./backup_to_s3.sh monthly

# 수동 백업 (중요 배포 전)
./backup_to_s3.sh manual
```

### 복원

```bash
# 사용 가능한 백업 목록 확인
./restore_from_s3.sh --list

# 최신 주간 백업에서 복원
./restore_from_s3.sh

# 특정 백업에서 복원
./restore_from_s3.sh weekly/ddoksori_20250128_040000.sql.gz

# 드라이런 (실제 복원 없이 검증만)
./restore_from_s3.sh --dry-run
```

## S3 버킷 구조

```
s3://ddoksori-backups/
├── weekly/              # 주간 백업 (4주 보존)
│   ├── latest.sql.gz    # 최신 백업 (자동 업데이트)
│   └── ddoksori_YYYYMMDD_HHMMSS.sql.gz
├── monthly/             # 월간 백업 (12개월 보존)
│   └── ddoksori_YYYYMMDD_HHMMSS.sql.gz
└── manual/              # 수동 백업 (자동 삭제 없음)
    └── ddoksori_YYYYMMDD_HHMMSS.sql.gz
```

## 보존 정책

| 백업 유형 | 보존 기간 |
|----------|----------|
| weekly   | 4주 (28일) |
| monthly  | 12개월 (365일) |
| manual   | 무기한 (수동 삭제) |

## 복원 후 검증 체크리스트

복원 완료 후 다음 항목을 확인하세요:

- [ ] documents 테이블 개수 확인
- [ ] chunks 테이블 개수 확인
- [ ] chunks에 embedding이 있는지 확인
- [ ] conversations 테이블 확인
- [ ] oauth_users 테이블 확인
- [ ] API 헬스체크 (`GET /health`)

```sql
-- 검증 쿼리
SELECT 'documents' as table_name, COUNT(*) as count FROM documents
UNION ALL
SELECT 'chunks', COUNT(*) FROM chunks
UNION ALL
SELECT 'chunks_with_embedding', COUNT(*) FROM chunks WHERE embedding IS NOT NULL
UNION ALL
SELECT 'conversations', COUNT(*) FROM conversations
UNION ALL
SELECT 'oauth_users', COUNT(*) FROM oauth_users;
```

## GitHub Actions 자동화

`.github/workflows/db-backup.yml` 워크플로우가 매주 일요일 04:00 UTC에 자동 실행됩니다.

수동 실행: GitHub > Actions > Weekly DB Backup > Run workflow

## 문제 해결

### pg_dump 연결 실패

```bash
# RDS 보안 그룹에서 GitHub Actions IP 허용 필요
# 또는 VPC 내부에서 실행
```

### S3 권한 오류

```bash
# IAM 정책 확인
aws iam get-user-policy --user-name your-user --policy-name S3BackupPolicy
```

### 복원 시 테이블 이미 존재

복원 스크립트는 `ON_ERROR_STOP=0`으로 실행되어 기존 데이터를 덮어씁니다.
완전히 새로운 DB에 복원하려면 먼저 DB를 재생성하세요:

```bash
psql -h $DB_HOST -U $DB_USER -c "DROP DATABASE ddoksori;"
psql -h $DB_HOST -U $DB_USER -c "CREATE DATABASE ddoksori;"
./restore_from_s3.sh
```
