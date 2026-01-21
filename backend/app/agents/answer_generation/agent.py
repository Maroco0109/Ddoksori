"""
똑소리 프로젝트 - 답변생성 노드
S2-3: RAGGenerator를 활용한 구조화된 답변 생성
S2-4: 제한 모드(FSS/K-Medi) 응답 분기 추가
"""

import os
from typing import Dict, List

from langchain_core.messages import AIMessage

from ...orchestrator.state import ChatState
from ...domain import classify_domain, AGENCY_INFO


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
    return os.getenv('LLM_MODEL', 'gpt-4o-mini')


def _build_general_response(user_query: str) -> str:
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
    from .cache import get_answer_cache
    
    user_query = state.get('user_query', '')
    query_analysis = state.get('query_analysis')
    retrieval = state.get('retrieval')
    query_type = query_analysis.get('query_type', 'dispute') if query_analysis else 'dispute'
    
    if query_analysis and query_type == 'general':
        general_response = _build_general_response(user_query)
        return {
            'draft_answer': general_response,
            'has_sufficient_evidence': True,
            'clarifying_questions': [],
            'messages': [AIMessage(content=general_response)],
        }
    
    classification = classify_domain(user_query)
    if classification.is_restricted:
        return _build_restricted_response(user_query, classification, retrieval or {})
    
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

    draft_answer, model_used, claim_evidence_map = AnswerGenerationFallback.generate_with_fallback(
        query=user_query,
        retrieval=retrieval,
        agency_info=agency_info,
        include_disclaimer=include_disclaimer,
    )
    
    has_evidence = model_used not in ('rule_based', 'safe_fallback')
    
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
