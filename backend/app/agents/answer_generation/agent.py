"""
똑소리 프로젝트 - 답변생성 에이전트 (Answer Generation Agent)

작성일: 2026-01-14
최종 수정: 2026-01-28 (v2: 사례 인용 + retry_context 지원)

[역할 및 책임]
검색된 정보(RetrievalResult)를 바탕으로 사용자에게 제공할 최종 답변 초안(Draft)을 생성합니다.
LLM(GPT-4o, Claude 등)을 활용하여 문맥에 맞는 자연스러운 답변을 작성하며,
답변의 근거(Claim-Evidence Mapping)를 함께 생성하여 신뢰성을 높입니다.

[주요 로직]
1. 일반 대화 처리: "안녕", "고마워" 등 단순 대화는 LLM 없이 규칙 기반으로 즉시 응답.
2. 전문기관 도메인 처리 (Phase 9): 금융, 의료, 개인정보, 부동산, 건설 도메인은 전문기관 안내 + 유사 사례 제공.
3. 답변 생성 (Fallback): LLM 호출 실패 시 백업 로직(Rule-based)으로 안전한 답변 생성.
4. 캐싱: 동일한 질문에 대해 빠르게 응답하기 위한 답변 캐시 적용.

[v2 추가 기능]
- retry_context 처리: LegalReviewer 재생성 요청 시 위반사항 참고
- CitedCase 생성: 인용된 사례 정보 구조화
"""

import os
from typing import Dict, List, AsyncGenerator, Any

from langchain_core.messages import AIMessage
from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.runnables import RunnableConfig

from ...supervisor.state import ChatState
from ...domain import classify_domain, AGENCY_INFO
from .cache import get_answer_cache
from .fallback import AnswerGenerationFallback
from ...common.config import get_config
from ..retrieval.sufficiency import RetrievalSufficiencyChecker


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

# Phase 9: 전문기관 도메인 응답 템플릿
# query_analysis에서 restricted로 분류된 경우 사용
SPECIALIST_AGENCY_RESPONSE_TEMPLATE = """
안녕하세요, 똑소리입니다.

질문하신 내용은 **{domain_name}** 분야로, 전문 분쟁조정기관의 도움이 필요한 영역입니다.

## 담당 전문기관 안내

| 항목 | 내용 |
|------|------|
| **기관명** | {agency_name} |
| **상위기관** | {organization} |
| **홈페이지** | {url} |
| **대표전화** | {phone} |

{similar_cases_section}

## 권장 절차

1. **자료 준비**: 계약서, 영수증, 대화 기록 등 관련 증빙자료를 정리해주세요.
2. **전문기관 상담**: 위 기관에 연락하여 상담을 받아보세요.
3. **분쟁조정 신청**: 필요시 공식 분쟁조정을 신청하실 수 있습니다.

---
> 본 서비스는 일반 소비자 분쟁(한국소비자원, 전자거래분쟁조정위원회 관할)을 전문으로 합니다.
> {domain_name} 분야는 위 전문기관에서 더 정확한 안내를 받으실 수 있습니다.
""".strip()

# 도메인별 한국어 명칭 매핑
DOMAIN_KOREAN_NAMES = {
    "finance": "금융",
    "medical": "의료",
    "privacy": "개인정보",
    "realestate": "부동산 임대차",
    "construction": "건설/건축",
}

# === Progressive Disclosure Phase Templates ===

PHASE_CASE_SUMMARY_FOLLOWUP = """
{main_content}

---
**관련 법령과 분쟁해결기준도 상세히 알려드릴까요?** 해당 상황에 적용되는 법적 근거를 확인하실 수 있습니다.
""".strip()

PHASE_LAW_DETAIL_FOLLOWUP = """
{main_content}

---
**분쟁 해결 절차(한국소비자원, 전자거래분쟁조정 등)도 안내해 드릴까요?** 직접 분쟁조정을 신청하시는 방법을 알려드릴 수 있습니다.
""".strip()

PHASE_PROCEDURE_TEMPLATE = """
## 분쟁 해결 절차 안내

### 1. 한국소비자원 (KCA)
- **대표전화**: 1372
- **홈페이지**: https://www.kca.go.kr
- **신청 방법**:
  1. 소비자상담센터(1372) 전화상담
  2. 홈페이지 온라인 상담/분쟁조정 신청
  3. 방문상담 (전국 소비자원 지부)

### 2. 전자거래분쟁조정위원회 (ECMC)
- **관할**: 온라인 쇼핑, 전자상거래 분쟁
- **홈페이지**: https://www.ecmc.or.kr
- **신청 방법**: 온라인 분쟁조정 신청서 제출

### 3. 준비 서류
- 계약서, 영수증, 결제 내역
- 판매자와의 대화 기록 (문자, 이메일, 채팅)
- 제품 사진, 하자 증빙 자료

### 4. 분쟁조정 진행 과정
1. **상담 신청** → 2. **사실 조사** → 3. **조정안 제시** → 4. **수락/거부** → 5. **조정 성립/불성립**

---
> 분쟁조정위원회의 조정안에 양측이 동의하면 재판상 화해와 같은 효력이 발생합니다.
""".strip()

PHASE_COMPLETED_TEMPLATE = """
도움이 되셨기를 바랍니다. 추가로 궁금하신 소비자 분쟁 사항이 있으시면 언제든 말씀해 주세요!
""".strip()

# Legacy aliases (하위호환)
PHASE_CASE_OFFER_TEMPLATE = PHASE_CASE_SUMMARY_FOLLOWUP
PHASE_PROCEDURE_OFFER_TEMPLATE = PHASE_LAW_DETAIL_FOLLOWUP


import logging

logger = logging.getLogger(__name__)


# === Progressive Disclosure 메타 쿼리 응답 템플릿 ===
META_CONVERSATIONAL_TEMPLATE = """안녕하세요, 똑소리입니다! 소비자 분쟁 상담을 도와드립니다.

다음과 같은 정보를 알려주시면 맞춤 상담을 해드릴 수 있어요:

1. **구매한 품목/서비스**: 어떤 제품이나 서비스인가요?
2. **구매 시기**: 언제 구매하셨나요?
3. **문제 상황**: 어떤 문제가 발생했나요? (예: 환불 거부, 제품 불량, 배송 지연 등)
4. **원하시는 해결**: 어떻게 해결되길 원하시나요? (예: 환불, 교환, 수리, 배상 등)

> 예시: "쿠팡에서 산 노트북이 불량인데 환불을 거부당했어요"

편하게 말씀해 주세요!""".strip()

