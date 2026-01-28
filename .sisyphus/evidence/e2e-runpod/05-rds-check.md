# RDS 연결 점검 절차

## 1. 개요

AWS RDS PostgreSQL 데이터베이스에 대한 연결 검증 절차입니다.

로컬 Docker 기반 PostgreSQL 대신 AWS RDS를 사용하는 환경에서:
- RDS 엔드포인트 연결성 확인
- 데이터베이스 인증 검증
- 기본 쿼리 실행 가능 여부 확인
- 네트워크/보안 설정 진단

---

## 2. RDS 모드 Docker Compose 실행

### 2.1 전제조건

RDS 연결 전에 다음을 확인하세요:

#### 네트워크 요구사항
- [ ] RDS 인스턴스가 생성되어 있음
- [ ] RDS 보안 그룹이 포트 5432(PostgreSQL)를 허용하도록 설정됨
- [ ] 클라이언트 IP가 RDS 보안 그룹의 인바운드 규칙에 포함됨
- [ ] VPC 라우팅이 올바르게 설정됨 (퍼블릭 액세스 가능 또는 VPC 내부 접근)

#### 환경 변수 설정

`backend/.env` 파일에 다음 변수를 설정하세요:

```bash
# RDS 연결 정보
DB_HOST=your-instance.xxxx.ap-northeast-2.rds.amazonaws.com
DB_PORT=5432
DB_NAME=ddoksori
DB_USER=admin
DB_PASSWORD=your-secure-password

# 임베딩 서버 (로컬 또는 원격)
EMBED_API_URL=http://embedding:8001/embed
EMBEDDING_MODEL_NAME=nlpai-lab/KURE-v1

# OpenAI 임베딩 사용 시 (선택)
USE_OPENAI_EMBEDDING=false
OPENAI_API_KEY=sk-...
```

### 2.2 서비스 시작

RDS 모드에서는 로컬 `db` 서비스를 시작하지 않습니다.

```bash
# 1단계: 임베딩 서버 시작
docker compose -f docker-compose.yml -f docker-compose.rds.yml up --build -d embedding

# 2단계: 백엔드 서비스 시작 (로컬 db 의존성 제외)
docker compose -f docker-compose.yml -f docker-compose.rds.yml up --build -d --no-deps backend
```

**주의사항**:
- `--no-deps` 플래그는 로컬 `db` 서비스 시작을 방지합니다
- 임베딩 서버가 먼저 시작되어야 백엔드가 정상 작동합니다
- 백엔드 로그에서 "DB connected" 메시지를 확인하세요

---

## 3. DB 연결 검증

### 3.1 방법 1: Python/psycopg2 (권장)

**실행 위치**: Backend 컨테이너 내부 또는 로컬 conda `dsr` 환경

#### 3.1.1 Backend 컨테이너에서 실행

```bash
docker compose exec backend python - <<'PY'
import os
import psycopg2

# 환경 변수에서 RDS 연결 정보 읽기
conn = psycopg2.connect(
    host=os.environ['DB_HOST'],
    port=int(os.environ.get('DB_PORT', '5432')),
    dbname=os.environ['DB_NAME'],
    user=os.environ['DB_USER'],
    password=os.environ['DB_PASSWORD'],
)

# 간단한 쿼리 실행
cur = conn.cursor()
cur.execute('SELECT 1;')
result = cur.fetchone()[0]
print(f"✓ RDS 연결 성공: {result}")

# 추가 검증: 테이블 존재 여부 확인
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public' 
    LIMIT 5;
""")
tables = cur.fetchall()
print(f"✓ 테이블 확인: {len(tables)}개 테이블 존재")

cur.close()
conn.close()
PY
```

**예상 출력**:
```
✓ RDS 연결 성공: 1
✓ 테이블 확인: 5개 테이블 존재
```

#### 3.1.2 로컬 conda 환경에서 실행

```bash
# 1. conda dsr 환경 활성화
conda activate dsr

# 2. 환경 변수 설정 (backend/.env 파일 로드)
export $(cat backend/.env | xargs)

# 3. Python 스크립트 실행
python - <<'PY'
import os
import psycopg2

conn = psycopg2.connect(
    host=os.environ['DB_HOST'],
    port=int(os.environ.get('DB_PORT', '5432')),
    dbname=os.environ['DB_NAME'],
    user=os.environ['DB_USER'],
    password=os.environ['DB_PASSWORD'],
)

cur = conn.cursor()
cur.execute('SELECT 1;')
result = cur.fetchone()[0]
print(f"✓ RDS 연결 성공: {result}")

cur.close()
conn.close()
PY
```

### 3.2 방법 2: 애플리케이션 로그 (간접 확인)

백엔드 서비스가 정상 시작되었는지 확인합니다:

```bash
# 백엔드 로그 확인
docker compose logs backend | grep -E "(DB|database|connected|error)"
```

**성공 지표**:
- `"Database connected successfully"` 또는 유사 메시지
- `"Orchestrator initialized"` 메시지
- 에러 메시지 없음

**실패 지표**:
- `"Connection refused"` 또는 `"Connection timeout"`
- `"Authentication failed"` 또는 `"Invalid password"`
- `"SSL error"` 또는 `"certificate verify failed"`

### 3.3 방법 3: Health Check 엔드포인트

```bash
# 백엔드 health 엔드포인트 확인
curl -s http://localhost:8000/health | jq .

# 또는 간단히
curl http://localhost:8000/health
```

**성공 응답**:
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2026-01-27T10:30:00Z"
}
```

---

## 4. 성공 기준

다음 조건을 모두 만족하면 RDS 연결이 성공한 것입니다:

- [ ] **연결 성공**: `SELECT 1` 쿼리가 `1`을 반환
- [ ] **인증 성공**: 사용자 자격증명으로 로그인 가능
- [ ] **쿼리 실행**: 기본 쿼리 실행 가능 (테이블 조회 등)
- [ ] **애플리케이션 시작**: 백엔드 서비스가 정상 시작됨
- [ ] **Health Check**: `/health` 엔드포인트가 `healthy` 상태 반환

---

## 5. 실패 시 진단 절차

### 5.1 연결 오류 분류

#### 오류 1: "Connection refused" 또는 "Connection timeout"

**원인**: 네트워크 연결 불가

**진단 체크리스트**:
```bash
# 1. RDS 엔드포인트 DNS 확인
nslookup your-instance.xxxx.ap-northeast-2.rds.amazonaws.com

# 2. 포트 접근성 확인 (nc 또는 telnet)
nc -zv your-instance.xxxx.ap-northeast-2.rds.amazonaws.com 5432
# 또는
telnet your-instance.xxxx.ap-northeast-2.rds.amazonaws.com 5432

# 3. 라우팅 확인
traceroute your-instance.xxxx.ap-northeast-2.rds.amazonaws.com
```

**해결 방법**:
- [ ] RDS 보안 그룹 인바운드 규칙 확인 (포트 5432 허용)
- [ ] 클라이언트 IP가 보안 그룹에 포함되어 있는지 확인
- [ ] VPC 라우팅 테이블 확인
- [ ] RDS 인스턴스가 "available" 상태인지 확인

#### 오류 2: "Authentication failed" 또는 "Invalid password"

**원인**: 자격증명 오류

**진단 체크리스트**:
```bash
# 1. 환경 변수 확인
echo "DB_HOST: $DB_HOST"
echo "DB_USER: $DB_USER"
echo "DB_NAME: $DB_NAME"
# (DB_PASSWORD는 출력하지 않음)

# 2. RDS 마스터 사용자 확인
# AWS 콘솔에서 RDS 인스턴스 > Configuration 탭 확인

# 3. 비밀번호 특수문자 확인
# 비밀번호에 특수문자가 있으면 URL 인코딩 필요
```

**해결 방법**:
- [ ] `DB_USER` 및 `DB_PASSWORD` 재확인
- [ ] RDS 마스터 사용자명과 일치하는지 확인
- [ ] 비밀번호에 특수문자가 있으면 URL 인코딩 적용
- [ ] RDS 콘솔에서 "Modify" → "Master password" 재설정

#### 오류 3: "SSL error" 또는 "certificate verify failed"

**원인**: SSL/TLS 인증서 검증 실패

**진단 체크리스트**:
```bash
# 1. RDS SSL 지원 확인
# AWS 콘솔에서 RDS 인스턴스 > Configuration 탭 확인

# 2. SSL 인증서 다운로드
# https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html

# 3. psycopg2 SSL 모드 확인
python - <<'PY'
import psycopg2
conn = psycopg2.connect(
    host="your-instance.xxxx.ap-northeast-2.rds.amazonaws.com",
    port=5432,
    dbname="ddoksori",
    user="admin",
    password="your-password",
    sslmode="require",  # 또는 "prefer", "disable"
)
PY
```

**해결 방법**:
- [ ] RDS SSL 지원 확인 (대부분의 RDS는 기본 지원)
- [ ] `sslmode=prefer` 또는 `sslmode=disable`로 시도
- [ ] 필요시 RDS CA 인증서 다운로드 및 설정

#### 오류 4: "Database does not exist"

**원인**: 데이터베이스 이름 오류 또는 미생성

**진단 체크리스트**:
```bash
# 1. 환경 변수 확인
echo "DB_NAME: $DB_NAME"

