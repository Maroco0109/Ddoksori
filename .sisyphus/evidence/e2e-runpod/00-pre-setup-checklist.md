# E2E 사전 준비 체크리스트

본 문서는 Runpod/RDS 환경에서의 E2E 테스트를 위한 사전 준비 사항 및 환경 변수, 증거 수집 절차를 정의합니다.

## 1. 테스트 대상 환경
테스트는 다음 두 가지 환경 구분을 명확히 하여 진행합니다.
- **로컬 Docker 환경**: 로컬 DB(PostgreSQL), Redis, Backend, Frontend 컨테이너 사용
- **Runpod + RDS 환경**: 외부 Runpod(EXAONE 모델) 및 AWS RDS(PostgreSQL) 연결 환경

## 2. 필수 환경변수 목록
`backend/.env.example` 및 테스트 계획을 바탕으로 한 필수 환경변수입니다.

### 2.1 Runpod/EXAONE (모델 연결)
| 변수명 | 설명 | 필수 여부 | 기본값/예시 |
|:---|:---|:---:|:---|
| `EXAONE_RUNPOD_URL` | Runpod API 엔드포인트 | 필수 | `http://localhost:19080/v1` |
| `EXAONE_RUNPOD_API_KEY` | Runpod API 인증 키 | 필수 | `dummy` |
| `EXAONE_MODEL` | 사용할 모델명 | 필수 | `LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct` |
| `EXAONE_MODEL_SIZE` | 모델 파라미터 크기 | 선택 | `7.8B` |
| `EXAONE_TIMEOUT` | API 호출 타임아웃(초) | 선택 | `10` |
| `EXAONE_TEMPERATURE` | 생성 온도 | 선택 | `0.3` |
| `EXAONE_MAX_TOKENS` | 최대 생성 토큰 수 | 선택 | `1024` |

### 2.2 Query Rewrite (Runpod 호출 트리거)
| 변수명 | 설명 | 필수 여부 | 기본값/예시 |
|:---|:---|:---:|:---|
| `QUERY_REWRITE_ENABLED` | 쿼리 재작성 활성화 여부 | 필수 | `true` |
| `QUERY_REWRITE_TIMEOUT` | LLM 호출 타임아웃(ms) | 필수 | `90` (Mode A), `2000` (Mode B) |
| `QUERY_REWRITE_MIN_COMPLEXITY` | 재작성 트리거 최소 복잡도 | 선택 | `1` |

### 2.3 MAS/Graph (오케스트레이터)
| 변수명 | 설명 | 필수 여부 | 기본값/예시 |
|:---|:---|:---:|:---|
| `MAS_SUPERVISOR_ENABLED` | MAS Supervisor 그래프 사용 여부 | 필수 | `true` |
| `MAS_SUPERVISOR_CANARY_PERCENT` | Canary 배포 비율 (0-100) | 선택 | `0` |

### 2.4 DB/RDS (데이터 저장소)
| 변수명 | 설명 | 필수 여부 | 기본값/예시 |
|:---|:---|:---:|:---|
| `DB_HOST` | 데이터베이스 호스트 주소 | 필수 | `db` 또는 RDS 엔드포인트 |
| `DB_PORT` | 데이터베이스 포트 | 필수 | `5432` |
| `DB_NAME` | 데이터베이스 이름 | 필수 | `ddoksori` |
| `DB_USER` | 데이터베이스 사용자 | 필수 | `postgres` |
| `DB_PASSWORD` | 데이터베이스 비밀번호 | 필수 | `postgres` |