META_CONVERSATIONAL_ONBOARDING_TEMPLATE = """안녕하세요, 똑소리입니다!

**{purchase_item}** 관련으로 상담을 원하시는군요. 좀 더 구체적인 상황을 알려주시면 정확한 도움을 드릴 수 있어요:

1. **문제 상황**: 어떤 문제가 발생했나요?
2. **현재 진행 상황**: 판매자와 이미 연락하셨나요?
3. **원하시는 해결 방법**: 환불, 교환, 수리 중 무엇을 원하시나요?

자세한 상황을 말씀해 주시면 관련 법령과 유사 사례를 바탕으로 해결 방법을 안내해 드리겠습니다.""".strip()

# Progressive Disclosure 요약 응답 후속 질문 생성용
PROGRESSIVE_FOLLOWUP_TEMPLATES = {
    'laws': "관련 법령을 자세히 알려드릴까요?",
    'criteria': "분쟁해결기준(배상/환불 기준)을 확인해보시겠어요?",
    'cases': "비슷한 분쟁 조정 사례 {count}건도 확인해 보시겠어요?",
    'procedure': "분쟁 해결 절차(한국소비자원, 전자거래분쟁조정 등)도 안내해드릴까요?",
}


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


def _format_similar_cases_for_specialist(cases: List[Dict]) -> str:
    """전문기관 응답용 유사 사례 포맷팅 (Phase 9)"""
    if not cases:
        return ""

    lines = ["## 참고: 유사 사례", ""]
    for i, case in enumerate(cases[:3], 1):
        title = case.get('doc_title', '제목 없음')
        org = case.get('source_org', '')
        summary = case.get('summary', case.get('content', ''))[:200]

        lines.append(f"### {i}. {title}")
        if org:
            lines.append(f"- **출처**: {org}")
        if summary:
            lines.append(f"- **요약**: {summary}...")
        lines.append("")

    return "\n".join(lines)


def _build_specialist_agency_response(
    user_query: str,
    query_analysis: Dict,
    retrieval: Dict,
) -> Dict:
    """
    전문기관 도메인 (Phase 9) 응답 생성

    query_analysis에서 restricted로 분류된 경우,
    유사 사례가 있으면 사례 요약 + 전문기관 안내,
    없으면 전문기관 안내만 제공합니다.

    Args:
        user_query: 사용자 질문
        query_analysis: QueryAnalysisResult (restricted_domain, restricted_agency_info 포함)
        retrieval: RetrievalResult (cases 포함)

    Returns:
        Dict with draft_answer, final_answer, etc.
    """
    restricted_domain = query_analysis.get('restricted_domain', 'finance')
    agency_info = query_analysis.get('restricted_agency_info', {})

    # agency_info가 없으면 기본값 사용
    if not agency_info:
        from ..query_analysis.agent import RESTRICTED_DOMAIN_AGENCIES
        agency_info = RESTRICTED_DOMAIN_AGENCIES.get(restricted_domain, {
            'name': '전문분쟁조정위원회',
            'organization': '관할 기관',
            'url': 'https://www.kca.go.kr',
            'phone': '1372',
        })

    domain_name = DOMAIN_KOREAN_NAMES.get(restricted_domain, restricted_domain)

    # 유사 사례 추출 (CaseRetrievalAgent 결과)
    cases = []
    if retrieval:
        cases = retrieval.get('disputes', [])[:3]
        if not cases:
            cases = retrieval.get('counsels', [])[:3]

    similar_cases_section = _format_similar_cases_for_specialist(cases)

    # 응답 생성
    answer = SPECIALIST_AGENCY_RESPONSE_TEMPLATE.format(
        domain_name=domain_name,
        agency_name=agency_info.get('name', '전문기관'),
        organization=agency_info.get('organization', '관할 기관'),
        url=agency_info.get('url', ''),
        phone=agency_info.get('phone', ''),
        similar_cases_section=similar_cases_section,
    )

    return {
        'draft_answer': answer,
        'final_answer': answer,
        'has_sufficient_evidence': len(cases) > 0,
        'clarifying_questions': [],
        'messages': [AIMessage(content=answer)],
        'is_restricted': True,
        'restricted_domain': restricted_domain,
        'generation_model_used': 'specialist_template',
    }


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