# 2. RDS에 존재하는 데이터베이스 목록 확인
python - <<'PY'
import psycopg2
conn = psycopg2.connect(
    host="your-instance.xxxx.ap-northeast-2.rds.amazonaws.com",
    port=5432,
    dbname="postgres",  # 기본 데이터베이스
    user="admin",
    password="your-password",
)
cur = conn.cursor()
cur.execute("SELECT datname FROM pg_database WHERE datistemplate = false;")
databases = cur.fetchall()
print("Available databases:", [db[0] for db in databases])
cur.close()
conn.close()
PY
```

**해결 방법**:
- [ ] `DB_NAME` 환경 변수 재확인
- [ ] RDS에서 데이터베이스 생성 (필요시)
- [ ] 데이터베이스 초기화 스크립트 실행

#### 오류 5: "Permission denied" 또는 "Insufficient privileges"

**원인**: 사용자 권한 부족

**진단 체크리스트**:
```bash
# 1. 사용자 권한 확인
python - <<'PY'
import psycopg2
conn = psycopg2.connect(
    host="your-instance.xxxx.ap-northeast-2.rds.amazonaws.com",
    port=5432,
    dbname="ddoksori",
    user="admin",
    password="your-password",
)
cur = conn.cursor()
cur.execute("SELECT current_user;")
print("Current user:", cur.fetchone()[0])

# 테이블 생성 권한 확인
cur.execute("CREATE TABLE test_permission (id INT);")
cur.execute("DROP TABLE test_permission;")
print("✓ 테이블 생성/삭제 권한 있음")
cur.close()
conn.close()
PY
```

**해결 방법**:
- [ ] RDS 마스터 사용자 사용 (모든 권한 보유)
- [ ] 또는 필요한 권한을 가진 사용자 생성
- [ ] 데이터베이스 소유권 확인

### 5.2 종합 진단 스크립트

모든 항목을 한 번에 확인하는 스크립트:

```bash
#!/bin/bash

# RDS 연결 종합 진단 스크립트

RDS_HOST="${DB_HOST}"
RDS_PORT="${DB_PORT:-5432}"
RDS_USER="${DB_USER}"
RDS_NAME="${DB_NAME}"

echo "=== RDS 연결 진단 시작 ==="
echo "Host: $RDS_HOST"
echo "Port: $RDS_PORT"
echo "Database: $RDS_NAME"
echo "User: $RDS_USER"
echo ""

# 1. DNS 확인
echo "[1/5] DNS 확인..."
if nslookup "$RDS_HOST" > /dev/null 2>&1; then
    echo "✓ DNS 해석 성공"
else
    echo "✗ DNS 해석 실패"
    exit 1
fi

# 2. 포트 접근성 확인
echo "[2/5] 포트 접근성 확인..."
if nc -zv "$RDS_HOST" "$RDS_PORT" > /dev/null 2>&1; then
    echo "✓ 포트 $RDS_PORT 접근 가능"
else
    echo "✗ 포트 $RDS_PORT 접근 불가"
    exit 1
fi

# 3. 데이터베이스 연결 확인
echo "[3/5] 데이터베이스 연결 확인..."
python - <<PY
import os
import psycopg2
import sys

try:
    conn = psycopg2.connect(
        host=os.environ['DB_HOST'],
        port=int(os.environ.get('DB_PORT', '5432')),
        dbname=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
    )
    print("✓ 데이터베이스 연결 성공")
    conn.close()
except Exception as e:
    print(f"✗ 데이터베이스 연결 실패: {e}")
    sys.exit(1)
PY

# 4. 쿼리 실행 확인
echo "[4/5] 쿼리 실행 확인..."
python - <<PY
import os
import psycopg2

try:
    conn = psycopg2.connect(
        host=os.environ['DB_HOST'],
        port=int(os.environ.get('DB_PORT', '5432')),
        dbname=os.environ['DB_NAME'],
        user=os.environ['DB_USER'],
        password=os.environ['DB_PASSWORD'],
    )
    cur = conn.cursor()
    cur.execute('SELECT 1;')
    result = cur.fetchone()[0]
    print(f"✓ 쿼리 실행 성공: SELECT 1 = {result}")
    cur.close()
    conn.close()
except Exception as e:
    print(f"✗ 쿼리 실행 실패: {e}")
    exit(1)
PY

# 5. 애플리케이션 상태 확인
echo "[5/5] 애플리케이션 상태 확인..."
if curl -s http://localhost:8000/health | grep -q "healthy"; then
    echo "✓ 애플리케이션 정상 작동"
else
    echo "⚠ 애플리케이션 상태 확인 불가 (서비스 미시작 가능)"
fi

