# Ambiguous Query Detection & Pre-Clarification

**작성일**: 2026-01-20
**PR**: feature/22-orchestrator
**관련 파일**:
- `backend/app/agents/query_analysis/agent.py`
- `backend/app/orchestrator/graph.py`
- `backend/app/orchestrator/nodes/clarify.py`
- `backend/app/orchestrator/state.py`
- `backend/scripts/testing/query_analysis/test_ambiguous_queries.py`

---

## 1. 문제 정의

### 증상
- 모호한 쿼리("요약", "도와줘" 등)가 `general` 또는 `dispute`로 잘못 분류
- RAG 검색이 무의미하게 진행되거나, 부적절한 응답 생성

### 원인 분석
```
[기존 흐름]
"요약" → _classify_query_type() → 'general' → NO_RETRIEVAL → guardrail만 실행
```

1. `_classify_query_type()`에서 모호한 쿼리를 별도 타입으로 분류하지 않음
2. 짧은 쿼리가 `general` 또는 기본값 `dispute`로 분류
3. `graph.py` 라우팅에서 `NEED_USER_CLARIFICATION` 모드 미처리

---

## 2. 해결 방안: Hybrid Ambiguous Detection

### 2.1 아키텍처

```
[쿼리 입력]
    │
    ▼
┌─────────────────────────────────────────┐
│ Layer 0: Intent Keyword Check           │
│ (환불, 반품, 교환 등 → NOT ambiguous)    │
└─────────────────────────────────────────┘
    │ 의도 키워드 없음
    ▼
┌─────────────────────────────────────────┐
│ Layer 0.5: Product Keyword Check        │
│ (노트북, 휴대폰 등 → NOT ambiguous)      │
└─────────────────────────────────────────┘
    │ 제품 키워드 없음
    ▼
┌─────────────────────────────────────────┐
│ Layer 1: Pattern Matching               │
│ (정규식 패턴 → ambiguous)               │
└─────────────────────────────────────────┘
    │ 패턴 미매칭 & len ≤ 30
    ▼
┌─────────────────────────────────────────┐
│ Layer 2: LLM Fallback                   │
│ (GPT-4o-mini로 판단)                    │
└─────────────────────────────────────────┘
```

### 2.2 구현 상세

#### Layer 0: 의도 키워드 체크 (Highest Priority)
```python
DISPUTE_INTENT_KEYWORDS = [
    "환불", "반품", "교환", "수리", "취소", "해지", "해약",
    "피해", "하자", "불량", "고장", "파손", "사기",
    "배송", "지연", "미배송", "오배송", "누락",
    "계약", "위약금", "보상", "배상", "청약철회",
    "카드", "결제", "청구", "문의", "상담",
]
```
- 의도 키워드가 있으면 **즉시 NOT ambiguous** 반환
- 예: "환불" (2글자지만 명확한 의도)

#### Layer 1: 패턴 매칭
```python
AMBIGUOUS_QUERY_PATTERNS = [
    r'^(요약|정리|알려줘|알려주세요|도와줘|도와주세요)$',
    r'^(이거|저거|그거)\s*(어떻게|뭐야|뭐예요|어떡해)\??$',
    r'^(뭐|뭘|어떻게|어떡해|무엇|무엇을)\s*해?\??$',
    r'^.{1,2}$',  # 1-2글자
]
```

#### Layer 2: LLM Fallback
```python
def _check_ambiguity_with_llm(query: str) -> bool:
    """30자 이하 쿼리에 대해 LLM으로 모호성 판단"""
    prompt = f"""다음 쿼리가 소비자 분쟁 상담에서 모호한지 판단해주세요.

쿼리: "{query}"

모호한 쿼리 기준:
- 구체적인 제품/서비스가 언급되지 않음
- 분쟁 유형(환불, 교환, 배송 등)이 불명확
- 단순 감정 표현이나 일반적 질문

"모호함" 또는 "구체적" 중 하나만 답변하세요."""
```

---

## 3. 라우팅 수정

### 3.1 문제
`graph.py`의 `_route_unified_after_query_analysis()`에서 `NEED_USER_CLARIFICATION` 모드를 체크하지 않음

### 3.2 수정
```python
# 수정 전
if mode == 'NEED_CLARIFICATION':
    return 'ask_clarification'

# 수정 후
if mode in ('NEED_CLARIFICATION', 'NEED_USER_CLARIFICATION'):
    logger.info(f"[Unified] {mode} mode, asking user")
    return 'ask_clarification'
```

### 3.3 모드 구분
| 모드 | 트리거 시점 | 용도 |
|------|-------------|------|
| `NEED_USER_CLARIFICATION` | 검색 전 (Pre-clarification) | 모호한 쿼리 |
| `NEED_CLARIFICATION` | 검색 후 (Post-retrieval) | 유사도 낮음/정보 부족 |