async def generation_node(state: ChatState, config: RunnableConfig = None) -> Dict:
    """
    [답변생성 노드 진입점]

    1. 일반 대화 처리: Query Analysis 결과가 'general'이면 규칙 기반 응답.
    2. 제한 영역 확인: 금융/의료 등 특수 분야는 Restricted Response 반환.
    3. 검색 결과 확인: 결과가 없으면 추가 정보 요청.
    4. 캐시 확인: 동일 질문에 대한 캐시된 답변 반환.
    5. 답변 생성: LLM(AnswerGenerationFallback)을 사용하여 초안 생성.

    Args:
        state: ChatState from supervisor graph
        config: RunnableConfig for streaming mode detection (if callbacks present, emit custom events)
    """
    user_query = state.get('user_query', '')
    query_analysis = state.get('query_analysis')
    retrieval = state.get('retrieval')
    query_type = query_analysis.get('query_type', 'dispute') if query_analysis else 'dispute'

    # Detect streaming mode
    is_streaming = config and config.get('callbacks') is not None
    
    # 1. 일반 대화 처리
    if query_analysis and query_type == 'general':
        general_response = _build_general_response(user_query)
        return {
            'draft_answer': general_response,
            'has_sufficient_evidence': True,
            'clarifying_questions': [],
            'messages': [AIMessage(content=general_response)],
        }

    # 2. Phase 9: 전문기관 도메인 처리 (query_type == 'restricted')
    if query_analysis and query_type == 'restricted':
        return _build_specialist_agency_response(
            user_query=user_query,
            query_analysis=query_analysis,
            retrieval=retrieval or {},
        )

    # 3. 도메인 분류 및 제한 영역 처리 (Legacy - classify_domain 기반)
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

    # Track 2: 유연한 답변 형식 지원
    app_config = get_config()
    use_flexible_format = (app_config.chatbot_features.answer_format_mode == 'flexible')

    # LLM 호출 (실패 시 Fallback)
    # Streaming mode: emit custom events during generation
    # Non-streaming mode: use blocking generate_with_fallback
    if is_streaming:
        # Emit tokens as custom events during LLM generation
        full_answer = ""
        model_used = "unknown"
        claim_evidence_map = []

        async for event in AnswerGenerationFallback.generate_with_fallback_streaming(
            query=user_query,
            retrieval=retrieval,
            agency_info=agency_info,
            include_disclaimer=include_disclaimer
        ):
            event_type = event.get('type')

            if event_type == 'token':
                # Emit individual token
                await adispatch_custom_event(
                    'generation_token',
                    {'content': event['content'], 'model': event.get('model', 'unknown')},
                    config=config
                )
                full_answer += event['content']

            elif event_type == 'fallback':
                # Emit fallback notification
                await adispatch_custom_event(
                    'generation_fallback',
                    {'model': event['model'], 'message': f"{event['model']}로 전환중..."},
                    config=config
                )

            elif event_type == 'complete':
                # Final answer assembled
                full_answer = event['content']
                model_used = event.get('model', 'unknown')
                claim_evidence_map = event.get('claim_evidence_map', [])

            elif event_type == 'error':
                # Emit error event
                await adispatch_custom_event(
                    'generation_error',
                    {'message': event.get('message', 'Unknown error')},
                    config=config
                )

        draft_answer = full_answer
    else:
        # Non-streaming mode: blocking call
        draft_answer, model_used, claim_evidence_map = AnswerGenerationFallback.generate_with_fallback(
            query=user_query,
            retrieval=retrieval,
            agency_info=agency_info,
            include_disclaimer=include_disclaimer,
        )

    has_evidence = model_used not in ('rule_based', 'safe_fallback')

    # Track 2: 후속 질문 생성
    followup_questions = []
    clarifying_questions = []

    if app_config.chatbot_features.enable_followup_questions and query_analysis:
        from ..followup import FollowupQuestionGenerator

        followup_generator = FollowupQuestionGenerator()
        questions_result = followup_generator.generate_questions(
            query_analysis=query_analysis,
            retrieval=retrieval,
            answer=draft_answer
        )
        followup_questions = questions_result.get('followup_questions', [])
        clarifying_questions = questions_result.get('clarifying_questions', [])

    # 캐시 저장
    cache.set(user_query, query_type, {
        'answer': draft_answer,
        'claim_evidence_map': claim_evidence_map,
        'has_evidence': has_evidence,
        'followup_questions': followup_questions,
        'clarifying_questions': clarifying_questions,
    })

    return {
        'draft_answer': draft_answer,
        'has_sufficient_evidence': has_evidence,
        'clarifying_questions': clarifying_questions,
        'followup_questions': followup_questions,
        'claim_evidence_map': claim_evidence_map,
        'messages': [AIMessage(content=draft_answer)],
        'generation_model_used': model_used,
        '_cache_hit': False,
    }


# ========================================
# 토큰 스트리밍 지원 (2026-01-28)
# ========================================

async def generation_node_streaming(state: ChatState) -> AsyncGenerator[Dict[str, Any], None]:
    """답변 생성 노드 (스트리밍 버전)

    Yields:
        Dict with streaming events: {'type': 'token'|'fallback'|'complete'|'error', ...}
    """
    user_query = state.get('user_query', '')
    query_analysis = state.get('query_analysis')
    retrieval = state.get('retrieval')
    query_type = query_analysis.get('query_type', 'dispute') if query_analysis else 'dispute'

    # 1. 일반 대화 처리
    if query_analysis and query_type == 'general':
        response = _build_general_response(user_query)
        yield {'type': 'complete', 'content': response, 'model': 'rule_based', 'claim_evidence_map': []}
        return

    # 2. Phase 9: 전문기관 도메인 처리 (query_type == 'restricted')
    if query_analysis and query_type == 'restricted':
        restricted_result = _build_specialist_agency_response(
            user_query=user_query,
            query_analysis=query_analysis,
            retrieval=retrieval or {},
        )
        yield {'type': 'complete', 'content': restricted_result['draft_answer'], 'model': 'specialist_template', 'claim_evidence_map': []}
        return

    # 3. 도메인 분류 및 제한 영역 처리 (Legacy)
    classification = classify_domain(user_query)
    if classification.is_restricted:
        restricted_result = _build_restricted_response(user_query, classification, retrieval or {})
        yield {'type': 'complete', 'content': restricted_result['draft_answer'], 'model': 'restricted', 'claim_evidence_map': []}
        return

    # 3. 검색 결과 없음 처리
    if not retrieval:
        no_result_msg = "죄송합니다. 관련 정보를 찾을 수 없습니다. 질문을 더 구체적으로 작성해 주시면 도움이 될 것 같습니다."
        yield {'type': 'complete', 'content': no_result_msg, 'model': 'no_retrieval', 'claim_evidence_map': []}
        return

    # 4. LLM 스트리밍 답변 생성
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

    async for event in AnswerGenerationFallback.generate_with_fallback_streaming(
        query=user_query,
        retrieval=retrieval,
        agency_info=agency_info,
        include_disclaimer=include_disclaimer
    ):
        yield event


# ========================================
# Progressive Disclosure 헬퍼 함수 (Phase C+E)
# ========================================