echo ""
echo "=== RDS 연결 진단 완료 ==="
```

---

## 6. 참조 파일

### 6.1 Docker Compose 설정

- **파일**: `docker-compose.rds.yml`
- **역할**: RDS 모드 오버라이드 설정
- **주요 내용**:
  - 로컬 `db` 서비스 제거
  - 백엔드 환경 변수 오버라이드 (DB_HOST, DB_PORT 등)
  - 임베딩 서버 설정

### 6.2 애플리케이션 설정

- **파일**: `backend/app/common/config.py`
- **클래스**: `DatabaseConfig`
- **환경 변수**:
  - `DB_HOST`: RDS 엔드포인트
  - `DB_PORT`: PostgreSQL 포트 (기본: 5432)
  - `DB_NAME`: 데이터베이스 이름
  - `DB_USER`: 데이터베이스 사용자
  - `DB_PASSWORD`: 데이터베이스 비밀번호

### 6.3 환경 변수 파일

- **파일**: `backend/.env`
- **형식**: KEY=VALUE (한 줄에 하나)
- **예시**:
  ```
  DB_HOST=my-instance.c9akciq32.ap-northeast-2.rds.amazonaws.com
  DB_PORT=5432
  DB_NAME=ddoksori
  DB_USER=admin
  DB_PASSWORD=MySecurePassword123!
  ```

---

## 7. 실행 순서 및 검증

### 7.1 단계별 실행

1. **환경 변수 설정**
   ```bash
   # backend/.env 파일 작성
   vi backend/.env
   ```

2. **RDS 모드 시작**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.rds.yml up --build -d embedding
   docker compose -f docker-compose.yml -f docker-compose.rds.yml up --build -d --no-deps backend
   ```

3. **연결 검증 (방법 1: Python)**
   ```bash
   docker compose exec backend python - <<'PY'
   import os
   import psycopg2
   conn = psycopg2.connect(
       host=os.environ['DB_HOST'],
       port=int(os.environ.get('DB_PORT', '5432')),
       dbname=os.environ['DB_NAME'],
       user=os.environ['DB_USER'],
       password=os.environ['DB_PASSWORD'],
   )
   cur = conn.cursor()
   cur.execute('SELECT 1;')
   print(cur.fetchone()[0])
   cur.close(); conn.close()
   PY
   ```

4. **로그 확인 (방법 2: 간접)**
   ```bash
   docker compose logs backend | grep -i "database\|connected"
   ```

5. **Health Check (방법 3)**
   ```bash
   curl http://localhost:8000/health
   ```

### 7.2 검증 체크리스트

- [ ] 환경 변수 설정 완료
- [ ] 임베딩 서버 시작 완료 (`docker compose logs embedding`)
- [ ] 백엔드 서비스 시작 완료 (`docker compose logs backend`)
- [ ] Python 연결 테스트 성공 (SELECT 1 = 1)
- [ ] 애플리케이션 로그에 에러 없음
- [ ] Health Check 엔드포인트 응답 정상

---

## 8. 성공 기준 및 예상 결과

### 8.1 성공 시나리오

```bash
# Python 연결 테스트 성공
$ docker compose exec backend python - <<'PY'
import os
import psycopg2
conn = psycopg2.connect(
    host=os.environ['DB_HOST'],
    port=int(os.environ.get('DB_PORT', '5432')),
    dbname=os.environ['DB_NAME'],
    user=os.environ['DB_USER'],
    password=os.environ['DB_PASSWORD'],
)
cur = conn.cursor()
cur.execute('SELECT 1;')
print(cur.fetchone()[0])
cur.close(); conn.close()
PY

# 예상 출력
1
```

```bash
# 애플리케이션 로그 확인
$ docker compose logs backend | tail -20

backend_1  | INFO:     Application startup complete
backend_1  | Database connected successfully
backend_1  | Orchestrator initialized
```

```bash
# Health Check 성공
$ curl http://localhost:8000/health

{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2026-01-27T10:30:00Z"
}
```

### 8.2 실패 시나리오

```bash
# 연결 실패
$ docker compose exec backend python - <<'PY'
...
PY

# 예상 출력
psycopg2.OperationalError: could not connect to server: Connection refused
```

```bash
# 인증 실패
psycopg2.OperationalError: FATAL: password authentication failed for user "admin"
```

```bash
# 보안 그룹 차단
psycopg2.OperationalError: could not connect to server: Connection timed out
```

---

## 9. 추가 리소스

### AWS RDS 문서
- [RDS PostgreSQL 연결](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_ConnectToPostgreSQLInstance.html)
- [RDS 보안 그룹 설정](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/Overview.RDSSecurityGroups.html)
- [RDS SSL/TLS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html)

### 프로젝트 문서
- `backend/app/common/config.py` - 데이터베이스 설정 클래스
- `docker-compose.rds.yml` - RDS 모드 Docker Compose 설정
- `backend/.env.example` - 환경 변수 예시

---

**작성일**: 2026-01-27  
**최종 수정**: 2026-01-27  
**상태**: Task 5 완료
