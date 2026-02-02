# Docker 점검 절차

## 1. 개요

Docker Compose 기반 서비스 기동 및 헬스 상태 검증 절차입니다.

**검증 범위**:
- 주요 서비스 기동 상태 확인 (Backend, Frontend, DB, Redis, Embedding)
- Backend 헬스 엔드포인트 검증
- 컨테이너 간 네트워크 통신 확인
- 임베딩 서비스 URL/포트 검증
- 임베딩 헬스 상태 실제 확인

---

## 2. 로컬 Docker 임베딩 토폴로지

### 문제점
`docker-compose.yml`만으로는 KURE 임베딩 서비스가 포함되지 않습니다.

### 해결책
`docker-compose.rds.yml`의 `embedding` 서비스를 로컬 DB와 함께 사용합니다.

**구성**:
- `DB_HOST=db` (로컬 Docker DB 유지)
- `docker-compose.rds.yml`이 backend에 `REMOTE_EMBED_URL=http://embedding:8001` 주입
- 결과: 앱 시작 시 `Embedding API: http://embedding:8001/embed`로 고정

**이점**:
- 로컬 환경에서 완전한 스택 테스트 가능
- 원격 임베딩 서버 의존성 제거
- 컨테이너 네트워크 내 빠른 통신

---

## 3. 서비스 기동

### 3.1 기본 서비스 시작 (권장)

```bash
# 로컬 DB + 임베딩 서비스 포함
docker compose -f docker-compose.yml -f docker-compose.rds.yml up --build -d db redis embedding backend frontend

# (선택) 모니터링까지 포함
docker compose -f docker-compose.yml -f docker-compose.rds.yml up --build -d db redis embedding backend frontend prometheus grafana
```

**명령어 설명**:
- `-f docker-compose.yml`: 기본 서비스 정의
- `-f docker-compose.rds.yml`: 임베딩 서비스 + backend 환경 변수 오버라이드
- `--build`: 이미지 재빌드
- `-d`: 백그라운드 실행
- 서비스 목록: `db`, `redis`, `embedding`, `backend`, `frontend`

### 3.2 서비스 포트 정보

| 서비스 | 포트 | 설명 |
|--------|------|------|
| Frontend | 5173 | React Web UI |
| Backend | 8000 | FastAPI API Server |
| Database | 5432 | PostgreSQL + pgvector |
| Redis | 6379 | Answer Caching |
| Embedding | 8001 | KURE Embedding Server (RDS compose) |
| BGE-M3 | 8003 | BGE-M3 Embedding Server (선택 프로필) |
| CloudBeaver | 8978 | Web-based DB Manager |
| Prometheus | 9090 | Monitoring Metrics |
| Grafana | 3000 | Monitoring Dashboard |

### 3.3 서비스 상태 확인

```bash
# 모든 컨테이너 상태 확인
docker compose -f docker-compose.yml -f docker-compose.rds.yml ps

# 예상 출력:
# NAME                    STATUS
# ddoksori_db             Up (healthy)
# ddoksori_redis          Up
# ddoksori_embedding      Up (healthy)
# ddoksori_backend        Up
# ddoksori_frontend       Up
```

---

## 4. 헬스 체크

### 4.1 Backend Health 엔드포인트

**목적**: Backend API 서버가 정상 작동하는지 확인

**Host에서 실행**:
```bash
curl -s http://localhost:8000/health | jq .
```

**예상 응답** (200 OK):
```json
{
  "status": "ok",
  "timestamp": "2025-01-27T10:30:45.123456"
}
```

**Backend 컨테이너에서 실행** (네트워크 내부 검증):
```bash
docker compose -f docker-compose.yml -f docker-compose.rds.yml exec backend curl -s http://localhost:8000/health
```

### 4.2 컨테이너 간 네트워크 통신 확인

**목적**: Backend가 DB/Redis와 통신 가능한지 확인