def _build_available_details(retrieval: Dict) -> Dict:
    """
    검색 결과에서 아직 제공하지 않은 상세 정보 메타데이터를 추출합니다.

    Progressive Disclosure의 핵심: 사용자에게 어떤 정보가 더 있는지 알려주어
    필요한 정보만 선택적으로 요청할 수 있게 합니다.

    Args:
        retrieval: RetrievalResult dict

    Returns:
        available_details dict with section counts and previews
    """
    details = {}

    laws = retrieval.get('laws', [])
    if laws:
        preview_titles = [l.get('doc_title', '') for l in laws[:2]]
        details['laws'] = {
            'count': len(laws),
            'preview': ', '.join(t for t in preview_titles if t) or '관련 법령',
        }

    criteria = retrieval.get('criteria', [])
    if criteria:
        preview_titles = [c.get('doc_title', '') for c in criteria[:2]]
        details['criteria'] = {
            'count': len(criteria),
            'preview': ', '.join(t for t in preview_titles if t) or '분쟁해결기준',
        }

    cases = retrieval.get('disputes', []) + retrieval.get('counsels', [])
    if cases:
        details['cases'] = {
            'count': len(cases),
            'preview': f"유사 조정사례 {len(cases)}건",
        }

    return details


def _build_progressive_summary(
    draft_answer: str,
    retrieval: Dict,
    max_length: int = 200,
) -> str:
    """
    전체 답변에서 핵심 요약만 추출합니다 (minimal 모드).

    규칙 기반 추출:
    1. draft_answer의 첫 문단 (또는 첫 200자)
    2. 마크다운 헤딩(##) 제거, 핵심 문장만 유지

    Args:
        draft_answer: LLM이 생성한 전체 답변
        retrieval: RetrievalResult (요약 보강용)
        max_length: 요약 최대 길이

    Returns:
        요약된 답변 문자열
    """
    if not draft_answer:
        return "관련 정보를 찾았습니다. 상세 내용을 확인해보시겠어요?"

    # 마크다운 헤딩/구분선 제거
    import re
    lines = draft_answer.split('\n')
    content_lines = []
    for line in lines:
        stripped = line.strip()
        # 헤딩, 구분선, 빈 줄 건너뛰기
        if stripped.startswith('#') or stripped.startswith('---') or stripped.startswith('> 본 답변'):
            continue
        if stripped:
            content_lines.append(stripped)

    summary = ' '.join(content_lines)

    # max_length로 자르되 문장 단위로
    if len(summary) > max_length:
        # 마지막 완성된 문장까지 자르기
        truncated = summary[:max_length]
        last_period = max(truncated.rfind('.'), truncated.rfind('다.'), truncated.rfind('요.'))
        if last_period > max_length // 2:
            summary = truncated[:last_period + 1]
        else:
            summary = truncated.rstrip() + '...'

    return summary


def _build_progressive_followups(retrieval: Dict, available_details: Dict) -> list:
    """
    available_details 기반으로 구체적인 후속 질문을 생성합니다.

    Args:
        retrieval: RetrievalResult
        available_details: _build_available_details() 결과

    Returns:
        후속 질문 리스트 (최대 3개)
    """
    questions = []

    if 'laws' in available_details or 'criteria' in available_details:
        questions.append(PROGRESSIVE_FOLLOWUP_TEMPLATES['laws'])

    if 'cases' in available_details:
        count = available_details['cases']['count']
        questions.append(PROGRESSIVE_FOLLOWUP_TEMPLATES['cases'].format(count=count))

    questions.append(PROGRESSIVE_FOLLOWUP_TEMPLATES['procedure'])

    return questions[:3]


def _meta_conversational_response(state: Dict) -> Dict:
    """
    메타 대화 쿼리에 대한 가이드 응답을 생성합니다 (Phase E-2).

    "뭘 물어봐야 할까?", "도와줘" 같은 메타 수준의 질문에 대해
    RAG 검색 없이 가이드 응답을 생성합니다.

    minimal 모드: 규칙 기반 템플릿
    adaptive 모드: 온보딩 정보 참고한 맞춤 가이드 (현재는 규칙 기반)

    Args:
        state: ChatState

    Returns:
        generation 노드 결과 Dict
    """
    import time
    from langchain_core.messages import AIMessage

    start_time = time.time()
    onboarding = state.get('onboarding') or {}
    purchase_item = onboarding.get('purchase_item', '')

    if purchase_item:
        response = META_CONVERSATIONAL_ONBOARDING_TEMPLATE.format(
            purchase_item=purchase_item,
        )
    else:
        response = META_CONVERSATIONAL_TEMPLATE

    return {
        'draft_answer': response,
        'final_answer': response,
        'claim_evidence_map': [],
        'cited_cases': [],
        'has_sufficient_evidence': True,
        'retrieval_confidence': 1.0,
        'followup_questions': [],
        'response_depth': 'full',
        'available_details': None,
        'generation_time_ms': (time.time() - start_time) * 1000,
        'messages': [AIMessage(content=response)],
        'generation_model_used': 'meta_conversational_template',
    }


def _filter_retrieval_for_detail(retrieval: Dict, detail_type: str) -> Dict:
    """
    전체 retrieval 결과에서 요청된 섹션만 필터링합니다.

    Args:
        retrieval: 전체 RetrievalResult
        detail_type: 요청된 상세 유형 ('laws', 'cases', 'criteria', 'full')

    Returns:
        필터링된 retrieval dict
    """
    if detail_type == 'full':
        return retrieval

    filtered = {}

    if detail_type == 'laws':
        filtered['laws'] = retrieval.get('laws', [])
        filtered['criteria'] = retrieval.get('criteria', [])
    elif detail_type == 'criteria':
        filtered['criteria'] = retrieval.get('criteria', [])
    elif detail_type == 'cases':
        filtered['disputes'] = retrieval.get('disputes', [])
        filtered['counsels'] = retrieval.get('counsels', [])

    # 원본의 agency 정보 보존
    if 'agency' in retrieval:
        filtered['agency'] = retrieval['agency']

    return filtered