### 2.5 Embedding (KURE & BGE-M3)
| 변수명 | 설명 | 필수 여부 | 기본값/예시 |
|:---|:---|:---:|:---|
| `REMOTE_EMBED_URL` | KURE 임베딩 서버 URL | 필수 | `http://localhost:19001` |
| `KURE_LOCAL_PORT` | KURE 로컬 포트 | 선택 | `9001` |
| `DISABLE_LOCAL_EMBED_AUTO_START` | 로컬 임베딩 자동 시작 방지 | 선택 | `true` |
| `BGE_M3_REMOTE_URL` | BGE-M3 서버 URL | 선택 | `http://localhost:19003` |
| `BGE_M3_LOCAL_PORT` | BGE-M3 로컬 포트 | 선택 | `9003` |
| `EMBEDDING_MODEL` | 활성 임베딩 모델 선택 | 선택 | `kure-v1` 또는 `bge-m3` |
| `ENABLE_SPARSE_SEARCH` | Sparse 검색 활성화 여부 | 선택 | `false` |

### 2.6 External LLM (외부 모델)
| 변수명 | 설명 | 필수 여부 | 기본값/예시 |
|:---|:---|:---:|:---|
| `OPENAI_API_KEY` | OpenAI API 키 | 선택 | `sk-...` |
| `ANTHROPIC_API_KEY` | Anthropic API 키 | 선택 | `sk-ant-...` |
| `USE_OPENAI_EMBEDDING` | OpenAI 임베딩 사용 여부 | 선택 | `false` |

## 3. 환경변수 누락 시 처리 규칙
- **`EXAONE_RUNPOD_URL` 누락**: Runpod 관련 테스트(Task 2/6 중 Runpod 호출 검증)를 **FAIL**로 종료합니다.
- **DB 관련 변수 누락**: RDS/DB 점검(Task 5)을 **FAIL**로 종료합니다.
- **`QUERY_REWRITE_ENABLED=false`**: Runpod 호출을 강제하는 E2E 케이스는 **SKIP** 처리하고, health-only 검증으로 대체합니다.

## 4. E2E 표준값 (재현성/지연시간)
테스트 목적에 따라 `QUERY_REWRITE_TIMEOUT` 값을 조정하여 두 가지 모드로 수행합니다.

### Mode A: 연결성/폴백 검증
- **설정**: `QUERY_REWRITE_TIMEOUT=90` (ms)
- **목적**: 의도적으로 낮은 타임아웃을 설정하여, Runpod 응답 지연 시 시스템이 규칙 기반 폴백(Rule-based fallback)으로 정상 전환되는지 검증합니다.

### Mode B: 정상 호출 검증
- **설정**: `QUERY_REWRITE_TIMEOUT=2000` (ms)
- **목적**: 현실적인 타임아웃을 설정하여, Runpod(EXAONE)의 응답을 실제로 수신하고 이를 쿼리 재작성에 활용하는지 검증합니다.

## 5. 증거 수집 절차
모든 테스트 결과는 지정된 폴더에 저장하며, 다음 명령어를 사용하여 수집합니다.

### 5.1 증거 폴더 생성
```bash
mkdir -p .sisyphus/evidence/e2e-runpod
```

### 5.2 Backend 로그 저장
```bash
docker compose logs backend --no-color > .sisyphus/evidence/e2e-runpod/backend.log
```

### 5.3 Runpod Health 응답 저장
```bash
BASE_URL="${EXAONE_RUNPOD_URL%/}"; BASE_URL="${BASE_URL//\/v1/}"; curl -fsS "$BASE_URL/health" > .sisyphus/evidence/e2e-runpod/exaone-health.txt
```

### 5.4 /chat 응답 저장
```bash
curl -fsS http://localhost:8000/chat -H 'Content-Type: application/json' -d '{"message":"전자상거래 등에서의 소비자보호에 관한 법률 제17조에 따른 청약철회권 행사 가능 여부","chat_type":"dispute","debug":true,"top_k":5}' > .sisyphus/evidence/e2e-runpod/chat-response.json
```

## 6. 참조 파일
- `backend/app/common/config.py`: 설정 및 환경변수 로딩 로직
- `docker-compose.yml`: 로컬 서비스 구성
- `docker-compose.rds.yml`: RDS 및 외부 임베딩 연결 구성
- `backend/.env.example`: 환경변수 템플릿
