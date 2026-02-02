# AWS RDS PostgreSQL + pgvector 구축 가이드

**작성일**: 2026-01-23
**대상**: AWS 초보자
**목적**: AWS RDS에 PostgreSQL + pgvector 환경 구축 (팀 프로젝트용)

---

## 목차

1. [왜 AWS RDS를 사용하는가?](#왜-aws-rds를-사용하는가)
2. [사전 준비](#사전-준비)
3. [방법 A: AWS 콘솔(GUI)로 RDS 생성 (권장)](#방법-a-aws-콘솔gui로-rds-생성-권장)
4. [방법 B: AWS CLI로 RDS 생성](#방법-b-aws-cli로-rds-생성)
5. [pgvector 확장 설치](#pgvector-확장-설치)
6. [스키마 및 데이터 삽입](#스키마-및-데이터-삽입)
7. [팀원과 공유](#팀원과-공유)
8. [비용 관리](#비용-관리)
9. [문제 해결](#문제-해결-troubleshooting)

---

## 왜 AWS RDS를 사용하는가?

### Docker vs AWS RDS 비교

| 항목 | Docker (로컬) | AWS RDS |
|-----|--------------|---------|
| **팀 공유** | ❌ 각자 설치 필요 | ✅ URL만 공유 |
| **데이터 공유** | ❌ 덤프/복원 필요 | ✅ 실시간 공유 |
| **접근성** | ❌ 로컬에서만 | ✅ 어디서나 접속 |
| **백업** | ❌ 수동 관리 | ✅ 자동 백업 |
| **성능** | 로컬 사양 의존 | 안정적 |
| **비용** | 무료 | 월 $15-30 (프리티어 가능) |

**팀 프로젝트라면 RDS 강력 추천!**

---

## 사전 준비

### AWS 계정 준비

1. [AWS 콘솔](https://console.aws.amazon.com/) 로그인
2. IAM 계정 또는 루트 계정 사용
3. 지역(Region)을 **아시아 태평양(서울) ap-northeast-2**로 설정
4. 카드 등록 필요 (프리티어도 카드 필요)

---

## 방법 A: AWS 콘솔(GUI)로 RDS 생성 (권장)

**AWS 초보자에게 추천하는 방법입니다!**

### 1단계: RDS 서비스로 이동

1. AWS 콘솔 로그인: https://console.aws.amazon.com/
2. 좌측 메뉴에서 **"Aurora and RDS"** 클릭
3. 우측 상단 **"데이터베이스 생성"** 버튼 클릭 (주황색)

---

### 2단계: 엔진 옵션 선택

#### 엔진 유형
- ⭐ **PostgreSQL** 선택

#### 엔진 버전
- ⭐ **PostgreSQL 17.2-R3** 선택
- (17.x 최신 버전 선택, pgvector 0.8.1 기본 포함)

#### 템플릿
- ⭐ **프리 티어** 선택 (무료)
- 또는 **개발/테스트** 선택 (비용 최소화)
- "프로덕션"은 선택하지 말 것 (비쌈)

#### 가용성 및 내구성
- ⭐ **단일 AZ DB 인스턴스 배포** 자동 선택됨

---

### 3단계: 설정

#### DB 인스턴스 식별자
```
ddoksori-postgres
```
- RDS 인스턴스 이름 (소문자, 숫자, 하이픈만)

#### 마스터 사용자 이름
```
postgres
```
- 기본값 사용 권장

#### 자격 증명 관리
- ⭐ **자체 관리** 선택
- "AWS Secrets Manager"는 선택하지 말 것

#### 마스터 암호
- 최소 8자 이상
- 영문 대소문자 + 숫자 + 특수문자 조합
- 예시: `Ddoksori2024!`, `PostgreSQL#2024`
- ⚠️ **반드시 메모장에 저장!** (잊어버리면 복구 불가)

---

### 4단계: 인스턴스 구성

#### DB 인스턴스 클래스
- 프리티어 선택 시 **db.t4g.micro** 자동 선택
- 그대로 사용

---

### 5단계: 스토리지

#### 스토리지 유형
- ⭐ **범용 SSD (gp2)** 선택

#### 할당된 스토리지
- ⭐ **20 GiB** (기본값)

#### 스토리지 자동 조정
- 체크 해제 가능 (비용 절감)

---

### 6단계: 연결 (⚠️ 매우 중요!)

#### 컴퓨팅 리소스
- ⭐ **EC2 컴퓨팅 리소스에 연결 안 함** 선택

#### 네트워크 유형
- ⭐ **IPv4** 선택

#### Virtual Private Cloud (VPC)
- **새 VPC 생성** 또는 **Default VPC** 선택
- IAM 계정의 경우 "새 VPC 생성"만 가능 → 그대로 진행

#### DB 서브넷 그룹
- ⭐ **새 DB 서브넷 그룹 생성** (자동 생성)

#### 퍼블릭 액세스 ⚠️ **가장 중요!**
- ❌ "아니요" (기본값)
- ⭐ **"예"로 변경 필수!**
- 이것을 "예"로 해야 팀원들이 외부에서 접속 가능!

#### VPC 보안 그룹
- ⭐ **새로 생성** 선택
- 이름 입력: `ddoksori-postgres-sg`

#### 가용 영역
- "기본 설정 없음" 그대로

#### 데이터베이스 포트
- ⭐ **5432** (PostgreSQL 기본 포트)

---

### 7단계: 데이터베이스 인증

- ⭐ **암호 인증** 선택 (기본값)

---

### 8단계: 추가 구성

**"추가 구성" 섹션을 펼쳐서 설정합니다.**

#### 초기 데이터베이스 이름 ⚠️ 중요!
```
ddoksori
```
- **반드시 입력!** 안 하면 나중에 수동 생성해야 함

#### DB 파라미터 그룹
- ⭐ **default.postgres17** (기본값)

#### 옵션 그룹
- ⭐ **default-postgres-17** (기본값)

#### 백업
- **자동 백업 활성화**: 체크됨
- **백업 보존 기간**: 1일 (비용 절감) 또는 7일
- **백업 기간**: 기본 설정 없음

#### 암호화
- **암호화 활성화**: 체크됨
- **AWS KMS 키**: (default) aws/rds

#### 성능 개선 도우미
- 선택 사항 (추가 비용 발생)
- EC2 연결 계획 있으면 체크, 없으면 해제

#### Enhanced monitoring
- 체크 해제 (비용 절감)

#### 마이너 버전 자동 업그레이드
- 체크됨 (보안 업데이트 자동 적용)

---

### 9단계: 생성!

#### 최종 확인
- 퍼블릭 액세스: **"예"** 확인
- 초기 데이터베이스 이름: **"ddoksori"** 확인

#### 생성 버튼 클릭
- 페이지 맨 아래 **"데이터베이스 생성"** 버튼 클릭 (주황색)

#### 생성 대기
- 상태: "생성 중" → "백업 중" → **"사용 가능"**
- 소요 시간: **5-10분**
- 1-2분마다 페이지 새로고침

---

### 10단계: 엔드포인트 확인

**"사용 가능" 상태가 되면:**

1. 데이터베이스 목록에서 **ddoksori-postgres** 클릭
2. **"연결 & 보안"** 탭 확인
3. **엔드포인트** 주소 복사
   - 예: `ddoksori-postgres.c1a2b3c4d5e6.ap-northeast-2.rds.amazonaws.com`
   - 이 주소를 `.env` 파일의 `DB_HOST`에 사용

---

### 11단계: 보안 그룹 확인 (중요!)

**5432 포트가 열려있는지 확인:**

1. RDS 세부 정보 페이지에서
2. **"연결 & 보안"** 탭 → **"VPC 보안 그룹"** 클릭
3. **"인바운드 규칙"** 탭 확인
4. 규칙이 있는지 확인:
   - 유형: PostgreSQL
   - 프로토콜: TCP
   - 포트 범위: 5432
   - 소스: 0.0.0.0/0 (모든 IP, 프로젝트용)

**만약 규칙이 없다면:**

1. **"인바운드 규칙 편집"** 클릭
2. **"규칙 추가"** 클릭
3. 설정:
   - 유형: **PostgreSQL**
   - 프로토콜: TCP (자동)
   - 포트 범위: 5432 (자동)
   - 소스: **0.0.0.0/0** (Anywhere-IPv4)
4. **"규칙 저장"** 클릭

---

## 방법 B: AWS CLI로 RDS 생성

**CLI에 익숙한 사용자용입니다.**

### CLI 설치 및 설정

#### 1. AWS CLI 설치

**Windows (PowerShell 관리자 권한)**:
```powershell
# MSI 다운로드 및 설치
msiexec.exe /i https://awscli.amazonaws.com/AWSCLIV2.msi
```

**설치 확인**:
```bash
aws --version
# 출력 예: aws-cli/2.x.x Python/3.x.x Windows/10
```

### 3. AWS CLI 설정

```bash
# 1. IAM 사용자 생성 (AWS 콘솔)
# - 서비스 검색: IAM
# - 사용자 > 사용자 생성
# - 이름: ddoksori-admin
# - 권한: AdministratorAccess (또는 RDSFullAccess)
# - 액세스 키 생성 후 다운로드

# 2. CLI 설정
aws configure

# 입력 정보:
# AWS Access Key ID: [발급받은 키]
# AWS Secret Access Key: [발급받은 시크릿 키]
# Default region name: ap-northeast-2  # 서울 리전
# Default output format: json
```

---

## AWS RDS PostgreSQL 생성 (CLI)

### 1. 보안 그룹 생성

**보안 그룹 = 방화벽 규칙**

```bash
# 1-1. VPC ID 확인 (기본 VPC 사용)
aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text

# 출력 예: vpc-0a1b2c3d4e5f6g7h8
# 👆 이 값을 아래 명령어에 사용

# 1-2. 보안 그룹 생성
aws ec2 create-security-group \
  --group-name ddoksori-postgres-sg \
  --description "Security group for ddoksori PostgreSQL RDS" \
  --vpc-id vpc-XXXXXXXX  # 👈 위에서 확인한 VPC ID

# 출력 예:
# {
#     "GroupId": "sg-0a1b2c3d4e5f6g7h8"
# }
# 👆 이 GroupId를 복사해두세요!

# 1-3. 인바운드 규칙 추가 (PostgreSQL 포트 5432 오픈)
aws ec2 authorize-security-group-ingress \
  --group-id sg-XXXXXXXX \  # 👈 위에서 받은 GroupId
  --protocol tcp \
  --port 5432 \
  --cidr 0.0.0.0/0  # 모든 IP 허용 (프로젝트용, 보안 주의!)

# 성공 메시지:
# {
#     "Return": true,
#     "SecurityGroupRules": [...]
# }
```

**보안 주의**: `0.0.0.0/0`은 모든 IP를 허용합니다. 프로덕션에서는 특정 IP만 허용하세요.

### 2. DB 서브넷 그룹 생성

**서브넷 그룹 = RDS가 사용할 네트워크 영역**

```bash
# 2-1. 서브넷 ID 확인 (최소 2개 필요)
aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=vpc-XXXXXXXX" \  # 👈 1-1에서 확인한 VPC ID
  --query "Subnets[*].[SubnetId,AvailabilityZone]" \
  --output table

# 출력 예:
# ---------------------------------
# |       DescribeSubnets         |
# +--------------+----------------+
# |  subnet-aaa  |  ap-northeast-2a |
# |  subnet-bbb  |  ap-northeast-2b |
# |  subnet-ccc  |  ap-northeast-2c |
# +--------------+----------------+
# 👆 최소 2개의 서로 다른 AZ(가용영역) 서브넷 ID를 복사

# 2-2. DB 서브넷 그룹 생성
aws rds create-db-subnet-group \
  --db-subnet-group-name ddoksori-subnet-group \
  --db-subnet-group-description "Subnet group for ddoksori PostgreSQL" \
  --subnet-ids subnet-aaa subnet-bbb  # 👈 위에서 확인한 서브넷 ID (최소 2개)

# 성공 메시지:
# {
#     "DBSubnetGroup": {
#         "DBSubnetGroupName": "ddoksori-subnet-group",
#         ...
#     }
# }
```

### 3. RDS 인스턴스 생성

**메인 이벤트! PostgreSQL 데이터베이스 생성**

```bash
aws rds create-db-instance \
  --db-instance-identifier ddoksori-postgres \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --engine-version 17.2 \
  --master-username postgres \
  --master-user-password YOUR_STRONG_PASSWORD \
  --allocated-storage 20 \
  --storage-type gp3 \
  --vpc-security-group-ids sg-XXXXXXXX \
  --db-subnet-group-name ddoksori-subnet-group \
  --backup-retention-period 7 \
  --publicly-accessible \
  --no-multi-az \
  --db-name ddoksori

# 파라미터 설명:
# --db-instance-identifier: RDS 인스턴스 이름
# --db-instance-class: 인스턴스 타입 (t3.micro = 프리티어)
# --engine: postgres (PostgreSQL)
# --engine-version: 17.2 (최신 버전)
# --master-username: 관리자 계정 (postgres)
# --master-user-password: 비밀번호 (영문+숫자+특수문자 8자 이상)
# --allocated-storage: 디스크 크기 (20GB)
# --storage-type: gp3 (최신 SSD)
# --vpc-security-group-ids: 보안 그룹 ID (1-2에서 생성)
# --db-subnet-group-name: 서브넷 그룹 (2-2에서 생성)
# --publicly-accessible: 외부 접속 허용
# --no-multi-az: 단일 가용영역 (비용 절감)
# --db-name: 초기 데이터베이스 이름

# 출력:
# {
#     "DBInstance": {
#         "DBInstanceIdentifier": "ddoksori-postgres",
#         "DBInstanceStatus": "creating",
#         ...
#     }
# }
```

### 4. 생성 완료 대기 (5-10분 소요)

```bash
# 상태 확인
aws rds describe-db-instances \
  --db-instance-identifier ddoksori-postgres \
  --query "DBInstances[0].DBInstanceStatus" \
  --output text

# 출력:
# creating → backing-up → available (완료!)

# 반복 확인 (30초마다)
watch -n 30 'aws rds describe-db-instances --db-instance-identifier ddoksori-postgres --query "DBInstances[0].DBInstanceStatus" --output text'
```

### 5. 엔드포인트(접속 주소) 확인

```bash
aws rds describe-db-instances \
  --db-instance-identifier ddoksori-postgres \
  --query "DBInstances[0].Endpoint.Address" \
  --output text

# 출력 예:
# ddoksori-postgres.c1a2b3c4d5e6.ap-northeast-2.rds.amazonaws.com
# 👆 이 주소를 .env 파일의 DB_HOST에 입력!
```

---

## pgvector 확장 설치

**중요**: RDS PostgreSQL 17.2는 pgvector를 기본 지원합니다!

### 1. psql로 연결

```bash
# 엔드포인트 주소를 환경변수로 저장 (편의상)
export RDS_HOST="ddoksori-postgres.XXXXX.ap-northeast-2.rds.amazonaws.com"

# psql 연결 (Windows에서는 Git Bash 또는 WSL 사용)
psql -h $RDS_HOST -U postgres -d ddoksori -p 5432

# 비밀번호 입력: YOUR_STRONG_PASSWORD

# 연결 성공 시:
# ddoksori=>
```

### 2. pgvector 확장 설치

```sql
-- pgvector 확장 설치
CREATE EXTENSION IF NOT EXISTS vector;

-- 확인
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';

-- 출력:
--  extname | extversion
-- ---------+------------
--  vector  | 0.8.1
-- (1 row)

-- 연결 종료
\q
```

---

## 스키마 및 데이터 삽입

### 1. .env 파일 설정

**data_n_db/.env** 파일을 생성하고 다음 내용을 입력:

```env
# AWS RDS PostgreSQL 연결 정보
DB_HOST=ddoksori-postgres.XXXXX.ap-northeast-2.rds.amazonaws.com
DB_PORT=5432
DB_NAME=ddoksori
DB_USER=postgres
DB_PASSWORD=YOUR_STRONG_PASSWORD
```

### 2. 스키마 실행

```bash
# DB 폴더로 이동 (프로젝트 루트에서)
cd data_n_db/DB

# Python 스크립트로 스키마 실행
python 02_01_run_schema.py
```

### 3. 데이터 삽입

```bash
# A_law_ED_guide 데이터 삽입 (6,138건, 약 30초)
python 02_02_insert_law_guide.py

# B_case 데이터 삽입 (46,314건, 약 5-6분)
python 02_03_insert_case.py
```

---

## 팀원과 공유

### 1. 연결 정보 공유

**팀원에게 전달할 정보**:
```
DB_HOST=ddoksori-postgres.XXXXX.ap-northeast-2.rds.amazonaws.com
DB_PORT=5432
DB_NAME=ddoksori
DB_USER=postgres
DB_PASSWORD=YOUR_STRONG_PASSWORD
```

**보안 주의**:
- 비밀번호는 Slack DM 또는 암호화된 채널로 공유
- GitHub에 .env 파일 절대 업로드 금지 (.gitignore 확인)

### 2. 팀원 설정 방법

팀원은 다음 파일만 수정하면 됩니다:

```bash
# 1. GitHub에서 프로젝트 클론
git clone <저장소 URL>
cd data_n_db

# 2. .env 파일 생성
cp .env.example .env

# 3. .env 파일 편집 (위의 연결 정보 입력)
notepad .env  # Windows
# 또는
nano .env     # Mac/Linux

# 4. 연결 테스트 (선택사항)
python DB/test_connection.py
```

---

## 비용 관리

### 프리티어 (1년 무료)

- **db.t3.micro**: 월 750시간 무료 (= 31일 24시간)
- **스토리지**: 20GB 무료
- **백업**: 20GB 무료

**조건**: AWS 가입 후 12개월 이내

### 프리티어 이후 예상 비용

**db.t3.micro (1vCPU, 1GB RAM)**:
- 인스턴스: $15/월
- 스토리지 20GB: $2.3/월
- 백업: 무료 (20GB 이내)
- **총 예상 비용**: **$17-20/월**

### 비용 절감 팁

1. **개발 완료 후 중지**:
   ```bash
   # RDS 인스턴스 중지 (최대 7일)
   aws rds stop-db-instance --db-instance-identifier ddoksori-postgres

   # 재시작
   aws rds start-db-instance --db-instance-identifier ddoksori-postgres
   ```

2. **스냅샷 백업 후 삭제**:
   ```bash
   # 스냅샷 생성
   aws rds create-db-snapshot \
     --db-instance-identifier ddoksori-postgres \
     --db-snapshot-identifier ddoksori-backup-2026-01-23

   # RDS 삭제 (최종 스냅샷 생성)
   aws rds delete-db-instance \
     --db-instance-identifier ddoksori-postgres \
     --final-db-snapshot-identifier ddoksori-final-snapshot \
     --no-skip-final-snapshot

   # 나중에 복원
   aws rds restore-db-instance-from-db-snapshot \
     --db-instance-identifier ddoksori-postgres-restored \
     --db-snapshot-identifier ddoksori-final-snapshot
   ```

---

## 문제 해결 (Troubleshooting)

### 1. 연결 실패 (Connection refused)

**원인**: 보안 그룹 설정 문제

**해결**:
```bash
# 보안 그룹 인바운드 규칙 확인
aws ec2 describe-security-groups \
  --group-ids sg-XXXXXXXX \
  --query "SecurityGroups[0].IpPermissions"

# 5432 포트가 0.0.0.0/0으로 열려있는지 확인
```

### 2. 비밀번호 인증 실패

**원인**: 비밀번호 오타 또는 특수문자 문제

**해결**:
```bash
# 비밀번호 재설정
aws rds modify-db-instance \
  --db-instance-identifier ddoksori-postgres \
  --master-user-password NEW_STRONG_PASSWORD \
  --apply-immediately
```

### 3. pgvector 확장 없음

**원인**: PostgreSQL 버전이 17.2 미만

**확인**:
```sql
-- PostgreSQL 버전 확인
SELECT version();

-- 17.2 이상이어야 pgvector 기본 지원
```

**해결**: RDS 인스턴스를 17.2로 재생성

---

## RDS 관리 명령어 모음

```bash
# 상태 확인
aws rds describe-db-instances \
  --db-instance-identifier ddoksori-postgres \
  --query "DBInstances[0].[DBInstanceStatus,Endpoint.Address]" \
  --output table

# 중지 (최대 7일, 비용 절감)
aws rds stop-db-instance --db-instance-identifier ddoksori-postgres

# 시작
aws rds start-db-instance --db-instance-identifier ddoksori-postgres

# 재부팅
aws rds reboot-db-instance --db-instance-identifier ddoksori-postgres

# 로그 확인
aws rds describe-db-log-files --db-instance-identifier ddoksori-postgres

# 삭제 (주의! 복구 불가)
aws rds delete-db-instance \
  --db-instance-identifier ddoksori-postgres \
  --final-db-snapshot-identifier ddoksori-final-snapshot \
  --no-skip-final-snapshot
```

---

## 다음 단계

1. ✅ AWS RDS PostgreSQL 생성 완료
2. ✅ pgvector 확장 설치 완료
3. ✅ 스키마 및 데이터 삽입 완료
4. ✅ 팀원과 연결 정보 공유
5. → **검색 API 구축** (FastAPI)
6. → **RAG 파이프라인 통합**

---

## 참고 자료

- [AWS RDS 공식 문서](https://docs.aws.amazon.com/rds/)
- [AWS CLI 명령어 레퍼런스](https://awscli.amazonaws.com/v2/documentation/api/latest/reference/rds/index.html)
- [pgvector GitHub](https://github.com/pgvector/pgvector)
- [PostgreSQL 17.2 릴리스 노트](https://www.postgresql.org/docs/17/release-17-2.html)
