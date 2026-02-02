"""
똑소리 프로젝트 - LangGraph 상태 스키마 (하위 호환성 모듈)

[주의]
이 파일은 하위 호환성을 위해 유지됩니다.
새 코드에서는 app.supervisor.state 패키지를 직접 사용하세요.

권장 사용법:
    from app.supervisor.state import ChatState, create_initial_state
    from app.supervisor.state import QueryAnalysisResult, RetrievalResult

기존 코드 호환:
    from app.supervisor.state import ChatState  # 계속 동작함

모듈 구조:
    app/supervisor/state/
    ├── __init__.py      # 통합 API
    ├── session.py       # 세션 메타데이터
    ├── agent_results.py # 에이전트 결과
    ├── output.py        # 최종 출력
    ├── control.py       # 제어 플래그
    ├── supervisor.py    # MAS Supervisor 상태
    └── memory.py        # 메모리 관리
"""

# 새 state 패키지에서 모든 것을 re-export
from app.supervisor.state import (  # 세션; 에이전트 결과; 출력; 제어; ReAct (deprecated stubs); 메모리; Supervisor; 통합 상태
    AgentMessage,
    AgentResultsState,
    ChatState,
    ChatType,
    ClaimEvidenceMapping,
    CompactSummary,
    ControlState,
    ConversationTurn,
    MemoryState,
    OnboardingInfo,
    OutputState,
    QueryAnalysisResult,
    ReActState,
    ReActStep,
    RetrievalResult,
    ReviewResult,
    RoutingMode,
    SessionState,
    SupervisorState,
    UnifiedState,
    create_initial_state,
)

__all__ = [
    # 세션
    "OnboardingInfo",
    "ChatType",
    "SessionState",
    # 에이전트 결과
    "QueryAnalysisResult",
    "RetrievalResult",
    "ReviewResult",
    "AgentResultsState",
    # 출력
    "ClaimEvidenceMapping",
    "OutputState",
    # 제어
    "RoutingMode",
    "ControlState",
    # ReAct (deprecated)
    "ReActStep",
    "ReActState",
    # 메모리
    "ConversationTurn",
    "CompactSummary",
    "MemoryState",
    # Supervisor
    "SupervisorState",
    "AgentMessage",
    # 통합 상태
    "ChatState",
    "UnifiedState",
    "create_initial_state",
]
