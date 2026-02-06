# DDOKSORI 백업 시스템 설정 가이드

> DB 운영이 처음인 분도 따라할 수 있도록 단계별로 상세히 설명합니다.

## 목차

1. [사전 준비](#1-사전-준비)
2. [AWS CLI 설치 및 설정](#2-aws-cli-설치-및-설정)
3. [S3 버킷 생성](#3-s3-버킷-생성)
4. [RDS 자동 백업 활성화](#4-rds-자동-백업-활성화)
5. [GitHub Secrets 설정](#5-github-secrets-설정)
6. [첫 백업 테스트](#6-첫-백업-테스트)
7. [백업 확인 및 모니터링](#7-백업-확인-및-모니터링)
8. [문제 해결](#8-문제-해결)

---

## 1. 사전 준비

### 필요한 정보 확인

시작하기 전에 다음 정보를 준비하세요:

| 항목 | 예시 | 내 정보 |
|------|------|---------|
| RDS 엔드포인트 | `dsr-postgres.xxxx.us-east-1.rds.amazonaws.com` | |
| DB 사용자명 | `postgres` | |
| DB 비밀번호 | `****` | |
| DB 이름 | `ddoksori` | |
| AWS Access Key ID | `AKIA...` | |
| AWS Secret Access Key | `****` | |
| AWS 리전 | `us-east-1` | |

### RDS 엔드포인트 확인 방법

1. [AWS 콘솔](https://console.aws.amazon.com/) 로그인
2. 상단 검색창에 `RDS` 입력 → RDS 서비스 클릭
3. 좌측 메뉴에서 `데이터베이스` 클릭
4. `dsr-postgres` (또는 본인의 DB 인스턴스) 클릭
5. **연결 & 보안** 탭에서 **엔드포인트** 복사

![RDS 엔드포인트 위치](https://docs.aws.amazon.com/images/AmazonRDS/latest/UserGuide/images/endpoint.png)

---

## 2. AWS CLI 설치 및 설정

### 2-1. AWS CLI 설치

**Linux (Ubuntu/WSL):**
```bash
# 설치
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# 설치 확인
aws --version
# 출력 예: aws-cli/2.x.x Python/3.x.x Linux/...
```

**macOS:**
```bash
brew install awscli
```

### 2-2. AWS 자격 증명 설정

```bash
aws configure
```

다음 정보를 순서대로 입력:

```
AWS Access Key ID [None]: AKIA여기에_액세스_키_입력
AWS Secret Access Key [None]: 여기에_시크릿_키_입력
Default region name [None]: us-east-1
Default output format [None]: json
```

### 2-3. 설정 확인

```bash
# 현재 사용자 확인
aws sts get-caller-identity

# 정상 출력 예:
# {
#     "UserId": "AIDA...",
#     "Account": "123456789012",
#     "Arn": "arn:aws:iam::123456789012:user/your-username"
# }
```

### AWS Access Key 발급 방법 (없는 경우)

1. AWS 콘솔 → 우측 상단 계정 이름 클릭 → `보안 자격 증명`
2. `액세스 키` 섹션 → `액세스 키 만들기`
3. `Command Line Interface (CLI)` 선택 → 다음
4. **Access Key ID**와 **Secret Access Key** 저장 (Secret은 한 번만 표시됨!)

---

## 3. S3 버킷 생성

### 3-1. AWS 콘솔에서 생성 (권장)

1. AWS 콘솔 → 검색창에 `S3` 입력 → S3 서비스 클릭
2. `버킷 만들기` 버튼 클릭
3. 다음 설정 입력:

| 설정 | 값 |
|------|-----|
| 버킷 이름 | `ddoksori-backups` (고유해야 함, 이미 있으면 `-dev` 등 추가) |
| AWS 리전 | `us-east-1` (RDS와 같은 리전 권장) |
| 객체 소유권 | ACL 비활성화됨 (권장) |
| 퍼블릭 액세스 차단 | **모든 퍼블릭 액세스 차단** ✅ (보안상 필수!) |
| 버킷 버전 관리 | 비활성화 (선택) |

4. `버킷 만들기` 클릭

### 3-2. CLI로 생성

```bash
# 버킷 생성
aws s3 mb s3://ddoksori-backups --region us-east-1

# 확인
aws s3 ls
# 출력: 2025-01-28 12:00:00 ddoksori-backups
```

### 3-3. 폴더 구조 생성

```bash
# 백업용 폴더 생성 (빈 파일로 폴더 표시)
aws s3api put-object --bucket ddoksori-backups --key weekly/
aws s3api put-object --bucket ddoksori-backups --key monthly/
aws s3api put-object --bucket ddoksori-backups --key manual/

# 확인
aws s3 ls s3://ddoksori-backups/
# 출력:
#                            PRE manual/
#                            PRE monthly/
#                            PRE weekly/
```

---

## 4. RDS 자동 백업 활성화

### 4-1. AWS 콘솔에서 설정 (권장)

1. AWS 콘솔 → RDS → 데이터베이스
2. `dsr-postgres` 클릭
3. 우측 상단 `수정` 버튼 클릭
4. 아래로 스크롤하여 **백업** 섹션 찾기
5. 다음 설정 변경:

| 설정 | 값 | 설명 |
|------|-----|------|
| 자동 백업 활성화 | ✅ 체크 | 자동 백업 켜기 |
| 백업 보존 기간 | `35`일 | 최대 35일까지 가능 |
| 백업 기간 | `03:00-04:00 UTC` 선택 | 한국시간 12:00-13:00 |

6. 페이지 맨 아래 `계속` 클릭
7. **수정 사항 적용**: `즉시 적용` 선택
8. `DB 인스턴스 수정` 클릭

### 4-2. CLI로 설정

```bash
aws rds modify-db-instance \
  --db-instance-identifier dsr-postgres \
  --backup-retention-period 35 \
  --preferred-backup-window "03:00-04:00" \
  --apply-immediately

# 상태 확인 (modifying → available 될 때까지 대기)
aws rds describe-db-instances \
  --db-instance-identifier dsr-postgres \
  --query 'DBInstances[0].DBInstanceStatus'
```

### 4-3. 설정 확인

```bash
aws rds describe-db-instances \
  --db-instance-identifier dsr-postgres \
  --query 'DBInstances[0].{BackupRetention:BackupRetentionPeriod,BackupWindow:PreferredBackupWindow}'

# 출력 예:
# {
#     "BackupRetention": 35,
#     "BackupWindow": "03:00-04:00"
# }
```

---

## 5. GitHub Secrets 설정

GitHub Actions가 AWS와 RDS에 접근할 수 있도록 비밀 정보를 설정합니다.

### 5-1. GitHub 저장소로 이동

1. 브라우저에서 GitHub 저장소 열기
2. 상단 탭에서 `Settings` 클릭

### 5-2. Secrets 설정 페이지

1. 좌측 메뉴에서 `Secrets and variables` 클릭
2. `Actions` 클릭
3. `New repository secret` 버튼 클릭

### 5-3. 각 Secret 추가

다음 6개의 Secret을 하나씩 추가하세요:

| Name | Secret (값) | 설명 |
|------|------------|------|
| `AWS_ACCESS_KEY_ID` | `AKIA...` | AWS 액세스 키 |
| `AWS_SECRET_ACCESS_KEY` | `****` | AWS 시크릿 키 |
| `DB_HOST` | `dsr-postgres.xxxx.rds.amazonaws.com` | RDS 엔드포인트 |
| `DB_USER` | `postgres` | DB 사용자명 |
| `DB_PASSWORD` | `****` | DB 비밀번호 |
| `DB_NAME` | `ddoksori` | DB 이름 |

**추가 방법 (반복):**
1. `New repository secret` 클릭
2. `Name` 입력 (예: `AWS_ACCESS_KEY_ID`)
3. `Secret` 입력 (실제 값)
4. `Add secret` 클릭

### 5-4. 설정 확인

모두 추가하면 다음과 같이 보입니다:

```
Repository secrets (6)
├── AWS_ACCESS_KEY_ID        Updated just now
├── AWS_SECRET_ACCESS_KEY    Updated just now
├── DB_HOST                  Updated just now
├── DB_NAME                  Updated just now
├── DB_PASSWORD              Updated just now
└── DB_USER                  Updated just now
```

---

## 6. 첫 백업 테스트

RDS에 데이터가 채워진 후에 진행하세요.

### 6-1. GitHub Actions에서 수동 실행

1. GitHub 저장소 → `Actions` 탭
2. 좌측에서 `Weekly DB Backup` 워크플로우 클릭
3. 우측 `Run workflow` 버튼 클릭
4. `backup_type` 선택: `manual` (첫 테스트용)
5. `Run workflow` 클릭

### 6-2. 실행 결과 확인

1. 방금 시작한 워크플로우 클릭
2. `backup` job 클릭하여 로그 확인
3. 성공 시 녹색 체크 ✅ 표시

### 6-3. S3에서 백업 파일 확인

```bash
aws s3 ls s3://ddoksori-backups/manual/
# 출력 예:
# 2025-01-28 13:00:00    12345678 ddoksori_20250128_130000.sql.gz
# 2025-01-28 13:00:01    12345678 latest.sql.gz
```

또는 AWS 콘솔 → S3 → `ddoksori-backups` 버킷에서 확인

### 6-4. 로컬에서 수동 테스트 (선택)

```bash
# 환경변수 설정
export DB_HOST="dsr-postgres.xxxx.rds.amazonaws.com"
export DB_USER="postgres"
export DB_NAME="ddoksori"
export DB_PASSWORD="your-password"
export S3_BUCKET="ddoksori-backups"

# 백업 실행
cd /home/maroco/LLM
./backend/scripts/backup/backup_to_s3.sh manual
```

---

## 7. 백업 확인 및 모니터링

### 7-1. RDS 자동 스냅샷 확인

```bash
# 자동 생성된 스냅샷 목록
aws rds describe-db-snapshots \
  --db-instance-identifier dsr-postgres \
  --snapshot-type automated \
  --query 'DBSnapshots[*].[DBSnapshotIdentifier,SnapshotCreateTime,Status]' \
  --output table
```

AWS 콘솔에서도 확인 가능:
- RDS → 스냅샷 → 자동 탭

### 7-2. S3 백업 파일 확인

```bash
# 전체 백업 목록
./backend/scripts/backup/restore_from_s3.sh --list
```

### 7-3. GitHub Actions 실행 기록

- GitHub → Actions → Weekly DB Backup
- 매주 일요일 04:00 UTC에 자동 실행됨
- 실패 시 자동으로 Issue 생성됨

### 7-4. 알림 설정 (선택)

GitHub 저장소 → Settings → Notifications에서:
- Actions 실패 알림 이메일 설정 가능

---

## 8. 문제 해결

### 문제: AWS CLI "Unable to locate credentials"

```bash
# 자격 증명 재설정
aws configure

# 또는 환경변수로 직접 설정
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
```

### 문제: S3 버킷 이름 중복

```
An error occurred (BucketAlreadyExists)
```

**해결:** 버킷 이름은 전 세계에서 고유해야 합니다. 다른 이름 사용:
```bash
aws s3 mb s3://ddoksori-backups-yourname-2025
```

### 문제: RDS 연결 실패 (pg_dump)

```
pg_dump: error: connection to server failed
```

**확인 사항:**
1. RDS 보안 그룹에서 현재 IP 허용 여부
2. RDS가 `Publicly accessible` 설정인지 확인
3. 엔드포인트, 사용자명, 비밀번호 정확한지 확인

**RDS 보안 그룹 수정:**
1. RDS → 데이터베이스 → dsr-postgres
2. 연결 & 보안 → VPC 보안 그룹 클릭
3. 인바운드 규칙 편집
4. 규칙 추가:
   - 유형: PostgreSQL
   - 소스: 내 IP (또는 0.0.0.0/0 - 테스트용, 보안 주의!)

### 문제: GitHub Actions 실패

1. Actions 탭에서 실패한 워크플로우 클릭
2. 빨간색 ❌ 단계 클릭하여 로그 확인
3. 일반적인 원인:
   - Secrets 오타
   - RDS 보안 그룹에서 GitHub IP 차단
   - S3 버킷 권한 문제

### 문제: 백업 파일이 너무 큼

대용량 DB의 경우 GitHub Actions 타임아웃 발생 가능

**해결:** Lambda로 마이그레이션 또는 백업 시간 조정

---

## 체크리스트

모든 단계를 완료했는지 확인하세요:

- [ ] AWS CLI 설치 및 설정 완료
- [ ] S3 버킷 생성 (`ddoksori-backups`)
- [ ] RDS 자동 백업 활성화 (35일 보존)
- [ ] GitHub Secrets 6개 모두 설정
- [ ] 첫 수동 백업 테스트 성공
- [ ] S3에서 백업 파일 확인

---

## 다음 단계

1. **정기 모니터링**: 매주 월요일에 백업 성공 여부 확인
2. **분기별 복구 테스트**: `docs/runbooks/database-recovery.md` 참고
3. **프로덕션 전환 시**: Multi-AZ 활성화 고려

---

## 도움이 필요하면

- [AWS RDS 공식 문서](https://docs.aws.amazon.com/rds/)
- [GitHub Actions 문서](https://docs.github.com/en/actions)
- [PostgreSQL pg_dump 문서](https://www.postgresql.org/docs/current/app-pgdump.html)
