# PR-T2: Orchestrator 테스트 기대값 수정 (ReAct 전환 반영)

**작성일**: 2026-01-23  
**상태**: ✅ Completed (Implementation 완료, 3개 테스트 모두 통과)  
**목표**: Orchestrator 관련 실패 테스트 3개 해결

| 항목 | 상세 |
|------|------|
| **영향받는 테스트** | 3개 fail |
| **테스트 파일** | `test_pr3_graph.py` (1개), `test_react.py` (1개), `test_action_registry.py` (1개) |
| **예상 소요** | 0.25일 |
| **우선순위** | 🟡 높음 |

---

## 1. 배경 (Context)

### 아키텍처 전환
Orchestrator가 **Legacy linear pipeline**에서 **ReAct 기반 Unified Graph**로 전환되었습니다.
- **이전**: `query_analysis → retrieval → generation → review → END`
- **현재**: `query_analysis → react_think ⟷ react_act → generation → review → END`

### 현황
- 그래프 기본 모드: `ORCHESTRATOR_MODE=react` (환경변수 기본값, `backend/app/orchestrator/graph.py`)
- 미반영된 테스트: 
  1. `test_pr3_graph.py::test_graph_has_all_nodes` — `retrieval` 노드 존재 기대 (실제: `react_think`, `react_act`)
  2. `test_react.py::test_unknown_action_returns_error` (2개) — DB 연결 오류 발생 (예상: "알 수 없는 액션" 메시지)
  3. `test_action_registry.py::test_react_act_node_handles_unknown_action` — 동일 원인

---

## 2. 근본 원인 분석 (RCA)

### 원인 1: 그래프 노드 기대값 불일치
**파일**: `backend/scripts/testing/orchestrator/test_pr3_graph.py:32-45`

```python
# 현재 테스트 코드 (outdated)
expected_nodes = [
    'query_analysis',
    'retrieval',                # ❌ 더이상 존재하지 않음
    'generation',
    'review',
    'ask_clarification',
]
```

**실제 그래프 노드** (`backend/app/orchestrator/graph.py:340-403`):
```python
def create_react_chat_graph() -> StateGraph:
    """ReAct 패턴 그래프"""
    graph.add_node('query_analysis', ...)     # ✅
    graph.add_node('react_think', ...)        # ✅ 새로 추가
    graph.add_node('react_act', ...)          # ✅ 새로 추가
    graph.add_node('generation', ...)         # ✅
    graph.add_node('review', ...)             # ✅
    graph.add_node('ask_clarification', ...)  # ✅
```

### 원인 2: Unknown action 처리의 fallback 오류
**파일**: `backend/app/agents/react/react_act.py:81-108`

```python
def execute(self, state: ChatState) -> Dict:
    action = state.get('last_action')
    registered_actions = ActionRegistry.get_action_names()
    
    # 규칙 기반 액션 확인
    if action and action in registered_actions:
        return self._execute_rule_based(action, state, query, thought)
    
    # LLM 기반 시도...
    
    # ❌ 문제: fallback으로 무조건 search_all 실행
    default_action = 'search_all'  # Line 104
    return self._execute_rule_based(default_action, state, query, thought)
```

**테스트 환경에서의 연쇄 실패**:
1. 테스트에서 `last_action='invalid_action'` 설정
2. `HybridToolExecutor.execute()` → fallback으로 `search_all` 실행
3. `search_all` 액션이 실제 DB/Embedding API 호출 시도
4. PostgreSQL 또는 Embedding 서버 미실행 → 연결 오류 반환
5. 테스트 기대값 "알 수 없는 액션" ≠ 실제 결과 "DB 연결 오류"

**정상 동작 (ActionRegistry에 이미 존재)**:
`backend/app/agents/react/action_registry.py:240-250`

```python
# ActionRegistry.execute()가 이미 올바른 에러 메시지 제공
else:
    logger.warning(f"[ActionRegistry] Unknown action: {name}")
    return {
        'last_observation': f"알 수 없는 액션: {name}",
        'react_steps': [{
            'thought': thought,
            'action': name or 'unknown',
            'action_input': {},
            'observation': f"알 수 없는 액션: {name}",
        }],
    }
```

---

## 3. 해결 방안 (Solution)

### A. 그래프 노드 기대값 업데이트

**파일**: `backend/scripts/testing/orchestrator/test_pr3_graph.py`  
**라인**: 32-45  
**변경사항**:
- `retrieval` 제거
- `react_think`, `react_act` 추가

```python
def test_graph_has_all_nodes(self):
    graph = create_chat_graph()
    node_names = list(graph.nodes.keys())
    
    expected_nodes = [
        'query_analysis',
        'react_think',      # ✅ 변경: retrieval → react_think
        'react_act',        # ✅ 추가
        'generation',
        'review',
        'ask_clarification',
    ]
    
    for node in expected_nodes:
        assert node in node_names, f"Missing node: {node}"
```

### B. Unknown Action 처리 개선 (Production Logic)

