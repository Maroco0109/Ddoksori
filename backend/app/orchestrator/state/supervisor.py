"""
똑소리 프로젝트 - 슈퍼바이저 상태 스키마

MAS(Multi-Agent System) 슈퍼바이저 아키텍처를 위한 상태 정의입니다.
에이전트 간 메시지 통신과 슈퍼바이저의 의사결정 상태를 관리합니다.
"""

from typing import List, Dict, Optional, Any
from typing_extensions import TypedDict


class AgentMessage(TypedDict):
    """
    슈퍼바이저 ↔ 에이전트 간 메시지

    에이전트 간 통신을 위한 표준 메시지 형식입니다.
    모든 에이전트 간 상호작용은 이 형식을 따릅니다.

    Attributes:
        from_agent: 발신 에이전트 이름 (예: 'supervisor', 'query_analyst', 'retrieval_agent')
        to_agent: 수신 에이전트 이름 (예: 'query_analyst', 'retrieval_agent')
        message_type: 메시지 유형
            - 'request': 작업 요청
            - 'response': 작업 결과 응답
            - 'error': 오류 보고
        content: 실제 페이로드 (메시지 유형에 따라 다양한 구조)
            - request: {'task': str, 'params': Dict[str, Any]}
            - response: {'result': Any, 'status': str}
            - error: {'error_type': str, 'message': str}
        timestamp: 메시지 생성 시간 (Unix timestamp, float)

    Example:
        >>> msg: AgentMessage = {
        ...     'from_agent': 'supervisor',
        ...     'to_agent': 'query_analyst',
        ...     'message_type': 'request',
        ...     'content': {
        ...         'task': 'analyze_query',
        ...         'params': {'query': '헬스장 환불 규정'}
        ...     },
        ...     'timestamp': 1705000000.0
        ... }
    """
    from_agent: str
    to_agent: str
    message_type: str
    content: Dict[str, Any]
    timestamp: float


class SupervisorState(TypedDict):
    """
    슈퍼바이저 전용 상태

    슈퍼바이저가 에이전트 워크플로우를 관리하기 위한 상태입니다.
    현재 실행 단계, 에이전트 간 통신 기록, 작업 큐, 의사결정 근거를 포함합니다.

    Attributes:
        current_phase: 현재 실행 단계
            - 'analyzing': 질의 분석 단계
            - 'retrieving': 정보 검색 단계
            - 'drafting': 답변 초안 작성 단계
            - 'reviewing': 법률 검토 단계
            - 'done': 완료
        agent_messages: 에이전트 간 통신 기록 (누적)
            모든 AgentMessage가 시간순으로 저장됩니다.
            슈퍼바이저와 에이전트 간의 전체 대화 히스토리입니다.
        pending_tasks: 대기 중인 작업 목록
            아직 실행되지 않은 작업들의 ID 또는 설명입니다.
            예: ['analyze_query', 'retrieve_documents', 'generate_answer']
        completed_tasks: 완료된 작업 목록
            성공적으로 완료된 작업들의 ID 또는 설명입니다.
            예: ['analyze_query', 'retrieve_documents']
        supervisor_reasoning: 슈퍼바이저의 현재 판단 근거
            다음 단계 결정, 에이전트 선택, 작업 우선순위 등의 이유를 기록합니다.
            예: "Query analysis shows need for legal document retrieval. Routing to retrieval_agent."
        next_agent: 다음 호출할 에이전트 이름
            None이면 현재 단계 완료 또는 종료를 의미합니다.
            예: 'retrieval_agent', 'legal_reviewer', None

    Example:
        >>> state: SupervisorState = {
        ...     'current_phase': 'analyzing',
        ...     'agent_messages': [
        ...         {
        ...             'from_agent': 'supervisor',
        ...             'to_agent': 'query_analyst',
        ...             'message_type': 'request',
        ...             'content': {'task': 'analyze_query', 'params': {...}},
        ...             'timestamp': 1705000000.0
        ...         }
        ...     ],
        ...     'pending_tasks': ['retrieve_documents', 'generate_answer', 'review_answer'],
        ...     'completed_tasks': ['analyze_query'],
        ...     'supervisor_reasoning': 'Query requires legal document retrieval. Routing to retrieval_agent.',
        ...     'next_agent': 'retrieval_agent'
        ... }
    """
    current_phase: str
    agent_messages: List[AgentMessage]
    pending_tasks: List[str]
    completed_tasks: List[str]
    supervisor_reasoning: str
    next_agent: Optional[str]
    iteration_count: int


__all__ = [
    'AgentMessage',
    'SupervisorState',
]
