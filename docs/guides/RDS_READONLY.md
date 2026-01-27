# AWS RDS Read-only 계정 생성 가이드

AWS RDS(PostgreSQL)에 Read-only(읽기 전용) 계정을 생성하는 방법을 안내합니다.

---

## 📋 접속 전 체크리스트

터미널에서 접속하기 전에 AWS 콘솔에서 다음을 확인하세요.

1. **퍼블릭 액세스 허용 여부**
   - 로컬 PC에서 직접 접속하려면 RDS 설정의 **Public Accessibility(퍼블릭 액세스 가능)**가 `Yes`여야 합니다.
   - `No`인 경우 VPN 또는 Bastion Host를 통해서만 접속 가능합니다.

2. **보안 그룹(Security Group) 인바운드 규칙**
   - RDS에 연결된 보안 그룹의 인바운드 규칙에 **내 IP**에서 오는 **TCP 5432** 트래픽이 허용되어 있어야 합니다.
   - 설정이 안 되어 있으면 `Operation timed out` 에러가 발생합니다.

---

## 1️⃣ 관리자 계정으로 RDS 접속 (SSL 적용)

### AWS 콘솔에서 엔드포인트 확인
1. AWS RDS 대시보드에서 해당 DB 인스턴스 선택
2. **엔드포인트** 주소 복사 (예: `ddoksori-db.abc12345.ap-northeast-2.rds.amazonaws.com`)

### 터미널에서 접속

```bash
# 한 줄로 복사해서 대괄호 부분만 수정하세요
psql "host=[RDS_엔드포인트] port=5432 dbname=[DB명] user=[관리자ID] sslmode=require"
```

**예시:**
```bash
psql "host=ddoksori-db.abc12345.ap-northeast-2.rds.amazonaws.com port=5432 dbname=ddoksori user=postgres sslmode=require"
```

> **💡 참고:** 명령어 실행 후 관리자 비밀번호를 입력하라는 메시지가 나옵니다. 관리자 비밀번호를 입력하세요.

---

## 2️⃣ Read-only 계정 생성 및 권한 부여

접속에 성공했다면 프롬프트(`postgres=>`또는 `ddoksori=>`)가 보입니다. 아래 SQL을 순서대로 실행하세요.

### 1단계: 유저 생성 및 기본 권한

```sql
-- 1. 읽기 전용 유저 생성
CREATE USER readonly_user WITH PASSWORD '🔐🔐🔐 로그인할 때 사용할 비밀번호 입력하기 🔐🔐🔐';

-- 2. DB 접속 허용
GRANT CONNECT ON DATABASE ddoksori TO readonly_user;

-- 3. public 스키마 사용 허용
GRANT USAGE ON SCHEMA public TO readonly_user;
```

### 2단계: 조회 권한 부여 (핵심)

```sql
-- 4. [핵심] 현재 존재하는 모든 테이블에 대한 SELECT 권한 부여
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;

-- 5. [중요] 미래에 생성될 테이블들도 자동으로 SELECT 가능하도록 설정
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;

-- 6. (선택) 시퀀스(id 자동증가 등) 조회 권한
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO readonly_user;
```

### 권한 부여 확인

```sql
-- 부여된 권한 확인
\du readonly_user
-- <출력 예시>
--       List of roles
--    Role name  | Attributes 
-- --------------+--------------
-- readonly_user | 

-- 테이블 권한 확인
SELECT grantee, privilege_type 
FROM role_table_grants 
WHERE table_schema='public' AND grantee='readonly_user' 
LIMIT 5;
```

---

## 3️⃣ 접속 테스트 (Read-only 계정 + SSL)

### 관리자 접속 종료

프롬프트에서 `\q`를 입력하여 종료합니다.

```bash
postgres=> \q
```

### Read-only 계정으로 재접속

```bash
# 새 계정으로 접속
psql "host=[RDS_엔드포인트] port=5432 dbname=[DB명] user=readonly_user sslmode=require"
```

**예시:**
```bash
psql "host=ddoksori-db.abc12345.ap-northeast-2.rds.amazonaws.com port=5432 dbname=ddoksori user=readonly_user sslmode=require"
```

### 검증 쿼리 실행

```sql
-- 1. SSL 연결 확인 (t가 나오면 SSL 연결 중)
SELECT ssl_is_used();

-- 2. 테이블 목록 확인
\dt

-- 3. 조회 테스트 (성공해야 함)
SELECT count(*) FROM users;

-- 4. 쓰기 테스트 (실패해야 함: ERROR: permission denied)
CREATE TABLE test_hack (id int);
```

---

## 🔧 트러블슈팅

### SSL 인증서 오류
```
error: FATAL: SSL connection failed
```

**해결책:**
- `sslmode=require` → 암호화 통신만 필요할 경우 (권장)
- `sslmode=verify-full` → 엄격한 검증 필요 (루트 인증서 필요)
- `sslmode=no-verify` → 임시 테스트용 (프로덕션 비권장)

### 접속 타임아웃
```
psql: error: FATAL: remaining connection slots are reserved for non-replication superuser connections
```

**해결책:**
- 보안 그룹의 인바운드 규칙에 내 IP와 TCP 5432가 허용되어 있는지 확인
- RDS의 퍼블릭 액세스가 `Yes`로 설정되어 있는지 확인

### 권한 오류
```
ERROR: permission denied for schema public
```

**해결책:**
- 위의 **2️⃣ 2단계** SQL을 다시 실행하여 권한을 완전히 부여합니다.

---

## 📌 최소 권한 원칙 (Principle of Least Privilege)

특정 스키마나 테이블만 접근 가능하게 제한하려면:

```sql
-- 특정 스키마만 접근
GRANT USAGE ON SCHEMA analytics TO readonly_user;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO readonly_user;

-- 특정 테이블만 접근
GRANT SELECT ON users, orders, products TO readonly_user;

-- 특정 열(Column)만 접근 (고급)
-- PostgreSQL 15+ 지원
GRANT SELECT (id, email, name) ON users TO readonly_user;
```

---

## 🔐 보안 체크리스트

- [ ] 비밀번호는 충분히 강력한가? (대소문자, 숫자, 특수문자 포함)
- [ ] RDS 퍼블릭 액세스는 필요한 경우만 활성화되어 있는가?
- [ ] 보안 그룹은 필요한 IP 범위만 허용하는가?
- [ ] 정기적으로 읽기 전용 권한이 맞는지 감사하는가?
- [ ] 불필요한 계정은 정기적으로 삭제하는가?

---

## 📚 참고 자료

- [PostgreSQL 권한 관리](https://www.postgresql.org/docs/current/sql-grant.html)
- [AWS RDS 보안](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.html)
- [PostgreSQL 역할과 권한](https://www.postgresql.org/docs/current/user-manag.html)