**파일**: `backend/app/agents/react/react_act.py`  
**메서드**: `HybridToolExecutor.execute()`  
**라인**: 81-108  
**변경사항**: explicit unknown action 체크 추가 (fallback 전)

```python
def execute(self, state: ChatState) -> Dict:
    action = state.get('last_action')
    thought = state.get('last_thought') or ''
    query = _build_search_query(state)
    
    registered_actions = ActionRegistry.get_action_names()
    
    # [NEW] 1. Unknown action 조기 반환 (fallback 차단)
    # 명시적으로 요청된 action이 있으나 레지스트리에 없으면 즉시 에러 반환
    if action and action not in registered_actions:
        logger.warning(f"[HybridToolExecutor] Unknown action requested: {action}")
        # ActionRegistry가 올바른 에러 메시지 반환
        return ActionRegistry.execute(action, state, query, thought)
    
    # 2. 규칙 기반 액션 실행
    if action and action in registered_actions:
        logger.debug(f"[HybridToolExecutor] Rule-based execution: {action}")
        PROM_TOOL_USAGE.labels(tool_name=action, mode="rule").inc()
        return self._execute_rule_based(action, state, query, thought)
    
    # 3. LLM 기반 도구 선택 시도
    if self.use_llm_tools and self._ensure_tools_bound():
        logger.info("[HybridToolExecutor] Attempting LLM-based tool selection")
        try:
            return self._execute_with_tools(state, query, thought)
        except Exception as e:
            logger.warning(f"[HybridToolExecutor] LLM tool calling failed: {e}, falling back")
            PROM_TOOL_USAGE.labels(tool_name="fallback_to_search_all", mode="fallback").inc()
    
    # 4. 폴백: 기본 검색 (search_all) — action 없는 경우만
    default_action = 'search_all'
    logger.debug(f"[HybridToolExecutor] Fallback to rule-based: {default_action}")
    return self._execute_rule_based(default_action, state, query, thought)
```

**변경 원리**:
- **Before**: `if action in registry` → fallback to `search_all` (무조건)
- **After**: `if action and action NOT in registry` → return unknown action error (조기 차단)

---

## 4. 영향받는 테스트 및 기대 동작

### 테스트 1: Graph Node Assertion
**파일**: `backend/scripts/testing/orchestrator/test_pr3_graph.py::test_graph_has_all_nodes`
- **현재 상태**: ❌ FAIL
- **실패 원인**: `retrieval` 노드 없음 (예상 vs 실제)
- **수정 후**: ✅ PASS
- **변경**: `expected_nodes` 업데이트 만으로 해결

### 테스트 2-3: Unknown Action (2개)
**파일**: 
- `backend/scripts/testing/orchestrator/test_react.py::test_unknown_action_returns_error`
- `backend/scripts/testing/orchestrator/test_action_registry.py::test_react_act_node_handles_unknown_action`

- **현재 상태**: ❌ FAIL (DB/Embedding 연결 오류)
- **실패 원인**: `HybridToolExecutor` fallback → 실제 검색 시도 → 인프라 에러
- **수정 후**: ✅ PASS
- **변경**: `HybridToolExecutor.execute()`에서 explicit unknown action check 추가

---

## 5. 구현 체크리스트

### A. 테스트 업데이트
- [x] `backend/scripts/testing/orchestrator/test_pr3_graph.py` 수정
  - [x] Line 36-42: `expected_nodes` 갱신
  - [x] `retrieval` 제거, `react_think` / `react_act` 추가
  - [x] 테스트 실행 확인: `test_graph_has_all_nodes` ✅ PASSED

### B. 프로덕션 로직 수정
- [x] `backend/app/agents/react/react_act.py` 수정
  - [x] Line 81-108: `HybridToolExecutor.execute()` 메서드
  - [x] Unknown action 조기 반환 로직 추가 (Line 88-92)
  - [x] 기존 comment 번호 재정렬 (1, 2, 3, 4 유지)
  - [x] 테스트 실행 확인: unknown action 2개 ✅ PASSED

### C. 회귀 테스트
- [x] Orchestrator 전체 테스트 실행
  - [x] `conda run -n dsr pytest backend/scripts/testing/orchestrator/ -v`
  - [x] 회귀 없음: 248 passed (baseline 245보다 +3 개선) ✅

---

## 6. 완료 기준 (Acceptance Criteria)

| 기준 | 검증 방법 |
|------|----------|
| ✅ `test_graph_has_all_nodes` 통과 | `pytest test_pr3_graph.py::test_graph_has_all_nodes -v` |
| ✅ `test_unknown_action_returns_error` (1/2) 통과 | `pytest test_react.py::test_unknown_action_returns_error -v` |
| ✅ `test_react_act_node_handles_unknown_action` 통과 | `pytest test_action_registry.py::test_react_act_node_handles_unknown_action -v` |
| ✅ 회귀 없음 | `pytest orchestrator/ -v` → 기존 245개 테스트 모두 PASS |
| ✅ 3개 fail → 0개 fail | 전체 테스트 성공률: 93.8% → 94.3% (564 → 567 passed) |