def _followup_detail_response(state: Dict, config=None) -> Dict:
    """
    후속 질문에 대한 상세 응답을 생성합니다 (Phase D).

    이전 턴의 검색 결과(_last_turn_context.retrieval)를 재활용하여
    요청된 섹션(법령/사례/기준/절차)의 상세 정보만 제공합니다.

    Args:
        state: ChatState
        config: RunnableConfig

    Returns:
        generation 노드 결과 Dict (response_depth='detail')
    """
    import time
    from langchain_core.messages import AIMessage

    start_time = time.time()

    user_query = state.get('user_query', '')
    last_turn_context = state.get('_last_turn_context') or {}
    cached_retrieval = last_turn_context.get('retrieval') or {}
    available_details = last_turn_context.get('available_details') or {}

    # Detect which section the user is asking about
    from ..query_analysis.detectors import detect_requested_detail_type
    detail_type = detect_requested_detail_type(user_query, available_details)

    logger.info(f"[Generation] FOLLOWUP_WITH_CONTEXT: detail_type={detail_type}")

    # 절차 안내 요청
    if detail_type == 'procedure':
        response = PHASE_PROCEDURE_TEMPLATE
        return {
            'draft_answer': response,
            'claim_evidence_map': [],
            'cited_cases': [],
            'has_sufficient_evidence': True,
            'retrieval_confidence': 1.0,
            'followup_questions': [],
            'response_depth': 'detail',
            'available_details': None,  # 절차 후에는 남은 상세 없음
            'generation_time_ms': (time.time() - start_time) * 1000,
            'messages': [AIMessage(content=response)],
            'generation_model_used': 'procedure_template',
        }

    # 캐시된 retrieval이 없으면 fallback
    if not cached_retrieval:
        fallback_msg = "죄송합니다. 이전 검색 결과를 찾을 수 없습니다. 질문을 다시 입력해 주세요."
        return {
            'draft_answer': fallback_msg,
            'claim_evidence_map': [],
            'cited_cases': [],
            'has_sufficient_evidence': False,
            'retrieval_confidence': 0.0,
            'followup_questions': [],
            'response_depth': 'detail',
            'available_details': None,
            'generation_time_ms': (time.time() - start_time) * 1000,
            'messages': [AIMessage(content=fallback_msg)],
            'generation_model_used': 'followup_no_cache',
        }

    # 요청된 섹션만 포함하는 필터링된 retrieval 구성
    filtered_retrieval = _filter_retrieval_for_detail(cached_retrieval, detail_type)

    # LLM으로 상세 답변 생성
    agency_info = cached_retrieval.get('agency', {
        'agency': 'KCA',
        'agency_info': {
            'name': '한국소비자원',
            'full_name': '한국소비자원 소비자분쟁조정위원회',
            'description': '일반 소비자 분쟁 조정',
            'url': 'https://www.kca.go.kr'
        },
    })

    # Get onboarding for context
    onboarding = state.get('onboarding') or {}

    draft_answer, model_used, claim_evidence_map = AnswerGenerationFallback.generate_with_fallback(
        query=user_query,
        retrieval=filtered_retrieval,
        agency_info=agency_info,
        include_disclaimer=True,
        onboarding=onboarding,
    )

    cited_cases = _extract_cited_cases(filtered_retrieval)
    has_evidence = model_used not in ('rule_based', 'safe_fallback')

    # 남은 상세 정보 계산 (이미 제공한 섹션 제외)
    remaining_details = {k: v for k, v in available_details.items() if k != detail_type}
    remaining_followups = _build_progressive_followups(cached_retrieval, remaining_details)

    return {
        'draft_answer': draft_answer,
        'claim_evidence_map': claim_evidence_map,
        'cited_cases': cited_cases,
        'has_sufficient_evidence': has_evidence,
        'retrieval_confidence': 0.8,  # 캐시 사용이므로 고정값
        'followup_questions': remaining_followups,
        'response_depth': 'detail',
        'available_details': remaining_details if remaining_details else None,
        'retrieval': filtered_retrieval,  # retrieval state도 업데이트
        'generation_time_ms': (time.time() - start_time) * 1000,
        'messages': [AIMessage(content=draft_answer)],
        'generation_model_used': model_used,
    }


