# 테스트 가이드

## 개요

DDOKSORI 백엔드 테스트 스위트입니다.
pytest 기반으로 구성되어 있으며, 기능별로 디렉토리가 분리되어 있습니다.

## 디렉토리 구조

```
backend/scripts/testing/
├── conftest.py          # 공통 Fixture (DB 연결, 시드 데이터 등)
├── README.md            # 이 문서
├── test_mas_architecture.py  # MAS 아키텍처 통합 테스트 (15개)
│
├── api/                 # API 엔드포인트 테스트
│   ├── test_api_endpoints.py     # 기본 API 테스트
│   ├── test_api_concurrent.py    # 동시성 테스트
│   └── test_api_error_handling.py # 에러 핸들링 테스트
│
├── orchestrator/        # 오케스트레이터 테스트
│   ├── test_pr3_graph.py         # 그래프 정의 테스트
│   ├── test_react.py             # ReAct 패턴 테스트 (Archived)
│   ├── test_routing_logic.py     # 라우팅 로직 테스트
│   └── ...
│
├── query_analysis/      # 질의분석 테스트
│   ├── test_pr2_hybrid.py        # 하이브리드 분석 테스트
│   └── test_ambiguous_queries.py # 모호한 질의 테스트
│
├── retrieval/           # 검색 테스트
│   └── test_embedding_client.py  # 임베딩 클라이언트 테스트
│
├── generation/          # 답변 생성 테스트
│   └── test_generation.py        # 생성 노드 테스트
│
├── legal_review/        # 검토 테스트
│   └── test_review_logic.py      # 검토 로직 테스트
│
├── domain/              # 도메인 분류 테스트
│   └── test_domain_classification.py
│
├── data/                # 데이터 관련 테스트
│   ├── test_data_quality.py      # 데이터 품질 테스트
│   └── test_collect_training_data.py # 학습 데이터 수집 테스트
│
├── integration/         # 통합 테스트
│   ├── test_api_integration.py   # API 통합 테스트
│   └── test_docker_environment.py # Docker 환경 테스트
│
├── llm/                 # LLM 관련 테스트
│   ├── test_exaone_health.py     # EXAONE 상태 테스트
│   └── test_tool_use_accuracy.py # 도구 사용 정확도 테스트
│
└── guardrail/           # 가드레일 테스트
```

## 테스트 실행

### 전체 테스트

```bash
conda run -n dsr pytest
```

### 특정 디렉토리만

```bash
conda run -n dsr pytest scripts/testing/orchestrator/
conda run -n dsr pytest scripts/testing/api/
```

### 특정 파일만

```bash
conda run -n dsr pytest scripts/testing/orchestrator/test_pr3_graph.py
```

### 특정 테스트 함수만

```bash
conda run -n dsr pytest scripts/testing/orchestrator/test_pr3_graph.py::test_graph_has_all_nodes
```

## 마커 사용

### 마커 목록

| 마커 | 설명 |
|------|------|
| `unit` | Unit 테스트 (DB 의존성 없음) |
| `integration` | 통합 테스트 (PostgreSQL 필요) |
| `api` | API 엔드포인트 테스트 |
| `orchestrator` | 오케스트레이터 테스트 |
| `slow` | 느린 테스트 (LLM 호출 등) |
| `docker` | Docker 환경 필요 |
| `skip_ci` | CI에서 스킵 |
| `llm` | LLM API 호출 필요 |
| `needs_db` | DB 연결 필요 |
| `needs_data` | 시드 데이터 필요 |

### 마커로 필터링

```bash
# Unit 테스트만
conda run -n dsr pytest -m unit

# Integration 테스트 제외
conda run -n dsr pytest -m "not integration"

# Docker 테스트만 (RUN_DOCKER_TESTS=1 필요)
RUN_DOCKER_TESTS=1 conda run -n dsr pytest -m docker

# 느린 테스트 제외
conda run -n dsr pytest -m "not slow"
```

## Fixture

### 주요 Fixture (conftest.py)

| Fixture | 설명 |
|---------|------|
| `db_connection` | PostgreSQL 연결 (세션 스코프) |
| `ensure_test_data` | 시드 데이터 보장 |
| `test_client` | FastAPI TestClient |

### DB Fixture 동작

- DB 연결 실패 시: `yield None` (Unit 테스트 계속 실행)
- 스키마 누락 시: 명확한 메시지와 함께 Skip
- 시드 데이터: 자동으로 최소 데이터 주입

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `RUN_DOCKER_TESTS` | `0` | `1`로 설정 시 Docker 테스트 실행 |
| `OPENAI_API_KEY` | - | LLM 테스트에 필요 |
| `CI` | - | CI 환경 감지 (Docker 테스트 스킵) |
| `GITHUB_ACTIONS` | - | GitHub Actions 환경 감지 |

## 테스트 작성 가이드

### 새 테스트 추가

1. 적절한 디렉토리 선택 (기능별)
2. `test_*.py` 파일명 사용
3. `Test*` 클래스 또는 `test_*` 함수 사용
4. 적절한 마커 추가

### 마커 추가 예시

```python
import pytest

@pytest.mark.unit
def test_simple_logic():
    \"\"\"Unit 테스트 - DB 불필요\"\"\"
    assert 1 + 1 == 2

@pytest.mark.integration
@pytest.mark.needs_db
def test_with_database(db_connection):
    \"\"\"Integration 테스트 - DB 필요\"\"\"
    if db_connection is None:
        pytest.skip("DB 연결 불가")
    # ...

@pytest.mark.slow
@pytest.mark.llm
def test_llm_response():
    \"\"\"느린 LLM 테스트\"\"\"
    # ...
```

### conftest.py 확장

디렉토리별 conftest.py에서 로컬 fixture 정의:

```python
# scripts/testing/retrieval/conftest.py
import pytest

@pytest.fixture
def mock_retriever():
    \"\"\"Mock retriever for retrieval tests\"\"\"
    return MockRetriever()
```

## 테스트 결과 해석

### 성공 예시

```
===== 248 passed, 10 skipped in 1.15s =====
```

### Skip 원인

- `SKIPPED [1] conftest.py:35: DB 연결 불가`
- `SKIPPED [1] conftest.py:45: 시드 데이터 없음`
- `SKIPPED [1] test_docker.py:10: RUN_DOCKER_TESTS=1 필요`

## 참고 문서

- pytest.ini: `backend/pytest.ini`
- CLAUDE.md 테스트 섹션: `/home/maroco/LLM/CLAUDE.md`
