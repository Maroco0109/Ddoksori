"""
똑소리 프로젝트 - ReAct 추론 노드
작성일: 2026-01-17
S2-7: ReAct 패턴 구현 - 추론(Thought) 노드
S2-8: LLM 기반 추론 추가 (EXAONE 3.5 2.4B)

ReAct 패턴의 Thought 단계를 담당하는 노드.
현재 상태를 분석하고 다음 행동(Action)을 결정.
- REACT_THINK_MODE=llm: LLM 기반 추론 (EXAONE)
- REACT_THINK_MODE=rule: 규칙 기반 추론 (기본값/폴백)
"""

import os
import json
import logging
from typing import Dict, Optional

from ...orchestrator.state import ChatState

logger = logging.getLogger(__name__)


def _analyze_retrieval_status(state: ChatState) -> Dict[str, bool]:
    """
    현재 검색 결과 상태 분석

    Returns:
        각 섹션별 데이터 존재 여부
    """
    retrieval = state.get('retrieval') or {}

    return {
        'has_disputes': bool(retrieval.get('disputes')),
        'has_counsels': bool(retrieval.get('counsels')),
        'has_laws': bool(retrieval.get('laws')),
        'has_criteria': bool(retrieval.get('criteria')),
        'has_agency': bool(retrieval.get('agency')),
    }


def _check_similarity_threshold(state: ChatState, threshold: float = 0.55) -> bool:
    """
    검색 결과의 유사도가 임계값 이상인지 확인

    Args:
        state: 현재 상태
        threshold: 유사도 임계값 (기본 0.55)

    Returns:
        최대 유사도가 임계값 이상이면 True
    """
    retrieval = state.get('retrieval') or {}
    max_similarity = retrieval.get('max_similarity', 0.0)
    return max_similarity >= threshold


def _determine_next_action(
    iteration: int,
    max_iterations: int,
    retrieval_status: Dict[str, bool],
    has_good_similarity: bool,
    query_type: Optional[str],
) -> tuple[str, Optional[str], bool]:
    """
    규칙 기반 다음 액션 결정

    Args:
        iteration: 현재 반복 횟수
        max_iterations: 최대 반복 횟수
        retrieval_status: 섹션별 데이터 존재 여부
        has_good_similarity: 유사도 임계값 충족 여부
        query_type: 쿼리 타입 (dispute, general, law, criteria)

    Returns:
        (thought, next_action, should_continue) 튜플
    """
    has_disputes = retrieval_status['has_disputes']
    has_counsels = retrieval_status['has_counsels']
    has_laws = retrieval_status['has_laws']
    has_criteria = retrieval_status['has_criteria']

    # 최대 반복 도달
    if iteration >= max_iterations:
        return (
            f"최대 반복 횟수({max_iterations})에 도달. 수집된 정보로 답변 생성 진행.",
            None,
            False
        )

    # 첫 번째 반복: 전체 검색 필요
    if iteration == 0:
        if not has_disputes and not has_counsels and not has_laws:
            return (
                "검색 데이터 없음. 분쟁사례, 상담사례, 법령 전체 검색 필요.",
                "search_all",
                True
            )

    # 유사도가 낮은 경우 - 추가 검색 시도
    if not has_good_similarity:
        if iteration < max_iterations - 1:
            return (
                f"검색 결과 유사도 낮음. 추가 검색 시도 (반복 {iteration + 1}/{max_iterations}).",
                "search_all",
                True
            )
        else:
            return (
                "유사도가 낮지만 최대 반복에 근접. 현재 결과로 답변 생성.",
                None,
                False
            )

    # 분쟁 관련 쿼리인데 기준 정보 부족
    if query_type in ('dispute', 'criteria'):
        if (has_disputes or has_counsels) and not has_criteria:
            return (
                "분쟁사례는 있으나 분쟁해결기준 부족. 기준 검색 필요.",
                "search_criteria",
                True
            )

    # 법률 관련 쿼리인데 법령 정보 부족
    if query_type == 'law':
        if not has_laws:
            return (
                "법령 정보 부족. 법령 검색 필요.",
                "search_laws",
                True
            )

    # 충분한 정보 수집됨
    if has_disputes or has_counsels or has_laws or has_criteria:
        return (
            "충분한 정보 수집 완료. 답변 생성 진행.",
            None,
            False
        )

    # 정보가 전혀 없는 경우
    return (
        "검색 결과 없음. 전체 검색 시도.",
        "search_all",
        True
    )


# === LLM 기반 추론 (S2-8) ===

REACT_THINK_SYSTEM_PROMPT = """당신은 소비자 분쟁 해결을 돕는 AI 어시스턴트입니다.

현재 상황을 분석하고 다음 행동을 결정하세요.

가능한 액션:
- search_all: 분쟁사례, 상담사례, 법령, 기준 전체 검색 (정보가 부족할 때)
- search_criteria: 분쟁해결기준만 추가 검색 (사례는 있지만 기준이 없을 때)
- search_laws: 관련 법령만 추가 검색 (법령 정보가 부족할 때)
- generate: 충분한 정보가 있으면 답변 생성으로 진행

반드시 아래 JSON 형식으로만 응답하세요:
{"thought": "현재 상황에 대한 분석", "action": "다음에 수행할 액션", "should_continue": true}

action이 "generate"이면 should_continue는 false입니다.
"""