---

## 4. Pre-Clarification 템플릿

### 4.1 짧은 쿼리용 (≤5자)
```python
'ambiguous_short': "질문을 좀 더 구체적으로 해주시면 정확한 답변을 드릴 수 있어요.
                    어떤 제품/서비스에서 어떤 문제가 발생했는지 알려주세요."
```

### 4.2 일반 모호한 쿼리용 (>5자)
```python
'ambiguous_general': """좀 더 자세한 상황을 알려주시면 도움을 드릴 수 있어요.

예를 들어 알려주시면 좋은 정보:
• 어떤 제품이나 서비스에 대한 문의인가요?
• 어떤 문제가 발생했나요? (환불, 교환, 수리, 배송 등)
• 언제, 어디서 구매하셨나요?"""
```

---

## 5. State 스키마 변경

### query_type Literal 추가
```python
# state.py
query_type: Literal['dispute', 'general', 'law', 'criteria', 'system_meta', 'ambiguous']
```

---

## 6. 테스트 케이스

### 6.1 테스트 구조
```
test_ambiguous_queries.py
├── TestAmbiguousQueryPatternMatching (8 cases)
├── TestAmbiguousQueryLLMFallback (8 cases, @slow)
├── TestSpecificDisputeQueries (10 cases)
├── TestGeneralConversation (4 cases)
├── TestSystemMetaQueries (3 cases)
├── TestEdgeCases (6 cases)
└── TestIntegrationFullFlow (3 cases)
```

### 6.2 주요 테스트 시나리오

| 카테고리 | 입력 예시 | 예상 결과 |
|----------|-----------|-----------|
| 모호한 쿼리 (Pattern) | "요약", "도와줘", "?" | `ambiguous` → `NEED_USER_CLARIFICATION` |
| 모호한 쿼리 (LLM) | "이거 좀 봐줄 수 있어요?" | LLM 판단 |
| 구체적 분쟁 | "환불 거부당했어요" | `dispute` → `NEED_RAG` |
| 일반 대화 | "안녕하세요", "감사합니다" | `general` → `NO_RETRIEVAL` |
| 시스템 메타 | "너 이름이 뭐야?" | `system_meta` → `NO_RETRIEVAL` |
| Edge: 의도 키워드 | "환불" (2글자) | NOT ambiguous |

### 6.3 테스트 실행
```bash
# 빠른 테스트 (LLM 제외)
pytest backend/scripts/testing/query_analysis/test_ambiguous_queries.py -v -m "not slow"

# 전체 테스트 (LLM 포함)
pytest backend/scripts/testing/query_analysis/test_ambiguous_queries.py -v
```

---

## 7. API 테스트 결과

### 7.1 모호한 쿼리
```bash
curl -X POST http://localhost:8000/chat \
  -d '{"message": "요약", "session_id": "test", "chat_type": "dispute"}'
```
```json
{
  "answer": "질문을 좀 더 구체적으로 해주시면 정확한 답변을 드릴 수 있어요...",
  "chunks_used": 0,
  "clarifying_questions": ["제품/서비스 정보", "문제 유형"]
}
```

### 7.2 구체적 분쟁 쿼리
```bash
curl -X POST http://localhost:8000/chat \
  -d '{"message": "환불 거부당했어요", "session_id": "test", "chat_type": "dispute",
       "onboarding": {"purchase_item": "노트북", "dispute_details": "화면 불량"}}'
```
```json
{
  "answer": "## 1. 유사 사례 분석...",
  "chunks_used": 9,
  "domain": {"agency": "KCA", ...},
  "similar_cases": [...]
}
```

---

## 8. 향후 개선 사항

1. **LLM Fallback 최적화**: 캐싱 또는 더 경량화된 모델 사용
2. **패턴 확장**: 사용자 피드백 기반 패턴 추가
3. **다국어 지원**: 영어 쿼리 처리
4. **A/B 테스트**: Clarification 응답 효과 측정

---

## 9. 관련 로그 분석

### 정상 동작 로그 패턴
```
[QueryAnalysis] Query: '요약', chat_type: dispute
[QueryAnalysis] Ambiguous query detected: '요약' (pattern matched)
[QueryAnalysis] Query type: ambiguous
[QueryAnalysis] Mode: NEED_USER_CLARIFICATION
[Unified] NEED_USER_CLARIFICATION mode, asking user
[Clarify] Pre-clarification for ambiguous query: '요약...'
```

### 디버깅 체크포인트
1. `query_analysis` 로그에서 `query_type` 확인
2. `mode` 값이 `NEED_USER_CLARIFICATION`인지 확인
3. 라우팅이 `ask_clarification`으로 가는지 확인