**DB 연결 테스트**:
```bash
docker compose -f docker-compose.yml -f docker-compose.rds.yml exec backend python - <<'PY'
import psycopg2
try:
    conn = psycopg2.connect(
        host="db",
        port=5432,
        database="ddoksori",
        user="postgres",
        password="postgres"
    )
    print("✅ DB 연결 성공")
    conn.close()
except Exception as e:
    print(f"❌ DB 연결 실패: {e}")
PY
```

**Redis 연결 테스트**:
```bash
docker compose -f docker-compose.yml -f docker-compose.rds.yml exec backend python - <<'PY'
import redis
try:
    r = redis.Redis(host="redis", port=6379, decode_responses=True)
    r.ping()
    print("✅ Redis 연결 성공")
except Exception as e:
    print(f"❌ Redis 연결 실패: {e}")
PY
```

---

## 5. 임베딩 서비스 검증

### 5.1 URL 우선순위 규칙

**핵심 원칙**: `backend/app/main.py`가 `get_embedding_api_url()` 결과로 `EMBED_API_URL`을 **항상** 덮어씁니다.

**우선순위 순서** (backend/utils/embedding_connection.py):
1. **REMOTE_EMBED_URL** (환경 변수)
   - RDS compose에서 `REMOTE_EMBED_URL=http://embedding:8001` 주입
   - 가장 높은 우선순위
   
2. **로컬 실행 중인 서버** (KURE_LOCAL_PORT)
   - 기본값: `http://localhost:9001`
   - 로컬 개발 환경에서 사용
   
3. **로컬 서버 자동 시작** (DISABLE_LOCAL_EMBED_AUTO_START=false)
   - 위 두 가지 모두 실패 시 자동 시작
   - 컨테이너 환경에서는 비활성화 (`DISABLE_LOCAL_EMBED_AUTO_START=true`)

**BGE-M3 주의**:
- `BGE_M3_*` 환경 변수는 HybridRetriever의 sparse 경로에서만 사용
- `EMBED_API_URL` 자체를 대체하지 않음

### 5.2 Startup Log 확인

**목적**: 앱 시작 시 실제 사용되는 임베딩 URL 확인

**로그 확인**:
```bash
# Backend 컨테이너 로그 확인
docker compose -f docker-compose.yml -f docker-compose.rds.yml logs backend | grep -i "embedding"

# 예상 로그:
# [Startup] Embedding API: http://embedding:8001/embed
```

**로그 해석**:
- `http://embedding:8001/embed` → RDS compose의 embedding 서비스 사용 (정상)
- `http://localhost:9001/embed` → 로컬 KURE 서버 사용 (로컬 개발)
- `http://localhost:9003/embed` → BGE-M3 사용 (sparse 검색 활성화)

### 5.3 Embedding Health Check

**목적**: 임베딩 서비스가 실제로 응답하는지 확인 (로그만으로 PASS 처리 금지)

**Backend 컨테이너에서 실행**:
```bash
docker compose -f docker-compose.yml -f docker-compose.rds.yml exec backend python - <<'PY'
import requests
try:
    r = requests.get('http://embedding:8001/health', timeout=5)
    print(f"Status Code: {r.status_code}")
    if r.status_code == 200:
        print("✅ Embedding 헬스 체크 성공")
    else:
        print(f"❌ Embedding 헬스 체크 실패: {r.status_code}")
except Exception as e:
    print(f"❌ Embedding 연결 실패: {e}")
PY
```

**예상 응답**:
```
Status Code: 200
✅ Embedding 헬스 체크 성공
```

### 5.4 Embedding 포트 검증

**KURE 기본 포트**:
- 로컬 개발: `KURE_LOCAL_PORT=9001` (기본값)
- 컨테이너 (RDS compose): `8001` (docker-compose.rds.yml에서 정의)

**BGE-M3 기본 포트**:
- 로컬 개발: `BGE_M3_LOCAL_PORT=9003` (기본값)
- 컨테이너: `8003` (docker-compose.yml에서 정의, 프로필: bge-m3)

