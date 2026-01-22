"""
똑소리 프로젝트 - 답변생성 에이전트 (Answer Generation Agent)

작성일: 2026-01-14
최종 수정: 2026-01-22

[역할 및 책임]
검색된 정보(RetrievalResult)를 바탕으로 사용자에게 제공할 최종 답변 초안(Draft)을 생성합니다.
LLM(GPT-4o, Claude 등)을 활용하여 문맥에 맞는 자연스러운 답변을 작성하며,
답변의 근거(Claim-Evidence Mapping)를 함께 생성하여 신뢰성을 높입니다.

[주요 로직]
1. 일반 대화 처리: "안녕", "고마워" 등 단순 대화는 LLM 없이 규칙 기반으로 즉시 응답.
2. 제한 영역 감지: 금융(FSS), 의료(K-Medi) 등 특수 전문 영역은 정보 제공만 하고 법적 판단을 회피(Restricted Response).
3. 답변 생성 (Fallback): LLM 호출 실패 시 백업 로직(Rule-based)으로 안전한 답변 생성.
4. 캐싱: 동일한 질문에 대해 빠르게 응답하기 위한 답변 캐시 적용.
"""

import os
from typing import Dict, List

from langchain_core.messages import AIMessage

from ...orchestrator.state import ChatState
from ...domain import classify_domain, AGENCY_INFO


# 제한된 영역(금융, 의료 등)에 대한 고정 응답 템플릿
# 법적 책임 회피를 위해 LLM 생성 대신 미리 정의된 안전한 문구를 사용합니다.
RESTRICTED_RESPONSE_TEMPLATE = """
본 답변은 정보 제공 목적이며 법률 자문이 아닙니다.

## 주의: 전문가 상담이 필요한 영역입니다

**{agency_full_name}** 관련 분쟁으로 판단됩니다.

### 1. 담당 기관 정보
- **기관**: {agency_full_name}
- **웹사이트**: {agency_url}
- **분야**: {agency_description}

### 2. 관련 유사 사례
{similar_cases_section}

### 3. 권장 다음 단계
1. 전문가(변호사, 해당 분야 상담사)와 상담
2. 관련 서류 및 증빙자료 정리
3. {agency_name}에 정식 상담/조정 신청 검토

---
**{restriction_reason}**

본 서비스는 {agency_description} 분쟁에 대해 정보 제공만 가능하며, 구체적인 법률 판단이나 조정 결과를 예측하지 않습니다.
""".strip()


def _get_llm_model() -> str:
    """사용할 LLM 모델명 반환"""
    return os.getenv('LLM_MODEL', 'gpt-4o-mini')


def _build_general_response(user_query: str) -> str:
    """
    일반 대화(인사, 감사)에 대한 규칙 기반 응답 생성
    LLM 비용 절감을 위해 단순 패턴 매칭 사용.
    """
    greetings = ['안녕', '반가', 'hello', 'hi']
    thanks = ['감사', '고마', 'thanks', 'thank']
    
    query_lower = user_query.lower()
    
    for g in greetings:
        if g in query_lower:
            return "안녕하세요! 저는 소비자 분쟁 상담을 도와드리는 똑소리입니다. 궁금하신 분쟁 관련 사항이 있으시면 말씀해 주세요."
    
    for t in thanks:
        if t in query_lower:
            return "도움이 되셨다면 다행이에요. 추가로 궁금하신 사항이 있으시면 언제든 물어봐 주세요!"
    
    return "네, 무엇을 도와드릴까요? 소비자 분쟁 관련 상담을 원하시면 자세한 상황을 알려주세요."


def _format_similar_cases(disputes: List[Dict], counsels: List[Dict]) -> str:
    """유사 사례 목록을 마크다운 리스트로 포맷팅"""
    if not disputes and not counsels:
        return "관련 사례가 없습니다."
    
    lines = []
    
    if disputes:
        lines.append("**분쟁조정사례**")
        for i, case in enumerate(disputes[:2], 1):
            title = case.get('doc_title', '제목 없음')
            org = case.get('source_org', '')
            lines.append(f"{i}. [{org}] {title}")
    
    if counsels:
        if lines:
            lines.append("")
        lines.append("**상담사례 (참고용)**")
        for i, case in enumerate(counsels[:2], 1):
            title = case.get('doc_title', '제목 없음')
            lines.append(f"{i}. {title}")
    
    return "\n".join(lines)


