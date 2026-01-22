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
