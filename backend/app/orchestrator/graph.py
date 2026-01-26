"""
똑소리 프로젝트 - LangGraph 그래프 엔트리포인트

작성일: 2026-01-14
최종 수정: 2026-01-26 (Phase 7: graph.py 분리)

[역할]
그래프 선택 및 공통 유틸리티를 제공합니다.

[그래프 파일 구조]
- graph.py (이 파일): 엔트리포인트 및 공통 유틸리티
- graph_mas.py: MAS Supervisor 그래프 (현재 운영)
- graph_legacy.py: Legacy/Unified 그래프 (deprecated, 롤백용)

[주요 함수]
- get_graph_for_chat_type(): Feature Flag 기반 그래프 선택
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
    Phase 7: Feature Flag 기반 그래프 선택

    chat_type별 동작 차이는 state 초기화 시 설정:
    - general: max_iterations=1, review 자동 통과
    - dispute: max_iterations=2, 전체 review 수행

    Feature Flag:
    - MAS_SUPERVISOR_ENABLED=true: MAS Supervisor 그래프 사용 (기본값)
    - MAS_SUPERVISOR_CANARY_PERCENT=N: N% 트래픽에 MAS 그래프 적용 (Canary 배포)

    Args:
        chat_type: 'dispute' 또는 'general'
        session_id: Canary 배포 시 일관된 라우팅을 위한 세션 ID (선택)

    Returns:
        컴파일된 LangGraph 그래프
    """
    from .graph_mas import get_mas_supervisor_graph
    from .graph_legacy import get_unified_graph

    # 1. 전체 전환 플래그 확인 (Phase 7: 기본값 true)
    if os.getenv('MAS_SUPERVISOR_ENABLED', 'true').lower() == 'true':
        logger.info(f"[GraphSelect] MAS_SUPERVISOR_ENABLED=true, using MAS graph")
        return get_mas_supervisor_graph()

    # 2. Canary 배포 확인
    canary_percent = int(os.getenv('MAS_SUPERVISOR_CANARY_PERCENT', '0'))
    if canary_percent > 0 and session_id:
        # 세션 ID 해시 기반 일관된 라우팅 (같은 세션은 항상 같은 그래프)
        session_hash = hash(session_id) % 100
        if session_hash < canary_percent:
            logger.info(f"[GraphSelect] Canary {canary_percent}%, session in canary group, using MAS graph")
            return get_mas_supervisor_graph()

    # 3. Fallback: 기존 Unified 그래프 (deprecated)
    logger.warning("[GraphSelect] Using deprecated Unified graph - consider enabling MAS_SUPERVISOR_ENABLED=true")
    return get_unified_graph()


# ============================================================================
# 그래프 리셋 (테스트용)
# ============================================================================

def reset_graph():
    """모든 그래프 싱글톤 리셋"""
    from .graph_mas import reset_mas_graph
    from .graph_legacy import reset_legacy_graphs
    reset_mas_graph()
    reset_legacy_graphs()


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
    [Deprecated] graph_legacy.py로 이동됨.
    직접 from .graph_legacy import get_unified_graph 사용 권장.
    """
    from .graph_legacy import get_unified_graph as _get_unified
    return _get_unified()


def create_mas_supervisor_graph():
    """
    [Deprecated] graph_mas.py로 이동됨.
    직접 from .graph_mas import create_mas_supervisor_graph 사용 권장.
    """
    from .graph_mas import create_mas_supervisor_graph as _create_mas
    return _create_mas()


def create_unified_chat_graph():
    """
    [Deprecated] graph_legacy.py로 이동됨.
    직접 from .graph_legacy import create_unified_chat_graph 사용 권장.
    """
    from .graph_legacy import create_unified_chat_graph as _create_unified
    return _create_unified()


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
    [Deprecated] graph_legacy.py로 이동됨.
    직접 from .graph_legacy import _route_unified_after_query_analysis 사용 권장.
    """
    from .graph_legacy import _route_unified_after_query_analysis as _route
    return _route(state)


def _route_unified_after_review(state):
    """
    [Deprecated] graph_legacy.py로 이동됨.
    직접 from .graph_legacy import _route_unified_after_review 사용 권장.
    """
    from .graph_legacy import _route_unified_after_review as _route
    return _route(state)


def create_chat_graph():
    """
    [Deprecated] ORCHESTRATOR_MODE 기반 그래프 선택.
    get_graph_for_chat_type() 사용 권장.
    """
    from .graph_legacy import create_chat_graph as _create_chat
    return _create_chat()


def get_compiled_graph():
    """
    [Deprecated] graph_legacy.py로 이동됨.
    """
    from .graph_legacy import create_chat_graph
    from .checkpointer import get_checkpointer
    graph = create_chat_graph()
    checkpointer = get_checkpointer()
    return graph.compile(checkpointer=checkpointer)


def get_graph():
    """
    [Deprecated] get_graph_for_chat_type() 사용 권장.
    """
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = get_compiled_graph()
    return _compiled_graph


_compiled_graph = None
