# PR-C: MAS Supervisor 테스트 수정 가이드

> **Status**: 구현 완료 (2026-01-31)
> **대상 파일**: `test_mas_supervisor_graph.py`, `test_mas_integration.py`, `test_e2e_queries.py`
> **결과**: 35 passed, 2 skipped, 0 failed

---

## 1. 배경

Phase 5→7 마이그레이션(MAS v2 전환) 과정에서 코드가 변경되었으나 기존 테스트가 갱신되지 않아 20건의 테스트 실패가 발생. PR-A/B 구현 작업 중 발견됨.

### 1.1 실패 분포

| 테스트 파일 | 실패 수 | 주요 원인 |
|------------|---------|-----------|
| `test_mas_supervisor_graph.py` | 12건 | Import 경로 불일치 (RC1) |
| `test_mas_integration.py` | 8건 | Import 불일치 (RC1) + State 스키마 (RC2) |
| `test_e2e_queries.py` | (PR-C에서 추가 발견) | 위 3가지 모두 |

---

## 2. 근본 원인 분석 (Root Cause Analysis)

### 2.1 RC1: Import 경로 불일치 (12건)

**원인**: Phase 7에서 그래프 함수들이 `graph.py` → `graph_mas.py`로 이동됨.

| 함수 | 이전 위치 | 현재 위치 |
|------|----------|-----------|
| `create_mas_supervisor_graph()` | `graph.py` | `graph_mas.py` |
| `get_mas_supervisor_graph()` | `graph.py` | `graph_mas.py` |
| `reset_mas_graph()` | `graph.py` | `graph_mas.py` |
| `_route_mas_supervisor()` | `graph.py` | `graph_mas.py` |
| `_create_retrieval_agent_node()` | `graph.py` | `graph_mas.py` |

`graph.py`는 엔트리포인트 유틸리티(`get_graph_for_chat_type`, `_create_timed_node`, `summarize_node_output` 등)만 남김.

**수정**: 모든 `from app.supervisor.graph import X` → `from app.supervisor.graph_mas import X`

**참고**: `get_mas_supervisor_compiled_graph()`는 제거됨. 대신 `get_mas_supervisor_graph()`가 compiled graph를 직접 반환. 테스트에서 `reset_mas_graph()` → `get_mas_supervisor_graph()` 순서로 호출하도록 변경.

### 2.2 RC2: `_rule_based_fallback` State 스키마 불일치 (4건)

**원인**: `_rule_based_fallback()` 메서드가 v2에서 2-전략 라우팅으로 변경됨.

**기존 테스트가 가정한 동작** (Phase 5):
```python
# completed_tasks만으로 다음 단계 결정
if 'query_analysis' not in completed_tasks:
    return query_analyst
elif 'retrieval' not in completed_tasks:
    return retrieval_team
# ...
```

**실제 코드 동작** (Phase 7, `supervisor.py:592-613`):
```python
def _rule_based_fallback(self, state):
    mode = state.get("mode", "NEED_RAG")

    if mode in ("NO_RETRIEVAL", "RESTRICTED_DOMAIN"):
        return self._no_retrieval_decision(state)  # Fast Path

    return self._full_pipeline_decision(state)  # Full Pipeline
```

`_full_pipeline_decision()` (L361-431):
```python
def _full_pipeline_decision(self, state):
    retrieval = state.get("retrieval")       # ← 실제 필드 확인
    draft_answer = state.get("draft_answer") # ← completed_tasks가 아님!
    review = state.get("review")

    if mode == "NEED_RAG" and not retrieval:
        return {"target_agent": "retrieval_team"}
    if not draft_answer:
        return {"target_agent": "answer_drafter"}
    if not review:
        return {"target_agent": "legal_reviewer"}
    return {"action": "respond"}
```

**핵심 차이점**:
1. `query_analyst`는 `_rule_based_fallback`에서 반환하지 않음 (별도 `decide_next_action` 경로)
2. `completed_tasks`가 아닌 **실제 state 필드** (`retrieval`, `draft_answer`, `review`)를 기준으로 판단
3. `mode` 필드가 필수 (`NEED_RAG`가 기본값)

**수정**: 테스트 state에 `mode`, `retrieval`, `draft_answer`, `review` 필드 추가.

수정 전:
```python
state = {
    'user_query': '노트북 환불',
    'supervisor': {'completed_tasks': [], 'iteration_count': 0},
}
# 기대: query_analyst (X — 실제로는 retrieval_team)
```

수정 후:
```python
state = {
    'user_query': '노트북 환불',
    'mode': 'NEED_RAG',
    'supervisor': {'completed_tasks': [], 'iteration_count': 0},
}
# 기대: retrieval_team (O — NEED_RAG, retrieval 없음)
```

