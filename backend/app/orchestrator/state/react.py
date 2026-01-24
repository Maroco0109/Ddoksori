"""
똑소리 프로젝트 - ReAct 패턴 상태 스키마

ReAct(Reasoning + Acting) 패턴 실행을 위한 상태를 관리합니다.
반복적 추론-행동 사이클의 히스토리와 제어 변수를 포함합니다.
"""

from typing import List, Dict, Optional, Any, Annotated
from typing_extensions import TypedDict
import operator


class ReActStep(TypedDict):
    """
    ReAct 단일 스텝 기록

    Thought-Action-Observation 사이클 한 단위를 기록합니다.
    react_steps 필드에 operator.add로 누적되어 전체 추론 과정을 추적합니다.

    Attributes:
        thought: 현재 상황 분석 및 다음 행동에 대한 추론
            예: "사용자가 환불 규정을 물어보고 있다. 분쟁해결기준을 검색해야 한다."

        action: 선택된 액션 (도구 이름)
            - 'search_all': 전체 검색
            - 'search_criteria': 분쟁해결기준 검색
            - 'search_law': 법령 검색
            - 'ask_clarification': 되묻기
            - 'final_answer': 최종 답변 생성

        action_input: 액션에 전달되는 입력값
            예: {'query': '헬스장 환불', 'top_k': 5}

        observation: 액션 실행 결과 요약
            예: "3건의 관련 사례를 찾았습니다. 최대 유사도: 0.85"

    Example:
        >>> step: ReActStep = {
        ...     'thought': '사용자가 헬스장 환불에 대해 물어봤다.',
        ...     'action': 'search_criteria',
        ...     'action_input': {'query': '헬스장 회원권 환불'},
        ...     'observation': '2건의 기준을 찾았습니다.'
        ... }
    """
    thought: str
    action: str
    action_input: Dict[str, Any]
    observation: str


class ReActState(TypedDict, total=False):
    """
    ReAct 패턴 상태

    반복적 추론-행동 사이클의 실행 상태를 관리합니다.

    Attributes:
        react_steps: ReAct 히스토리 (operator.add로 누적)
            - 지금까지 실행된 모든 스텝 기록
            - 최종 답변 생성 시 컨텍스트로 사용

        current_iteration: 현재 ReAct 반복 횟수 (0-based)
            - 첫 번째 사이클: 0
            - max_iterations 도달 시 강제 종료

        max_iterations: 최대 반복 횟수
            - 기본값: general=1, dispute=2
            - 무한 루프 방지

        should_continue: ReAct 루프 계속 여부
            - True: 다음 iteration 실행
            - False: 루프 종료 (final_answer로 진행)

        last_thought: 마지막 추론 내용
            - 직전 think 노드의 출력
            - 디버깅 및 로깅용

        last_action: 마지막 선택 액션
            - 직전 act 노드에서 선택한 도구

        last_observation: 마지막 관찰 결과
            - 직전 액션 실행 결과 요약

    Note:
        react_steps는 operator.add를 사용하여
        각 iteration의 결과가 자동으로 누적됩니다.

    Example:
        >>> state: ReActState = {
        ...     'react_steps': [],
        ...     'current_iteration': 0,
        ...     'max_iterations': 2,
        ...     'should_continue': True
        ... }
    """
    react_steps: Annotated[List[ReActStep], operator.add]
    current_iteration: int
    max_iterations: int
    should_continue: bool
    last_thought: Optional[str]
    last_action: Optional[str]
    last_observation: Optional[str]


__all__ = [
    'ReActStep',
    'ReActState',
]
