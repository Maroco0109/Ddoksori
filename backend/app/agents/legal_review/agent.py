"""
똑소리 프로젝트 - 법률검토 에이전트 (Legal Review Agent)

작성일: 2026-01-14
최종 수정: 2026-01-22

[역할 및 책임]
생성된 답변(Draft)의 안전성과 신뢰성을 최종적으로 검증합니다.
LLM이 생성한 답변이 법적 책임 소지가 있는 단정적인 표현을 포함하거나, 
근거 없는 주장을 하는지(Hallucination) 감시합니다.

[주요 로직]
1. 금지 표현 탐지 (Prohibited Expressions): "반드시 ~해야 합니다", "100% 승소" 등의 단정적 표현 감지.
2. 출처 검사 (Citation Check): 답변에 [출처] 표기가 포함되어 있는지 확인.
3. 근거 충분성 (Evidence Sufficiency): 검색된 문서가 충분한지 State 기반 확인.
4. 답변 정제 (Filtering): 경미한 위반은 "가능성이 있습니다" 등으로 표현 완화(Softening).
5. 재생성 요청 (Retry): 중대한 위반이나 출처 누락 시 Generation 단계로 되돌려 보냄.
"""

import re
from typing import Dict, List, Tuple

from ...orchestrator.state import ChatState, ReviewResult


# ============================================================
# [Review Rules Definitions]
# 답변의 안전성을 보장하기 위한 정규식 패턴 모음입니다.
# ============================================================

# 금지 표현 패턴 (법적 단정/확정적 표현)
# 변호사법 위반 소지가 있거나, 사용자에게 잘못된 확신을 줄 수 있는 표현들입니다.
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
# 답변에 근거 자료가 인용되었는지 확인하는 패턴입니다.
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

# 권장 완화 표현 (Softening Phrases)
# 금지 표현이 발견되었을 때, 이를 대체할 안전한 표현 매핑입니다.
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
    답변 텍스트에서 금지된 표현을 탐지합니다.
    
    Returns:
        [(위반 패턴 설명, 실제 발견된 텍스트), ...] 리스트
    """
    violations = []
    
    for pattern, description in PROHIBITED_PATTERNS:
        matches = re.findall(pattern, answer, re.IGNORECASE)
        if matches:
            for match in matches[:3]:  # 너무 많은 위반이 나와도 3개까지만 보고
                match_str = match if isinstance(match, str) else match[0] if match else ''
                violations.append((description, match_str))
    
    return violations


def _check_citation_presence(answer: str, has_sources: bool) -> bool:
    """
    답변에 출처/근거가 명시되어 있는지 확인합니다.
    검색 결과(sources)가 있는데도 답변에 인용이 없다면 Hallucination 가능성이 높습니다.
    """
    if not has_sources:
        # sources가 없으면 출처 검사 불필요 (검색 결과 자체가 없음)
        return True
    
    # 하나 이상의 출처 패턴이 있으면 통과
    for pattern in CITATION_PATTERNS:
        if re.search(pattern, answer):
            return True
    
    return False


def _check_evidence_sufficiency(state: ChatState) -> bool:
    """
    검색 단계에서 충분한 근거(분쟁사례, 법령 등)를 찾았는지 확인합니다.
    """
    retrieval = state.get('retrieval')
    if not retrieval:
        return False
    
    # 분쟁조정사례 또는 법령이 있으면 충분하다고 간주
    disputes = retrieval.get('disputes', [])
    laws = retrieval.get('laws', [])
    
    if disputes or laws:
        return True
    
    return False


def _filter_prohibited_expressions(answer: str, violations: List[Tuple[str, str]]) -> str:
    """
    발견된 금지 표현을 안전한 표현(Softening Phrases)으로 자동 치환합니다.
    재생성(Retry) 비용을 아끼기 위해 경미한 위반은 이 함수로 수정하여 내보냅니다.
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
    """검토 결과 리포트용 메시지 생성"""
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
    [검토 노드 진입점] (Standard Review)
    
    생성된 초안(draft_answer)을 3단계로 검증합니다.
    1. 금지 표현 여부
    2. 출처 표시 여부
    3. 근거 충분성 여부
    
    위반 사항이 심각하면 'passed=False'를 반환하여 Orchestrator가 재생성을 지시하게 하고,
    경미하면 자체적으로 수정(Filtering)하여 'final_answer'를 확정합니다.
    
    Args:
        state: 현재 ChatState
        
    Returns:
        부분 상태 업데이트 dict:
        {
            'review': ReviewResult,
            'final_answer': str (통과 또는 수정된 경우),
            'retry_count': int (재생성 필요한 경우 증가)
        }
    """
    draft_answer = state.get('draft_answer', '')
    query_analysis = state.get('query_analysis')
    sources = state.get('sources', [])
    retry_count = state.get('retry_count', 0)
    
    # 일반 대화(General)는 검토 스킵 (PR-1 Fast Path)
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
    
    # 재생성(Retry) 조건:
    # 1. 금지 표현이 너무 많거나 (Threshold 초과)
    # 2. 아직 최대 재시도 횟수에 도달하지 않았을 때
    needs_retry = (
        len(prohibited_violations) >= AgentConfig.PROHIBITED_VIOLATION_THRESHOLD 
        and retry_count < AgentConfig.MAX_REVIEW_RETRIES
    )
    
    # 경미한 위반은 필터링으로 처리
    if prohibited_violations and not needs_retry:
        filtered = _filter_prohibited_expressions(draft_answer, prohibited_violations)
    else:
        filtered = None
    
    # 통과 여부 결정 (금지 표현 없고, 출처가 있거나 원래 검색 결과가 없으면 통과)
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
        # 재생성 필요 (retry_count 증가 -> Orchestrator가 다시 Generation 노드로 보냄)
        return {
            'review': review_result,
            'retry_count': retry_count + 1,
        }
    elif passed:
        # 완전 통과 - final_answer 확정
        return {
            'review': review_result,
            'final_answer': draft_answer,
        }
    else:
        # 조건부 통과 (필터링된 답변 사용)
        final = filtered if filtered else draft_answer
        return {
            'review': review_result,
            'final_answer': final,
        }


def review_node_wrapper(state: ChatState) -> Dict:
    """
    [리뷰 노드 래퍼] (PR-2 통합 그래프용)
    
    ChatState의 chat_type에 따라 리뷰 수행 여부를 결정합니다.
    - general: 무조건 통과 (Fast Path)
    - dispute: 정밀 리뷰 수행
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