def _progressive_summary_response(state: Dict, config=None) -> Dict:
    """
    Progressive Disclosure 요약 응답을 생성합니다 (Phase C+E).

    1. 기존 LLM 답변 생성 (전체)
    2. 요약만 추출하여 사용자에게 제공
    3. available_details로 상세 정보 안내
    4. 후속 질문으로 상세 요청 유도

    Args:
        state: ChatState
        config: RunnableConfig

    Returns:
        generation 노드 결과 Dict (response_depth='summary')
    """
    import time
    from langchain_core.messages import AIMessage

    start_time = time.time()

    user_query = state.get('user_query', '')
    query_analysis = state.get('query_analysis', {})
    retrieval = state.get('retrieval', {})
    retry_context = state.get('retry_context')

    # 검색 결과 없음
    if not retrieval:
        no_result_msg = "죄송합니다. 관련 정보를 찾을 수 없습니다. 질문을 더 구체적으로 작성해 주시면 도움이 될 것 같습니다."
        return {
            'draft_answer': no_result_msg,
            'claim_evidence_map': [],
            'cited_cases': [],
            'has_sufficient_evidence': False,
            'retrieval_confidence': 0.0,
            'response_depth': 'summary',
            'available_details': None,
            'generation_time_ms': (time.time() - start_time) * 1000,
            'clarifying_questions': ["어떤 제품/서비스에 대한 분쟁인가요?", "어떤 문제가 발생했나요?"],
            'messages': [AIMessage(content=no_result_msg)],
        }

    # Sufficiency Check
    checker = RetrievalSufficiencyChecker()
    suf_result = checker.evaluate(retrieval)
    retrieval_confidence = suf_result.confidence

    if suf_result.level == 'insufficient':
        insufficient_msg = f"죄송합니다. 검색된 정보가 충분하지 않아 정확한 답변을 드리기 어렵습니다.\n\n{suf_result.reason}"
        for i, q in enumerate(suf_result.clarifying_questions, 1):
            insufficient_msg += f"\n{i}. {q}"
        return {
            'draft_answer': insufficient_msg,
            'claim_evidence_map': [],
            'cited_cases': [],
            'has_sufficient_evidence': False,
            'retrieval_confidence': retrieval_confidence,
            'response_depth': 'summary',
            'available_details': None,
            'clarifying_questions': suf_result.clarifying_questions,
            'generation_time_ms': (time.time() - start_time) * 1000,
            'messages': [AIMessage(content=insufficient_msg)],
            'generation_model_used': 'sufficiency_insufficient',
        }

    # LLM 답변 생성 (전체)
    retry_supplement = None
    if retry_context:
        retry_supplement = _build_retry_prompt_supplement(retry_context)

    agency_info = retrieval.get('agency', {
        'agency': 'KCA',
        'agency_info': {
            'name': '한국소비자원',
            'full_name': '한국소비자원 소비자분쟁조정위원회',
            'description': '일반 소비자 분쟁 조정',
            'url': 'https://www.kca.go.kr'
        },
    })

    mode = state.get('mode', 'NEED_RAG')
    include_disclaimer = (mode == 'NEED_RAG')

    # Get onboarding for context
    onboarding = state.get('onboarding') or {}

    draft_answer, model_used, claim_evidence_map = AnswerGenerationFallback.generate_with_fallback(
        query=user_query,
        retrieval=retrieval,
        agency_info=agency_info,
        include_disclaimer=include_disclaimer,
        retry_supplement=retry_supplement,
        onboarding=onboarding,
    )

    # Progressive Disclosure: 요약 추출 + available_details
    app_config = get_config()
    summary_max_length = app_config.response.summary_max_length

    summary_answer = _build_progressive_summary(draft_answer, retrieval, summary_max_length)
    available_details = _build_available_details(retrieval)

    # Customized follow-up questions based on onboarding
    days = onboarding.get('days_since_purchase')
    purchase_item = onboarding.get('purchase_item', '')

    if days is not None:
        custom_followups = []
        if days <= 14:
            custom_followups.append(f"청약철회 관련 법령을 자세히 알려드릴까요? (구매 후 {days}일 경과)")
        else:
            custom_followups.append(f"관련 법령을 자세히 알려드릴까요? (구매 후 {days}일 경과)")

        if purchase_item:
            custom_followups.append(f"'{purchase_item}' 관련 유사 분쟁 조정 사례도 확인해 보시겠어요?")
        else:
            custom_followups.append("유사 분쟁 조정 사례도 확인해 보시겠어요?")

        custom_followups.append("조정신청 절차가 궁금하시면 안내해드릴까요?")
        followup_questions = custom_followups[:3]
    else:
        followup_questions = _build_progressive_followups(retrieval, available_details)

    cited_cases = _extract_cited_cases(retrieval)
    has_evidence = model_used not in ('rule_based', 'safe_fallback')

    # 캐시 저장 (전체 답변도 저장 - 후속 detail 요청 시 사용)
    if not retry_context:
        cache = get_answer_cache()
        cache.set(user_query, query_analysis.get('query_type', 'dispute'), {
            'answer': draft_answer,
            'summary': summary_answer,
            'claim_evidence_map': claim_evidence_map,
            'cited_cases': cited_cases,
            'has_evidence': has_evidence,
            'retrieval_confidence': retrieval_confidence,
            'available_details': available_details,
        })

    return {
        'draft_answer': summary_answer,  # 요약만 제공
        'claim_evidence_map': claim_evidence_map,
        'cited_cases': cited_cases,
        'has_sufficient_evidence': has_evidence,
        'retrieval_confidence': retrieval_confidence,
        'followup_questions': followup_questions,
        'response_depth': 'summary',
        'available_details': available_details,
        'generation_time_ms': (time.time() - start_time) * 1000,
        'messages': [AIMessage(content=summary_answer)],
        'generation_model_used': model_used,
        '_cache_hit': False,
    }


# ========================================
# v2: CitedCase 생성 + retry_context 지원
# ========================================

def _extract_cited_cases(retrieval: Dict) -> List[Dict]:
    """
    검색 결과에서 인용된 사례 정보를 추출합니다.

    Returns:
        List of CitedCase dicts
    """
    cited_cases = []

    # case retrieval 결과에서 추출
    case_results = retrieval.get('cases', [])
    if not case_results:
        # 기존 구조 호환성
        case_results = retrieval.get('disputes', [])

    for result in case_results[:3]:  # 최대 3개
        # category 결정
        category = '조정'  # 기본값
        if isinstance(result, dict):
            cat = result.get('category') or result.get('doc_type', '')
            if '해결' in cat or 'resolve' in cat.lower():
                category = '해결'
            elif '상담' in cat or 'counsel' in cat.lower():
                category = '상담'

            cited_cases.append({
                'case_id': result.get('chunk_id') or result.get('doc_id', ''),
                'category': category,
                'title': result.get('doc_title') or result.get('title', ''),
                'summary': (result.get('content', '') or result.get('summary', ''))[:200],
                'relevance': '사용자 질의와 유사한 분쟁 사례',
            })

    return cited_cases


def _build_retry_prompt_supplement(retry_context: Dict) -> str:
    """
    retry_context에서 이전 위반사항을 프롬프트 보충 정보로 변환합니다.

    Args:
        retry_context: RetryContext dict (violations, previous_draft, retry_count)

    Returns:
        프롬프트에 추가할 위반사항 안내 문자열
    """
    if not retry_context:
        return ""

    violations = retry_context.get('violations', [])
    if not violations:
        return ""

    lines = [
        "\n## 이전 답변 검토 결과 (반드시 수정 필요)",
        "이전 답변에서 다음 문제가 발견되었습니다. 재생성 시 이 문제들을 반드시 해결해주세요:",
        ""
    ]

    for i, violation in enumerate(violations, 1):
        if isinstance(violation, dict):
            v_type = violation.get('type', 'unknown')
            v_desc = violation.get('description', '')
            v_suggestion = violation.get('suggestion', '')
            lines.append(f"{i}. [{v_type}] {v_desc}")
            if v_suggestion:
                lines.append(f"   → 제안: {v_suggestion}")
        else:
            lines.append(f"{i}. {violation}")

    lines.append("")
    lines.append("위 문제점을 수정한 새로운 답변을 생성해주세요.")

    return "\n".join(lines)


