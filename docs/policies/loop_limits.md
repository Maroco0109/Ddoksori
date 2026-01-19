# 루프 제한 정책 (Loop Limits Policy)

Orchestrator와 에이전트의 무한 루프 방지를 위한 제한 정책입니다.

## 제한 값 요약

| 제한 | 기본값 | 환경 변수 | 설명 |
|------|--------|-----------|------|
| `max_iterations` | 2 | `MAX_REACT_ITERATIONS` | ReAct 최대 반복 횟수 |
| `max_execution_time_ms` | 30000 | `MAX_EXECUTION_TIME_MS` | 총 실행 시간 제한 (ms) |
| `max_retry_count` | 2 | `MAX_RETRY_COUNT` | Review 실패 시 최대 재시도 |
| `max_search_rounds` | 3 | `MAX_SEARCH_ROUNDS` | 최대 검색 라운드 |
| `time_budget_per_round_ms` | 5000 | `TIME_BUDGET_PER_ROUND_MS` | 라운드당 시간 예산 |

## ReAct 루프 제한

### 반복 횟수 제한

```python
def react_think_node(state: ChatState_v2) -> dict:
    current = state.get('current_iteration', 0)
    max_iter = state.get('max_iterations', 2)
    
    if current >= max_iter:
        return {
            'should_continue': False,
            'last_thought': '최대 반복 횟수 도달. 답변 생성으로 이동.'
        }
    
    # ... 추론 로직 ...
    
    return {
        'current_iteration': current + 1,
        'should_continue': should_continue,
        # ...
    }
```

### 시간 예산 제한

```python
import time

def check_time_budget(state: ChatState_v2, start_time: float) -> bool:
    elapsed_ms = (time.time() - start_time) * 1000
    budget_remaining = state.get('budget_remaining_ms', 30000)
    
    return elapsed_ms < budget_remaining

def update_time_budget(state: ChatState_v2, elapsed_ms: float) -> dict:
    current_budget = state.get('budget_remaining_ms', 30000)
    return {'budget_remaining_ms': max(0, current_budget - elapsed_ms)}
```

## Review 재시도 제한

```python
def review_node(state: ChatState_v2) -> dict:
    retry_count = state.get('retry_count', 0)
    
    # 검토 로직 실행
    review_result = perform_review(state)
    
    if not review_result['passed']:
        if retry_count >= 2:
            # 최대 재시도 초과 - 안전 답변으로 대체
            return {
                'review_report_v2': review_result,
                'generation_output': create_safe_fallback_answer()
            }
        return {
            'review_report_v2': review_result,
            'retry_count': retry_count + 1
        }
    
    return {'review_report_v2': review_result}
```

## 검색 라운드 제한

```python
def retrieval_node(state: ChatState_v2) -> dict:
    search_round = state.get('search_round', 0)
    max_rounds = 3
    
    if search_round >= max_rounds:
        return {
            'retrieval_report_v2': {
                'relevance': 0.0,
                'coverage': [],
                'diversity': 0.0,
                'marginal_gain': 0.0,
                'total_chunks': 0,
                'sources_distribution': {}
            }
        }
    
    # 검색 실행
    result = perform_search(state)
    
    return {
        'retrieval': result['documents'],
        'retrieval_report_v2': result['report'],
        'search_round': search_round + 1
    }
```

## Marginal Gain 기반 조기 종료

검색 라운드 간 품질 향상이 미미하면 조기 종료합니다.

```python
def should_stop_searching(state: ChatState_v2) -> bool:
    history = state.get('retrieval_report_history', [])
    
    if len(history) < 2:
        return False
    
    last_gain = history[-1].get('marginal_gain', 0.0)
    
    # 품질 향상이 10% 미만이면 종료
    return last_gain < 0.1
```

## 타임아웃 처리

### 노드 단위 타임아웃

```python
import asyncio
from functools import wraps

def with_timeout(timeout_ms: int):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=timeout_ms / 1000
                )
            except asyncio.TimeoutError:
                return {'error': 'timeout', 'message': f'{func.__name__} 타임아웃'}
        return wrapper
    return decorator
```

### 전체 실행 타임아웃

```python
def run_graph_with_timeout(graph, state: ChatState_v2):
    max_time_ms = state.get('max_execution_time_ms', 30000)
    start_time = time.time()
    
    for event in graph.stream(state):
        elapsed_ms = (time.time() - start_time) * 1000
        
        if elapsed_ms > max_time_ms:
            return {
                'final_answer': '처리 시간이 초과되었습니다. 질문을 더 구체적으로 해주세요.',
                'error': 'timeout'
            }
        
        yield event
```

## 모니터링 및 로깅

### 제한 도달 로깅

```python
import logging

logger = logging.getLogger(__name__)

def log_limit_reached(limit_type: str, current: int, max_value: int):
    logger.warning(
        f"[LIMIT_REACHED] {limit_type}: {current}/{max_value}"
    )
```

### 메트릭 수집

| 메트릭 | 설명 |
|--------|------|
| `react_iterations_total` | ReAct 반복 총 횟수 |
| `review_retries_total` | Review 재시도 총 횟수 |
| `search_rounds_total` | 검색 라운드 총 횟수 |
| `timeout_occurrences` | 타임아웃 발생 횟수 |
| `avg_execution_time_ms` | 평균 실행 시간 |
