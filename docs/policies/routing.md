# 라우팅 정책 (Routing Policy)

Orchestrator의 라우팅 결정 규칙을 정의합니다.

## 라우팅 모드

| 모드 | 설명 | 트리거 조건 |
|------|------|-------------|
| `NO_RETRIEVAL` | 검색 없이 답변 | 일반 대화, 간단한 인사 |
| `NEED_RAG` | RAG 파이프라인 실행 | 법률/분쟁 관련 질문 |
| `NEED_USER_CLARIFICATION` | 추가 정보 요청 | 필수 정보 누락 |

## 라우팅 흐름도

```
User Input
    │
    ▼
┌─────────────────┐
│ Query Analysis  │
│   Agent         │
└────────┬────────┘
         │
         ▼
    ┌────────────┐
    │ mode 결정  │
    └────────────┘
         │
    ┌────┴────┬────────────┐
    │         │            │
    ▼         ▼            ▼
NO_RETRIEVAL  NEED_RAG    NEED_USER_CLARIFICATION
    │         │            │
    ▼         ▼            ▼
Generator   SearchPlan   Generator
    │       → Retriever   (질문 생성)
    │       → Generator       │
    │       → Reviewer        │
    ▼         │               ▼
Guardrail     ▼           User
    │       (필요시 루프)      │
    ▼         │           (재입력)
  User      User              │
                              ▼
                        Query Analysis
                          (재진입)
```

## Fast Path 승격 규칙

`NO_RETRIEVAL`로 분류되어도 아래 조건에서는 `NEED_RAG`로 **강제 승격**됩니다.

### 승격 트리거 키워드

| 카테고리 | 키워드 예시 |
|----------|-------------|
| 법적 판단 | 위법, 불법, 합법, 소송, 고소 |
| 권리/기간 | 청약철회, 환불기간, 보증기간, 제척기간 |
| 행동 권유 | ~해야 합니다, ~하세요, ~권합니다 |
| 분쟁 고위험 | 손해배상, 위약금, 분쟁조정, 피해구제 |

### 승격 로직

```python
def should_promote_to_rag(query: str, mode: RoutingMode) -> bool:
    if mode != 'NO_RETRIEVAL':
        return False
    
    HIGH_RISK_KEYWORDS = [
        '위법', '불법', '합법', '소송', '고소',
        '청약철회', '환불기간', '보증기간',
        '손해배상', '위약금', '분쟁조정'
    ]
    
    return any(kw in query for kw in HIGH_RISK_KEYWORDS)
```

## 라우팅 결정 로직

### Query Analysis → 후속 노드

```python
def route_after_query_analysis(state: ChatState_v2) -> str:
    qa = state.get('query_analysis_v2')
    
    if not qa:
        return 'react_think'  # 기본값
    
    mode = qa.get('mode', 'NEED_RAG')
    
    # Fast Path 승격 체크
    if should_promote_to_rag(state['user_query'], mode):
        mode = 'NEED_RAG'
    
    if mode == 'NO_RETRIEVAL':
        return 'generation'
    elif mode == 'NEED_USER_CLARIFICATION':
        return 'ask_clarification'
    else:  # NEED_RAG
        return 'react_think'
```

### Retrieval → 후속 노드

```python
def route_after_retrieval(state: ChatState_v2) -> str:
    report = state.get('retrieval_report_v2')
    
    if not report:
        return 'ask_clarification'
    
    relevance = report.get('relevance', 0.0)
    coverage = report.get('coverage', [])
    
    missing_slots = [s for s in coverage if s['status'] == 'missing']
    
    if relevance >= 0.7 and not missing_slots:
        return 'generation'
    elif relevance < 0.3:
        return 'ask_clarification'
    else:
        return 'generation'  # 부분 근거로 답변 시도
```

### Review → 후속 노드

```python
def route_after_review(state: ChatState_v2) -> str:
    review = state.get('review_report_v2')
    retry_count = state.get('retry_count', 0)
    
    if review and review.get('passed'):
        return '__end__'
    
    if retry_count < 2:
        if review and review.get('required_more_evidence'):
            return 'retrieval'  # 재검색
        return 'generation'  # 재생성
    
    return '__end__'  # 최대 재시도 초과
```

## 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `ENABLE_FAST_PATH_PROMOTION` | `true` | Fast Path 승격 활성화 |
| `SIMILARITY_THRESHOLD_HIGH` | `0.55` | 높은 유사도 임계값 |
| `SIMILARITY_THRESHOLD_LOW` | `0.30` | 낮은 유사도 임계값 |