def _build_phase_aware_law_detail(retrieval: Dict) -> str:
    """
    providing_law_detail phase용 법령/기준 상세 답변 생성.

    캐시된 Retrieval 결과에서 laws/criteria 섹션을 추출하여
    구조화된 법령 상세 정보를 생성합니다.
    """
    laws = retrieval.get('laws', [])
    criteria = retrieval.get('criteria', [])

    lines = []

    if laws:
        lines.append("## 관련 법령")
        lines.append("")
        for i, law in enumerate(laws[:5], 1):
            title = law.get('doc_title') or law.get('title', '제목 없음')
            content = (law.get('content') or '')[:300]
            lines.append(f"### {i}. {title}")
            if content:
                lines.append(f"> {content}")
            lines.append("")

    if criteria:
        lines.append("## 분쟁해결기준")
        lines.append("")
        for i, crit in enumerate(criteria[:5], 1):
            title = crit.get('doc_title') or crit.get('title', '제목 없음')
            content = (crit.get('content') or '')[:300]
            lines.append(f"### {i}. {title}")
            if content:
                lines.append(f"> {content}")
            lines.append("")

    if not lines:
        return "관련 법령 및 기준 정보를 찾을 수 없습니다."

    return "\n".join(lines)


def _generate_retrieval_based_followups(
    retrieval: Dict,
    query_analysis: Dict,
) -> List[str]:
    """
    검색 결과 섹션 존재 여부에 기반한 후속질문 생성.

    Phase 시스템 제거 후 단순화된 후속질문:
    - 법령 결과가 있으면: "관련 법령도 알려드릴까요?"
    - 유사 사례가 있으면: "비슷한 분쟁 조정 사례도 보시겠어요?"
    - 절차 정보 관련: "분쟁 해결 절차도 안내해드릴까요?"
    """
    questions = []

    if not retrieval:
        return questions

    laws = retrieval.get('laws', [])
    criteria = retrieval.get('criteria', [])
    disputes = retrieval.get('disputes', [])
    counsels = retrieval.get('counsels', [])

    # 법령 결과가 있으면
    if laws or criteria:
        questions.append("관련 법령과 분쟁해결기준도 상세히 알려드릴까요?")

    # 유사 사례가 있으면
    if disputes or counsels:
        case_count = len(disputes) + len(counsels)
        if case_count > 1:
            questions.append(f"비슷한 분쟁 조정 사례 {case_count}건도 확인해 보시겠어요?")

    # 절차 안내는 항상 제안
    questions.append("분쟁 해결 절차(한국소비자원, 전자거래분쟁조정 등)도 안내해드릴까요?")

    return questions[:3]  # 최대 3개


