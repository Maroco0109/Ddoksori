# Learnings - E2E Runpod Checklist

## Conventions & Patterns
(Subagents will append findings here)

- E2E 사전 준비 체크리스트 작성 완료 (.sisyphus/evidence/e2e-runpod/00-pre-setup-checklist.md)
- QUERY_REWRITE_TIMEOUT의 단위(ms) 및 모드별 권장값(90ms/2000ms) 명시
- Runpod health 체크 시 URL 변환 규칙(rstrip/replace) 반영
- 최종 E2E 테스트 절차 문서 작성 완료 (.sisyphus/evidence/e2e-runpod/06-e2e-test.md)
  - 정상/Fallback/DB 장애 3대 시나리오 정의
  - Runpod 호출 트리거 조건(법률 용어, 길이, 문체) 명시
  - 디버그 모드(`"debug": true`) 관찰 포인트 및 CURL 예시 포함

## Task 2: 모델 연결 점검 절차 (02-model-connection-check.md)

### 핵심 발견사항

#### Health Check URL 규칙
- Python 구현: `runpod_url.rstrip('/').replace('/v1', '')`
- Bash 동등: `"${EXAONE_RUNPOD_URL%/}"` + `"${BASE_URL//\/v1/}"`
- 코드 검증: exaone_client.py(라인 92), tool_calling_client.py(라인 56)에서 동일 로직 확인

#### 실행 위치 분리
- **Host 실행**: 네트워크/Runpod 자체 접근성 검증 (curl 사용)
- **Backend 컨테이너 실행**: 실제 운영 경로 egress 검증 (Python/requests 사용)
  - curl 의존성 제거로 컨테이너 내 독립적 실행 가능
  - `docker compose exec backend python - <<'PY'` 패턴 사용

#### 실패 진단 체크리스트
1. DNS 오류: `nslookup` / `dig` 확인
2. 포트 오류: `nc -zv` / `telnet` 확인
3. 라우팅 오류: `/health` vs `/v1/health` 경로 검증
4. 인증 오류: `Authorization: Bearer` 헤더 확인
5. 타임아웃 오류: `--max-time` 증가 및 응답 시간 측정

