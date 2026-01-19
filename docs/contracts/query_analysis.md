# QueryAnalysisResult_v2 스키마

질의 분석 에이전트의 출력 스키마입니다.

## 필드 정의

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `mode` | `RoutingMode` | O | 라우팅 모드 (`NO_RETRIEVAL`, `NEED_RAG`, `NEED_USER_CLARIFICATION`) |
| `draft` | `str \| null` | X | 임시 답변 초안 (NO_RETRIEVAL 모드에서 사용) |
| `uncertainties` | `list[str]` | X | 불확실한 부분 목록 |
| `need_evidence` | `bool` | X | 근거 필요 여부 |
| `required_slots` | `list[str]` | X | 필요한 정보 슬롯 목록 |
| `filters_candidate` | `dict` | X | 검색 필터 후보 |
| `sql_params_candidate` | `dict` | X | RDB 조회 파라미터 후보 |
| `query_type` | `Literal` | X | 질의 유형 (`dispute`, `general`, `law`, `criteria`) |
| `keywords` | `list[str]` | X | 추출된 키워드 |
| `agency_hint` | `str \| null` | X | 추천 기관 힌트 (`KCA`, `ECMC`, `KCDRC`) |
| `rewritten_query` | `str` | X | 재작성된 검색 쿼리 |
| `search_queries` | `list[str]` | X | 다중 검색 쿼리 목록 |

## RoutingMode 값

| 값 | 설명 | 후속 흐름 |
|----|------|----------|
| `NO_RETRIEVAL` | 검색 불필요 | Generator 직행 → Guardrail → User |
| `NEED_RAG` | RAG 필요 | SearchPlan → Retriever → Generator → Reviewer |
| `NEED_USER_CLARIFICATION` | 추가 정보 필요 | Generator(질문 생성) → User |

## 예시 Payload

### NEED_RAG 예시

```json
{
  "mode": "NEED_RAG",
  "draft": null,
  "uncertainties": ["구매 시점 불명확"],
  "need_evidence": true,
  "required_slots": ["purchase_item", "dispute_type"],
  "filters_candidate": {
    "doc_type": ["dispute", "counsel"],
    "agency": "KCA"
  },
  "sql_params_candidate": {
    "item_category": "가전제품",
    "dispute_type": "환불"
  },
  "query_type": "dispute",
  "keywords": ["노트북", "환불", "불량"],
  "agency_hint": "KCA",
  "rewritten_query": "노트북 불량 환불 분쟁조정 피해구제",
  "search_queries": [
    "노트북 불량 환불",
    "노트북 불량 환불 분쟁조정 피해구제",
    "노트북 환불 불량"
  ]
}
```

### NO_RETRIEVAL 예시

```json
{
  "mode": "NO_RETRIEVAL",
  "draft": "안녕하세요! 소비자 분쟁 상담 서비스입니다. 무엇을 도와드릴까요?",
  "uncertainties": [],
  "need_evidence": false,
  "required_slots": [],
  "filters_candidate": {},
  "sql_params_candidate": {},
  "query_type": "general",
  "keywords": [],
  "agency_hint": null,
  "rewritten_query": "",
  "search_queries": []
}
```

### NEED_USER_CLARIFICATION 예시

```json
{
  "mode": "NEED_USER_CLARIFICATION",
  "draft": null,
  "uncertainties": ["구매 품목 불명확", "분쟁 유형 불명확"],
  "need_evidence": false,
  "required_slots": ["purchase_item", "dispute_details"],
  "filters_candidate": {},
  "sql_params_candidate": {},
  "query_type": "dispute",
  "keywords": ["환불"],
  "agency_hint": null,
  "rewritten_query": "",
  "search_queries": []
}
```

## 검증

```python
from app.orchestrator import validate_query_analysis_result_v2

data = {"mode": "NEED_RAG", "query_type": "dispute", ...}
is_valid, errors = validate_query_analysis_result_v2(data)
```