async def generation_node_v2(state: Dict, config: Any = None) -> Dict:
    """
    [답변생성 노드 v2 진입점]

    v2 추가 기능:
    - Sufficiency Check: 검색 결과 충분성 평가 (LLM 호출 전)
        - insufficient: 안내 메시지 반환 (LLM 생략)
        - partial/sufficient: LLM 답변 생성 진행
    - retry_context 처리: LegalReviewer 재생성 요청 시 위반사항을 retry_supplement로 LLM에 전달
    - cited_cases 생성: 인용된 사례 정보 구조화
    - expanded_queries 활용: 검색 컨텍스트 참조
    - followup_questions: 검색 결과 기반 후속질문 생성

    Progressive Disclosure (Phase C+E):
    - response_mode == "legacy": 기존 동작 (전체 정보)
    - response_mode == "minimal"/"adaptive": 요약 먼저, 상세는 후속 대화에서
    - mode == "META_CONVERSATIONAL": 가이드 응답 (RAG 미실행)

    Args:
        state: ChatState (v2 호환)
        config: RunnableConfig (스트리밍용)

    Returns:
        Dict with draft_answer, claim_evidence_map, cited_cases, has_sufficient_evidence, retrieval_confidence
    """
    import time
    from langchain_core.messages import AIMessage

    start_time = time.time()

    # === Phase E-1: response_mode 기반 분기 ===
    app_config = get_config()
    response_mode = app_config.response.response_mode
    mode = state.get('mode', 'NEED_RAG')

    # META_CONVERSATIONAL: 가이드 응답 (legacy 이외 모드에서만)
    if mode == 'META_CONVERSATIONAL':
        logger.info("[Generation] META_CONVERSATIONAL mode → guide response")
        return _meta_conversational_response(state)

    # Phase D: FOLLOWUP_WITH_CONTEXT — 이전 턴 캐시 결과로 상세 응답
    if mode == 'FOLLOWUP_WITH_CONTEXT':
        logger.info("[Generation] FOLLOWUP_WITH_CONTEXT mode → detail response")
        return _followup_detail_response(state, config)

    # Progressive Disclosure: minimal/adaptive 모드에서 NEED_RAG인 경우 요약 응답
    if response_mode != 'legacy' and mode == 'NEED_RAG':
        logger.info(f"[Generation] Progressive Disclosure mode={response_mode} → summary response")
        return _progressive_summary_response(state, config)

    # === Legacy 동작 (기존 코드 유지) ===

    user_query = state.get('user_query', '')
    query_analysis = state.get('query_analysis', {})
    retrieval = state.get('retrieval', {})
    retry_context = state.get('retry_context')  # v2: 재생성 컨텍스트

    query_type = query_analysis.get('query_type', 'dispute')
    expanded_queries = query_analysis.get('expanded_queries', [])

    # followup query_type (후속 턴이지만 검색 결과 없는 경우)
    if query_type == 'followup' and not retrieval:
        fallback_msg = "추가 정보를 확인 중입니다. 잠시만 기다려주세요."
        return {
            'draft_answer': fallback_msg,
            'claim_evidence_map': [],
            'cited_cases': [],
            'has_sufficient_evidence': False,
            'generation_time_ms': (time.time() - start_time) * 1000,
            'messages': [AIMessage(content=fallback_msg)],
            'generation_model_used': 'followup_fallback',
        }

    # === 일반 분류 흐름 ===

    # 1. 일반 대화 처리
    if query_type == 'general':
        response = _build_general_response(user_query)
        return {
            'draft_answer': response,
            'claim_evidence_map': [],
            'cited_cases': [],
            'has_sufficient_evidence': True,
            'generation_time_ms': (time.time() - start_time) * 1000,
            'messages': [AIMessage(content=response)],
        }

    # 2. 전문기관 도메인 처리 (restricted)
    if query_type == 'restricted':
        result = _build_specialist_agency_response(
            user_query=user_query,
            query_analysis=query_analysis,
            retrieval=retrieval,
        )
        result['cited_cases'] = []
        result['retrieval_confidence'] = 0.0  # 전문기관 안내는 검색 충분성 평가 비대상
        result['generation_time_ms'] = (time.time() - start_time) * 1000
        return result

    # 3. 도메인 분류 (Legacy)
    classification = classify_domain(user_query)
    if classification.is_restricted:
        result = _build_restricted_response(user_query, classification, retrieval or {})
        result['cited_cases'] = []
        result['retrieval_confidence'] = 0.0  # 전문기관 안내는 검색 충분성 평가 비대상
        result['generation_time_ms'] = (time.time() - start_time) * 1000
        return result

    # 4. 검색 결과 없음
    if not retrieval:
        no_result_msg = "죄송합니다. 관련 정보를 찾을 수 없습니다. 질문을 더 구체적으로 작성해 주시면 도움이 될 것 같습니다."
        return {
            'draft_answer': no_result_msg,
            'claim_evidence_map': [],
            'cited_cases': [],
            'has_sufficient_evidence': False,
            'retrieval_confidence': 0.0,
            'generation_time_ms': (time.time() - start_time) * 1000,
            'clarifying_questions': [
                "어떤 제품/서비스에 대한 분쟁인가요?",
                "언제 구매하셨나요?",
                "어떤 문제가 발생했나요?"
            ],
            'messages': [AIMessage(content=no_result_msg)],
        }

    # 5. Sufficiency Check (LLM 호출 전)
    checker = RetrievalSufficiencyChecker()
    suf_result = checker.evaluate(retrieval)

    # Store sufficiency results in state
    retrieval_confidence = suf_result.confidence
    has_sufficient_evidence_initial = suf_result.is_sufficient

    # 5-1. Insufficient 레벨: 안내 메시지 반환 (LLM 생략)
    if suf_result.level == 'insufficient':
        insufficient_msg = f"""죄송합니다. 검색된 정보가 충분하지 않아 정확한 답변을 드리기 어렵습니다.

{suf_result.reason}

다음 정보를 추가로 알려주시면 더 정확한 답변을 드릴 수 있습니다:"""

        # Add clarifying questions
        for i, q in enumerate(suf_result.clarifying_questions, 1):
            insufficient_msg += f"\n{i}. {q}"

        return {
            'draft_answer': insufficient_msg,
            'claim_evidence_map': [],
            'cited_cases': [],
            'has_sufficient_evidence': False,
            'retrieval_confidence': retrieval_confidence,
            'clarifying_questions': suf_result.clarifying_questions,
            'generation_time_ms': (time.time() - start_time) * 1000,
            'messages': [AIMessage(content=insufficient_msg)],
            'generation_model_used': 'sufficiency_insufficient',
        }

    # 5-2. Partial or Sufficient: LLM 답변 생성 진행

    # 6. 캐시 확인 (retry가 아닌 경우에만)
    if not retry_context:
        cache = get_answer_cache()
        cached = cache.get(user_query, query_type)
        if cached:
            return {
                'draft_answer': cached['answer'],
                'claim_evidence_map': cached.get('claim_evidence_map', []),
                'cited_cases': cached.get('cited_cases', []),
                'has_sufficient_evidence': cached.get('has_evidence', True),
                'retrieval_confidence': cached.get('retrieval_confidence', retrieval_confidence),
                'generation_time_ms': (time.time() - start_time) * 1000,
                'messages': [AIMessage(content=cached['answer'])],
                '_cache_hit': True,
            }

    # 7. v2: retry_context 처리
    retry_supplement = None
    if retry_context:
        retry_supplement = _build_retry_prompt_supplement(retry_context)

    # 8. LLM 답변 생성
    agency_info = retrieval.get('agency', {
        'agency': 'KCA',
        'agency_info': {
            'name': '한국소비자원',
            'full_name': '한국소비자원 소비자분쟁조정위원회',
            'description': '일반 소비자 분쟁 조정',
            'url': 'https://www.kca.go.kr'
        },
    })

    mode = state.get('mode', 'NEED_RAG')
    include_disclaimer = (mode == 'NEED_RAG')

    # Get onboarding for context
    onboarding = state.get('onboarding') or {}

    # v2: retry_supplement 패스스루 (위반사항 참고)
    draft_answer, model_used, claim_evidence_map = AnswerGenerationFallback.generate_with_fallback(
        query=user_query,
        retrieval=retrieval,
        agency_info=agency_info,
        include_disclaimer=include_disclaimer,
        retry_supplement=retry_supplement,
        onboarding=onboarding,
    )

    # 9. v2: CitedCase 추출
    cited_cases = _extract_cited_cases(retrieval)

    has_evidence = model_used not in ('rule_based', 'safe_fallback')
    generation_time_ms = (time.time() - start_time) * 1000

    # 캐시 저장 (retry가 아닌 경우에만)
    if not retry_context:
        cache = get_answer_cache()
        cache.set(user_query, query_type, {
            'answer': draft_answer,
            'claim_evidence_map': claim_evidence_map,
            'cited_cases': cited_cases,
            'has_evidence': has_evidence,
            'retrieval_confidence': retrieval_confidence,
        })

    # v2: 후속질문 생성 (Rule-based, 검색 결과 기반)
    followup_questions = []
    app_config = get_config()
    if app_config.chatbot_features.enable_followup_questions and query_type == 'dispute':
        followup_questions = _generate_retrieval_based_followups(retrieval, query_analysis)

    is_followup = False

    return {
        'draft_answer': draft_answer,
        'claim_evidence_map': claim_evidence_map,
        'cited_cases': cited_cases,
        'has_sufficient_evidence': has_evidence,
        'retrieval_confidence': retrieval_confidence,
        'followup_questions': followup_questions,
        'response_depth': 'full',
        'available_details': None,
        'generation_time_ms': generation_time_ms,
        'messages': [AIMessage(content=draft_answer)],
        'generation_model_used': model_used,
        'is_followup': is_followup,
        '_cache_hit': False,
    }


__all__ = [
    'generation_node',
    'generation_node_streaming',
    'generation_node_v2',
]