---

## 7. 리스크 및 주의사항

### 영향 범위
- **변경 범위**: 매우 제한적 (2개 파일)
- **Production Impact**: 낮음 (이미 `ActionRegistry`가 정상 메시지 제공 중)
- **테스트 영향**: 긍정적 (불필요한 DB 호출 제거)

### 의도적 동작 변화
| 시나리오 | Before | After | 의도 |
|---------|--------|-------|------|
| 명시적 invalid action 요청 | Fallback to `search_all` → DB 오류 | Return "Unknown action" | Fail-fast: 오류를 조기에 드러냄 |
| No action (LLM selection) | LLM 기반 도구 선택 | LLM 기반 도구 선택 (동일) | 변화 없음 |
| 정상 action 요청 | 즉시 실행 | 즉시 실행 (동일) | 변화 없음 |

### 개선 효과
- **테스트 환경**: DB/Embedding 인프라 없이도 unknown action 테스트 가능
- **디버깅**: 잘못된 action이 즉시 caught되어 원인 파악 용이
- **안정성**: 불필요한 폴백 시도 제거로 성능/비용 절감

---

## 8. 참고 자료

### 코드 위치
- **Orchestrator Graph**: `backend/app/orchestrator/graph.py:340-403`
- **HybridToolExecutor**: `backend/app/agents/react/react_act.py:37-227`
- **ActionRegistry**: `backend/app/agents/react/action_registry.py:122-312`
- **테스트 파일**: 
  - `backend/scripts/testing/orchestrator/test_pr3_graph.py:32-45`
  - `backend/scripts/testing/orchestrator/test_react.py:338-350`
  - `backend/scripts/testing/orchestrator/test_action_registry.py:254-264`

### LangGraph 최고 사례 (참고)
- **Graph Introspection**: `compiled_graph.get_graph().nodes` → 노드 딕셔너리 접근
- **Test Robustness**: 노드 이름 하드코딩 대신 `graph.nodes` 검사 패턴 권장
- **Tool Error Handling**: `ToolNode(handle_tool_errors=True)` 패턴 고려

---

## 9. 다음 단계

### 즉시 실행 (이 PR 완료 후)
1. PR-T1 (Data Fixture) 완료 확인
2. PR-T2 구현 및 테스트 ✅ 3개 fail → 0개로 전환
3. PR-T3 (Agent Mock) 준비 (PR-T2의 import 패턴 참고)

### 중기 계획
- PR-T4, T5, T6, T7 순차 진행
- 테스트 성공률: 93.8% → 97%+ (목표)

### 선택적 개선 (Future)
- LangGraph `get_graph()` 기반 snapshot testing 도입
  - `compiled_graph.get_graph().draw_mermaid()` → 변경 감지
  - `to_json()` 스냅샷 기반 회귀 테스트
- Node metadata tagging으로 "이름 무관" 테스트 설계

---

## 10. 구현 결과 (Implementation Results)

### 실행 일시
**2026-01-23** (동일일 구현 완료)

### 변경 사항
1. **`backend/scripts/testing/orchestrator/test_pr3_graph.py`** (Line 36-42)
   - `'retrieval'` 제거
   - `'react_think'`, `'react_act'` 추가

2. **`backend/app/agents/react/react_act.py`** (Line 81-113)
   - Line 88-92: Unknown action 조기 반환 로직 추가
   - Comment 번호 재정렬 (1 → 2 → 3 → 4 순서 유지)

### 테스트 결과
```bash
# 3개 affected tests - 모두 PASSED
✅ test_pr3_graph.py::test_graph_has_all_nodes                          PASSED in 0.19s
✅ test_react.py::test_unknown_action_returns_error                     PASSED in 0.08s
✅ test_action_registry.py::test_react_act_node_handles_unknown_action PASSED in 0.06s

# Regression tests - 248 passed (baseline 245보다 개선)
✅ pytest backend/scripts/testing/orchestrator/ -v
   248 passed, 10 skipped, 2 errors (BGE-M3, unrelated) in 1.15s
```

### 완료 기준 달성
| 기준 | 상태 | 결과 |
|------|------|------|
| `test_graph_has_all_nodes` 통과 | ✅ | PASSED |
| `test_unknown_action_returns_error` 통과 | ✅ | PASSED |
| `test_react_act_node_handles_unknown_action` 통과 | ✅ | PASSED |
| 회귀 없음 | ✅ | 248 passed (baseline 245 → +3 개선) |
| 3개 fail → 0개 fail | ✅ | 100% 해결 |

### 영향 분석
- **Production Impact**: 낮음 (의도된 동작 변경: fail-fast for invalid actions)
- **Test Quality**: 개선 (DB 의존성 제거, 테스트 독립성 향상)
- **Code Maintainability**: 향상 (조기 반환으로 로직 명확화)

---

**최종 상태**: ✅ Completed & Verified
