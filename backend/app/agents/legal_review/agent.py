"""
똑소리 프로젝트 - 검토 노드
작성일: 2026-01-14
S2-3: 규칙 기반 답변 검토 (S2-2 Legal Review Agent MVP)

검토 노드의 역할:
1. 금지 표현 탐지 (법적 단정, 확정적 판단 등)
2. 출처 누락 검사 (근거 없는 주장)
3. 근거 충분성 평가
4. 위반 시 filtered_answer 생성 또는 재생성 요청
"""

import re
from typing import Dict, List, Tuple

from ...orchestrator.state import ChatState, ReviewResult


# 금지 표현 패턴 (법적 단정/확정적 표현)
PROHIBITED_PATTERNS = [
    # 법적 단정
    (r'반드시\s+\S+해야\s*합니다', '반드시 ~해야 합니다'),
    (r'법적으로\s+\S+입니다', '법적으로 ~입니다'),
    (r'위법입니다', '위법입니다'),
    (r'불법입니다', '불법입니다'),
    (r'소송\s*(을|에서)\s*이길\s*(수\s*있|것)', '소송에서 이길 수 있다'),
    (r'승소\s*할\s*(수\s*있|것)', '승소할 수 있다'),
    (r'패소\s*할\s*(수\s*있|것)', '패소할 수 있다'),
    (r'확실히\s+\S+받을\s*수\s*있', '확실히 ~받을 수 있다'),
    (r'100%\s*\S+', '100% ~'),
    
    # 확정적 판단
    (r'당연히\s+\S+해야', '당연히 ~해야'),
    (r'무조건\s+\S+', '무조건 ~'),
    (r'틀림없이\s+\S+', '틀림없이 ~'),
    (r'분명히\s+\S+할\s*것입니다', '분명히 ~할 것입니다'),
    
    # 전문가 사칭
    (r'법률\s*전문가로서', '법률 전문가로서'),
    (r'변호사\s*입장에서', '변호사 입장에서'),
    (r'법적\s*조언을\s*드리자면', '법적 조언을 드리자면'),
]

# 출처 표시 패턴
CITATION_PATTERNS = [
    r'\[출처[:\s]',
    r'\[참고[:\s]',
    r'출처\s*:',
    r'근거\s*:',
    r'관련\s*법령\s*:',
    r'관련\s*기준\s*:',
    r'분쟁조정사례',
    r'상담사례',
    r'소비자보호법',
    r'전자상거래법',
    r'약관규제법',
    r'제\d+조',
    r'별표\s*\d+',
]

# 권장 완화 표현
SOFTENING_PHRASES = {
    '해야 합니다': '~할 수 있습니다',
    '입니다': '~로 판단될 수 있습니다',
    '이길 수 있': '유리한 측면이 있을 수 있',
    '받을 수 있': '요청해 볼 수 있',
    '확실히': '가능성이 있',
    '무조건': '일반적으로',
    '당연히': '통상적으로',
}


def _check_prohibited_expressions(answer: str) -> List[Tuple[str, str]]:
    """
    금지 표현 탐지
    
    Returns:
        [(위반 패턴, 발견된 텍스트), ...]
    """
    violations = []
    
    for pattern, description in PROHIBITED_PATTERNS:
        matches = re.findall(pattern, answer, re.IGNORECASE)
        if matches:
            for match in matches[:3]:  # 최대 3개까지만 보고
                match_str = match if isinstance(match, str) else match[0] if match else ''
                violations.append((description, match_str))
    
    return violations


def _check_citation_presence(answer: str, has_sources: bool) -> bool:
    """
    출처/근거 표시 여부 확인
    
    분쟁 관련 답변인데 출처가 전혀 없으면 문제.
    """
    if not has_sources:
        # sources가 없으면 출처 검사 불필요 (검색 결과 없음)
        return True
    
    # 하나 이상의 출처 패턴이 있으면 OK
    for pattern in CITATION_PATTERNS:
        if re.search(pattern, answer):
            return True
    
    return False


def _check_evidence_sufficiency(state: ChatState) -> bool:
    """
    근거 충분성 확인
    
    retrieval 결과가 있고, 유사도가 일정 수준 이상이면 충분.
    """
    retrieval = state.get('retrieval')
    if not retrieval:
        return False
    
    # 분쟁조정사례 또는 법령이 있으면 충분
    disputes = retrieval.get('disputes', [])
    laws = retrieval.get('laws', [])
    
    if disputes or laws:
        return True
    
    return False