### 2.3 RC3: `retrieval_counsel` 제거 (4건)

**원인**: v2에서 Retrieval Agent가 4개 → 3개로 축소 (counsel 제거).

| v1 (Phase 5) | v2 (Phase 7) |
|--------------|--------------|
| law, criteria, case, **counsel** | law, criteria, case |
| Fan-out 4개 | Fan-out 3개 |
| `retrieval_counsel` 노드 존재 | 제거됨 |

**수정**:
- `required_nodes`에서 `retrieval_counsel` 제거
- `len(result) == 4` → `len(result) == 3`
- `assert 'retrieval_counsel' in node_names` 제거
- `memory_save` 노드 assertion 추가 (PR-B에서 추가됨)
- Entry point: `input_guardrail` → `cache_check` (PR-6 캐시 노드 추가됨)

---

## 3. 수정 상세

### 3.1 test_mas_supervisor_graph.py (C1, C2)

| 클래스 | 테스트 | 수정 내용 |
|--------|--------|-----------|
| `TestMasSupervisorGraphCreation` | `test_graph_has_all_required_nodes` | import 변경, `retrieval_counsel` → `memory_save` |
| `TestMasSupervisorGraphCreation` | `test_graph_compiles_successfully` | `get_mas_supervisor_compiled_graph` → `get_mas_supervisor_graph` + `reset_mas_graph` |
| `TestMasRouting` | 5개 전체 | import 변경 |
| `TestMasRouting` | `test_route_fan_out_returns_send_list` | `len == 4` → `len == 3`, counsel assertion 제거 |
| `TestRetrievalAgentNodes` | 2개 전체 | import 변경 |
| `TestGraphSingleton` | 2개 전체 | import 변경 |
| `TestSupervisorNodeIntegration` | 1개 | import 변경 |

### 3.2 test_mas_integration.py (C3-C7)

| 클래스 | 테스트 | 수정 내용 |
|--------|--------|-----------|
| `TestSupervisorRuleBasedFallback` | `test_rule_based_calls_query_analyst_first` | → `test_rule_based_calls_retrieval_first` (이름 변경 + state 재작성) |
| `TestSupervisorRuleBasedFallback` | `test_rule_based_calls_retrieval_after_analysis` | state에 `mode` + `retrieval` 필드 추가 |
| `TestSupervisorRuleBasedFallback` | `test_rule_based_calls_drafter_after_retrieval` | state에 `mode` + `retrieval` 필드 추가 |
| `TestSupervisorRuleBasedFallback` | `test_rule_based_calls_reviewer_after_draft` | state에 `mode` + `retrieval` + `draft_answer` 필드 추가 |
| `TestSupervisorRuleBasedFallback` | `test_rule_based_responds_after_all_complete` | state에 `mode` + `retrieval` + `draft_answer` + `review` 추가 |
| `TestSupervisorRuleBasedFallback` | (신규) `test_no_retrieval_mode_skips_retrieval` | NO_RETRIEVAL 모드 테스트 추가 |
| `TestMasGraphRouting` | 2개 | import 변경, fan-out 3개 |
| `TestGraphEndToEnd` | `test_graph_structure_is_valid` | import 변경, `memory_save` assertion 추가 |
| `TestGraphEndToEnd` | `test_compiled_graph_has_invoke_method` | `get_mas_supervisor_compiled_graph` → `get_mas_supervisor_graph` |

### 3.3 test_e2e_queries.py (C8)

| 클래스 | 테스트 | 수정 내용 |
|--------|--------|-----------|
| `TestE2EDisputeQueryFullFlow` | `test_supervisor_processes_dispute_query` | `query_analyst` → `retrieval_team`, `mode` 필드 추가 |
| `TestE2EDisputeQueryFullFlow` | `test_supervisor_calls_retrieval_after_query_analysis` | → `test_supervisor_calls_retrieval_when_no_retrieval_result` (이름 변경 + state 재작성) |
| `TestE2EDisputeQueryFullFlow` | `test_supervisor_calls_generation_after_retrieval` | `retrieval` 필드 추가 |
| `TestE2ERetrievalParallelExecution` | `test_retrieval_fan_out_returns_send_list` | import 변경, fan-out 3개, `query_analysis` fixture 추가 |
| `TestE2ERetrievalParallelExecution` | `test_retrieval_merge_combines_results` | counsels section 검증 제거, doc count 조정 |
| `TestE2EFallbackOnFailure` | `test_rule_based_fallback_order` | 전체 state 재작성 (4단계: retrieval → drafter → reviewer → respond) |
| `TestE2EMaxIterationProtection` | `test_iteration_count_below_limit_continues` | `query_analyst` → `retrieval_team`, `mode` 추가 |
| `TestMASGraphStructure` | `test_mas_graph_has_all_required_nodes` | import 변경, counsel 제거, memory_save 추가 |
| `TestMASGraphStructure` | `test_mas_graph_entry_point_is_input_guardrail` | → `test_mas_graph_entry_point_is_cache_check` (entry point 변경) |
| fixture | `mock_retrieval_results` | counsel 데이터 제거 (4개 → 3개 agent 결과) |

