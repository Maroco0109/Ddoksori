"""
똑소리 프로젝트 - Supervisor 패키지

Phase 7: MAS Supervisor 기본 운영 그래프로 전환 완료.
- ReAct/Legacy 그래프 제거 (archived to _archive/)
- orchestrator → supervisor 모듈 이름 변경
"""
from .state import (
    ChatState,
    OnboardingInfo,
    QueryAnalysisResult,
    RetrievalResult,
    ReviewResult,
    RoutingMode,
    ClaimEvidenceMapping,
    ReActStep,  # [DEPRECATED] 하위 호환성 유지용
    UnifiedState,  # ChatState 별칭
    create_initial_state,
    # Phase 5: MAS Supervisor
    SupervisorState,
    AgentMessage,
    IndividualRetrievalResult,
)
from .checkpointer import (
    get_checkpointer,
    get_checkpointer_mode,
)

__all__ = [
    # State types
    'ChatState',
    'OnboardingInfo',
    'QueryAnalysisResult',
    'RetrievalResult',
    'ReviewResult',
    'RoutingMode',
    'ClaimEvidenceMapping',
    'ReActStep',  # [DEPRECATED]
    'UnifiedState',  # [DEPRECATED] ChatState 사용 권장
    'create_initial_state',

    # MAS Supervisor (Phase 5)
    'SupervisorState',
    'AgentMessage',
    'IndividualRetrievalResult',

    # Checkpointer
    'get_checkpointer',
    'get_checkpointer_mode',

    # Graph functions (lazy loaded)
    'create_chat_graph',  # [DEPRECATED]
    'create_unified_chat_graph',  # [DEPRECATED]
    'create_mas_supervisor_graph',  # 현재 운영
    'get_compiled_graph',  # [DEPRECATED]
    'get_graph',  # [DEPRECATED]
    'get_graph_for_chat_type',  # 권장 엔트리포인트
    'get_mas_supervisor_graph',  # 권장
    'reset_graph',
]


_graph_functions = {
    'create_chat_graph',
    'create_unified_chat_graph',
    'create_mas_supervisor_graph',
    'get_compiled_graph',
    'get_graph',
    'get_graph_for_chat_type',
    'get_mas_supervisor_graph',
    'reset_graph',
}


def __getattr__(name):
    if name in _graph_functions:
        import importlib
        graph_module = importlib.import_module('.graph', __name__)
        return getattr(graph_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
