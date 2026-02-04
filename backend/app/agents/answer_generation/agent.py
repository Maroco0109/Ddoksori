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
from typing import Any, Dict, List

from langchain_core.messages import AIMessage

from ...domain import AGENCY_INFO
from ..followup.generator import FollowupQuestionGenerator
from ..retrieval.sufficiency import RetrievalSufficiencyChecker
from .cache import get_answer_cache
from .context_builder import ContextBuilder
from .fallback import AnswerGenerationFallback
from .template_loader import TemplateLoader
from .template_router import TemplateRouter

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


def _get_llm_model() -> str:
    """사용할 LLM 모델명 반환"""
    return os.getenv("LLM_MODEL", "gpt-4o-mini")


def _build_general_response(user_query: str) -> str:
    """
    일반 대화(인사, 감사, 확인, 작별)에 대한 규칙 기반 응답 생성
    LLM 비용 절감을 위해 단순 패턴 매칭 사용.
    """
    query_lower = user_query.lower().strip()

    # 1. 작별 인사 (먼저 체크 - "안녕히"가 "안녕"보다 먼저 매칭되어야 함)
    goodbyes = ["bye", "안녕히", "잘가", "수고"]
    for g in goodbyes:
        if g in query_lower:
            return "이용해 주셔서 감사합니다! 다음에 또 찾아주세요."

    # 2. 인사말 패턴 (확장)
    greetings = ["안녕", "반가", "hello", "hi", "하이", "ㅎㅇ", "ㅎ2"]
    for g in greetings:
        if g in query_lower:
            return (
                "안녕하세요! 저는 소비자 분쟁 상담을 도와드리는 **똑소리**입니다.\n\n"
                "궁금하신 분쟁 관련 사항이 있으시면 편하게 말씀해 주세요.\n\n"
                "예를 들어:\n"
                '- "노트북 환불 가능한가요?"\n'
                '- "헬스장 계약 취소하고 싶어요"\n'
                '- "청약철회 기간이 어떻게 되나요?"'
            )

    # 3. 감사 패턴
    thanks = ["감사", "고마", "thanks", "thank"]
    for t in thanks:
        if t in query_lower:
            return "도움이 되셨다면 다행이에요! 추가로 궁금하신 사항이 있으시면 언제든 물어봐 주세요."

    # 4. 확인/동의 패턴
    confirmations = ["네", "예", "알겠", "오케이", "ok", "ㅇㅇ", "ㅇㅋ"]
    for c in confirmations:
        if query_lower == c or query_lower.startswith(c + " "):
            return "네, 추가로 궁금하신 점이 있으시면 말씀해 주세요!"

    # 5. 기본 응답
    return "네, 무엇을 도와드릴까요? 소비자 분쟁 관련 상담을 원하시면 자세한 상황을 알려주세요."


def _format_similar_cases(disputes: List[Dict], counsels: List[Dict]) -> str:
    """유사 사례 목록을 마크다운 리스트로 포맷팅"""
    if not disputes and not counsels:
        return "관련 사례가 없습니다."

    lines = []

    if disputes:
        lines.append("**분쟁조정사례**")
        for i, case in enumerate(disputes[:2], 1):
            title = case.get("doc_title", "제목 없음")
            org = case.get("source_org", "")
            lines.append(f"{i}. [{org}] {title}")

    if counsels:
        if lines:
            lines.append("")
        lines.append("**상담사례 (참고용)**")
        for i, case in enumerate(counsels[:2], 1):
            title = case.get("doc_title", "제목 없음")
            lines.append(f"{i}. {title}")

    return "\n".join(lines)


