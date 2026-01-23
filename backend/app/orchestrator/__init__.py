from .state import (
    ChatState,
    OnboardingInfo,
    QueryAnalysisResult,
    RetrievalResult,
    ReviewResult,
    RoutingMode,
    SlotStatus,
    ClaimEvidenceMapping,
    ReActStep,
    UnifiedState,
    create_initial_state,
)
from .checkpointer import (
    get_checkpointer,
    get_checkpointer_mode,
)

__all__ = [
    'ChatState',
    'OnboardingInfo',
    'QueryAnalysisResult',
    'RetrievalResult',
    'ReviewResult',
    'RoutingMode',
    'SlotStatus',
    'ClaimEvidenceMapping',
    'ReActStep',
    'UnifiedState',
    'create_initial_state',
    'get_checkpointer',
    'get_checkpointer_mode',
    'create_chat_graph',
    'create_unified_chat_graph',
    'get_compiled_graph',
    'get_graph',
    'get_graph_for_chat_type',
    'reset_graph',
]


_graph_functions = {
    'create_chat_graph',
    'create_unified_chat_graph',
    'get_compiled_graph',
    'get_graph',
    'get_graph_for_chat_type',
    'reset_graph',
}


def __getattr__(name):
    if name in _graph_functions:
        import importlib
        graph_module = importlib.import_module('.graph', __name__)
        return getattr(graph_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
