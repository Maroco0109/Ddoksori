# API 라우터 모듈

## 개요

FastAPI 엔드포인트를 기능별로 분리한 모듈입니다.
기존 674줄의 `main.py`를 모듈화하여 유지보수성을 향상시켰습니다.

## 모듈 구조

```
backend/app/api/
├── __init__.py      # 통합 API (라우터, 모델, 의존성 export)
├── models.py        # Pydantic 요청/응답 모델
├── dependencies.py  # FastAPI 의존성 (get_retriever 등)
├── health.py        # 헬스체크 라우터 (/, /health)
├── chat.py          # 채팅 라우터 (/chat, /chat/stream)
├── search.py        # 검색 라우터 (/search)
├── case.py          # 사례 조회 라우터 (/case/{uid})
├── metrics.py       # 메트릭스 라우터 (/metrics/*)
└── README.md        # 이 문서
```

## 사용법

### main.py에서 라우터 등록

```python
from app.api import (
    health_router,
    chat_router,
    search_router,
    case_router,
    metrics_router,
)

app = FastAPI()
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(search_router)
app.include_router(case_router)
app.include_router(metrics_router)
```

### 모델 import

```python
from app.api.models import ChatRequest, ChatResponse

# 또는 main.py 하위 호환성 사용
from app.main import ChatRequest, ChatResponse
```

### 의존성 import

```python
from app.api.dependencies import get_retriever, get_db_config
```

## 엔드포인트 목록

| 경로 | 메서드 | 라우터 | 설명 |
|------|--------|--------|------|
| `/` | GET | health | 서버 정보 |
| `/health` | GET | health | 헬스체크 |
| `/search` | POST | search | 벡터 검색 (LLM 없이) |
| `/chat` | POST | chat | 챗봇 응답 생성 |
| `/chat/stream` | POST | chat | SSE 스트리밍 응답 |
| `/case/{uid}` | GET | case | 사례 전체 조회 |
| `/metrics/agents` | GET | metrics | 에이전트 메트릭 |
| `/metrics/agents/summary` | GET | metrics | 메트릭 요약 |
| `/metrics/agents/recent` | GET | metrics | 최근 메트릭 |

## 모델 정의

### 요청 모델

| 모델 | 설명 |
|------|------|
| `ChatRequest` | 채팅 요청 (message, session_id, chat_type 등) |
| `SearchRequest` | 검색 요청 (query, top_k 등) |

### 응답 모델

| 모델 | 설명 |
|------|------|
| `ChatResponse` | 채팅 응답 (answer, sources, similar_cases 등) |
| `AgencyRecommendation` | 추천 기관 정보 |
| `CaseReference` | 사례 참조 정보 |
| `LawReference` | 법령 참조 정보 |
| `CriteriaReference` | 분쟁해결기준 참조 정보 |
| `SimilarCases` | 유사 사례 모음 |
| `NodeTiming` | 노드 실행 시간 (debug 모드) |

## 의존성

| 함수 | 설명 |
|------|------|
| `get_retriever()` | Retriever 인스턴스 (요청별 DB 연결 관리) |
| `get_db_config()` | DB 연결 설정 |
| `get_embed_api_url()` | 임베딩 API URL |
| `get_retrieval_mode()` | 검색 모드 ('hybrid' 또는 'dense') |

## 하위 호환성

기존 `main.py`에서 직접 import하던 코드가 있다면 계속 동작합니다:

```python
# 기존 방식 (계속 동작)
from app.main import ChatRequest, ChatResponse, get_retriever

# 새 방식 (권장)
from app.api.models import ChatRequest, ChatResponse
from app.api.dependencies import get_retriever
```

## 코드 통계

| 항목 | 이전 | 이후 |
|------|------|------|
| main.py 라인 수 | 674줄 | 132줄 |
| 모듈 수 | 1개 | 7개 |
| 유지보수성 | 낮음 | 높음 |
