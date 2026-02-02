# 로깅 모듈

## 개요

똑소리 프로젝트의 통합 로깅 시스템입니다. 표준 Python 로거와 RAG 파이프라인 전용 구조화 로거를 모두 제공합니다.

## 모듈 구조

```
backend/app/common/logging/
├── __init__.py      # 통합 API (get_logger, get_rag_logger 등)
├── config.py        # 로깅 설정 (레벨, 포맷)
├── handlers.py      # 커스텀 핸들러 (콘솔, 파일)
├── rag_logger.py    # RAG 파이프라인 전용 구조화 로거
└── README.md        # 이 문서
```

## 사용법

### 표준 로거

```python
from app.common.logging import get_logger

# 모듈별 로거 생성
logger = get_logger(__name__)

# 로그 기록
logger.debug("디버그 메시지")
logger.info("정보 메시지")
logger.warning("경고 메시지")
logger.error("오류 메시지", exc_info=True)
logger.critical("치명적 오류 메시지")
```

### RAG 구조화 로거

```python
from app.common.logging import get_rag_logger
import time

# 로거 인스턴스 가져오기
rag_logger = get_rag_logger()

# 로그 엔트리 생성
start_time = time.time()
entry = rag_logger.create_entry(query="환불 문의")

# 입력 기록
rag_logger.log_input(entry, message="환불 가능한가요?", chat_type="dispute")

# 검색 결과 기록
rag_logger.log_retrieval(
    entry,
    mode="hybrid",
    top_k=5,
    embedding_time_ms=50.0,
    search_time_ms=120.0,
    chunks=[{"chunk_id": "c1", "similarity": 0.85, ...}]
)

# LLM 호출 기록
rag_logger.log_llm(
    entry,
    model="gpt-4o-mini",
    system_prompt="...",
    user_prompt="...",
    response_time_ms=1500.0
)

# 마무리 및 저장
rag_logger.finalize(entry, start_time)
filepath = rag_logger.save(entry)
```

### 로깅 시스템 초기화

애플리케이션 시작 시 한 번 호출:

```python
from app.common.logging import setup_logging

# 기본 설정
setup_logging()

# 커스텀 설정
setup_logging(
    level="DEBUG",           # 로그 레벨
    use_color=True,          # 컬러 콘솔 출력
    log_to_file=True,        # 파일 출력 활성화
    log_dir="logs/app"       # 로그 파일 디렉토리
)
```

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `LOG_LEVEL` | `INFO` | 로그 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `RAG_LOG_ENABLED` | `true` | RAG 구조화 로그 활성화 여부 |
| `RAG_LOG_DIR` | `logs/rag` | RAG 로그 저장 디렉토리 |

## 로그 출력 형식

### 콘솔 출력 (컬러)

```
2026-01-24 11:51:12 | INFO     | 처리를 시작합니다
2026-01-24 11:51:12 | WARNING  | 주의가 필요합니다
2026-01-24 11:51:12 | ERROR    | 오류가 발생했습니다
```

### RAG JSON 로그

`logs/rag/YYYY-MM-DD/HHMMSS_{request_id}.json` 형식으로 저장:

```json
{
  "request_id": "9a241ead-...",
  "timestamp": "2026-01-24T11:51:12.123456",
  "query": "환불 가능한가요?",
  "retrieval": {
    "mode": "hybrid",
    "top_k": 5,
    "chunks": [...]
  },
  "llm": {
    "model": "gpt-4o-mini",
    "response_time_ms": 1500.0
  },
  "total_time_ms": 2350.5
}
```

## 하위 호환성

기존 코드에서 사용하던 import 경로는 계속 동작합니다:

```python
# 기존 방식 (계속 동작)
from app.common.logger import get_rag_logger

# 새 방식 (권장)
from app.common.logging import get_logger, get_rag_logger
```

## 로거 레벨 오버라이드

외부 라이브러리의 로그 레벨은 자동으로 조정됩니다:

- `httpx`, `httpcore`: WARNING
- `openai`, `anthropic`: WARNING
- `langchain`: WARNING
- `langgraph`: INFO
