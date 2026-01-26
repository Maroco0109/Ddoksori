"""
[DEPRECATED] ReAct 패턴 모듈

Phase 7에서 MAS Supervisor로 전환됨.
이 모듈은 graph_legacy.py (롤백용)에서만 사용됩니다.

MAS_SUPERVISOR_ENABLED=false 설정 시에만 이 코드가 실행됩니다.
새로운 코드는 MAS Supervisor 그래프를 사용하세요.

이동된 백업: _archive/agents/react/
"""
import warnings

warnings.warn(
    "react 모듈은 deprecated 되었습니다. MAS Supervisor 그래프를 사용하세요.",
    DeprecationWarning,
    stacklevel=2
)

__all__ = [
    'react_think_node',
    'react_act_node',
    'ActionRegistry',
    'BaseAction',
    'ActionResult',
]


def __getattr__(name):
    if name == 'react_think_node':
        from .react_think import react_think_node
        return react_think_node
    elif name == 'react_act_node':
        from .react_act import react_act_node
        return react_act_node
    elif name == 'ActionRegistry':
        from .action_registry import ActionRegistry
        return ActionRegistry
    elif name == 'BaseAction':
        from .action_registry import BaseAction
        return BaseAction
    elif name == 'ActionResult':
        from .action_registry import ActionResult
        return ActionResult
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