def _format_similar_cases_for_specialist(cases: List[Dict]) -> str:
    """전문기관 응답용 유사 사례 포맷팅 (Phase 9)"""
    if not cases:
        return ""

    lines = ["## 참고: 유사 사례", ""]
    for i, case in enumerate(cases[:3], 1):
        title = case.get("doc_title", "제목 없음")
        org = case.get("source_org", "")
        summary = case.get("summary", case.get("content", ""))[:200]

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
    restricted_domain = query_analysis.get("restricted_domain", "finance")
    agency_info = query_analysis.get("restricted_agency_info", {})

    # agency_info가 없으면 기본값 사용
    if not agency_info:
        from ..query_analysis.agent import RESTRICTED_DOMAIN_AGENCIES

        agency_info = RESTRICTED_DOMAIN_AGENCIES.get(
            restricted_domain,
            {
                "name": "전문분쟁조정위원회",
                "organization": "관할 기관",
                "url": "https://www.kca.go.kr",
                "phone": "1372",
            },
        )

    domain_name = DOMAIN_KOREAN_NAMES.get(restricted_domain, restricted_domain)

    # 유사 사례 추출 (CaseRetrievalAgent 결과)
    cases = []
    if retrieval:
        cases = retrieval.get("disputes", [])[:3]
        if not cases:
            cases = retrieval.get("counsels", [])[:3]

    similar_cases_section = _format_similar_cases_for_specialist(cases)

    # 응답 생성
    answer = SPECIALIST_AGENCY_RESPONSE_TEMPLATE.format(
        domain_name=domain_name,
        agency_name=agency_info.get("name", "전문기관"),
        organization=agency_info.get("organization", "관할 기관"),
        url=agency_info.get("url", ""),
        phone=agency_info.get("phone", ""),
        similar_cases_section=similar_cases_section,
    )

    return {
        "draft_answer": answer,
        "final_answer": answer,
        "has_sufficient_evidence": len(cases) > 0,
        "clarifying_questions": [],
        "messages": [AIMessage(content=answer)],
        "is_restricted": True,
        "restricted_domain": restricted_domain,
        "generation_model_used": "specialist_template",
    }


