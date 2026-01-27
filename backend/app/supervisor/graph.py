"""
똑소리 프로젝트 - LangGraph 그래프 엔트리포인트

작성일: 2026-01-14
최종 수정: 2026-01-27 (Phase 7: supervisor 모듈로 이름 변경, Legacy 제거)

[역할]
MAS Supervisor 그래프 엔트리포인트 및 공통 유틸리티를 제공합니다.

[그래프 파일 구조]
- graph.py (이 파일): 엔트리포인트 및 공통 유틸리티
- graph_mas.py: MAS Supervisor 그래프 (현재 운영)
- (archived) graph_legacy.py: Legacy/Unified 그래프 → _archive/orchestrator/로 이동됨

[주요 함수]
- get_graph_for_chat_type(): MAS Supervisor 그래프 반환
- _create_timed_node(): 노드 타이밍 래퍼
"""

import os
import time
import logging
from typing import Dict, Any, Callable

from .state import ChatState

logger = logging.getLogger(__name__)

# ============================================================================
# 공통 상수 및 유틸리티
# ============================================================================

NODE_TIMINGS_KEY = '_node_timings'
SIMILARITY_THRESHOLD_HIGH = 0.55

# 노드별 스냅샷 대상 필드 정의
NODE_SNAPSHOT_FIELDS = {
    'query_analysis': {
        'input': ['user_query', 'onboarding', 'chat_type'],
        'output': ['query_analysis', 'mode'],
    },
    'retrieval': {
        'input': ['user_query', 'query_analysis', 'onboarding'],
        'output': ['retrieval', 'sources'],
    },
    'react_think': {
        'input': ['user_query', 'retrieval', 'react_steps', 'iteration_count'],
        'output': ['last_thought', 'last_action', 'should_continue', 'iteration_count'],
    },
    'react_act': {
        'input': ['last_action', 'last_thought'],
        'output': ['retrieval', 'tool_result'],
    },
    'generation': {
        'input': ['user_query', 'retrieval', 'query_analysis', 'react_steps'],
        'output': ['final_answer', 'draft_answer'],
    },
    'review': {
        'input': ['final_answer', 'draft_answer', 'retrieval'],
        'output': ['review', 'retry_count'],
    },
    'input_guardrail': {
        'input': ['user_query'],
        'output': ['guardrail_blocked', 'guardrail_type'],
    },
    'output_guardrail': {
        'input': ['final_answer'],
        'output': ['guardrail_blocked', 'final_answer'],
    },
}


def _snapshot_state(state: Dict[str, Any], fields: list) -> Dict[str, Any]:
    """상태에서 지정된 필드만 추출하여 스냅샷 생성"""
    snapshot = {}
    for field in fields:
        if field in state:
            value = state[field]
            # 직렬화 가능하도록 처리
            if hasattr(value, '__dict__'):
                snapshot[field] = str(value)[:500]  # 객체는 문자열로 변환 (500자 제한)
            elif isinstance(value, (list, dict)):
                try:
                    import json
                    serialized = json.dumps(value, ensure_ascii=False, default=str)
                    snapshot[field] = json.loads(serialized[:2000])  # 2KB 제한
                except Exception:
                    snapshot[field] = str(value)[:500]
            else:
                snapshot[field] = value
    return snapshot


def _detect_state_changes(input_state: Dict[str, Any], output: Dict[str, Any]) -> list:
    """출력에서 변경/추가된 필드 목록 반환"""
    changes = []
    for key in output.keys():
        if key.startswith('_'):
            continue  # 내부 필드 제외
        if key not in input_state:
            changes.append(f"+{key}")  # 새로 추가된 필드
        elif input_state.get(key) != output.get(key):
            changes.append(f"~{key}")  # 변경된 필드
    return changes


def _create_timed_node(node_fn: Callable, node_name: str) -> Callable:
    """노드 함수를 감싸서 실행 시간과 I/O 스냅샷을 기록하는 래퍼 생성"""
    def timed_wrapper(state: ChatState) -> Dict[str, Any]:
        start_time = time.time()
        logger.info(f"[NODE START] {node_name}")

        # 입력 스냅샷 수집
        snapshot_config = NODE_SNAPSHOT_FIELDS.get(node_name, {'input': [], 'output': []})
        input_snapshot = _snapshot_state(dict(state), snapshot_config['input'])

        result = node_fn(state)

        end_time = time.time()
        duration_ms = round((end_time - start_time) * 1000, 2)
        logger.info(f"[NODE END] {node_name} - {duration_ms}ms")

        # 출력 스냅샷 수집
        output_snapshot = _snapshot_state(result, snapshot_config['output'])

        # 상태 변경 감지
        state_changes = _detect_state_changes(dict(state), result)

        existing_timings = state.get(NODE_TIMINGS_KEY)
        timings = dict(existing_timings) if existing_timings else {}
        timings[node_name] = {
            'start': start_time,
            'end': end_time,
            'duration_ms': duration_ms,
            'input_snapshot': input_snapshot,
            'output_snapshot': output_snapshot,
            'state_changes': state_changes,
        }
        result[NODE_TIMINGS_KEY] = timings

        return result

    return timed_wrapper


# ============================================================================
# 그래프 선택 (Feature Flag 기반)
# ============================================================================

