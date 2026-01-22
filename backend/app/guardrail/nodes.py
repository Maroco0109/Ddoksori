"""
Guardrail LangGraph Nodes
"""

import logging
from typing import Dict, Any

from .moderation import check_input, check_output, MODERATION_ENABLED

logger = logging.getLogger(__name__)


def input_guardrail_node(state: Dict[str, Any]) -> Dict[str, Any]:
    if not MODERATION_ENABLED:
        return {}

    user_query = state.get('user_query', '')
    if not user_query:
        messages = state.get('messages', [])
        if messages:
            last_msg = messages[-1]
            if hasattr(last_msg, 'content'):
                user_query = last_msg.content
            elif isinstance(last_msg, dict):
                user_query = last_msg.get('content', '')

    if not user_query:
        return {}

    result = check_input(user_query)
    
    if result['blocked']:
        logger.warning(f"[InputGuardrail] Blocked input: {user_query[:50]}...")
        return {
            'guardrail_blocked': True,
            'guardrail_type': 'input',
            'final_answer': result['fallback_message'],
        }

    return {'guardrail_blocked': False}


def output_guardrail_node(state: Dict[str, Any]) -> Dict[str, Any]:
    if not MODERATION_ENABLED:
        return {}

    final_answer = state.get('final_answer', '')
    if not final_answer:
        return {}

    result = check_output(final_answer)
    
    if result['blocked']:
        logger.warning(f"[OutputGuardrail] Blocked output")
        return {
            'guardrail_blocked': True,
            'guardrail_type': 'output',
            'final_answer': result['fallback_message'],
        }

    return {'guardrail_blocked': False}