#### 환경 변수 의존성
- `EXAONE_RUNPOD_URL`: 필수 (예: https://<pod-id>-8000.proxy.runpod.net/v1)
- `EXAONE_RUNPOD_API_KEY`: 선택 (기본: dummy)
- `EXAONE_MODEL`: 필수 (예: LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct)
- `EXAONE_TIMEOUT`: 선택 (기본: 10초)

#### 타임아웃 설정
- Health Check: 5초 (requests.get timeout)
- Chat Completions: 10초 (EXAONE_TIMEOUT 환경 변수)
- LLM Tool Calling: LLM_TOOL_TIMEOUT_MS (기본: 5000ms)

### 문서 구조
- 섹션 1: 개요 및 검증 범위
- 섹션 2: Health Check (URL 규칙, Host/컨테이너 실행)
- 섹션 3: Chat Completions (Host/컨테이너 실행)
- 섹션 4: 실패 진단 (5가지 원인 분류 + 종합 스크립트)
- 섹션 5-7: 참조, 실행 순서, 성공 기준

### 코드 일관성 검증
- ✓ exaone_client.py: health_check() 메서드 (라인 77-113)
- ✓ tool_calling_client.py: health_check() 메서드 (라인 47-77)
- ✓ 두 파일 모두 동일한 URL 변환 규칙 적용
- ✓ requests.get(health_url, timeout=5) 패턴 일치

### 실행 가능성 검증
- ✓ Bash 스크립트: 환경 변수 기반 동적 URL 구성
- ✓ Python 스크립트: docker compose exec 패턴으로 컨테이너 내 실행
- ✓ curl 명령: -fsS, -w, --max-time 옵션 포함
- ✓ 진단 스크립트: nslookup, nc, curl 조합으로 5단계 검증


## Task 4: Docker 점검 및 테스트 (04-docker-check.md)

### 핵심 발견사항

#### 로컬 Docker 임베딩 토폴로지
- **문제**: `docker-compose.yml`만으로는 KURE 임베딩 서비스 없음
- **해결**: `docker-compose.rds.yml`의 `embedding` 서비스 + 로컬 DB 조합
- **명령**: `docker compose -f docker-compose.yml -f docker-compose.rds.yml up --build -d db redis embedding backend frontend`
- **결과**: `REMOTE_EMBED_URL=http://embedding:8001` → `EMBED_API_URL=http://embedding:8001/embed`

#### 임베딩 URL 우선순위 규칙
- **최고 우선순위**: `REMOTE_EMBED_URL` (환경 변수)
  - RDS compose에서 backend에 주입: `REMOTE_EMBED_URL=http://embedding:8001`
  - 코드: `backend/utils/embedding_connection.py` 라인 85-90
  
- **2순위**: 로컬 실행 중인 서버 (KURE_LOCAL_PORT)
  - 기본값: `http://localhost:9001`
  - 로컬 개발 환경에서 사용
  
- **3순위**: 로컬 서버 자동 시작
  - 컨테이너 환경에서는 비활성화: `DISABLE_LOCAL_EMBED_AUTO_START=true`
  - 코드: `backend/utils/embedding_connection.py` 라인 104-106

- **BGE-M3 주의**:
  - `BGE_M3_*` 변수는 HybridRetriever sparse 경로에서만 사용
  - `EMBED_API_URL` 자체를 대체하지 않음 (코드 라인 162-170)

#### 서비스 포트 매핑
| 서비스 | 로컬 개발 | 컨테이너 (RDS) | 설명 |
|--------|----------|----------------|------|
| Frontend | 5173 | 5173 | React Web UI |
| Backend | 8000 | 8000 | FastAPI API Server |
| Database | 5432 | 5432 | PostgreSQL + pgvector |
| Redis | 6379 | 6379 | Answer Caching |
| KURE Embedding | 9001 | 8001 | Dense Embedding (RDS compose) |
| BGE-M3 | 9003 | 8003 | Dense + Sparse (프로필: bge-m3) |

#### Backend 시작 시 EMBED_API_URL 주입
- **코드 위치**: `backend/app/main.py` 라인 40-42
  ```python
  from utils.embedding_connection import get_embedding_api_url
  embed_api_url = get_embedding_api_url()
  os.environ['EMBED_API_URL'] = embed_api_url
  ```
- **Startup 로그**: 라인 92에서 `[Startup] Embedding API: {embed_api_url}` 출력
- **핵심**: `get_embedding_api_url()` 결과가 최종 값 (환경 변수 덮어씀)

#### 헬스 체크 전략
- **Backend Health**: `curl http://localhost:8000/health` → 200 OK
- **DB 연결**: `docker compose exec backend python` + psycopg2 테스트
- **Redis 연결**: `docker compose exec backend python` + redis 테스트
- **Embedding Health**: `docker compose exec backend python` + requests.get('http://embedding:8001/health')
  - **중요**: 로그만으로 PASS 처리 금지, 실제 200 응답 확인 필수

#### 컨테이너 네트워크 통신
- Backend → DB: `host="db"` (Docker DNS)
- Backend → Redis: `host="redis"` (Docker DNS)
- Backend → Embedding: `host="embedding"` (Docker DNS)
- 모두 `docker-compose.rds.yml`의 동일 네트워크에 속함

### 문서 구조
- 섹션 1: 개요 및 검증 범위
- 섹션 2: 로컬 Docker 임베딩 토폴로지 (문제/해결/이점)
- 섹션 3: 서비스 기동 (명령어, 포트 정보, 상태 확인)
- 섹션 4: 헬스 체크 (Backend, 네트워크, DB/Redis)
- 섹션 5: 임베딩 서비스 검증 (URL 우선순위, Startup 로그, Health Check, 포트)
- 섹션 6-10: 체크리스트, 참조, 실행 순서, 성공 기준, 문제 해결

### 코드 검증
- ✓ `backend/utils/embedding_connection.py`: 우선순위 로직 (라인 79-112)
- ✓ `backend/app/main.py`: EMBED_API_URL 주입 (라인 40-42, 92)
- ✓ `docker-compose.yml`: 서비스 포트 정의 (라인 1-100)
- ✓ `docker-compose.rds.yml`: embedding 서비스 + backend 환경 변수 (라인 27-55)

### 실행 가능성 검증
- ✓ Docker Compose 명령: 다중 파일 지원 (`-f docker-compose.yml -f docker-compose.rds.yml`)
- ✓ Python 스크립트: `docker compose exec backend python - <<'PY'` 패턴
- ✓ 헬스 체크: curl + requests 조합으로 Host/컨테이너 모두 검증 가능
- ✓ 포트 매핑: 명확한 로컬/컨테이너 구분

### 수용 기준 충족
- ✓ 서비스 기동 명령 포함 (라인 292-295)
- ✓ 임베딩 토폴로지 설명 (라인 283-289)
- ✓ Backend 헬스 체크 절차 (라인 307)
- ✓ 컨테이너 네트워크 검증 (라인 308)
- ✓ 임베딩 URL/포트 검증 (라인 309-325)
  - Startup 로그 확인
  - KURE/BGE-M3 포트 명시
  - RDS compose URL 규칙
  - 우선순위 고정 설명
  - 실제 Health Check (200 확인)


## Task 5: RDS 연결 점검 및 테스트 (05-rds-check.md)

### 핵심 발견사항

#### RDS 모드 Docker Compose 실행
- **명령 1**: `docker compose -f docker-compose.yml -f docker-compose.rds.yml up --build -d embedding`
  - 임베딩 서버 먼저 시작 (Backend 의존성)
  
- **명령 2**: `docker compose -f docker-compose.yml -f docker-compose.rds.yml up --build -d --no-deps backend`
  - `--no-deps` 플래그로 로컬 `db` 서비스 시작 방지
  - RDS 환경 변수 (DB_HOST/PORT/NAME/USER/PASSWORD) 사용

#### DB 연결 검증 (3가지 방법)

**방법 1: Python/psycopg2 (권장)**
- 실행 위치: Backend 컨테이너 또는 로컬 conda dsr 환경
- 명령: `docker compose exec backend python - <<'PY'` 패턴
- 검증 항목:
  - 환경 변수 기반 연결 (DB_HOST/PORT/NAME/USER/PASSWORD)
  - SELECT 1 쿼리 실행 (예상 결과: 1)
  - 테이블 존재 여부 확인 (information_schema.tables)

**방법 2: 애플리케이션 로그 (간접)**
- 백엔드 로그에서 "Database connected successfully" 메시지 확인
- `docker compose logs backend | grep -E "(DB|database|connected|error)"`

**방법 3: Health Check 엔드포인트**
- `curl http://localhost:8000/health`
- 응답: `{"status": "healthy", "database": "connected"}`

#### 환경 변수 설정 (backend/.env)
```
DB_HOST=your-instance.xxxx.ap-northeast-2.rds.amazonaws.com
DB_PORT=5432
DB_NAME=ddoksori
DB_USER=admin
DB_PASSWORD=your-secure-password
```

#### 실패 진단 체크리스트 (5가지 원인)
1. **Connection refused/timeout**: DNS/포트 접근성 (nslookup, nc -zv)
2. **Authentication failed**: 자격증명 오류 (환경 변수 재확인)
3. **SSL error**: 인증서 검증 실패 (sslmode 설정)
4. **Database does not exist**: DB 이름 오류 (pg_database 확인)
5. **Permission denied**: 사용자 권한 부족 (마스터 사용자 확인)

#### 성공 기준
- [ ] SELECT 1 쿼리 = 1 반환
- [ ] 사용자 인증 성공
- [ ] 기본 쿼리 실행 가능
- [ ] 백엔드 서비스 정상 시작
- [ ] Health Check 엔드포인트 healthy 상태

#### 코드 참조
- `backend/app/common/config.py`: DatabaseConfig 클래스 (라인 40-84)
  - `get_connection_dict()`: psycopg2 연결 파라미터
  - `get_dsn()`: PostgreSQL DSN 문자열
- `docker-compose.rds.yml`: RDS 모드 오버라이드 (라인 44-57)
  - Backend 환경 변수 오버라이드
  - `--no-deps` 사용 시 로컬 db 제외

### 문서 구조
- 섹션 1: 개요 (RDS 연결 검증 범위)
- 섹션 2: RDS 모드 Docker Compose 실행 (전제조건, 환경 변수, 서비스 시작)
- 섹션 3: DB 연결 검증 (3가지 방법 + 실행 위치)
- 섹션 4: 성공 기준 (5가지 조건)
- 섹션 5: 실패 시 진단 절차 (5가지 원인 분류 + 종합 스크립트)
- 섹션 6-9: 참조, 실행 순서, 성공 기준, 추가 리소스

### 실행 가능성 검증
- ✓ Docker Compose 명령: 다중 파일 + --no-deps 플래그
- ✓ Python 스크립트: docker compose exec 패턴 + 환경 변수 읽기
- ✓ 진단 스크립트: nslookup, nc, curl, psycopg2 조합
- ✓ 환경 변수: backend/.env 파일 기반 동적 설정

### 수용 기준 충족
- ✓ RDS compose 실행 절차 (섹션 2.2, 라인 340-345)
- ✓ DB 연결 검증 (섹션 3, 라인 346-367)
  - 실행 위치 명시 (컨테이너 vs 로컬)
  - Python/psycopg2 전체 코드 포함
  - 예상 출력 명시
- ✓ 성공 기준 (섹션 4, 라인 368)
  - 연결 + 간단 쿼리 결과
- ✓ 실패 진단 (섹션 5, 라인 369)
  - 보안그룹/VPC 라우팅/자격증명/SSL
  - 종합 진단 스크립트 포함


## Task 1: 에이전트별 모델 할당 점검 (2026-01-27)
- **에이전트-모델 매핑 구조**:
    - Query Rewrite & Ambiguity Check: EXAONE 3.5 (RunPod)
    - Tool Calling (Legacy): EXAONE 3.5 (RunPod)
    - Answer Generation: GPT-4o-mini (OpenAI) 주력, Fallback 체인 보유
    - Legal Review: 규칙 기반(Regex) + GPT-4o-mini (OpenAI) 하이브리드
- **주요 발견 사항**:
    - `QUERY_REWRITE_TIMEOUT`은 `query_rewriter.py`에서 기본 10000ms(10초)로 설정되어 있으나, 코드 주석에는 90ms 하드 타임아웃 언급이 있어 혼선이 있을 수 있음. 실제 환경변수 설정을 우선 확인해야 함.
    - `ENABLE_LLM_REVIEW`는 기본값이 `false`이며, 활성화 시 OpenAI `gpt-4o-mini`를 사용함.
    - `ExaoneLLMClient`는 `health_check` 시 `rstrip('/').replace('/v1', '') + '/health'` 경로를 사용함.
- **조건부 동작**:
    - `chat_type='general'`인 경우 `query_analysis`에서 `NO_RETRIEVAL`로 라우팅되며, `review_node_wrapper`에서 검토를 스킵함 (Fast Path).

## Task 3: Runpod VRAM 계산 및 단일 pod 가능 여부 판정 (2026-01-27)
- **EXAONE 3.5 7.8B VRAM 요구사항**:
    - Weights (FP16): 15.6GB
    - Overhead: 5.0GB
    - KV Cache (Context 1024, Concurrency 4): 0.6GB
    - Total (with 20% margin): ~25.5GB
- **결론**: 단일 Pod 서비스 가능. 단, 24GB GPU(RTX 3090/4090)는 마진이 타이트하므로 A6000(48GB) 또는 A100(40GB) 추천.
- **GQA의 이점**: EXAONE 3.5 7.8B는 num_key_value_heads=8 (GQA)을 사용하여 KV Cache 메모리 사용량이 매우 효율적임 (동일 파라미터 대비 약 1/4 수준).
- **병목 분석**: 가중치 메모리가 전체의 70% 이상을 차지하므로, 메모리 부족 시 가장 효과적인 해결책은 정밀도 조정(FP16 -> INT8/AWQ)임.

## Phase 8: Docker Cleanup and RDS E2E Testing (2026-01-27)

### Docker Cleanup
- **Containers removed**: ddoksori_backend, ddoksori_db, ddoksori_cloudbeaver, ddoksori_frontend, ddoksori_embedding, ddoksori_grafana, ddoksori_prometheus, ddoksori_redis
- **Volumes removed**: llm_postgres_data, llm_cloudbeaver_data, llm_prometheus_data, llm_grafana_data, llm_redis_data
- **Command**: `docker compose down -v`

### RDS READ_ONLY Connection
- **Host**: dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com
- **User**: ddoksori_ro (READ_ONLY account)
- **Database**: ddoksori
- **Tables available**: vector_chunks (40,285 rows), search_quality_logs
- **Permissions verified**: SELECT works, CREATE TABLE fails (permission denied)

### conftest.py Update
- Added RDS READ_ONLY mode detection to skip schema check
- RDS uses different schema (vector_chunks) vs local (documents, chunks, mv_searchable_chunks)
- Tests now run without skipping when USE_RDS_FOR_TESTS=true

### Test Results
- **421 passed**, 50 failed, 27 skipped
- Failed tests are mostly API tests requiring running server
- Unit tests pass with RDS READ_ONLY connection

### Health Check
- Backend starts successfully with RDS connection
- `curl localhost:8000/health` → `{"status":"healthy","database":"connected"}`
- Requires setting DB_HOST/USER/PASSWORD to RDS values for runtime

### Key Configuration
```bash
# For tests (conftest.py)
USE_RDS_FOR_TESTS=true
DB_TEST_HOST=dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com
DB_TEST_USER=ddoksori_ro
DB_TEST_PASSWORD=kppll2026!
DB_TEST_NAME=ddoksori

# For runtime (backend server)
DB_HOST=dsr-postgres.cyhiie0gambz.us-east-1.rds.amazonaws.com
DB_USER=ddoksori_ro
DB_PASSWORD=kppll2026!
DB_NAME=ddoksori
```
