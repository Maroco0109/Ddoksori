# 상태 스키마 모듈

**최종 수정**: 2026-07-05

## 개요

LangGraph MAS Supervisor(variant A/A-hub)에서 사용하는 상태(State) 스키마를 정의합니다.
기존 단일 파일(`state.py`)을 관심사별로 분리하여 유지보수성을 향상시켰습니다.

> `mode`(`RoutingMode`: NO_RETRIEVAL/NEED_RAG…)와 `routing_mode`(`"deterministic"` = A / `"llm"` = A-hub)는 다릅니다. 전자는 파이프라인 전략, 후자는 슈퍼바이저 라우팅 방식(M8)입니다. 변형 비교: [변형 시스템 아키텍처](../../../../docs/architecture/2026-07-05-variant-system-architecture.md).

## 모듈 구조

```
backend/app/supervisor/state/
├── __init__.py      # 통합 API (ChatState, create_initial_state, routing_mode 등)
├── session.py       # 세션 메타데이터 (OnboardingInfo, SessionState)
├── agent_results.py # 에이전트 결과 (QueryAnalysisResult, RetrievalResult, ReviewResult)
├── output.py        # 최종 출력 (ClaimEvidenceMapping, OutputState)
├── control.py       # 제어 플래그 (RoutingMode, ControlState)
├── supervisor.py    # Supervisor 의사결정 상태 (SupervisorState, AgentMessage)
├── memory.py        # 메모리 관리 (MemoryState)
└── README.md        # 이 문서
```

## 사용법

### 기본 사용 (권장)

```python
from app.supervisor.state import ChatState, create_initial_state

# 초기 상태 생성
state = create_initial_state(
    user_query="헬스장 환불 규정 알려줘",
    chat_type='dispute',
    onboarding={'purchase_item': '헬스장 회원권'}
)
```

### 개별 타입 사용

```python
from app.supervisor.state import (
    QueryAnalysisResult,
    RetrievalResult,
    ReviewResult,
    ReActStep,
)

# 타입 힌트에 사용
def process_query(result: QueryAnalysisResult) -> str:
    return result.get('rewritten_query', '')
```

### 하위 호환성

기존 코드는 수정 없이 계속 동작합니다:

```python
# 기존 방식 (계속 동작)
from app.supervisor.state import ChatState, RoutingMode

# 새 방식 (권장, 동일)
from app.supervisor.state import ChatState, RoutingMode
```

## 상태 그룹 설명

### 1. 세션 (session.py)

대화 세션의 메타데이터를 관리합니다.

| 타입 | 설명 |
|------|------|
| `OnboardingInfo` | 온보딩 폼 데이터 (분쟁 상담용) |
| `ChatType` | 대화 유형 ('dispute' \| 'general') |
| `SessionState` | 세션 메타데이터 상태 |

### 2. 에이전트 결과 (agent_results.py)

각 에이전트의 실행 결과를 저장합니다.

| 타입 | 설명 |
|------|------|
| `QueryAnalysisResult` | 질의분석 결과 (키워드, 의도, 검색쿼리) |
| `RetrievalResult` | 검색 결과 (4섹션 구조) |
| `ReviewResult` | 검토 결과 (통과 여부, 위반 사항) |
| `AgentResultsState` | 에이전트 결과 통합 상태 |

### 3. 출력 (output.py)

사용자에게 반환되는 최종 응답 데이터입니다.

| 타입 | 설명 |
|------|------|
| `ClaimEvidenceMapping` | 주장-근거 매핑 (할루시네이션 방지) |
| `OutputState` | 최종 출력 상태 |

### 4. 제어 (control.py)

그래프 실행 흐름을 제어합니다.

| 타입 | 설명 |
|------|------|
| `RoutingMode` | 라우팅 모드 (NO_RETRIEVAL, NEED_RAG, ...) |
| `ControlState` | 제어 플래그 상태 |

### 5. ReAct 타입 (ReActStep 등)

ReAct 패턴(추론-행동 사이클)을 지원합니다.

| 타입 | 설명 |
|------|------|
| `ReActStep` | 단일 Thought-Action-Observation 기록 |
| `ReActState` | ReAct 실행 상태 |

### 6. 메모리 (memory.py)

장기 대화를 위한 메모리 관리입니다.

| 타입 | 설명 |
|------|------|
| `ConversationTurn` | 대화 턴 기록 |
| `CompactSummary` | 대화 압축 요약 |
| `MemoryState` | 메모리 관리 상태 |

## ChatState 상태 흐름

```
User Query
    │
    ▼
┌─────────────────────────┐
│  SessionState 초기화     │  chat_type, onboarding, user_query
└─────────────────────────┘
    │
    ▼
┌─────────────────────────┐
│  query_analysis 노드     │  → AgentResultsState.query_analysis
└─────────────────────────┘
    │
    ▼ (mode에 따라 분기)
┌─────────────────────────┐
│  retrieval 노드          │  → AgentResultsState.retrieval
└─────────────────────────┘     OutputState.sources
    │
    ▼
┌─────────────────────────┐
│  generation 노드         │  → AgentResultsState.draft_answer
└─────────────────────────┘
    │
    ▼
┌─────────────────────────┐
│  review 노드             │  → AgentResultsState.review
└─────────────────────────┘     OutputState.final_answer
    │
    ▼
Response
```

## Reducer 사용

일부 필드는 `operator.add` reducer를 사용하여 값이 누적됩니다:

```python
# sources: 여러 노드에서 추가한 출처가 누적
sources: Annotated[List[Dict], operator.add]

# react_steps: ReAct 사이클 기록이 누적
react_steps: Annotated[List[ReActStep], operator.add]
```

## 테스트

```bash
# 상태 모듈 import 테스트
conda run -n dsr python -c "
from app.supervisor.state import ChatState, create_initial_state
state = create_initial_state('테스트 질문')
print(f'chat_type: {state[\"chat_type\"]}')
print(f'user_query: {state[\"user_query\"]}')
print('✅ Import 테스트 통과')
"

# 하위 호환성 테스트
conda run -n dsr python -c "
from app.supervisor.state import ChatState, RoutingMode
print('✅ 하위 호환성 테스트 통과')
"
```