---

## 4. 향후 테스트 작성 가이드라인

### 4.1 import 규칙

```python
# ✅ 올바른 import (graph_mas에서 직접)
from app.supervisor.graph_mas import create_mas_supervisor_graph
from app.supervisor.graph_mas import _route_mas_supervisor

# ❌ 잘못된 import (graph.py에는 이 함수들이 없음)
from app.supervisor.graph import create_mas_supervisor_graph
```

### 4.2 _rule_based_fallback 테스트 state 필수 필드

```python
state = {
    'user_query': '질문',
    'mode': 'NEED_RAG',          # 필수! 기본값은 NEED_RAG
    'retrieval': None,            # None이면 retrieval_team 호출
    'draft_answer': None,         # None이면 answer_drafter 호출
    'review': None,               # None이면 legal_reviewer 호출
    'supervisor': {
        'completed_tasks': [],
        'iteration_count': 0,
    }
}
```

### 4.3 Fan-out 테스트

```python
# v2: 3개 Agent만 사용
assert len(result) == 3
target_nodes = [send.node for send in result]
assert 'retrieval_law' in target_nodes
assert 'retrieval_criteria' in target_nodes
assert 'retrieval_case' in target_nodes
# retrieval_counsel은 v2에서 제거됨
```

### 4.4 그래프 노드 검증

```python
required_nodes = [
    'cache_check',        # PR-6 캐시
    'cache_response',     # PR-6 캐시
    'input_guardrail',
    'output_guardrail',
    'supervisor',
    'query_analysis',
    'generation',
    'review',
    'retrieval_law',
    'retrieval_criteria',
    'retrieval_case',
    'retrieval_merge',
    'memory_save',        # PR-B 메모리
]
# Entry point: cache_check (NOT input_guardrail)
```

---

## 5. 테스트 실행 결과

### 5.1 최종 결과 (2026-01-31)

```bash
# test_mas_supervisor_graph.py
12 passed, 0 failed

# test_mas_integration.py
11 passed, 0 failed (6→7 증가, NO_RETRIEVAL 테스트 추가)

# test_e2e_queries.py
12 passed, 2 skipped, 0 failed
```

**총계**: 35 passed, 2 skipped, 0 failed

### 5.2 Skip된 테스트

| 테스트 | Marker | 사유 |
|--------|--------|------|
| `test_retrieval_law_processes_law_documents` | `@pytest.mark.skip(reason="LLM")` | LLM 호출 비용 |
| `test_full_mas_supervisor_flow` | `@pytest.mark.skip(reason="LLM")` | 전체 그래프 실행 비용 |

---

## 6. 교훈 및 권장사항

### 6.1 코드 변경 시 테스트 동기화 필수

- Phase 마이그레이션 시 **구조 변경 사항은 즉시 테스트에 반영**
- Import 경로, State 스키마, 노드 구조 등 주요 계약이 변경될 경우 **영향받는 테스트 파일을 사전 파악**

### 6.2 State 필드 의존성 명시

- `_rule_based_fallback` 같은 라우팅 로직은 **필수 필드와 기본값을 문서화**
- 테스트 작성 시 최소 필수 state 스키마를 template으로 제공

### 6.3 노드 구조 변경 시 영향 분석

- 노드 추가/제거 시 `required_nodes`, fan-out 개수, entry point 등 **구조 검증 테스트를 전수 검토**

### 6.4 CI/CD에서 테스트 실패 시 긴급 수정

- 20건 실패가 누적되기 전에 **PR 단위로 테스트 통과를 강제**
- `pytest -xvs` 옵션으로 첫 실패 시점부터 디버깅

---

## 7. 관련 문서

- `/path/to/project/backend/app/supervisor/README.md` - MAS v2 아키텍처
- `/path/to/project/docs/guides/supervisor/2026-01-28-pr-a-trace-logging-implementation.md` - PR-A 구현
- `/path/to/project/docs/guides/supervisor/2026-01-29-pr-b-memory-save-implementation.md` - PR-B 구현

---

## 8. 변경 이력

| 날짜 | 작성자 | 내용 |
|------|--------|------|
| 2026-01-31 | Claude (Sisyphus-Junior) | 초안 작성 |
