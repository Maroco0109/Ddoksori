# PR 1: Fast Path & Architecture Optimization

## 1. 개요
현재 MAS 아키텍처는 모든 쿼리가 `generation` 단계를 거친 후 무조건 `review` (Legal Review) 단계를 통과하도록 설계되어 있습니다. 이로 인해 다음 문제가 발생합니다.
- **일반 대화(General Chat)** 시에도 Legal Review를 수행하거나, 불필요한 래퍼를 통과하며 지연 발생.
- **고신뢰 검색(High Confidence)** 결과에 대해서도 Review를 수행하여 응답 속도 저하.

본 PR은 `generation` 이후의 흐름을 조건부로 변경하여, 불필요한 단계를 건너뛰는 **Fast Path**를 완성하는 것을 목표로 합니다.

## 2. 변경 대상 및 상세 계획

### 2.1. Routing Logic 추가 (`backend/app/orchestrator/routing.py`)
`generation` 단계 이후의 경로를 결정하는 새로운 라우팅 함수 `route_after_generation`을 추가합니다.

```python
def route_after_generation(state: ChatState_v2) -> Literal['review', 'output_guardrail']:
    """
    Generation 이후 라우팅 로직
    - 일반 대화(general) -> Review 생략
    - 검색 신뢰도가 매우 높음(>0.8) -> Review 생략
    - 분쟁(dispute)이고 신뢰도 낮음 -> Review 수행
    """
    query_analysis = state.get('query_analysis_v2') or {}
    query_type = query_analysis.get('query_type', 'dispute')
    
    # 1. 일반 대화는 Review 생략
    if query_type == 'general':
        return 'output_guardrail'
        
    # 2. 시스템 메타 질문도 Review 생략
    if query_type == 'system_meta':
        return 'output_guardrail'

    # 3. 검색 신뢰도 기반 Skip (선택 사항)
    # retrieval_report = state.get('retrieval_report_v2')
    # if retrieval_report and retrieval_report.get('relevance', 0) > 0.8:
    #     return 'output_guardrail'

    # 기본: Review 수행
    return 'review'
```

### 2.2. Graph 구조 변경 (`backend/app/orchestrator/graph.py`)
`generation` 노드에서 `review` 노드로 가는 고정 엣지를 제거하고, 조건부 엣지(Conditional Edge)를 추가합니다.

**변경 전:**
```python
graph.add_edge('generation', 'review')
```

**변경 후:**
```python
from .routing import route_after_generation

# ...

graph.add_conditional_edges(
    'generation',
    route_after_generation,
    {
        'review': 'review',
        'output_guardrail': 'output_guardrail'
    }
)
```

## 3. 테스트 계획
1. **일반 대화 테스트**: "안녕", "고마워" 입력 시 `review` 노드가 실행되지 않고 즉시 응답하는지 로그 확인.
2. **분쟁 상담 테스트**: "환불해줘" 입력 시 `generation` -> `review` 경로를 타는지 확인.
3. **시스템 질문 테스트**: "너는 누구니?" 입력 시 Fast Path로 동작하는지 확인.

## 4. 기대 효과
- 일반 대화 응답 속도 약 **0.3~0.5초 단축**.
- 불필요한 Review Agent 호출 비용 절감.
