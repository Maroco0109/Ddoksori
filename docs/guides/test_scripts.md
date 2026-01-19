# 똑소리 테스트 스크립트 가이드

> 신규 개발자를 위한 테스트 실행 및 분석 가이드

**최종 업데이트**: 2026-01-19

---

## 목차

1. [개요](#1-개요)
2. [빠른 시작](#2-빠른-시작)
3. [환경 설정](#3-환경-설정)
4. [카테고리별 테스트 상세](#4-카테고리별-테스트-상세)
   - [4.1 API 테스트](#41-api-테스트)
   - [4.2 데이터 품질 테스트](#42-데이터-품질-테스트)
   - [4.3 통합 테스트](#43-통합-테스트)
   - [4.4 도메인 분류 테스트](#44-도메인-분류-테스트)
   - [4.5 쿼리 분석 테스트](#45-쿼리-분석-테스트)
   - [4.6 검색 엔진 테스트](#46-검색-엔진-테스트)
   - [4.7 오케스트레이터 테스트](#47-오케스트레이터-테스트)
5. [테스트 결과 분석 방법](#5-테스트-결과-분석-방법)
6. [공유 픽스처 가이드](#6-공유-픽스처-가이드)
7. [트러블슈팅](#7-트러블슈팅)

---

## 1. 개요

### 1.1 테스트 디렉토리 구조

```
backend/scripts/testing/
├── conftest.py                          # 전역 pytest 설정 및 공유 픽스처
├── api/                                 # API 엔드포인트 테스트
│   ├── test_api_endpoints.py            # /health, /search, /chat, /case 테스트
│   ├── test_api_error_handling.py       # 입력 검증, CORS 테스트
│   └── test_api_concurrent.py           # 동시성 및 성능 테스트
├── data/                                # 데이터 품질 테스트
│   └── test_data_quality.py             # DB 무결성, 스키마 검증
├── integration/                         # 엔드-투-엔드 통합 테스트
│   ├── test_api_integration.py          # 전체 RAG 워크플로우
│   └── test_docker_environment.py       # Docker Compose 스택 검증
├── domain/                              # 도메인 분류 테스트
│   └── test_domain_classifier.py        # 에이전시 라우팅 테스트
├── query_analysis/                      # 쿼리 분석 테스트
│   └── test_mode_classification.py      # 모드 분류 테스트
├── retrieval/                           # 검색 엔진 테스트
│   ├── test_rdb_retriever.py            # RDB 기반 검색
│   └── test_search_plan_retriever.py    # 검색 계획 수립
└── orchestrator/                        # 오케스트레이터 테스트
    ├── conftest.py                      # 오케스트레이터 전용 픽스처
    ├── test_orchestrator_e2e.py         # 엔드-투-엔드 그래프 실행
    ├── test_pr1_state.py                # ChatState 스키마 테스트
    ├── test_routing.py                  # 라우팅 및 예산 관리
    └── test_react.py                    # ReAct 패턴 테스트
```

### 1.2 테스트 카테고리 요약

| 카테고리 | 테스트 수 | 설명 | 실행 시간 |
|----------|-----------|------|-----------|
| API | 33개 | REST API 엔드포인트 기능 검증 | ~2분 |
| Data | 8개 | 데이터베이스 무결성 및 품질 | ~5초 |
| Integration | 16개 | 전체 시스템 통합 테스트 | ~5분 |
| Domain | 18개 | 에이전시 라우팅 분류 정확도 | ~3초 |
| Query Analysis | 10개 | 쿼리 모드 분류 검증 | ~5초 |
| Retrieval | 37개 | RDB 및 하이브리드 검색 | ~20초 |
| Orchestrator | 76개 | LangGraph 오케스트레이션 | ~30초 |
| **합계** | **198개** | | **~8분** |

---

## 2. 빠른 시작

### 2.1 편의 스크립트 사용

```bash
# 프로젝트 루트에서 실행
./backend/run_local_rag_tests.sh {카테고리}

# 사용 가능한 카테고리
./backend/run_local_rag_tests.sh api          # API 테스트만
./backend/run_local_rag_tests.sh integration  # 통합 테스트만
./backend/run_local_rag_tests.sh data         # 데이터 품질 테스트만
./backend/run_local_rag_tests.sh all          # 모든 테스트 실행
```

### 2.2 pytest 직접 실행

```bash
# Conda 환경 활성화 필수
conda activate dsr

# 전체 테스트
cd /home/maroco/LLM
PYTHONPATH=backend python -m pytest backend/scripts/testing/ -v

# 특정 디렉토리
python -m pytest backend/scripts/testing/api/ -v

# 특정 파일
python -m pytest backend/scripts/testing/api/test_api_endpoints.py -v

# 특정 클래스
python -m pytest backend/scripts/testing/api/test_api_endpoints.py::TestSearchEndpoint -v

# 특정 테스트 함수
python -m pytest backend/scripts/testing/api/test_api_endpoints.py::TestSearchEndpoint::test_search_basic_query -v
```

### 2.3 마커 필터링

```bash
# 느린 테스트 제외 (5초 이상 걸리는 테스트)
pytest backend/scripts/testing/ -v -m "not slow"

# 느린 테스트만 실행
pytest backend/scripts/testing/ -v -m slow

# Docker 테스트 제외
pytest backend/scripts/testing/ -v -m "not docker"

# 통합 테스트만
pytest backend/scripts/testing/ -v -m integration

# CI 환경에서 스킵되는 테스트 제외
pytest backend/scripts/testing/ -v -m "not skip_ci"

# 여러 마커 조합
pytest backend/scripts/testing/ -v -m "not slow and not docker"
```

### 2.4 추천 실행 순서

신규 개발자는 다음 순서로 테스트를 실행하는 것을 권장합니다:

```bash
# 1단계: 데이터 품질 확인 (빠름, DB 연결 테스트)
./backend/run_local_rag_tests.sh data

# 2단계: API 기능 확인 (서버 실행 필요)
./backend/run_local_rag_tests.sh api

# 3단계: 통합 테스트 (Docker 환경 필요)
./backend/run_local_rag_tests.sh integration

# 4단계: 전체 테스트
./backend/run_local_rag_tests.sh all
```

---

## 3. 환경 설정

### 3.1 필수 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `TEST_API_URL` | `http://localhost:8000` | Backend API 주소 |
| `DB_HOST` | `localhost` | PostgreSQL 호스트 |
| `DB_PORT` | `5432` | PostgreSQL 포트 |
| `DB_NAME` | `ddoksori` | 데이터베이스 이름 |
| `DB_USER` | `postgres` | DB 사용자명 |
| `DB_PASSWORD` | `postgres` | DB 비밀번호 |

### 3.2 선택 환경 변수

| 변수 | 설명 |
|------|------|
| `OPENAI_API_KEY` | LLM 테스트 활성화 (없으면 관련 테스트 skip) |
| `CHECKPOINTER_MODE` | `memory` (기본) 또는 `postgres` |
| `GOLDEN_SET_PATH` | 모드 분류 golden set 경로 |

### 3.3 Conda 환경

```bash
# 환경 활성화
conda activate dsr

# 또는 명시적 Python 경로 사용
/home/maroco/miniconda3/envs/dsr/bin/python -m pytest ...

# Windows에서 인코딩 설정
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1
```

### 3.4 서비스 요구사항

| 테스트 카테고리 | 필요 서비스 |
|----------------|-------------|
| API | Backend 서버 (포트 8000) |
| Data | PostgreSQL (포트 5432) |
| Integration | Docker Compose 전체 스택 |
| Domain | 없음 (유닛 테스트) |
| Query Analysis | 없음 (유닛 테스트) |
| Retrieval | PostgreSQL (포트 5432) |
| Orchestrator | 없음 (대부분 Mock 사용) |

```bash
# Backend 서버 시작
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# DB만 시작
docker-compose up -d db

# 전체 스택 시작
docker-compose up -d
```

---

## 4. 카테고리별 테스트 상세

### 4.1 API 테스트

**경로**: `backend/scripts/testing/api/`

#### 4.1.1 test_api_endpoints.py

API 엔드포인트의 기본 기능을 검증합니다.

##### TestRootEndpoint - 루트 엔드포인트 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 출력 |
|-------------|-----------|------|-----------|
| `test_root_returns_version` | 버전 정보 반환 | `GET /` | `{"version": "0.4.1", ...}` |
| `test_root_returns_retrieval_mode` | 검색 모드 포함 | `GET /` | `retrieval_mode: "hybrid"` 또는 `"dense"` |

**점검 사항**:
- API 서버가 정상 기동되었는지 확인
- 버전 정보가 올바르게 설정되었는지 확인

##### TestHealthEndpoint - 헬스체크 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 출력 |
|-------------|-----------|------|-----------|
| `test_health_check_healthy` | 상태 확인 | `GET /health` | `{"status": "healthy"}` |
| `test_health_check_performance` | 응답 시간 | `GET /health` | < 1초 |

**점검 사항**:
- DB 연결 상태
- 서비스 가용성

##### TestSearchEndpoint - 검색 엔드포인트 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 출력 |
|-------------|-----------|------|-----------|
| `test_search_basic_query` | 기본 검색 | `{"query": "환불 기준", "top_k": 5}` | 검색 결과 리스트 |
| `test_search_korean_text_encoding` | 한글 인코딩 | 한글 쿼리 | 한글이 깨지지 않은 결과 |
| `test_search_empty_results` | 빈 결과 처리 | 존재하지 않는 쿼리 | `{"results": []}` (200 OK) |
| `test_search_top_k_parameter` | top_k 적용 | `{"top_k": 3}` | 결과 개수 ≤ 3 |
| `test_search_chunk_type_filter` | 청크 타입 필터 | `{"chunk_types": ["facts"]}` | 해당 타입만 반환 |
| `test_search_agency_filter` | 에이전시 필터 | `{"agencies": ["KCA"]}` | KCA 데이터만 반환 |
| `test_search_performance_p95` | 성능 (p95) | 10회 반복 | p95 < 5초 |
| `test_search_result_schema` | 응답 스키마 | 검색 요청 | `chunk_id`, `similarity`, `content` 등 |
| `test_search_null_embeddings` | NULL 임베딩 | FTS 대체 쿼리 | FTS 결과 반환 |

**마커**: `@pytest.mark.slow` (성능 테스트)

**점검 사항**:
- 벡터 검색 정상 동작
- 필터링 로직 정확성
- 성능 SLA 준수 (5초 이내)

##### TestChatEndpoint - 채팅 엔드포인트 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 출력 |
|-------------|-----------|------|-----------|
| `test_chat_basic_query` | 기본 응답 생성 | `{"message": "환불 방법"}` | 답변 + 출처 |
| `test_chat_includes_disclaimer` | 면책 조항 | 채팅 요청 | 답변에 면책 문구 포함 |
| `test_chat_sources_valid` | 출처 유효성 | 채팅 요청 | sources 배열에 유효한 chunk_id |
| `test_chat_korean_text_preserved` | 한글 보존 | 한글 메시지 | 한글 답변 |
| `test_chat_performance_p95` | 성능 (p95) | 5회 반복 | p95 < 60초 |
| `test_chat_no_api_key` | API 키 누락 | 키 없이 요청 | 에러 또는 skip |
| `test_chat_stream_endpoint` | 스트리밍 | `POST /chat/stream` | SSE 스트림 |

**마커**: `@pytest.mark.slow`, `@pytest.mark.timeout(300)`

**환경 변수**: `OPENAI_API_KEY` 필요 (없으면 skip)

**점검 사항**:
- LLM 연동 정상 동작
- 출처 추적 정확성
- 스트리밍 응답 형식

##### TestCaseEndpoint - 케이스 조회 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 출력 |
|-------------|-----------|------|-----------|
| `test_get_case_valid_uid` | 유효한 UID | `GET /case/{valid_uid}` | 케이스 상세 정보 |
| `test_get_case_invalid_uid` | 무효한 UID | `GET /case/invalid` | 404 Not Found |
| `test_get_case_chunk_structure` | 청크 구조 | 유효한 UID | parent/child 청크 포함 |

**점검 사항**:
- 케이스 데이터 조회 정확성
- 청크 계층 구조 유지

---

#### 4.1.2 test_api_error_handling.py

입력 검증 및 CORS 설정을 테스트합니다.

##### TestInputValidation - 입력 검증 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 출력 |
|-------------|-----------|------|-----------|
| `test_search_missing_query` | 필수 필드 누락 | `{"top_k": 5}` | 422 Unprocessable Entity |
| `test_search_invalid_top_k_negative` | 음수 top_k | `{"query": "test", "top_k": -1}` | 422 |
| `test_search_invalid_top_k_zero` | top_k=0 | `{"query": "test", "top_k": 0}` | 422 |
| `test_search_malformed_json` | 잘못된 JSON | `{invalid json}` | 422 |
| `test_search_empty_string_query` | 빈 문자열 | `{"query": ""}` | 422 |

**점검 사항**:
- Pydantic 모델 검증 동작
- 적절한 에러 메시지 반환

##### TestCORS - CORS 설정 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 출력 |
|-------------|-----------|------|-----------|
| `test_cors_headers_present` | CORS 헤더 존재 | 일반 요청 | `Access-Control-*` 헤더 |
| `test_cors_allows_frontend_origin` | 프론트엔드 허용 | Origin: localhost:5173 | 허용 응답 |
| `test_cors_preflight_options` | Preflight 처리 | `OPTIONS /search` | 200 또는 204 |

**점검 사항**:
- 프론트엔드에서 API 호출 가능 여부
- 브라우저 보안 정책 준수

---

#### 4.1.3 test_api_concurrent.py

동시성 및 성능을 테스트합니다.

##### TestConcurrency - 동시성 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 출력 |
|-------------|-----------|------|-----------|
| `test_concurrent_search_requests` | 동시 요청 | 10개 병렬 요청 | 모두 성공 (200) |
| `test_no_connection_pool_exhaustion` | 연결 풀 | 50개 순차 요청 | 연결 풀 고갈 없음 |

**마커**: `@pytest.mark.slow`

**점검 사항**:
- 부하 상황에서의 안정성
- DB 연결 풀 설정 적절성

---

### 4.2 데이터 품질 테스트

**경로**: `backend/scripts/testing/data/`

#### 4.2.1 test_data_quality.py

데이터베이스 무결성과 데이터 품질을 검증합니다.

##### TestDataIntegrity - 데이터 무결성 테스트

| 테스트 함수 | 검증 항목 | SQL 쿼리 | 기대 결과 |
|-------------|-----------|----------|-----------|
| `test_all_chunks_have_valid_documents` | 고아 청크 없음 | `SELECT ... WHERE doc_id NOT IN documents` | 0개 |
| `test_chunk_totals_consistent` | chunk_total 일치 | `COUNT(*) vs chunk_total` | 차이 ≤ 10개 |
| `test_chunk_index_ranges_valid` | 인덱스 범위 | `chunk_index >= 0 AND < chunk_total` | 모두 유효 |

**점검 사항**:
- 외래 키 관계 유지
- 청크 인덱싱 정확성

##### TestDocumentStructure - 문서 구조 테스트

| 테스트 함수 | 검증 항목 | 검사 대상 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_counsel_cases_have_expected_chunk_types` | 상담사례 구조 | counsel 문서 | `problem`, `solution`, `full` 포함 |
| `test_dispute_cases_have_expected_chunk_types` | 분쟁사례 구조 | dispute 문서 | `facts`, `claims`, `mediation_outcome` 등 |

**점검 사항**:
- ETL 파이프라인 정확성
- 데이터 스키마 준수

##### TestSearchQuality - 검색 품질 테스트

| 테스트 함수 | 검증 항목 | 검사 대상 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_fts_search_returns_results` | FTS 검색 | `to_tsvector` 쿼리 | 결과 존재 |
| `test_embeddings_status_report` | 임베딩 상태 | embedding 컬럼 | NULL 비율 리포트 |
| `test_materialized_view_populated` | MV 데이터 | `mv_searchable_chunks` | 행 수 > 0 |

**점검 사항**:
- 검색 인덱스 상태
- 임베딩 생성 완료 여부

---

### 4.3 통합 테스트

**경로**: `backend/scripts/testing/integration/`

#### 4.3.1 test_api_integration.py

RAG 파이프라인 전체 흐름을 테스트합니다.

##### TestRAGWorkflow - RAG 워크플로우 테스트

| 테스트 함수 | 검증 항목 | 시나리오 | 기대 결과 |
|-------------|-----------|----------|-----------|
| `test_full_rag_pipeline` | 전체 흐름 | Search → Chat → Case | 모든 단계 성공 |
| `test_search_results_used_in_chat` | 검색-채팅 연동 | 검색 후 채팅 | 검색 결과가 답변에 반영 |
| `test_agency_recommendation` | 에이전시 추천 | 다양한 쿼리 | 올바른 기관 추천 |

**마커**: `@pytest.mark.integration`

**점검 사항**:
- 컴포넌트 간 연동 정확성
- 데이터 흐름 일관성

##### TestHybridRetrieval - 하이브리드 검색 테스트

| 테스트 함수 | 검증 항목 | 시나리오 | 기대 결과 |
|-------------|-----------|----------|-----------|
| `test_hybrid_mode_active` | 하이브리드 모드 | `/` 응답 확인 | `retrieval_mode: "hybrid"` |
| `test_fts_search_works_with_null_embeddings` | FTS 대체 | NULL 임베딩 쿼리 | FTS 결과 반환 |

---

#### 4.3.2 test_docker_environment.py

Docker Compose 환경을 검증합니다.

##### TestDockerStack - Docker 스택 테스트

| 테스트 함수 | 검증 항목 | 검사 대상 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_docker_compose_up` | 스택 시작 | docker-compose up | 성공 |
| `test_db_container_running` | DB 컨테이너 | ddoksori_db | 실행 중 |
| `test_db_container_healthy` | DB 헬스체크 | pg_isready | healthy |
| `test_pgvector_extension_installed` | pgvector | `\dx` | 확장 설치됨 |
| `test_schema_initialized` | 스키마 | documents, chunks, laws | 테이블 존재 |
| `test_backend_container_running` | Backend | ddoksori_backend | 실행 중 |
| `test_backend_db_connection` | DB 연결 | Backend → DB | 연결 성공 |
| `test_backend_api_available` | API 가용성 | `/health` | 응답 성공 |
| `test_cors_configuration` | CORS | 헤더 검사 | 설정됨 |
| `test_frontend_container_running` | Frontend | ddoksori_frontend | 실행 중 (선택) |
| `test_docker_compose_down` | 스택 종료 | docker-compose down | 성공 |

**마커**: `@pytest.mark.docker`

**점검 사항**:
- 컨테이너 오케스트레이션
- 서비스 간 네트워크 연결
- 볼륨 마운트 정상 동작

---

### 4.4 도메인 분류 테스트

**경로**: `backend/scripts/testing/domain/`

#### 4.4.1 test_domain_classifier.py

에이전시 라우팅 분류 정확도를 검증합니다.

**분류 결과 스키마**:
```python
ClassificationResult = {
    'agency': str,           # KCA, ECMC, KCDRC, FSS, K_MEDI, KOPICO
    'dispute_type': str,     # 1:N, 1:1, finance, medical, privacy, contents
    'is_restricted': bool,   # 제한 도메인 여부
    'confidence': float,     # 0.0 ~ 1.0
    'matched_keywords': List[str]
}
```

##### TestRestrictedDomains - 제한 도메인 테스트

| 테스트 함수 | 검증 항목 | 입력 쿼리 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_finance_domain_fss` | 금융 도메인 | "보험 환급", "펀드 손실" | `agency: "FSS"`, `is_restricted: True` |
| `test_medical_domain_k_medi` | 의료 도메인 | "진료비 환불", "의료사고" | `agency: "K_MEDI"`, `is_restricted: True` |
| `test_privacy_domain_kopico` | 개인정보 도메인 | "개인정보 유출", "정보주체" | `agency: "KOPICO"`, `is_restricted: True` |

**점검 사항**:
- 제한 도메인 정확히 식별
- 사용자에게 적절한 안내 제공

##### TestNonRestrictedDomains - 비제한 도메인 테스트

| 테스트 함수 | 검증 항목 | 입력 쿼리 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_content_domain_kcdrc` | 콘텐츠 도메인 | "OTT 해지", "게임 환불" | `agency: "KCDRC"` |
| `test_individual_domain_ecmc` | 개인간 거래 | "중고거래 사기" | `agency: "ECMC"` |
| `test_general_domain_kca` | 일반 분쟁 | "제품 불량", "환불 요청" | `agency: "KCA"` |

##### TestEqualPriorityForRestricted - 우선순위 테스트

| 테스트 함수 | 검증 항목 | 입력 쿼리 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_mixed_finance_and_medical_prefers_higher_score` | 복합 키워드 | 금융+의료 키워드 | 점수 높은 쪽 선택 |

##### TestClassificationResult - 결과 구조 테스트

| 테스트 함수 | 검증 항목 | 검사 대상 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_result_has_all_fields` | 필드 완성도 | ClassificationResult | 모든 필드 존재 |
| `test_confidence_is_bounded` | confidence 범위 | confidence 값 | 0.0 ≤ x ≤ 1.0 |

##### TestEdgeCases - 엣지 케이스 테스트

| 테스트 함수 | 검증 항목 | 입력 쿼리 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_empty_query_defaults_to_kca` | 빈 쿼리 | `""` | `agency: "KCA"` |
| `test_case_insensitive` | 대소문자 | "OTT", "ott" | 동일 결과 |

##### TestClassifyDomainFunction - 모듈 함수 테스트

| 테스트 함수 | 검증 항목 | 검사 대상 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_classify_domain_returns_result` | 함수 반환값 | `classify_domain()` | ClassificationResult |
| `test_classify_domain_singleton_behavior` | 싱글톤 | 여러 번 호출 | 동일 인스턴스 |

---

### 4.5 쿼리 분석 테스트

**경로**: `backend/scripts/testing/query_analysis/`

#### 4.5.1 test_mode_classification.py

쿼리 라우팅 모드 분류를 검증합니다.

**라우팅 모드**:
```python
RoutingMode = Literal[
    "NO_RETRIEVAL",           # 검색 불필요 (인사말, 잡담)
    "NEED_RAG",               # RAG 검색 필요
    "NEED_USER_CLARIFICATION" # 추가 정보 필요
]
```

##### TestModeClassification - 모드 분류 테스트

| 테스트 함수 | 검증 항목 | 입력 쿼리 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_no_retrieval_for_greetings` | 인사말 처리 | "안녕하세요" | `NO_RETRIEVAL` |
| `test_need_rag_for_disputes_with_info` | 분쟁 + 정보 | "노트북 환불하고 싶어요. 어제 샀어요." | `NEED_RAG` |
| `test_need_user_clarification_for_missing_info` | 정보 부족 | "환불하고 싶어요" (구매일/품목 없음) | `NEED_USER_CLARIFICATION` |
| `test_fast_path_promotion` | 빠른 경로 승격 | "청약철회란?" | `NO_RETRIEVAL` → `NEED_RAG` |
| `test_law_queries_need_rag` | 법령 쿼리 | "소비자기본법 17조" | `NEED_RAG` |
| `test_criteria_queries_need_rag` | 기준 쿼리 | "분쟁해결기준" | `NEED_RAG` |

##### TestGoldenSetAccuracy - Golden Set 정확도 테스트

| 테스트 함수 | 검증 항목 | 기준 | 기대 결과 |
|-------------|-----------|------|-----------|
| `test_schema_compliance` | 스키마 준수 | golden set 전체 | ≥ 99% |
| `test_mode_accuracy` | 모드 정확도 | golden set 전체 | ≥ 90% |

**Golden Set 경로**: `backend/data/golden_set/query_analysis/mode_classification.json`

##### TestQueryAnalysisOutput - 출력 스키마 테스트

| 테스트 함수 | 검증 항목 | 검사 대상 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_output_contains_both_schemas` | 버전 호환 | 출력 | `query_analysis` + `query_analysis_v2` |
| `test_v2_schema_has_required_fields` | v2 필드 | query_analysis_v2 | `mode`, `query_type`, `uncertainties` |

---

### 4.6 검색 엔진 테스트

**경로**: `backend/scripts/testing/retrieval/`

#### 4.6.1 test_rdb_retriever.py

RDB 기반 법령/기준 검색을 테스트합니다.

**SQL 파라미터 스키마**:
```python
sql_params_candidate = {
    # 기준 검색용
    'category': '용역(서비스)',
    'industry': '체육시설업',
    'item_group': '헬스장',
    'item': '헬스회원권',
    'dispute_type': '해지/환불',

    # 법령 검색용
    'law_name': '소비자기본법',
    'article_no': '17',
    'paragraph_no': '1',

    'enable_rdb_query': True,
    'preferred_tables': ['criteria_units'] | ['law_units'],
}
```

##### TestSqlParamsCandidate - 파라미터 스키마 테스트

| 테스트 함수 | 검증 항목 | 검사 대상 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_schema_has_criteria_fields` | 기준 필드 | sql_params | category, industry, item 등 |
| `test_schema_has_law_fields` | 법령 필드 | sql_params | law_name, article_no 등 |

##### TestSelectRetrieversWithRDB - 리트리버 선택 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 결과 |
|-------------|-----------|------|-----------|
| `test_rdb_added_when_enabled` | RDB 활성화 | `enable_rdb_query=True` | RDB 리트리버 포함 |
| `test_rdb_not_added_when_disabled` | RDB 비활성화 | `enable_rdb_query=False` | RDB 리트리버 미포함 |

##### TestCriteriaRDBRetriever - 기준 검색 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 결과 |
|-------------|-----------|------|-----------|
| `test_search_builds_correct_query` | SQL 생성 | 기준 파라미터 | 올바른 WHERE 조건 |
| `test_search_dispute_resolution_targets_table2_table3` | 테이블 대상 | 해지/환불 유형 | 별표2, 별표3 검색 |

##### TestLawRDBRetriever - 법령 검색 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 결과 |
|-------------|-----------|------|-----------|
| `test_search_normalizes_article_number` | 조문 정규화 | "제17조" | `article_no: "17"` |
| `test_get_article_with_children_orders_by_level` | 계층 정렬 | 조/항/호 | level 순 정렬 |

##### TestRDBRetriever - 통합 RDB 검색 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 결과 |
|-------------|-----------|------|-----------|
| `test_search_from_params_routes_to_criteria` | 기준 라우팅 | `preferred_tables: ["criteria_units"]` | CriteriaRDBRetriever 호출 |
| `test_search_from_params_routes_to_law` | 법령 라우팅 | `preferred_tables: ["law_units"]` | LawRDBRetriever 호출 |

##### TestExecuteRetrievalByTypeRDB - 실행 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 결과 |
|-------------|-----------|------|-----------|
| `test_rdb_type_uses_rdb_retriever` | RDB 타입 | `retriever_type: "rdb"` | RDBRetriever 사용 |
| `test_rdb_type_converts_results_to_standard_format` | 결과 변환 | RDB 결과 | `similarity: 1.0` |

---

#### 4.6.2 test_search_plan_retriever.py

검색 계획 수립 및 실행을 테스트합니다.

**리트리버 타입**:
```python
RETRIEVER_TYPES = [
    'hybrid',      # 하이브리드 (Dense + FTS)
    'structured',  # 구조화된 검색
    'dispute',     # 분쟁사례 전용
    'counsel',     # 상담사례 전용
    'law',         # 법령 전용
    'criteria',    # 기준 전용
    'rdb',         # RDB 직접 쿼리
]
```

##### TestRetrieverSelection - 리트리버 선택 테스트

| 테스트 함수 | 검증 항목 | 쿼리 타입 | 기대 리트리버 |
|-------------|-----------|-----------|---------------|
| `test_dispute_type_selects_hybrid_dispute_counsel` | 분쟁 타입 | `dispute` | [hybrid, dispute, counsel] |
| `test_law_type_selects_law_hybrid` | 법령 타입 | `law` | [law, hybrid] |
| `test_criteria_type_selects_criteria_hybrid` | 기준 타입 | `criteria` | [criteria, hybrid] |
| `test_general_type_selects_hybrid_only` | 일반 타입 | `general` | [hybrid] |
| `test_keywords_add_law_retriever` | 법률 키워드 | "소비자기본법" | law 추가 |
| `test_keywords_add_criteria_retriever` | 기준 키워드 | "분쟁해결기준" | criteria 추가 |

##### TestTopKDetermination - top_k 결정 테스트

| 테스트 함수 | 검증 항목 | 조건 | 기대 top_k |
|-------------|-----------|------|-----------|
| `test_dispute_default_top_k` | 분쟁 기본값 | 필터 없음 | 10 |
| `test_law_default_top_k` | 법령 기본값 | 필터 없음 | 5 |
| `test_with_filters_increases_top_k` | 필터 있음 | 필터 적용 | +5 증가 |
| `test_top_k_max_limit` | 최대값 | - | ≤ 20 |

##### TestRerankDecision - 리랭킹 결정 테스트

| 테스트 함수 | 검증 항목 | 쿼리 타입 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_dispute_should_rerank` | 분쟁 리랭킹 | `dispute` | `should_rerank: True` |
| `test_general_should_not_rerank` | 일반 리랭킹 | `general` | `should_rerank: False` |

##### TestSearchPlanNode - 검색 계획 노드 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 결과 |
|-------------|-----------|------|-----------|
| `test_creates_plan_with_dispute_analysis` | 분쟁 계획 | 분쟁 쿼리 분석 | 검색 계획 생성 |
| `test_round_increases_top_k` | 라운드 증가 | round > 1 | top_k: 15 |

##### TestMergeRetrievalResults - 결과 병합 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 결과 |
|-------------|-----------|------|-----------|
| `test_merges_disputes_from_multiple_results` | 다중 병합 | 여러 리트리버 결과 | 단일 리스트 |
| `test_deduplicates_by_chunk_id` | 중복 제거 | 중복 chunk_id | 유니크 결과 |

##### TestRetrievalNodeV2 - 검색 노드 v2 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 결과 |
|-------------|-----------|------|-----------|
| `test_no_retrieval_mode_returns_empty` | 검색 불필요 | `mode: NO_RETRIEVAL` | 빈 결과 |
| `test_uses_search_plan_retrievers` | 계획 활용 | search_plan | 계획된 리트리버 사용 |
| `test_handles_error_gracefully` | 에러 처리 | 검색 실패 | 빈 결과 + 로깅 |

---

### 4.7 오케스트레이터 테스트

**경로**: `backend/scripts/testing/orchestrator/`

#### 4.7.1 test_orchestrator_e2e.py

LangGraph 기반 오케스트레이터의 엔드-투-엔드 흐름을 테스트합니다.

##### TestOrchestratorGraphStructure - 그래프 구조 테스트

| 테스트 함수 | 검증 항목 | 검사 대상 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_graph_has_all_nodes` | 노드 존재 | 그래프 | query_analysis, retrieval, generation, review 등 |
| `test_graph_entry_point` | 진입점 | 그래프 | `query_analysis` |
| `test_graph_compiles_without_error` | 컴파일 | 그래프 | 에러 없음 |

##### TestHappyPathDispute - 정상 분쟁 경로 테스트

| 테스트 함수 | 검증 항목 | 시나리오 | 기대 결과 |
|-------------|-----------|----------|-----------|
| `test_full_sequence_with_mocks` | 전체 흐름 | Mock 리트리버/LLM | 모든 노드 통과 |

##### TestAskClarificationBranch - 명확화 요청 분기 테스트

| 테스트 함수 | 검증 항목 | 시나리오 | 기대 결과 |
|-------------|-----------|----------|-----------|
| `test_minimal_info_triggers_clarification` | 정보 부족 | 불완전한 분쟁 정보 | ask_clarification 노드로 분기 |

##### TestLowSimilarityBranch - 낮은 유사도 분기 테스트

| 테스트 함수 | 검증 항목 | 시나리오 | 기대 결과 |
|-------------|-----------|----------|-----------|
| `test_no_results_triggers_low_similarity` | 결과 없음 | 검색 결과 0개 | low_similarity_prompt 노드로 분기 |

##### TestGeneralConversation - 일반 대화 경로 테스트

| 테스트 함수 | 검증 항목 | 시나리오 | 기대 결과 |
|-------------|-----------|----------|-----------|
| `test_general_chat_path` | 일반 대화 | `chat_type: "general"` | 검색 없이 응답 생성 |

##### TestNodeTimings - 노드 타이밍 테스트

| 테스트 함수 | 검증 항목 | 검사 대상 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_node_timings_recorded` | 타이밍 기록 | `_node_timings` | 각 노드별 시간 |
| `test_timing_includes_start_end` | 시작/종료 | 타이밍 데이터 | start, end 타임스탬프 |

##### TestStateTransitions - 상태 전이 테스트

| 테스트 함수 | 검증 항목 | 검사 대상 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_initial_state_fields` | 초기 상태 | ChatState | 필수 필드 존재 |
| `test_query_analysis_updates_state` | 상태 업데이트 | query_analysis 후 | 분석 결과 반영 |

##### TestMultiTurnSession - 다중 턴 세션 테스트

| 테스트 함수 | 검증 항목 | 시나리오 | 기대 결과 |
|-------------|-----------|----------|-----------|
| `test_same_thread_id_shares_state` | 상태 공유 | 동일 thread_id | 이전 상태 유지 |
| `test_different_thread_ids_isolated` | 상태 격리 | 다른 thread_id | 독립적 상태 |

##### TestQueryRewritingIntegration - 쿼리 재작성 통합 테스트

| 테스트 함수 | 검증 항목 | 검사 대상 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_query_rewriting_fields_populated` | 재작성 필드 | 상태 | `rewritten_query`, `search_queries` |

---

#### 4.7.2 test_pr1_state.py

ChatState 스키마 및 Checkpointer를 테스트합니다.

**ChatState 구조**:
```python
ChatState = {
    'user_query': str,
    'chat_type': Literal['general', 'dispute'],
    'onboarding': OnboardingInfo,
    'query_analysis': QueryAnalysisResult,
    'retrieval_results': RetrievalResults,
    'generated_answer': str,
    'review_result': ReviewResult,
    '_node_timings': Dict[str, NodeTiming],
    ...
}

OnboardingInfo = {
    'purchase_date': str,
    'purchase_place': str,
    'purchase_platform': str,
    'purchase_item': str,
    'purchase_amount': str,
    'dispute_details': str,
}
```

##### TestChatState - 상태 생성 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 결과 |
|-------------|-----------|------|-----------|
| `test_create_initial_state_general` | 일반 상태 | `chat_type: "general"` | 기본 상태 생성 |
| `test_create_initial_state_dispute_with_onboarding` | 분쟁+온보딩 | onboarding 포함 | 온보딩 정보 반영 |
| `test_state_has_required_fields` | 필수 필드 | 상태 객체 | 모든 필드 존재 |

##### TestOnboardingInfo - 온보딩 정보 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 결과 |
|-------------|-----------|------|-----------|
| `test_partial_onboarding` | 부분 정보 | 일부 필드만 | 나머지 None |
| `test_full_onboarding` | 전체 정보 | 모든 필드 | 완전한 OnboardingInfo |

##### TestCheckpointer - 체크포인터 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 결과 |
|-------------|-----------|------|-----------|
| `test_default_mode_is_memory` | 기본 모드 | 환경변수 없음 | `memory` |
| `test_get_memory_checkpointer` | 메모리 반환 | `mode: "memory"` | MemorySaver |
| `test_postgres_not_implemented` | PostgreSQL | `mode: "postgres"` | NotImplementedError |
| `test_invalid_mode_raises_error` | 잘못된 모드 | `mode: "invalid"` | ValueError |

##### TestCheckpointerIntegration - 체크포인터 통합 테스트

| 테스트 함수 | 검증 항목 | 시나리오 | 기대 결과 |
|-------------|-----------|----------|-----------|
| `test_memory_saver_basic_operations` | 기본 동작 | 저장/조회 | 정상 동작 |
| `test_memory_saver_multi_turn` | 다중 턴 | 여러 번 업데이트 | 상태 유지 |

---

#### 4.7.3 test_routing.py

라우팅 로직 및 예산 관리를 테스트합니다.

**라우팅 함수**:
```python
# 쿼리 분석 후 라우팅
route_after_query_analysis(state) -> Literal['search_plan', 'generation', 'ask_clarification']

# 충분성 검사 후 라우팅
route_after_sufficiency(state) -> Literal['generation', 'search_plan', 'ask_clarification']

# 검토 후 라우팅
route_after_review(state) -> Literal['__end__', 'generation', 'retrieval']

# 빠른 경로 승격
should_promote_to_rag(query, mode) -> bool
```

##### TestFastPathPromotion - 빠른 경로 승격 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 결과 |
|-------------|-----------|------|-----------|
| `test_promote_no_retrieval_with_legal_keyword` | 법률 키워드 | "위법", "청약철회" | `True` |
| `test_no_promote_without_legal_keyword` | 일반 텍스트 | "안녕하세요" | `False` |

##### TestRouteAfterQueryAnalysis - 쿼리 분석 후 라우팅 테스트

| 테스트 함수 | 검증 항목 | 상태 | 기대 라우트 |
|-------------|-----------|------|-------------|
| `test_no_retrieval_goes_to_generation` | NO_RETRIEVAL | 인사말 분석 | `generation` |
| `test_need_rag_goes_to_search_plan` | NEED_RAG | 분쟁 분석 | `search_plan` |
| `test_need_clarification_goes_to_ask` | CLARIFICATION | 정보 부족 | `ask_clarification` |
| `test_fast_path_promotion` | 빠른 경로 | 법률 키워드 | `search_plan` |

##### TestRouteAfterSufficiency - 충분성 검사 후 라우팅 테스트

| 테스트 함수 | 검증 항목 | 상태 | 기대 라우트 |
|-------------|-----------|------|-------------|
| `test_high_relevance_no_missing_goes_to_generation` | 높은 유사도 | relevance ≥ 0.7 | `generation` |
| `test_low_relevance_after_search_asks_clarification` | 낮은 유사도 | relevance < 0.5 | `ask_clarification` |
| `test_medium_relevance_within_budget_continues_search` | 중간 유사도 | 예산 내 | `search_plan` |
| `test_budget_exhausted_goes_to_generation` | 예산 소진 | iterations ≥ max | `generation` |

##### TestRouteAfterReview - 검토 후 라우팅 테스트

| 테스트 함수 | 검증 항목 | 상태 | 기대 라우트 |
|-------------|-----------|------|-------------|
| `test_passed_ends` | 검토 통과 | `passed: True` | `__end__` |
| `test_failed_with_retries_regenerates` | 실패+재시도 | `passed: False`, retries < max | `generation` |
| `test_failed_max_retries_ends` | 최대 재시도 | retries ≥ max | `__end__` |
| `test_needs_more_evidence_retrieves` | 증거 부족 | `needs_evidence: True` | `retrieval` |

##### TestBudgetManagement - 예산 관리 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 결과 |
|-------------|-----------|------|-----------|
| `test_check_iteration_budget_within_limit` | 반복 예산 | iterations < max | `True` |
| `test_check_time_budget_exhausted` | 시간 예산 | elapsed > timeout | `False` |
| `test_increment_iteration` | 반복 증가 | 현재 상태 | iterations + 1 |

##### TestBudgetTracker - 예산 추적기 테스트

| 테스트 함수 | 검증 항목 | 검사 대상 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_initial_state_updates` | 초기 상태 | BudgetTracker | 초기화 완료 |
| `test_elapsed_time` | 경과 시간 | `get_elapsed()` | 정확한 시간 |

##### TestSearchPlanNode - 검색 계획 노드 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 결과 |
|-------------|-----------|------|-----------|
| `test_creates_plan_without_query_analysis` | 기본 계획 | 분석 없음 | 기본 검색 계획 |
| `test_creates_plan_for_dispute` | 분쟁 계획 | 분쟁 분석 | 분쟁 전용 계획 |

##### TestSufficiencyNode - 충분성 노드 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 결과 |
|-------------|-----------|------|-----------|
| `test_creates_report_without_retrieval` | 빈 검색 | 결과 없음 | `relevance: 0.0` |
| `test_creates_report_with_retrieval` | 검색 있음 | 결과 존재 | 유사도 계산 |

---

#### 4.7.4 test_react.py

ReAct (Reasoning + Acting) 패턴을 테스트합니다.

**ReAct 스텝 구조**:
```python
ReActStep = {
    'thought': str,        # 현재 상황 분석
    'action': str,         # 수행할 액션
    'action_input': dict,  # 액션 입력
    'observation': str,    # 액션 결과
}

# 지원 액션
ACTIONS = [
    'search_all',      # 전체 검색
    'search_law',      # 법령 검색
    'search_criteria', # 기준 검색
    'search_dispute',  # 분쟁 검색
    'search_counsel',  # 상담 검색
    'finish',          # 검색 종료
]
```

##### TestReActStepSchema - ReAct 스텝 스키마 테스트

| 테스트 함수 | 검증 항목 | 검사 대상 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_react_step_structure` | 스텝 구조 | ReActStep | 모든 필드 존재 |
| `test_initial_state_has_react_fields` | 초기 상태 | ChatState | react_steps, current_iteration |

##### TestReactThinkNode - Think 노드 테스트

| 테스트 함수 | 검증 항목 | 상태 | 기대 액션 |
|-------------|-----------|------|-----------|
| `test_first_iteration_no_data_returns_search_all` | 첫 반복 | 데이터 없음 | `search_all` |
| `test_max_iterations_reached_stops_loop` | 최대 반복 | iterations ≥ max | `finish` |
| `test_sufficient_data_stops_loop` | 충분한 데이터 | 검색 결과 충분 | `finish` |
| `test_low_similarity_triggers_additional_search` | 낮은 유사도 | similarity < threshold | 추가 검색 |
| `test_missing_criteria_triggers_criteria_search` | 기준 부족 | criteria 없음 | `search_criteria` |

##### TestAnalyzeRetrievalStatus - 검색 상태 분석 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 결과 |
|-------------|-----------|------|-----------|
| `test_empty_state_returns_all_false` | 빈 상태 | 결과 없음 | 모두 False |
| `test_with_data_returns_correct_status` | 데이터 있음 | 결과 존재 | 해당 항목 True |

##### TestCheckSimilarityThreshold - 유사도 임계값 테스트

| 테스트 함수 | 검증 항목 | 입력 | 기대 결과 |
|-------------|-----------|------|-----------|
| `test_above_threshold_returns_true` | 임계값 이상 | similarity ≥ 0.7 | `True` |
| `test_below_threshold_returns_false` | 임계값 미만 | similarity < 0.7 | `False` |

##### TestReactActNode - Act 노드 테스트

| 테스트 함수 | 검증 항목 | 액션 | 기대 결과 |
|-------------|-----------|------|-----------|
| `test_search_all_action` | 전체 검색 | `search_all` | 모든 리트리버 실행 |
| `test_search_criteria_action` | 기준 검색 | `search_criteria` | 기준 리트리버만 실행 |
| `test_unknown_action_returns_error` | 알 수 없는 액션 | `invalid_action` | 에러 observation |

##### TestReactGraphRouting - ReAct 그래프 라우팅 테스트

| 테스트 함수 | 검증 항목 | 현재 노드 | 기대 다음 노드 |
|-------------|-----------|-----------|----------------|
| `test_route_after_query_analysis_to_react_think` | 분석 후 | query_analysis | react_think |
| `test_route_after_react_think_to_act` | Think 후 (계속) | react_think | react_act |
| `test_route_after_react_think_to_generation` | Think 후 (종료) | react_think | generation |

##### TestReactGraphStructure - ReAct 그래프 구조 테스트

| 테스트 함수 | 검증 항목 | 검사 대상 | 기대 결과 |
|-------------|-----------|-----------|-----------|
| `test_react_graph_has_required_nodes` | 필수 노드 | 그래프 | react_think, react_act |
| `test_react_graph_entry_point` | 진입점 | 그래프 | query_analysis |

---

## 5. 테스트 결과 분석 방법

### 5.1 pytest 출력 해석

```bash
# 상세 출력
pytest backend/scripts/testing/ -v

# 출력 예시
backend/scripts/testing/api/test_api_endpoints.py::TestSearchEndpoint::test_search_basic_query PASSED  [ 10%]
backend/scripts/testing/api/test_api_endpoints.py::TestSearchEndpoint::test_search_korean_text_encoding PASSED  [ 20%]
backend/scripts/testing/api/test_api_endpoints.py::TestSearchEndpoint::test_search_performance_p95 FAILED  [ 30%]
```

**상태 코드**:
- `PASSED`: 테스트 성공
- `FAILED`: 테스트 실패 (assertion 에러)
- `ERROR`: 테스트 실행 중 예외 발생
- `SKIPPED`: 조건 미충족으로 스킵
- `XFAIL`: 예상된 실패 (expected failure)
- `XPASS`: 예상 실패했지만 성공

### 5.2 실패 테스트 디버깅

```bash
# 마지막 실패 테스트만 재실행
pytest backend/scripts/testing/ --lf

# 실패한 테스트 상세 출력
pytest backend/scripts/testing/ -v --tb=long

# 첫 번째 실패에서 중단
pytest backend/scripts/testing/ -x

# 실패 시 디버거 진입 (pdb)
pytest backend/scripts/testing/ --pdb

# 특정 테스트 디버깅
pytest backend/scripts/testing/api/test_api_endpoints.py::TestSearchEndpoint::test_search_performance_p95 -v --tb=long
```

### 5.3 커버리지 리포트

```bash
# 커버리지 측정
pip install pytest-cov

# HTML 리포트 생성
pytest backend/scripts/testing/ --cov=backend/app --cov-report=html

# 터미널 출력
pytest backend/scripts/testing/ --cov=backend/app --cov-report=term-missing
```

**리포트 해석**:
```
Name                              Stmts   Miss  Cover   Missing
---------------------------------------------------------------
backend/app/main.py                 150     20    87%   45-50, 120-130
backend/app/rag/retriever.py        200     10    95%   180-190
```

- `Stmts`: 총 코드 라인 수
- `Miss`: 실행되지 않은 라인 수
- `Cover`: 커버리지 비율
- `Missing`: 커버되지 않은 라인 번호

### 5.4 성능 지표 분석

**p95 기준**:
- 검색 API: < 5초
- 채팅 API: < 60초
- 헬스체크: < 1초

```python
# 테스트 코드 예시
def test_search_performance_p95(api_client, korean_test_queries):
    times = []
    for query in korean_test_queries[:10]:
        start = time.time()
        response = api_client.post("/search", json={"query": query, "top_k": 5})
        times.append(time.time() - start)

    p95 = np.percentile(times, 95)
    assert p95 < 5.0, f"p95 latency {p95:.2f}s exceeds 5s threshold"
```

### 5.5 JUnit XML 리포트 (CI용)

```bash
# JUnit XML 생성
pytest backend/scripts/testing/ --junitxml=test-results.xml

# CI에서 활용
# GitHub Actions, Jenkins 등에서 테스트 결과 시각화
```

---

## 6. 공유 픽스처 가이드

### 6.1 전역 conftest.py

**경로**: `backend/scripts/testing/conftest.py`

#### 세션 스코프 픽스처 (한 번만 초기화)

```python
@pytest.fixture(scope="session")
def api_client() -> httpx.Client:
    """API 테스트용 HTTP 클라이언트

    환경 변수:
        TEST_API_URL: API 서버 주소 (기본: http://localhost:8000)

    사용 예시:
        def test_search(api_client):
            response = api_client.post("/search", json={"query": "환불"})
            assert response.status_code == 200
    """

@pytest.fixture(scope="session")
def db_connection() -> psycopg.Connection:
    """PostgreSQL 데이터베이스 연결

    환경 변수:
        DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

    사용 예시:
        def test_query(db_connection):
            cursor = db_connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM documents")
    """
```

#### 함수 스코프 픽스처 (테스트마다 초기화)

```python
@pytest.fixture(scope="function")
def korean_test_queries() -> List[str]:
    """한글 테스트 쿼리 목록

    반환값:
        [
            "전자상거래 환불 규정이 어떻게 되나요?",
            "배송지연으로 인한 손해배상은?",
            "헬스장 회원권 환불 기준",
            ...
        ]
    """

@pytest.fixture(scope="function")
def sample_search_request() -> dict:
    """검색 요청 샘플

    반환값:
        {"query": "환불 기준", "top_k": 5}
    """

@pytest.fixture(scope="function")
def sample_chat_request() -> dict:
    """Chat 요청 샘플

    반환값:
        {"message": "전자상거래에서 환불을 받을 수 있나요?", "top_k": 5}
    """

@pytest.fixture(scope="function")
def api_key_available() -> bool:
    """OPENAI_API_KEY 존재 여부

    사용 예시:
        def test_chat(api_key_available):
            if not api_key_available:
                pytest.skip("OPENAI_API_KEY not set")
    """
```

#### Pytest 마커 등록

```python
# conftest.py에서 등록
def pytest_configure(config):
    config.addinivalue_line("markers", "slow: 장시간 실행 테스트")
    config.addinivalue_line("markers", "docker: Docker 필요 테스트")
    config.addinivalue_line("markers", "integration: 통합 테스트")
    config.addinivalue_line("markers", "skip_ci: CI 환경에서 스킵")
```

### 6.2 오케스트레이터 conftest.py

**경로**: `backend/scripts/testing/orchestrator/conftest.py`

#### 상태 픽스처

```python
@pytest.fixture
def sample_dispute_state() -> ChatState:
    """정보가 완전한 분쟁 상태

    반환값:
        ChatState(
            user_query="노트북 환불하고 싶어요",
            chat_type="dispute",
            onboarding={
                "purchase_date": "2026-01-10",
                "purchase_item": "노트북",
                "purchase_amount": "1,500,000원",
                ...
            }
        )
    """

@pytest.fixture
def sample_general_state() -> ChatState:
    """일반 대화 상태

    반환값:
        ChatState(
            user_query="안녕하세요",
            chat_type="general"
        )
    """

@pytest.fixture
def sample_minimal_info_state() -> ChatState:
    """정보가 부족한 분쟁 상태

    반환값:
        ChatState(
            user_query="환불하고 싶어요",
            chat_type="dispute",
            onboarding={}  # 정보 없음
        )
    """
```

#### 결과 Mock 픽스처

```python
@pytest.fixture
def mock_retrieval_result() -> Dict:
    """Mock 검색 결과

    반환값:
        {
            "disputes": [
                {"chunk_id": "d1", "content": "...", "similarity": 0.85},
                ...
            ],
            "counsels": [...],
            "laws": [...],
            "criteria": [...]
        }
    """

@pytest.fixture
def mock_query_analysis_result() -> Dict:
    """Mock 쿼리 분석 결과

    반환값:
        {
            "query_type": "dispute",
            "keywords": ["환불", "노트북"],
            "needs_clarification": False,
            "mode": "NEED_RAG"
        }
    """

@pytest.fixture
def mock_review_passed() -> Dict:
    """검증 통과 결과"""
    return {"passed": True, "issues": []}

@pytest.fixture
def mock_review_failed() -> Dict:
    """검증 실패 결과"""
    return {"passed": False, "issues": ["출처 불명확"]}
```

#### Mock 클래스

```python
class MockRetriever:
    """Mock 리트리버

    사용 예시:
        mock = MockRetriever(disputes=[...], counsels=[...])
        results = mock.search("환불", top_k=5)
    """
    def __init__(self, disputes=None, counsels=None, laws=None, criteria=None):
        self._results = {
            'disputes': disputes or [],
            'counsels': counsels or [],
            'laws': laws or [],
            'criteria': criteria or []
        }

    def search(self, query: str, top_k: int) -> List[Dict]:
        return self._results['disputes'] + self._results['counsels']

class MockLLM:
    """Mock LLM

    사용 예시:
        mock = MockLLM("테스트 응답입니다.")
        response = mock.invoke("프롬프트")
    """
    def __init__(self, response: str):
        self._response = response

    def invoke(self, prompt: str) -> str:
        return self._response
```

#### 그래프 픽스처

```python
@pytest.fixture
def uncompiled_graph():
    """컴파일되지 않은 LangGraph 그래프

    노드 수정이나 구조 테스트에 사용
    """

@pytest.fixture
def compiled_graph():
    """컴파일된 LangGraph 그래프 (MemorySaver 체크포인터 포함)

    실행 테스트에 사용
    """
```

---

## 7. 트러블슈팅

### 7.1 일반적인 오류와 해결책

| 오류 | 원인 | 해결책 |
|------|------|--------|
| `ModuleNotFoundError: No module named 'app'` | PYTHONPATH 미설정 | `PYTHONPATH=backend pytest ...` |
| `Connection refused (localhost:8000)` | Backend 서버 미실행 | `uvicorn app.main:app` 실행 |
| `Connection refused (localhost:5432)` | PostgreSQL 미실행 | `docker-compose up -d db` |
| `OPENAI_API_KEY not set` | API 키 미설정 | 환경 변수 설정 또는 테스트 skip |
| `UnicodeDecodeError` | 인코딩 문제 | `PYTHONIOENCODING=utf-8` 설정 |
| `pytest: command not found` | pytest 미설치 | `pip install pytest` |
| `docker: command not found` | Docker 미설치 | Docker Desktop 설치 |

### 7.2 환경별 이슈

#### Windows

```bash
# 인코딩 설정
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

# 또는 PowerShell
$env:PYTHONIOENCODING="utf-8"
$env:PYTHONUTF8="1"

# Conda 활성화
conda activate dsr
```

#### Linux/macOS

```bash
# 환경 변수 설정
export PYTHONIOENCODING=utf-8
export TEST_API_URL=http://localhost:8000

# Conda 활성화
conda activate dsr
```

#### CI 환경 (GitHub Actions)

```yaml
# .github/workflows/test.yml
jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg15
        env:
          POSTGRES_PASSWORD: postgres
        ports:
          - 5432:5432
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        env:
          DB_HOST: localhost
          TEST_API_URL: http://localhost:8000
        run: |
          pip install -r requirements.txt
          pytest backend/scripts/testing/ -v -m "not docker"
```

### 7.3 성능 문제

| 증상 | 원인 | 해결책 |
|------|------|--------|
| 테스트가 매우 느림 | slow 마커 테스트 포함 | `-m "not slow"` 옵션 |
| DB 쿼리 타임아웃 | 인덱스 누락 | `EXPLAIN ANALYZE`로 분석 |
| 메모리 부족 | 큰 데이터셋 로드 | 테스트 데이터 축소 |
| 동시성 테스트 실패 | 연결 풀 고갈 | `max_connections` 증가 |

### 7.4 디버깅 팁

```bash
# 특정 테스트만 실행 (빠른 피드백)
pytest backend/scripts/testing/api/test_api_endpoints.py::TestSearchEndpoint::test_search_basic_query -v

# print 문 출력 보기
pytest ... -s

# 로깅 출력
pytest ... --log-cli-level=DEBUG

# 실패한 테스트에서 변수 검사 (pdb)
pytest ... --pdb

# 테스트 함수 이름으로 필터링
pytest backend/scripts/testing/ -k "search"
pytest backend/scripts/testing/ -k "not slow"
pytest backend/scripts/testing/ -k "search and not performance"
```

---

## 부록: 테스트 파일 경로 요약

```
backend/scripts/testing/
├── conftest.py
├── api/
│   ├── test_api_endpoints.py
│   ├── test_api_error_handling.py
│   └── test_api_concurrent.py
├── data/
│   └── test_data_quality.py
├── integration/
│   ├── test_api_integration.py
│   └── test_docker_environment.py
├── domain/
│   └── test_domain_classifier.py
├── query_analysis/
│   └── test_mode_classification.py
├── retrieval/
│   ├── test_rdb_retriever.py
│   └── test_search_plan_retriever.py
└── orchestrator/
    ├── conftest.py
    ├── test_orchestrator_e2e.py
    ├── test_pr1_state.py
    ├── test_routing.py
    └── test_react.py
```

---

**문서 작성**: Claude Code
**최종 업데이트**: 2026-01-19
