# 테스트 가이드

## 개요

DDOKSORI 백엔드 테스트 스위트입니다.
pytest 기반으로 구성되어 있으며, 기능별로 디렉토리가 분리되어 있습니다.

## 디렉토리 구조

```
backend/scripts/testing/
├── conftest.py                      # 공통 Fixture (DB 연결, 시드 데이터 등)
├── README.md                        # 이 문서
├── test_mas_architecture.py         # MAS 아키텍처 통합 테스트
│
├── agents/                          # 에이전트 테스트
│   ├── __init__.py
│   └── test_base_agent.py
│
├── answer_generation/               # 답변 생성 테스트
│   ├── test_followup.py            # 후속 질문 생성
│   ├── test_formats.py             # 답변 포맷
│   └── test_specialist_agency.py   # 전문가 에이전시
│
├── auth/                            # 인증 테스트
│   └── test_jwt_dependencies.py    # JWT 의존성
│
├── data/                            # 데이터 테스트
│   ├── __init__.py
│   └── test_collect_training_data.py # 학습 데이터 수집
│
├── domain/                          # 도메인 분류 테스트
│   ├── __init__.py
│   ├── golden_set.py               # 도메인 분류 골든셋
│   └── test_domain_classifier.py   # 도메인 분류기
│
├── e2e/                             # E2E 통합 테스트
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_merged_graph.py        # 병합 그래프
│   ├── test_merged_retrieval.py    # 병합 검색
│   ├── test_mock_scenarios.py      # Mock 시나리오
│   ├── test_system_architecture.py # 시스템 아키텍처
│   ├── test_unified_retriever.py   # 통합 검색기
│   └── trace_logger.py             # 트레이스 로거
│
├── generation/                      # 생성 노드 테스트
│   ├── __init__.py
│   └── conftest.py
│
├── legal_review/                    # 법률 검토 테스트
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_enhanced_review.py     # 강화 검토
│   └── test_review_logic.py        # 검토 로직
│
├── llm/                             # LLM 테스트
│   └── verify_compatibility.py     # 호환성 검증
│
├── persistence/                     # 영속성 테스트
│   └── test_conversation_db_unit.py # 대화 DB 유닛
│
├── query_analysis/                  # 질의 분석 테스트
│   ├── conftest.py
│   ├── test_ambiguous_queries.py   # 모호한 질의
│   ├── test_classifier.py          # 분류기
│   ├── test_intent_cache.py        # 의도 캐시
│   ├── test_new_query_types.py     # 새 질의 타입
│   └── test_pr2_hybrid.py          # 하이브리드 분석
│
├── retrieval/                       # 검색 테스트
│   ├── __init__.py
│   ├── conftest.py
│   ├── embedding_server_simple.py  # 임베딩 서버 (테스트용)
│   └── test_embedding_client.py    # 임베딩 클라이언트
│
└── supervisor/                      # 슈퍼바이저 테스트
    ├── __init__.py
    ├── conftest.py
    ├── test_adaptive_rag.py              # 적응형 RAG
    ├── test_agent_communication.py       # 에이전트 통신
    ├── test_agent_metrics.py             # 에이전트 메트릭
    ├── test_agent_trace.py               # 에이전트 트레이스
    ├── test_answer_cache.py              # 답변 캐시
    ├── test_conversation_memory.py       # 대화 메모리
    ├── test_conversation_phase_manager.py # 대화 단계 관리자
    ├── test_e2e_queries.py               # E2E 질의
    ├── test_fast_path.py                 # 빠른 경로
    ├── test_followup_with_context.py     # 컨텍스트 후속 질문
    ├── test_mas_integration.py           # MAS 통합
    ├── test_mas_supervisor_graph.py      # MAS 슈퍼바이저 그래프
    ├── test_memory_db.py                 # 메모리 DB
    ├── test_progressive_disclosure.py    # 점진적 공개
    ├── test_retrieval_merge.py           # 검색 병합
    ├── test_retry_context.py             # 재시도 컨텍스트
    ├── test_selective_retrieval.py       # 선택적 검색
    ├── test_sufficiency.py               # 충분성 판단
    ├── test_supervisor.py                # 슈퍼바이저 기본
    ├── test_supervisor_state.py          # 슈퍼바이저 상태
    └── visualize_graph.py                # 그래프 시각화
```

## 테스트 실행

### 전체 테스트

```bash
PYTHONPATH=backend pytest
```

### 특정 디렉토리만

```bash
PYTHONPATH=backend pytest scripts/testing/supervisor/
PYTHONPATH=backend pytest scripts/testing/e2e/
PYTHONPATH=backend pytest scripts/testing/query_analysis/
```

### 특정 파일만

```bash
PYTHONPATH=backend pytest scripts/testing/supervisor/test_mas_supervisor_graph.py
PYTHONPATH=backend pytest scripts/testing/e2e/test_system_architecture.py
```

### 특정 테스트 함수만

```bash
PYTHONPATH=backend pytest scripts/testing/supervisor/test_mas_supervisor_graph.py::test_supervisor_graph_nodes
```

## 마커 사용

### 마커 목록

| 마커 | 설명 |
|------|------|
| `unit` | Unit 테스트 (DB 의존성 없음) |
| `integration` | 통합 테스트 (PostgreSQL 필요) |
| `api` | API 엔드포인트 테스트 |
| `supervisor` | 슈퍼바이저 테스트 (MAS Supervisor) |
| `agent` | 에이전트 테스트 |
| `retrieval` | 검색 테스트 |
| `generation` | 답변 생성 테스트 |
| `review` | 검토 테스트 |
| `slow` | 느린 테스트 (LLM 호출 등) |
| `docker` | Docker 환경 필요 (RUN_DOCKER_TESTS=1) |
| `skip_ci` | CI에서 스킵 (GITHUB_ACTIONS 환경) |
| `llm` | LLM API 호출 필요 (OPENAI_API_KEY) |
| `e2e` | E2E 통합 테스트 - 전체 워크플로우 검증 |
| `needs_db` | DB 연결 필요 |
| `needs_data` | 시드 데이터 필요 |
| `asyncio` | 비동기 테스트 (pytest-asyncio) |

### 마커로 필터링

```bash
# Unit 테스트만
PYTHONPATH=backend pytest -m unit

# Integration 테스트 제외
PYTHONPATH=backend pytest -m "not integration"

# Supervisor 테스트만
PYTHONPATH=backend pytest -m supervisor

# Docker 테스트만 (RUN_DOCKER_TESTS=1 필요)
RUN_DOCKER_TESTS=1 PYTHONPATH=backend pytest -m docker

# 느린 테스트 제외
PYTHONPATH=backend pytest -m "not slow"

# E2E 테스트만
PYTHONPATH=backend pytest -m e2e
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
    """Unit 테스트 - DB 불필요"""
    assert 1 + 1 == 2

@pytest.mark.integration
@pytest.mark.needs_db
def test_with_database(db_connection):
    """Integration 테스트 - DB 필요"""
    if db_connection is None:
        pytest.skip("DB 연결 불가")
    # ...

@pytest.mark.slow
@pytest.mark.llm
def test_llm_response():
    """느린 LLM 테스트"""
    # ...

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_full_workflow():
    """E2E 비동기 테스트"""
    # ...
```

### conftest.py 확장

디렉토리별 conftest.py에서 로컬 fixture 정의:

```python
# scripts/testing/retrieval/conftest.py
import pytest

@pytest.fixture
def mock_retriever():
    """Mock retriever for retrieval tests"""
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
- CLAUDE.md 테스트 섹션: `/path/to/project/CLAUDE.md`