def _filter_prohibited_expressions(answer: str, violations: List[Tuple[str, str]]) -> str:
    """
    금지 표현을 완화된 표현으로 대체
    """
    filtered = answer
    
    for old_phrase, new_phrase in SOFTENING_PHRASES.items():
        filtered = re.sub(
            re.escape(old_phrase),
            new_phrase,
            filtered,
            flags=re.IGNORECASE
        )
    
    return filtered


def _build_violation_messages(
    prohibited_violations: List[Tuple[str, str]],
    has_citation: bool,
    has_evidence: bool
) -> List[str]:
    """
    위반 사항 메시지 생성
    """
    messages = []
    
    if prohibited_violations:
        messages.append(
            f"금지 표현 발견 ({len(prohibited_violations)}건): "
            + ", ".join(v[0] for v in prohibited_violations[:3])
        )
    
    if not has_citation:
        messages.append("출처/근거 표시 부족")
    
    if not has_evidence:
        messages.append("근거 자료 불충분")
    
    return messages


def review_node(state: ChatState) -> Dict:
    """
    검토 노드 함수
    
    draft_answer를 규칙 기반으로 검토하여 위반 사항 확인.
    위반 시 filtered_answer 생성, 심각한 위반은 재생성 요청.
    
    Args:
        state: 현재 ChatState
        
    Returns:
        부분 상태 업데이트 dict:
        {
            'review': ReviewResult,
            'final_answer': str (passed=True인 경우),
            'retry_count': int (passed=False인 경우 증가)
        }
    """
    draft_answer = state.get('draft_answer', '')
    query_analysis = state.get('query_analysis')
    sources = state.get('sources', [])
    retry_count = state.get('retry_count', 0)
    
    # 일반 대화는 검토 스킵
    if query_analysis and query_analysis.get('query_type') == 'general':
        review_result: ReviewResult = {
            'passed': True,
            'violations': [],
            'filtered_answer': None,
        }
        return {
            'review': review_result,
            'final_answer': draft_answer,
        }
    
    # 1. 금지 표현 검사
    prohibited_violations = _check_prohibited_expressions(draft_answer)
    
    # 2. 출처 표시 검사
    has_sources = len(sources) > 0
    has_citation = _check_citation_presence(draft_answer, has_sources)
    
    # 3. 근거 충분성 검사
    has_evidence = _check_evidence_sufficiency(state)
    
    # 위반 메시지 생성
    violation_messages = _build_violation_messages(
        prohibited_violations, has_citation, has_evidence
    )
    
    # 결과 판정
    from ...common.config import AgentConfig
    
    needs_retry = (
        len(prohibited_violations) >= AgentConfig.PROHIBITED_VIOLATION_THRESHOLD 
        and retry_count < AgentConfig.MAX_REVIEW_RETRIES
    )
    
    # 경미한 위반은 필터링으로 처리
    if prohibited_violations and not needs_retry:
        filtered = _filter_prohibited_expressions(draft_answer, prohibited_violations)
    else:
        filtered = None
    
    # 통과 여부 결정
    passed = (
        len(prohibited_violations) == 0 
        and (has_citation or not has_sources)
    )
    
    review_result: ReviewResult = {
        'passed': passed,
        'violations': violation_messages,
        'filtered_answer': filtered,
    }
    
    # 결과에 따른 상태 업데이트
    if needs_retry:
        # 재생성 필요 (retry_count 증가)
        return {
            'review': review_result,
            'retry_count': retry_count + 1,
        }
    elif passed:
        # 통과 - final_answer 확정
        return {
            'review': review_result,
            'final_answer': draft_answer,
        }
    else:
        # 필터링된 답변 사용
        final = filtered if filtered else draft_answer
        return {
            'review': review_result,
            'final_answer': final,
        }


def review_node_wrapper(state: ChatState) -> Dict:
    """
    PR-2: 통합 그래프용 리뷰 노드 래퍼

    chat_type에 따라 리뷰 동작을 분기:
    - general: 자동 통과 (draft_answer → final_answer)
    - dispute: 전체 리뷰 수행

    Args:
        state: 현재 ChatState (또는 UnifiedState)

    Returns:
        부분 상태 업데이트 dict
    """
    chat_type = state.get('chat_type', 'dispute')

    if chat_type == 'general':
        # 일반 채팅: 리뷰 스킵, draft_answer를 final_answer로 직접 설정
        draft_answer = state.get('draft_answer', '')
        review_result: ReviewResult = {
            'passed': True,
            'violations': [],
            'filtered_answer': None,
        }
        return {
            'review': review_result,
            'final_answer': draft_answer,
        }

    # 분쟁 상담: 전체 리뷰 수행
    return review_node(state)
