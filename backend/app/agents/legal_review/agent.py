"""
똑소리 프로젝트 - 법률검토 에이전트 (Legal Review Agent)

작성일: 2026-01-14
최종 수정: 2026-01-28 (v2: Violation 상세 정보 + 재생성 루프 지원)

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

[v2 추가 기능]
- Violation 상세 정보 구조 (type, description, location, severity, suggestion)
- retry_context 구성: AnswerDrafter에 위반사항 전달
- next_agent='retry_generation' 반환으로 재생성 루프 지원
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from ...supervisor.state import ChatState, ReviewResult
from ...common.config import AgentConfig


# ============================================================
# [Review Rules Definitions]
# 답변의 안전성을 보장하기 위한 정규식 패턴 모음입니다.
# ============================================================

# 금지 표현 패턴 (법적 단정/확정적 표현)
# 변호사법 위반 소지가 있거나, 사용자에게 잘못된 확신을 줄 수 있는 표현들입니다.
PROHIBITED_PATTERNS = [
    # 법적 단정 (개선: 다양한 어미 포함)
    (r'반드시\s+\S+(해야\s*합니다|합니다|하세요|입니다)', '반드시 ~합니다'),
    (r'법적으로\s+\S+입니다', '법적으로 ~입니다'),
    (r'(위법|불법)입니다', '위법/불법입니다'),
    (r'소송\s*(을|에서)\s*이길\s*(수\s*있|것)', '소송에서 이길 수 있다'),
    
    # 예측 표현 (개선: 승소/패소 표현 통합 및 완화)
    (r'(승소|패소|이길)\s*수\s*있(습니다|어요)', '승소/패소할 수 있습니다'),
    (r'(승소|패소)\s*할\s*(것|수\s*있)', '승소/패소 예측 표현'),
    
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

# 법령/조문 추출 패턴 (Citation Accuracy Verification용)
LAW_REFERENCE_PATTERNS = [
    r'제\s*(\d+)\s*조',                          # 제17조
    r'제\s*(\d+)\s*조\s*제\s*(\d+)\s*항',         # 제17조 제1항
    r'별표\s*(\d+)',                              # 별표 1
    r'(소비자보호법|소비자기본법)',
    r'(전자상거래법|전자상거래\s*등에서의\s*소비자보호에\s*관한\s*법률)',
    r'(약관규제법|약관의\s*규제에\s*관한\s*법률)',
    r'(할부거래법|할부거래에\s*관한\s*법률)',
    r'(방문판매법|방문판매\s*등에\s*관한\s*법률)',
    r'(표시광고법|표시·광고의\s*공정화에\s*관한\s*법률)',
    r'(제조물책임법|제조물\s*책임법)',
    r'(민법)',
    r'(상법)',
]


@dataclass
class CitationVerifyResult:
    """
    인용 정확성 검증 결과

    Attributes:
        passed: 모든 인용이 유효한지 여부
        cited_refs: 답변에서 발견된 법령/조문 리스트
        verified_refs: 검색 결과에서 확인된 법령/조문 리스트
        unverified_refs: 검색 결과에서 확인되지 않은 법령/조문 (Hallucination 의심)
        accuracy: 인용 정확도 (0.0 ~ 1.0)
    """
    passed: bool
    cited_refs: List[str]
    verified_refs: List[str]
    unverified_refs: List[str]
    accuracy: float


def _extract_law_references(text: str) -> List[str]:
    """
    텍스트에서 법령/조문 참조를 추출합니다.

    Args:
        text: 검색할 텍스트

    Returns:
        발견된 법령/조문 참조 리스트 (중복 제거)
    """
    references = set()

    for pattern in LAW_REFERENCE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            if isinstance(match, tuple):
                # 그룹이 여러 개인 경우 (예: 제X조 제Y항)
                ref = ''.join(str(m) for m in match if m)
            else:
                ref = match
            if ref:
                references.add(ref.strip())

    return list(references)


def verify_citation_accuracy(
    answer: str,
    retrieved_chunks: List[Dict],
    strict_mode: bool = False
) -> CitationVerifyResult:
    """
    인용 정확성 검증 (Hallucination 방지)

    답변에서 인용된 법령/조문이 실제 검색된 문서에 존재하는지 확인합니다.
    검색 결과에 없는 법령을 인용하면 Hallucination으로 마킹합니다.

    Args:
        answer: 생성된 답변 텍스트
        retrieved_chunks: 검색된 문서 청크 리스트 (각 청크는 'content' 키 포함)
        strict_mode: True면 모든 인용이 검증되어야 통과

    Returns:
        CitationVerifyResult: 인용 검증 결과
    """
    if not answer:
        return CitationVerifyResult(
            passed=True,
            cited_refs=[],
            verified_refs=[],
            unverified_refs=[],
            accuracy=1.0
        )

    # 1. 답변에서 법령/조문 참조 추출
    cited_refs = _extract_law_references(answer)

    if not cited_refs:
        # 법령 인용이 없으면 검증 불필요
        return CitationVerifyResult(
            passed=True,
            cited_refs=[],
            verified_refs=[],
            unverified_refs=[],
            accuracy=1.0
        )

    # 2. 검색된 청크에서 법령/조문 참조 추출
    source_refs = set()
    for chunk in retrieved_chunks:
        content = chunk.get('content', '') or chunk.get('text', '') or str(chunk)
        chunk_refs = _extract_law_references(content)
        source_refs.update(chunk_refs)

    # 3. 인용 검증: 답변의 인용이 검색 결과에 존재하는지 확인
    verified_refs = []
    unverified_refs = []

    for ref in cited_refs:
        # 정규화된 매칭 (숫자 부분만 비교)
        ref_normalized = re.sub(r'\s+', '', ref)
        found = False

        for source_ref in source_refs:
            source_normalized = re.sub(r'\s+', '', source_ref)
            # 부분 매칭 허용 (예: "17" in "제17조")
            if ref_normalized in source_normalized or source_normalized in ref_normalized:
                found = True
                break

        if found:
            verified_refs.append(ref)
        else:
            unverified_refs.append(ref)

    # 4. 정확도 계산
    if cited_refs:
        accuracy = len(verified_refs) / len(cited_refs)
    else:
        accuracy = 1.0

    # 5. 통과 여부 결정
    if strict_mode:
        passed = len(unverified_refs) == 0
    else:
        # 관대 모드: 50% 이상 검증되면 통과
        passed = accuracy >= 0.5

    return CitationVerifyResult(
        passed=passed,
        cited_refs=cited_refs,
        verified_refs=verified_refs,
        unverified_refs=unverified_refs,
        accuracy=accuracy
    )


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

    # 4. 인용 정확성 검사 (Hallucination 방지)
    citation_verify = verify_citation_accuracy(draft_answer, sources)
    if not citation_verify.passed and citation_verify.unverified_refs:
        # 검증되지 않은 인용을 위반 목록에 추가
        prohibited_violations.append((
            'Hallucination 의심 (미검증 인용)',
            ', '.join(citation_verify.unverified_refs[:3])
        ))
    
    # 위반 메시지 생성
    violation_messages = _build_violation_messages(
        prohibited_violations, has_citation, has_evidence
    )
    
    # 결과 판정
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


# ========================================
# v2: Violation 상세 정보 + 재생성 루프 지원
# ========================================

def _build_violation_details(
    prohibited_violations: List[Tuple[str, str]],
    has_citation: bool,
    has_evidence: bool,
    citation_verify: CitationVerifyResult
) -> List[Dict]:
    """
    v2 Violation 상세 정보 리스트를 생성합니다.

    Returns:
        List of Violation dicts
    """
    violations = []

    # 1. 금지 표현 위반
    for description, match_text in prohibited_violations:
        violations.append({
            'type': 'prohibited_expression',
            'description': f"금지 표현 발견: {description}",
            'location': match_text[:100] if match_text else '',
            'severity': 'critical' if '법적' in description or '확실' in description else 'warning',
            'suggestion': SOFTENING_PHRASES.get(match_text, '~할 수 있습니다')[:50] if match_text else None,
        })

    # 2. Hallucination 의심 (미검증 인용)
    if not citation_verify.passed and citation_verify.unverified_refs:
        violations.append({
            'type': 'hallucination',
            'description': f"검색 결과에서 확인되지 않은 인용: {', '.join(citation_verify.unverified_refs[:3])}",
            'location': '',
            'severity': 'critical',
            'suggestion': '검색 결과에서 확인된 법령/조문만 인용해주세요.',
        })

    # 3. 출처 표시 부족
    if not has_citation:
        violations.append({
            'type': 'query_mismatch',  # 출처 누락도 정합성 문제로 분류
            'description': '답변에 출처/근거가 명시되어 있지 않습니다.',
            'location': '',
            'severity': 'warning',
            'suggestion': '[출처] 또는 관련 법령/기준을 명시해주세요.',
        })

    # 4. 근거 부족
    if not has_evidence:
        violations.append({
            'type': 'query_mismatch',
            'description': '검색된 근거 자료가 충분하지 않습니다.',
            'location': '',
            'severity': 'warning',
            'suggestion': None,
        })

    return violations


def _build_retry_context(violations: List[Dict], draft_answer: str, retry_count: int) -> Dict:
    """
    AnswerDrafter에 전달할 retry_context를 생성합니다.

    Returns:
        RetryContext dict
    """
    # 위반사항을 간결한 문자열 리스트로 변환
    violation_summaries = [
        f"[{v['type']}] {v['description']}" for v in violations[:5]
    ]

    return {
        'violations': violation_summaries,
        'previous_draft': draft_answer,
        'retry_count': retry_count,
    }


async def review_node_v2(state: Dict, config: Optional[Dict] = None) -> Dict:
    """
    [검토 노드 v2 진입점]

    v2 추가 기능:
    - Violation 상세 정보 (type, description, location, severity, suggestion)
    - retry_context 구성: AnswerDrafter에 위반사항 전달
    - next_agent='retry_generation' 반환으로 재생성 루프 지원

    Args:
        state: ChatState (v2 호환)
        config: RunnableConfig (optional)

    Returns:
        Dict with review 결과, retry_context (필요 시), next_agent
    """
    import time

    start_time = time.time()

    draft_answer = state.get('draft_answer', '')
    query_analysis = state.get('query_analysis', {})
    sources = state.get('sources', [])
    claim_evidence_map = state.get('claim_evidence_map', [])
    cited_cases = state.get('cited_cases', [])
    retry_count = state.get('retry_count', 0)

    query_type = query_analysis.get('query_type', 'dispute')

    # 일반 대화(General)는 검토 스킵 (Fast Path)
    if query_type == 'general':
        return {
            'review': {
                'passed': True,
                'violations': [],
                'final_answer': draft_answer,
                'review_time_ms': (time.time() - start_time) * 1000,
            },
            'final_answer': draft_answer,
        }

    # 1. 금지 표현 검사
    prohibited_violations = _check_prohibited_expressions(draft_answer)

    # 2. 출처 표시 검사
    has_sources = len(sources) > 0
    has_citation = _check_citation_presence(draft_answer, has_sources)

    # 3. 근거 충분성 검사
    has_evidence = _check_evidence_sufficiency(state)

    # 4. 인용 정확성 검사 (Hallucination 방지)
    citation_verify = verify_citation_accuracy(draft_answer, sources)

    # 5. v2: Violation 상세 정보 생성
    violation_details = _build_violation_details(
        prohibited_violations, has_citation, has_evidence, citation_verify
    )

    # 6. 심각한 위반 개수 계산
    critical_count = sum(1 for v in violation_details if v['severity'] == 'critical')

    # 7. 재생성 필요 여부 결정
    # - critical 위반이 있고
    # - 아직 최대 재시도 횟수(1회)에 도달하지 않았을 때
    max_retries = 1  # v2: 최대 1회 재생성
    needs_retry = critical_count > 0 and retry_count < max_retries

    review_time_ms = (time.time() - start_time) * 1000

    if needs_retry:
        # 재생성 필요 → retry_context 생성 + next_agent='retry_generation'
        retry_context = _build_retry_context(violation_details, draft_answer, retry_count)

        return {
            'review': {
                'passed': False,
                'violations': violation_details,
                'final_answer': None,
                'review_time_ms': review_time_ms,
            },
            'retry_context': retry_context,
            'retry_count': retry_count + 1,
            'next_agent': 'retry_generation',  # Supervisor가 이를 보고 재생성 라우팅
        }

    # 8. 경미한 위반은 필터링으로 처리
    filtered_answer = draft_answer
    if prohibited_violations:
        filtered_answer = _filter_prohibited_expressions(draft_answer, prohibited_violations)

    # 9. 통과 여부 결정
    passed = len(violation_details) == 0

    return {
        'review': {
            'passed': passed,
            'violations': violation_details,
            'final_answer': filtered_answer,
            'review_time_ms': review_time_ms,
        },
        'final_answer': filtered_answer,
    }


__all__ = [
    'review_node',
    'review_node_wrapper',
    'review_node_v2',
    'verify_citation_accuracy',
    'CitationVerifyResult',
]