def _build_restricted_response(
    user_query: str,
    classification_result,
    retrieval,
) -> Dict:
    """제한된 영역(Restricted Domain)에 대한 안전한 응답 생성"""
    agency_code = classification_result.agency
    agency_info = AGENCY_INFO.get(agency_code, AGENCY_INFO['KCA'])
    
    disputes = retrieval.get('disputes', [])[:2] if retrieval else []
    counsels = retrieval.get('counsels', [])[:2] if retrieval else []
    
    similar_cases_section = _format_similar_cases(disputes, counsels)
    
    answer = RESTRICTED_RESPONSE_TEMPLATE.format(
        agency_name=agency_info.get('name', ''),
        agency_full_name=agency_info.get('full_name', ''),
        agency_url=agency_info.get('url', ''),
        agency_description=agency_info.get('description', ''),
        similar_cases_section=similar_cases_section,
        restriction_reason=agency_info.get('restriction_reason', ''),
    )
    
    return {
        'draft_answer': answer,
        'final_answer': answer,
        'has_sufficient_evidence': False,
        'clarifying_questions': [],
        'messages': [AIMessage(content=answer)],
        'is_restricted': True,
        'agency_code': agency_code,
    }


def generation_node(state: ChatState) -> Dict:
    """
    [답변생성 노드 진입점]
    
    1. 일반 대화 처리: Query Analysis 결과가 'general'이면 규칙 기반 응답.
    2. 제한 영역 확인: 금융/의료 등 특수 분야는 Restricted Response 반환.
    3. 검색 결과 확인: 결과가 없으면 추가 정보 요청.
    4. 캐시 확인: 동일 질문에 대한 캐시된 답변 반환.
    5. 답변 생성: LLM(AnswerGenerationFallback)을 사용하여 초안 생성.
    """
    from .cache import get_answer_cache
    
    user_query = state.get('user_query', '')
    query_analysis = state.get('query_analysis')
    retrieval = state.get('retrieval')
    query_type = query_analysis.get('query_type', 'dispute') if query_analysis else 'dispute'
    
    # 1. 일반 대화 처리
    if query_analysis and query_type == 'general':
        general_response = _build_general_response(user_query)
        return {
            'draft_answer': general_response,
            'has_sufficient_evidence': True,
            'clarifying_questions': [],
            'messages': [AIMessage(content=general_response)],
        }
    
    # 2. 도메인 분류 및 제한 영역 처리
    classification = classify_domain(user_query)
    if classification.is_restricted:
        return _build_restricted_response(user_query, classification, retrieval or {})
    
    # 3. 검색 결과 없음 처리
    if not retrieval:
        no_result_msg = "죄송합니다. 관련 정보를 찾을 수 없습니다. 질문을 더 구체적으로 작성해 주시면 도움이 될 것 같습니다."
        return {
            'draft_answer': no_result_msg,
            'has_sufficient_evidence': False,
            'clarifying_questions': [
                "어떤 제품/서비스에 대한 분쟁인가요?",
                "언제 구매하셨나요?",
                "어떤 문제가 발생했나요?"
            ],
            'messages': [AIMessage(content=no_result_msg)],
        }
    
    # 4. 캐시 확인
    cache = get_answer_cache()
    cached = cache.get(user_query, query_type)
    if cached:
        return {
            'draft_answer': cached['answer'],
            'has_sufficient_evidence': cached.get('has_evidence', True),
            'clarifying_questions': [],
            'claim_evidence_map': cached.get('claim_evidence_map', []),
            'messages': [AIMessage(content=cached['answer'])],
            'generation_model_used': 'cache',
            '_cache_hit': True,
        }
    
    # 5. LLM 답변 생성 (Fallback 포함)
    from .fallback import AnswerGenerationFallback
    
    agency_info = retrieval.get('agency', {})
    if not agency_info:
        agency_info = {
            'agency': 'KCA',
            'agency_info': {
                'name': '한국소비자원',
                'full_name': '한국소비자원 소비자분쟁조정위원회',
                'description': '일반 소비자 분쟁 조정',
                'url': 'https://www.kca.go.kr'
            },
            'dispute_type': '1:N',
            'reason': '일반 소비자 분쟁으로 판단됩니다',
            'confidence': 0.7
        }
    
    mode = state.get('mode', 'NEED_RAG')
    include_disclaimer = (mode == 'NEED_RAG')

    # LLM 호출 (실패 시 Fallback)
    draft_answer, model_used, claim_evidence_map = AnswerGenerationFallback.generate_with_fallback(
        query=user_query,
        retrieval=retrieval,
        agency_info=agency_info,
        include_disclaimer=include_disclaimer,
    )
    
    has_evidence = model_used not in ('rule_based', 'safe_fallback')
    
    # 캐시 저장
    cache.set(user_query, query_type, {
        'answer': draft_answer,
        'claim_evidence_map': claim_evidence_map,
        'has_evidence': has_evidence,
    })
    
    return {
        'draft_answer': draft_answer,
        'has_sufficient_evidence': has_evidence,
        'clarifying_questions': [],
        'claim_evidence_map': claim_evidence_map,
        'messages': [AIMessage(content=draft_answer)],
        'generation_model_used': model_used,
        '_cache_hit': False,
    }