def _build_think_prompt(state: ChatState) -> str:
    """
    LLM 추론을 위한 사용자 프롬프트 구성

    Args:
        state: 현재 ChatState

    Returns:
        상황 요약 프롬프트
    """
    user_query = state.get('user_query', '')
    iteration = state.get('current_iteration', 0)
    max_iterations = state.get('max_iterations', 2)

    query_analysis = state.get('query_analysis') or {}
    query_type = query_analysis.get('query_type', 'unknown')

    retrieval = state.get('retrieval') or {}
    n_disputes = len(retrieval.get('disputes', []))
    n_counsels = len(retrieval.get('counsels', []))
    n_laws = len(retrieval.get('laws', []))
    n_criteria = len(retrieval.get('criteria', []))
    max_similarity = retrieval.get('max_similarity', 0.0)

    prompt = f"""## 현재 상황
- 사용자 질문: {user_query}
- 질의 유형: {query_type}
- 현재 반복: {iteration + 1}/{max_iterations}

## 검색 결과 현황
- 분쟁사례: {n_disputes}건
- 상담사례: {n_counsels}건
- 관련 법령: {n_laws}건
- 분쟁해결기준: {n_criteria}건
- 최대 유사도: {max_similarity:.2f}

## 판단 기준
- 유사도 0.55 이상이면 관련성 높음
- 분쟁 질의에는 기준 정보가 필요
- 법률 질의에는 법령 정보가 필요
- 최대 반복에 도달하면 현재 결과로 답변 생성

다음 행동을 결정하세요."""

    return prompt


def _parse_llm_response(response: str) -> Optional[Dict]:
    """
    LLM 응답에서 JSON 파싱

    Args:
        response: LLM 응답 텍스트

    Returns:
        파싱된 dict 또는 None (실패 시)
    """
    try:
        # JSON 블록 추출 시도
        response = response.strip()

        # ```json ... ``` 블록 처리
        if '```json' in response:
            start = response.find('```json') + 7
            end = response.find('```', start)
            response = response[start:end].strip()
        elif '```' in response:
            start = response.find('```') + 3
            end = response.find('```', start)
            response = response[start:end].strip()

        # JSON 파싱
        result = json.loads(response)

        # 필수 필드 검증
        if 'thought' in result and 'action' in result and 'should_continue' in result:
            return result

        logger.warning(f"[react_think] Missing required fields in LLM response: {result}")
        return None

    except json.JSONDecodeError as e:
        logger.warning(f"[react_think] JSON parse error: {e}, response: {response[:200]}")
        return None


def _llm_based_think(state: ChatState) -> Dict:
    """
    LLM 기반 추론 (EXAONE 3.5 2.4B)

    Args:
        state: 현재 ChatState

    Returns:
        부분 상태 업데이트 dict
    """
    from ...llm import ExaoneLLMClient, LLMUnavailableError

    iteration = state.get('current_iteration', 0)

    try:
        client = ExaoneLLMClient()
        user_prompt = _build_think_prompt(state)

        logger.info("[react_think] Using LLM-based reasoning")
        response = client.generate(REACT_THINK_SYSTEM_PROMPT, user_prompt)

        result = _parse_llm_response(response)

        if result:
            action = result['action']
            should_continue = result['should_continue']

            # action이 generate이면 should_continue는 False
            if action == 'generate':
                should_continue = False
                action = None

            return {
                'last_thought': result['thought'],
                'last_action': action if should_continue else None,
                'should_continue': should_continue,
                'current_iteration': iteration + 1,
            }

        # 파싱 실패 시 규칙 기반 폴백
        logger.warning("[react_think] LLM response parsing failed, falling back to rule-based")
        return _rule_based_think(state)

    except LLMUnavailableError as e:
        logger.warning(f"[react_think] LLM unavailable: {e}, falling back to rule-based")
        return _rule_based_think(state)
    except Exception as e:
        logger.error(f"[react_think] LLM error: {e}, falling back to rule-based")
        return _rule_based_think(state)


def _rule_based_think(state: ChatState) -> Dict:
    """
    규칙 기반 추론 (S2-7 로직)

    Args:
        state: 현재 ChatState

    Returns:
        부분 상태 업데이트 dict
    """
    iteration = state.get('current_iteration', 0)
    max_iterations = state.get('max_iterations', 2)

    query_analysis = state.get('query_analysis') or {}
    query_type = query_analysis.get('query_type')

    retrieval_status = _analyze_retrieval_status(state)
    has_good_similarity = _check_similarity_threshold(state)

    thought, next_action, should_continue = _determine_next_action(
        iteration=iteration,
        max_iterations=max_iterations,
        retrieval_status=retrieval_status,
        has_good_similarity=has_good_similarity,
        query_type=query_type,
    )

    return {
        'last_thought': thought,
        'last_action': next_action,
        'should_continue': should_continue,
        'current_iteration': iteration + 1,
    }


def react_think_node(state: ChatState) -> Dict:
    """
    ReAct 추론 노드 (LLM 기반 + 규칙 폴백)

    현재 상태를 분석하고 다음 행동을 결정.

    환경 변수:
        REACT_THINK_MODE: 추론 모드 선택
            - 'llm': LLM 기반 추론 (EXAONE 3.5 2.4B)
            - 'rule': 규칙 기반 추론 (기본값)

    Args:
        state: 현재 ChatState

    Returns:
        부분 상태 업데이트:
        {
            'last_thought': str,        # 추론 내용
            'last_action': Optional[str], # 다음 액션 (None이면 생성 단계로)
            'should_continue': bool,    # 루프 계속 여부
            'current_iteration': int,   # 반복 횟수 증가
        }
    """
    mode = os.getenv('REACT_THINK_MODE', 'rule').lower()

    if mode == 'llm':
        return _llm_based_think(state)
    else:
        return _rule_based_think(state)