def get_graph_for_chat_type(chat_type: str, session_id: str = None):
    """
    Phase 7: MAS Supervisor 그래프 반환

    chat_type별 동작 차이는 state 초기화 시 설정:
    - general: max_iterations=1, review 자동 통과
    - dispute: max_iterations=2, 전체 review 수행

    Note:
        Phase 7에서 Legacy/ReAct 그래프 지원이 제거되었습니다.
        MAS_SUPERVISOR_ENABLED 환경변수는 더 이상 사용되지 않습니다.

    Args:
        chat_type: 'dispute' 또는 'general'
        session_id: (사용되지 않음, 하위 호환성 유지용)

    Returns:
        컴파일된 MAS Supervisor LangGraph 그래프
    """
    from .graph_mas import get_mas_supervisor_graph

    logger.info(f"[GraphSelect] Using MAS Supervisor graph (chat_type={chat_type})")
    return get_mas_supervisor_graph()


# ============================================================================
# 그래프 리셋 (테스트용)
# ============================================================================

def reset_graph():
    """MAS 그래프 싱글톤 리셋"""
    from .graph_mas import reset_mas_graph
    reset_mas_graph()


# ============================================================================
# Backwards Compatibility (deprecated exports)
# ============================================================================

def get_mas_supervisor_graph():
    """
    [Deprecated] graph_mas.py로 이동됨.
    직접 from .graph_mas import get_mas_supervisor_graph 사용 권장.
    """
    from .graph_mas import get_mas_supervisor_graph as _get_mas
    return _get_mas()


def get_unified_graph():
    """
    [REMOVED] Legacy Unified 그래프는 Phase 7에서 제거되었습니다.
    MAS Supervisor 그래프(get_mas_supervisor_graph)를 사용하세요.
    """
    raise NotImplementedError(
        "Legacy Unified graph has been removed in Phase 7. "
        "Use get_mas_supervisor_graph() instead."
    )


def create_mas_supervisor_graph():
    """
    [Deprecated] graph_mas.py로 이동됨.
    직접 from .graph_mas import create_mas_supervisor_graph 사용 권장.
    """
    from .graph_mas import create_mas_supervisor_graph as _create_mas
    return _create_mas()


def create_unified_chat_graph():
    """
    [REMOVED] Legacy Unified 그래프는 Phase 7에서 제거되었습니다.
    MAS Supervisor 그래프(create_mas_supervisor_graph)를 사용하세요.
    """
    raise NotImplementedError(
        "Legacy Unified graph has been removed in Phase 7. "
        "Use create_mas_supervisor_graph() instead."
    )


def _route_mas_supervisor(state):
    """
    [Deprecated] graph_mas.py로 이동됨.
    직접 from .graph_mas import _route_mas_supervisor 사용 권장.
    """
    from .graph_mas import _route_mas_supervisor as _route
    return _route(state)


def get_mas_supervisor_compiled_graph():
    """
    [Deprecated] graph_mas.py로 이동됨.
    직접 from .graph_mas import get_mas_supervisor_compiled_graph 사용 권장.
    """
    from .graph_mas import get_mas_supervisor_compiled_graph as _get_compiled
    return _get_compiled()


def reset_mas_graph():
    """
    [Deprecated] graph_mas.py로 이동됨.
    직접 from .graph_mas import reset_mas_graph 사용 권장.
    """
    from .graph_mas import reset_mas_graph as _reset
    return _reset()


def _create_retrieval_agent_node(agent_type: str):
    """
    [Deprecated] graph_mas.py로 이동됨.
    직접 from .graph_mas import _create_retrieval_agent_node 사용 권장.
    """
    from .graph_mas import _create_retrieval_agent_node as _create
    return _create(agent_type)


def _route_unified_after_query_analysis(state):
    """
    [REMOVED] Legacy routing은 Phase 7에서 제거되었습니다.
    MAS Supervisor 그래프를 사용하세요.
    """
    raise NotImplementedError(
        "Legacy routing has been removed in Phase 7. "
        "Use MAS Supervisor graph instead."
    )


def _route_unified_after_review(state):
    """
    [REMOVED] Legacy routing은 Phase 7에서 제거되었습니다.
    MAS Supervisor 그래프를 사용하세요.
    """
    raise NotImplementedError(
        "Legacy routing has been removed in Phase 7. "
        "Use MAS Supervisor graph instead."
    )


def create_chat_graph():
    """
    [REMOVED] Legacy 그래프는 Phase 7에서 제거되었습니다.
    get_graph_for_chat_type() 또는 create_mas_supervisor_graph()를 사용하세요.
    """
    raise NotImplementedError(
        "Legacy create_chat_graph has been removed in Phase 7. "
        "Use get_graph_for_chat_type() or create_mas_supervisor_graph() instead."
    )


def get_compiled_graph():
    """
    [REMOVED] Legacy 그래프는 Phase 7에서 제거되었습니다.
    get_graph_for_chat_type() 또는 get_mas_supervisor_graph()를 사용하세요.
    """
    raise NotImplementedError(
        "Legacy get_compiled_graph has been removed in Phase 7. "
        "Use get_graph_for_chat_type() or get_mas_supervisor_graph() instead."
    )


def get_graph():
    """
    [REMOVED] Legacy 그래프는 Phase 7에서 제거되었습니다.
    get_graph_for_chat_type() 또는 get_mas_supervisor_graph()를 사용하세요.
    """
    raise NotImplementedError(
        "Legacy get_graph has been removed in Phase 7. "
        "Use get_graph_for_chat_type() or get_mas_supervisor_graph() instead."
    )
