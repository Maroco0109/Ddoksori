"""
똑소리 프로젝트 - 답변생성 에이전트 (Answer Generation Agent)

작성일: 2026-01-14
최종 수정: 2026-01-28 (PR-3: 전문기관 안내 응답 처리)

[역할 및 책임]
검색된 정보(RetrievalResult)를 바탕으로 사용자에게 제공할 최종 답변 초안(Draft)을 생성합니다.
LLM(GPT-4o, Claude 등)을 활용하여 문맥에 맞는 자연스러운 답변을 작성하며,
답변의 근거(Claim-Evidence Mapping)를 함께 생성하여 신뢰성을 높입니다.

[주요 로직]
1. 일반 대화 처리: "안녕", "고마워" 등 단순 대화는 LLM 없이 규칙 기반으로 즉시 응답.
2. 전문기관 도메인 처리 (Phase 9): 금융, 의료, 개인정보, 부동산, 건설 도메인은 전문기관 안내 + 유사 사례 제공.
3. 답변 생성 (Fallback): LLM 호출 실패 시 백업 로직(Rule-based)으로 안전한 답변 생성.
4. 캐싱: 동일한 질문에 대해 빠르게 응답하기 위한 답변 캐시 적용.
"""

import os
from typing import Dict, List, AsyncGenerator, Any

from langchain_core.messages import AIMessage
from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.runnables import RunnableConfig

from ...supervisor.state import ChatState, ConversationPhase
from ...domain import classify_domain, AGENCY_INFO
from .cache import get_answer_cache
from .fallback import AnswerGenerationFallback
from ...common.config import get_config


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

PHASE_CASE_OFFER_TEMPLATE = """
관련 법령과 분쟁해결기준을 안내해 드렸습니다.

{main_content}

---
**관련 분쟁조정 사례도 보여드릴까요?** 유사한 상황의 실제 조정 결과를 참고하시면 도움이 될 수 있습니다.
""".strip()

PHASE_PROCEDURE_OFFER_TEMPLATE = """
{main_content}

---
**분쟁 해결 절차(한국소비자원, 전자거래분쟁조정위원회 등)도 안내해 드릴까요?** 직접 분쟁조정을 신청하시는 방법을 알려드릴 수 있습니다.
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

    conversation_phase = state.get('conversation_phase', 'initial')
    if conversation_phase == 'providing_law':
        draft_answer = PHASE_CASE_OFFER_TEMPLATE.format(main_content=draft_answer)
    elif conversation_phase == 'providing_case':
        draft_answer = PHASE_PROCEDURE_OFFER_TEMPLATE.format(main_content=draft_answer)
    elif conversation_phase == 'providing_procedure':
        draft_answer = PHASE_PROCEDURE_TEMPLATE

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