def _build_restricted_response(
    user_query: str,
    classification_result,
    retrieval,
) -> Dict:
    """제한된 영역(Restricted Domain)에 대한 안전한 응답 생성"""
    agency_code = classification_result.agency
    agency_info = AGENCY_INFO.get(agency_code, AGENCY_INFO["KCA"])

    disputes = retrieval.get("disputes", [])[:2] if retrieval else []
    counsels = retrieval.get("counsels", [])[:2] if retrieval else []

    similar_cases_section = _format_similar_cases(disputes, counsels)

    answer = RESTRICTED_RESPONSE_TEMPLATE.format(
        agency_name=agency_info.get("name", ""),
        agency_full_name=agency_info.get("full_name", ""),
        agency_url=agency_info.get("url", ""),
        agency_description=agency_info.get("description", ""),
        similar_cases_section=similar_cases_section,
        restriction_reason=agency_info.get("restriction_reason", ""),
    )

    return {
        "draft_answer": answer,
        "final_answer": answer,
        "has_sufficient_evidence": False,
        "clarifying_questions": [],
        "messages": [AIMessage(content=answer)],
        "is_restricted": True,
        "agency_code": agency_code,
    }


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
    onboarding = state.get("onboarding") or {}
    purchase_item = onboarding.get("purchase_item", "")

    if purchase_item:
        response = META_CONVERSATIONAL_ONBOARDING_TEMPLATE.format(
            purchase_item=purchase_item,
        )
    else:
        response = META_CONVERSATIONAL_TEMPLATE

    return {
        "draft_answer": response,
        "final_answer": response,
        "claim_evidence_map": [],
        "cited_cases": [],
        "has_sufficient_evidence": True,
        "retrieval_confidence": 1.0,
        "followup_questions": [],
        "response_depth": "full",
        "available_details": None,
        "generation_time_ms": (time.time() - start_time) * 1000,
        "messages": [AIMessage(content=response)],
        "generation_model_used": "meta_conversational_template",
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
    if detail_type == "full":
        return retrieval

    filtered = {}

    if detail_type == "laws":
        filtered["laws"] = retrieval.get("laws", [])
        filtered["criteria"] = retrieval.get("criteria", [])
    elif detail_type == "criteria":
        filtered["criteria"] = retrieval.get("criteria", [])
    elif detail_type == "cases":
        filtered["disputes"] = retrieval.get("disputes", [])
        filtered["counsels"] = retrieval.get("counsels", [])

    # 원본의 agency 정보 보존
    if "agency" in retrieval:
        filtered["agency"] = retrieval["agency"]

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

    user_query = state.get("user_query", "")
    last_turn_context = state.get("_last_turn_context") or {}
    cached_retrieval = last_turn_context.get("retrieval") or {}
    available_details = last_turn_context.get("available_details") or {}

    # Detect which section the user is asking about
    from ..query_analysis.detectors import detect_requested_detail_type

    detail_type = detect_requested_detail_type(user_query, available_details)

    logger.info(f"[Generation] FOLLOWUP_WITH_CONTEXT: detail_type={detail_type}")

    # 절차 안내 요청
    if detail_type == "procedure":
        response = PHASE_PROCEDURE_TEMPLATE
        return {
            "draft_answer": response,
            "claim_evidence_map": [],
            "cited_cases": [],
            "has_sufficient_evidence": True,
            "retrieval_confidence": 1.0,
            "followup_questions": [],
            "response_depth": "detail",
            "available_details": None,  # 절차 후에는 남은 상세 없음
            "generation_time_ms": (time.time() - start_time) * 1000,
            "messages": [AIMessage(content=response)],
            "generation_model_used": "procedure_template",
        }

    # 캐시된 retrieval이 없으면 fallback
    if not cached_retrieval:
        fallback_msg = (
            "죄송합니다. 이전 검색 결과를 찾을 수 없습니다. 질문을 다시 입력해 주세요."
        )
        return {
            "draft_answer": fallback_msg,
            "claim_evidence_map": [],
            "cited_cases": [],
            "has_sufficient_evidence": False,
            "retrieval_confidence": 0.0,
            "followup_questions": [],
            "response_depth": "detail",
            "available_details": None,
            "generation_time_ms": (time.time() - start_time) * 1000,
            "messages": [AIMessage(content=fallback_msg)],
            "generation_model_used": "followup_no_cache",
        }

    # 요청된 섹션만 포함하는 필터링된 retrieval 구성
    filtered_retrieval = _filter_retrieval_for_detail(cached_retrieval, detail_type)

    # LLM으로 상세 답변 생성
    agency_info = cached_retrieval.get(
        "agency",
        {
            "agency": "KCA",
            "agency_info": {
                "name": "한국소비자원",
                "full_name": "한국소비자원 소비자분쟁조정위원회",
                "description": "일반 소비자 분쟁 조정",
                "url": "https://www.kca.go.kr",
            },
        },
    )

    # Get onboarding for context
    onboarding = state.get("onboarding") or {}

    draft_answer, model_used, claim_evidence_map = (
        AnswerGenerationFallback.generate_with_fallback(
            query=user_query,
            retrieval=filtered_retrieval,
            agency_info=agency_info,
            include_disclaimer=True,
            onboarding=onboarding,
        )
    )

    cited_cases = _extract_cited_cases(filtered_retrieval)
    has_evidence = model_used not in ("rule_based", "safe_fallback")

    # Generate followup questions (캐시 응답에서도 생성)
    query_analysis = state.get("query_analysis", {})
    followup_generator = FollowupQuestionGenerator()
    followup_result = followup_generator.generate_questions(
        query_analysis=query_analysis,
        retrieval=filtered_retrieval,
        answer=draft_answer,
    )
    followup_questions = followup_result.get("followup_questions", [])

    return {
        "draft_answer": draft_answer,
        "claim_evidence_map": claim_evidence_map,
        "cited_cases": cited_cases,
        "has_sufficient_evidence": has_evidence,
        "retrieval_confidence": 0.8,  # 캐시 사용이므로 고정값
        "followup_questions": followup_questions,
        "response_depth": "detail",
        "available_details": None,
        "retrieval": filtered_retrieval,  # retrieval state도 업데이트
        "generation_time_ms": (time.time() - start_time) * 1000,
        "messages": [AIMessage(content=draft_answer)],
        "generation_model_used": model_used,
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
    case_results = retrieval.get("cases", [])
    if not case_results:
        # 기존 구조 호환성
        case_results = retrieval.get("disputes", [])

    for result in case_results[:3]:  # 최대 3개
        # category 결정
        category = "조정"  # 기본값
        if isinstance(result, dict):
            cat = result.get("category") or result.get("doc_type", "")
            if "해결" in cat or "resolve" in cat.lower():
                category = "해결"
            elif "상담" in cat or "counsel" in cat.lower():
                category = "상담"

            case_info = ContextBuilder.extract_case_info(result)
            cited_cases.append(
                {
                    "case_id": result.get("chunk_id") or result.get("doc_id", ""),
                    "category": category,
                    "title": case_info["title"],
                    "summary": (result.get("content", "") or result.get("summary", ""))[
                        :200
                    ],
                    "relevance": "사용자 질의와 유사한 분쟁 사례",
                }
            )

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

    violations = retry_context.get("violations", [])
    if not violations:
        return ""

    lines = [
        "\n## 이전 답변 검토 결과 (반드시 수정 필요)",
        "이전 답변에서 다음 문제가 발견되었습니다. 재생성 시 이 문제들을 반드시 해결해주세요:",
        "",
    ]

    for i, violation in enumerate(violations, 1):
        if isinstance(violation, dict):
            v_type = violation.get("type", "unknown")
            v_desc = violation.get("description", "")
            v_suggestion = violation.get("suggestion", "")
            lines.append(f"{i}. [{v_type}] {v_desc}")
            if v_suggestion:
                lines.append(f"   → 제안: {v_suggestion}")
        else:
            lines.append(f"{i}. {violation}")

    lines.append("")
    lines.append("위 문제점을 수정한 새로운 답변을 생성해주세요.")

    return "\n".join(lines)


def _build_generation_result(
    answer: str,
    start_time: float,
    claim_evidence_map: List = None,
    cited_cases: List = None,
    has_evidence: bool = True,
    retrieval_confidence: float = 0.0,
    followup_questions: List = None,
    response_depth: str = "full",
    available_details: Dict = None,
    model_used: str = None,
    cache_hit: bool = False,
    clarifying_questions: List = None,
    **kwargs,
) -> Dict:
    """통합 결과 생성 헬퍼"""
    import time

    from langchain_core.messages import AIMessage

    result = {
        "draft_answer": answer,
        "claim_evidence_map": claim_evidence_map or [],
        "cited_cases": cited_cases or [],
        "has_sufficient_evidence": has_evidence,
        "retrieval_confidence": retrieval_confidence,
        "followup_questions": followup_questions or [],
        "response_depth": response_depth,
        "available_details": available_details,
        "generation_time_ms": (time.time() - start_time) * 1000,
        "messages": [AIMessage(content=answer)],
        "generation_model_used": model_used,
        "_cache_hit": cache_hit,
    }
    if clarifying_questions:
        result["clarifying_questions"] = clarifying_questions
    return result


def _try_early_exit(state: Dict, config: Any, start_time: float):
    """
    Phase 0: 빠른 탈출 — LLM 불필요한 경로를 처리합니다.

    META_CONVERSATIONAL, FOLLOWUP_WITH_CONTEXT, followup(검색 결과 없음),
    general, restricted 쿼리를 규칙 기반으로 즉시 응답합니다.

    Args:
        state: ChatState
        config: RunnableConfig
        start_time: 시작 시각 (time.time())

    Returns:
        결과 Dict (매칭 시) 또는 None (매칭 없음)
    """
    import time

    mode = state.get("mode", "NEED_RAG")

    if mode == "META_CONVERSATIONAL":
        logger.info("[Generation] META_CONVERSATIONAL mode → guide response")
        return _meta_conversational_response(state)

    if mode == "FOLLOWUP_WITH_CONTEXT":
        logger.info("[Generation] FOLLOWUP_WITH_CONTEXT mode → detail response")
        return _followup_detail_response(state, config)

    user_query = state.get("user_query", "")
    query_analysis = state.get("query_analysis", {})
    retrieval = state.get("retrieval", {})
    query_type = query_analysis.get("query_type", "dispute")

    # followup query_type (후속 턴이지만 검색 결과 없는 경우)
    if query_type == "followup" and not retrieval:
        fallback_msg = "추가 정보를 확인 중입니다. 잠시만 기다려주세요."
        return _build_generation_result(
            answer=fallback_msg,
            start_time=start_time,
            has_evidence=False,
            model_used="followup_fallback",
        )

    # general 쿼리 처리
    if query_type == "general":
        response = _build_general_response(user_query)
        return _build_generation_result(
            answer=response,
            start_time=start_time,
            has_evidence=True,
            model_used="rule_based",
        )

    # restricted (Phase 9)
    if query_type == "restricted":
        result = _build_specialist_agency_response(
            user_query=user_query,
            query_analysis=query_analysis,
            retrieval=retrieval,
        )
        result["cited_cases"] = result.get("cited_cases", [])
        result["retrieval_confidence"] = 0.0
        result["generation_time_ms"] = (time.time() - start_time) * 1000
        return result

    return None


def _check_sufficiency(state: Dict, retrieval: Dict, start_time: float) -> tuple:
    """
    Phase 1: 검색 결과 충분성 검사를 수행합니다.

    Args:
        state: ChatState
        retrieval: 검색 결과 Dict
        start_time: 시작 시각

    Returns:
        (result_or_none, confidence) 튜플.
        insufficient이면 result Dict, 아니면 None. confidence는 항상 반환.
    """
    checker = RetrievalSufficiencyChecker()
    suf_result = checker.evaluate(retrieval)
    retrieval_confidence = suf_result.confidence

    if suf_result.level == "insufficient":
        insufficient_msg = (
            f"죄송합니다. 검색된 정보가 충분하지 않아 정확한 답변을 드리기 어렵습니다."
            f"\n\n{suf_result.reason}"
            f"\n\n다음 정보를 추가로 알려주시면 더 정확한 답변을 드릴 수 있습니다:"
        )
        for i, q in enumerate(suf_result.clarifying_questions, 1):
            insufficient_msg += f"\n{i}. {q}"
        result = _build_generation_result(
            answer=insufficient_msg,
            start_time=start_time,
            has_evidence=False,
            retrieval_confidence=retrieval_confidence,
            clarifying_questions=suf_result.clarifying_questions,
            model_used="sufficiency_insufficient",
        )
        return (result, retrieval_confidence)

    return (None, retrieval_confidence)


def _try_cache(
    state: Dict,
    user_query: str,
    query_type: str,
    retry_context,
    retrieval_confidence: float,
    start_time: float,
):
    """
    Phase 2: 캐시 확인 — 동일 질문에 대한 캐시된 답변을 반환합니다.

    Args:
        state: ChatState
        user_query: 사용자 질문
        query_type: 쿼리 유형
        retry_context: 재시도 컨텍스트 (있으면 캐시 스킵)
        retrieval_confidence: 검색 신뢰도
        start_time: 시작 시각

    Returns:
        캐시된 결과 Dict 또는 None
    """
    if retry_context:
        return None

    cache = get_answer_cache()
    cached = cache.get(user_query, query_type)
    if cached:
        return _build_generation_result(
            answer=cached["answer"],
            start_time=start_time,
            claim_evidence_map=cached.get("claim_evidence_map", []),
            cited_cases=cached.get("cited_cases", []),
            has_evidence=cached.get("has_evidence", True),
            retrieval_confidence=cached.get(
                "retrieval_confidence", retrieval_confidence
            ),
            model_used="cache",
            cache_hit=True,
            response_depth=cached.get("response_depth", "full"),
            available_details=cached.get("available_details"),
        )

    return None


def _render_and_generate(
    state: Dict,
    user_query: str,
    retrieval: Dict,
    onboarding: Dict,
    retry_supplement,
    mode: str,
) -> tuple:
    """
    Phase 3-4: 템플릿 선택/렌더링 + LLM 생성을 수행합니다.

    Args:
        state: ChatState
        user_query: 사용자 질문
        retrieval: 검색 결과
        onboarding: 온보딩 정보
        retry_supplement: 재시도 보충 프롬프트 (없으면 None)
        mode: 현재 모드 (NEED_RAG 등)

    Returns:
        (draft_answer, model_used, claim_evidence_map) 튜플
    """
    query_analysis = state.get("query_analysis", {})
    query_type = query_analysis.get("query_type", "dispute")

    DEFAULT_AGENCY_INFO = {
        "agency": "KCA",
        "agency_info": {
            "name": "한국소비자원",
            "full_name": "한국소비자원 소비자분쟁조정위원회",
            "description": "일반 소비자 분쟁 조정",
            "url": "https://www.kca.go.kr",
        },
        "dispute_type": "1:N",
        "reason": "일반 소비자 분쟁으로 판단됩니다",
        "confidence": 0.7,
    }
    agency_info = retrieval.get("agency", DEFAULT_AGENCY_INFO)
    include_disclaimer = mode == "NEED_RAG"

    # Template system
    router = TemplateRouter()
    loader = TemplateLoader()
    ctx_builder = ContextBuilder()

    template_key = router.select_template(state)
    context = ctx_builder.build(state)

    if template_key == "fallback":
        context["logic_from_gold_set"] = router.get_fallback_reason(state)

    rendered_prompt = loader.render(template_key, context)
    logger.info(f"[Generation] Template: {template_key} (query_type={query_type})")

    format_system_prompt = rendered_prompt
    format_user_prompt = None  # Template already contains user context

    # LLM generation
    draft_answer, model_used, claim_evidence_map = (
        AnswerGenerationFallback.generate_with_fallback(
            query=user_query,
            retrieval=retrieval,
            agency_info=agency_info,
            include_disclaimer=include_disclaimer,
            retry_supplement=retry_supplement,
            onboarding=onboarding,
            system_prompt=format_system_prompt,
            user_prompt=format_user_prompt,
        )
    )

    return (draft_answer, model_used, claim_evidence_map)


async def generation_node_v2(state: Dict, config: Any = None) -> Dict:
    """
    [답변생성 노드 v2 진입점] — 통합 단일 파이프라인

    모든 response_mode(legacy/minimal/adaptive)에서 동일한 파이프라인을 거칩니다:
    Phase 0: 빠른 탈출 (LLM 불필요)
    Phase 1: 검색 결과 + Sufficiency Check
    Phase 2: 캐시 확인
    Phase 3: Template Selection + Rendering
    Phase 4: LLM 생성
    Phase 5: 후처리 (progressive summary, followup, cache)

    Args:
        state: ChatState (v2 호환)
        config: RunnableConfig (스트리밍용)

    Returns:
        Dict with draft_answer, claim_evidence_map, cited_cases, etc.
    """
    import time

    from langchain_core.messages import AIMessage

    start_time = time.time()

    # Phase 0: 빠른 탈출
    early_result = _try_early_exit(state, config, start_time)
    if early_result is not None:
        return early_result

    user_query = state.get("user_query", "")
    query_analysis = state.get("query_analysis", {})
    retrieval = state.get("retrieval", {})
    retry_context = state.get("retry_context")
    query_type = query_analysis.get("query_type", "dispute")
    onboarding = state.get("onboarding") or {}
    mode = state.get("mode", "NEED_RAG")

    # Phase 1: Sufficiency Check
    if not retrieval:
        return _build_generation_result(
            answer="죄송합니다. 관련 정보를 찾을 수 없습니다. 질문을 더 구체적으로 작성해 주시면 도움이 될 것 같습니다.",
            start_time=start_time,
            has_evidence=False,
            clarifying_questions=[
                "어떤 제품/서비스에 대한 분쟁인가요?",
                "언제 구매하셨나요?",
                "어떤 문제가 발생했나요?",
            ],
        )

    suf_result_tuple = _check_sufficiency(state, retrieval, start_time)
    if suf_result_tuple[0] is not None:
        return suf_result_tuple[0]
    retrieval_confidence = suf_result_tuple[1]

    # Phase 2: 캐시 확인
    cached = _try_cache(
        state, user_query, query_type, retry_context, retrieval_confidence, start_time
    )
    if cached is not None:
        return cached

    # Phase 3-4: Template + LLM 생성
    retry_supplement = (
        _build_retry_prompt_supplement(retry_context) if retry_context else None
    )
    draft_answer, model_used, claim_evidence_map = _render_and_generate(
        state, user_query, retrieval, onboarding, retry_supplement, mode
    )

    # Phase 5: Post-processing
    cited_cases = _extract_cited_cases(retrieval)
    has_evidence = model_used not in ("rule_based", "safe_fallback")

    # Phase 6: Generate followup questions
    query_analysis = state.get("query_analysis", {})
    followup_generator = FollowupQuestionGenerator()
    followup_result = followup_generator.generate_questions(
        query_analysis=query_analysis,
        retrieval=retrieval,
        answer=draft_answer,
    )
    followup_questions = followup_result.get("followup_questions", [])

    if not retry_context:
        cache = get_answer_cache()
        cache.set(
            user_query,
            query_type,
            {
                "answer": draft_answer,
                "claim_evidence_map": claim_evidence_map,
                "cited_cases": cited_cases,
                "has_evidence": has_evidence,
                "retrieval_confidence": retrieval_confidence,
            },
        )

    return {
        "draft_answer": draft_answer,
        "claim_evidence_map": claim_evidence_map,
        "cited_cases": cited_cases,
        "has_sufficient_evidence": has_evidence,
        "retrieval_confidence": retrieval_confidence,
        "followup_questions": followup_questions,
        "response_depth": "full",
        "available_details": None,
        "generation_time_ms": (time.time() - start_time) * 1000,
        "messages": [AIMessage(content=draft_answer)],
        "generation_model_used": model_used,
        "is_followup": False,
        "_cache_hit": False,
    }


__all__ = [
    "generation_node_v2",
]
