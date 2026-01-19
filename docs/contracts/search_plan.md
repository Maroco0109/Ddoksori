# SearchPlan 스키마

Orchestrator가 Retrieval Agent에게 전달하는 검색 계획입니다.

## 필드 정의

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `retrievers` | `list[str]` | X | 사용할 retriever 목록 |
| `top_k` | `int` | X | 검색 결과 상위 K개 |
| `rerank` | `bool` | X | Reranking 적용 여부 |
| `rounds_budget` | `int` | X | 최대 검색 라운드 수 |
| `time_budget_ms` | `int` | X | 시간 예산 (밀리초) |
| `filters` | `dict` | X | 검색 필터 |
| `query` | `str` | X | 검색 쿼리 |

## Retriever 종류

| Retriever | 설명 | 용도 |
|-----------|------|------|
| `dense` | Dense Vector 검색 (KURE-v1) | 의미 기반 유사도 |
| `sparse` | Sparse Vector 검색 (BGE-M3) | 키워드 매칭 |
| `hybrid` | Dense + Sparse + RRF | 종합 검색 |
| `law` | 법령 계층 검색 | 조/항/호 탐색 |
| `criteria` | 분쟁조정기준 검색 | 품목별 기준 |

## 예시 Payload

### 기본 하이브리드 검색

```json
{
  "retrievers": ["hybrid"],
  "top_k": 10,
  "rerank": true,
  "rounds_budget": 2,
  "time_budget_ms": 5000,
  "filters": {
    "doc_type": ["dispute", "counsel"]
  },
  "query": "노트북 불량 환불 분쟁조정"
}
```

### 법령 특화 검색

```json
{
  "retrievers": ["law", "dense"],
  "top_k": 15,
  "rerank": true,
  "rounds_budget": 1,
  "time_budget_ms": 3000,
  "filters": {
    "doc_type": ["law"],
    "law_name": "전자상거래법"
  },
  "query": "청약철회 기간 조항"
}
```

### 분쟁조정기준 검색

```json
{
  "retrievers": ["criteria", "hybrid"],
  "top_k": 5,
  "rerank": false,
  "rounds_budget": 1,
  "time_budget_ms": 2000,
  "filters": {
    "doc_type": ["criteria"],
    "item_category": "가전제품"
  },
  "query": "노트북 수리 보상 기준"
}
```

## 검증

```python
from app.orchestrator import validate_search_plan

data = {"retrievers": ["hybrid"], "top_k": 10, ...}
is_valid, errors = validate_search_plan(data)
```