**포트 확인**:
```bash
# 컨테이너 포트 매핑 확인
docker compose -f docker-compose.yml -f docker-compose.rds.yml ps embedding

# 예상 출력:
# NAME                    PORTS
# ddoksori_embedding      0.0.0.0:8001->8001/tcp
```

---

## 6. 전체 검증 체크리스트

### 기동 단계
- [ ] `docker compose up --build` 명령 실행 성공
- [ ] 모든 서비스가 "Up" 상태로 확인됨
- [ ] 에러 로그 없음

### Backend 헬스
- [ ] `curl http://localhost:8000/health` → 200 OK
- [ ] Backend 컨테이너 로그에 `[Startup] Embedding API: ...` 확인

### 네트워크 통신
- [ ] Backend → DB 연결 성공
- [ ] Backend → Redis 연결 성공

### 임베딩 서비스
- [ ] Startup 로그에서 `http://embedding:8001/embed` 확인
- [ ] `docker compose exec backend python` 스크립트로 `/health` 200 확인
- [ ] 포트 매핑 확인: `8001:8001`

---

## 7. 참조 파일

| 파일 | 설명 |
|------|------|
| `docker-compose.yml` | 기본 서비스 정의 (frontend, backend, db, redis, bge_m3 등) |
| `docker-compose.rds.yml` | RDS + 임베딩 서비스 오버라이드 |
| `backend/Dockerfile` | Backend 이미지 빌드 |
| `frontend/Dockerfile` | Frontend 이미지 빌드 |
| `backend/Dockerfile.embedding` | Embedding 서비스 이미지 (RDS compose) |
| `backend/Dockerfile.bge_m3` | BGE-M3 임베딩 서버 이미지 |
| `backend/utils/embedding_connection.py` | 임베딩 URL 결정 로직 (라인 79-112) |
| `backend/app/main.py` | Backend 시작 시 EMBED_API_URL 주입 (라인 40-42, 92) |

---

## 8. 실행 순서 (권장)

1. **서비스 기동**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.rds.yml up --build -d db redis embedding backend frontend
   ```

2. **서비스 상태 확인**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.rds.yml ps
   ```

3. **Backend 헬스 확인**
   ```bash
   curl -s http://localhost:8000/health | jq .
   ```

4. **네트워크 통신 확인**
   ```bash
   # DB 연결
   docker compose -f docker-compose.yml -f docker-compose.rds.yml exec backend python - <<'PY'
   import psycopg2
   conn = psycopg2.connect(host="db", port=5432, database="ddoksori", user="postgres", password="postgres")
   print("✅ DB 연결 성공")
   conn.close()
   PY
   ```

5. **Embedding 헬스 확인**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.rds.yml exec backend python - <<'PY'
   import requests
   r = requests.get('http://embedding:8001/health', timeout=5)
   print(f"Status: {r.status_code}")
   PY
   ```

6. **Startup 로그 확인**
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.rds.yml logs backend | grep -i "embedding"
   ```

---

## 9. 성공 기준

✅ **모든 항목이 확인되어야 Task 4 PASS**:

1. `docker compose up --build` 성공 (에러 없음)
2. 모든 서비스 "Up" 상태
3. Backend `/health` → 200 OK
4. Backend → DB/Redis 연결 성공
5. Embedding `/health` → 200 OK (실제 요청)
6. Startup 로그: `Embedding API: http://embedding:8001/embed`

---

## 10. 문제 해결

### Embedding 서비스가 시작되지 않음
- 로그 확인: `docker compose logs embedding`
- 포트 충돌 확인: `lsof -i :8001`
- 이미지 재빌드: `docker compose build --no-cache embedding`

### Backend가 Embedding에 연결 불가
- 네트워크 확인: `docker network ls`
- DNS 확인: `docker compose exec backend nslookup embedding`
- 포트 확인: `docker compose ps embedding`

### DB 연결 실패
- 환경 변수 확인: `docker compose exec backend env | grep DB_`
- 포트 확인: `docker compose ps db`
- 헬스 확인: `docker compose exec db pg_isready -U postgres`

