"""
똑소리 프로젝트 - 프롬프트 빌더

작성일: 2026-01-28
수정일: 2026-02-01

[역할 및 책임]
ResponseFormat에 따라 시스템 프롬프트와 사용자 프롬프트를 생성합니다.

[프롬프트 유형 - 7종]
1. law_response: 법령 검색 결과 계층적 안내
2. law_onboarding: 사용자 상황 기반 법령 안내
3. criteria_response: 분쟁해결기준 품목별 안내
4. case_response: 분쟁조정/상담 사례 분석
5. comprehensive_dispute: 종합 분쟁 상담 (법령 + 기준 + 기관)
6. general_greeting: 자연스러운 대화 및 상담 유도
7. info_only: 기관 안내 중심 정보 제공
"""

from typing import Dict, List, Optional

from app.common.sanitization import (
    get_security_instructions,
    wrap_retrieved_context,
    wrap_user_input,
)

from .config import ResponseFormat

# 면책 문구
DISCLAIMER = "본 답변은 정보 제공 목적이며 법률 자문이 아닙니다. 최종 판단·결정은 관련 기관 또는 전문가와 상담하여 진행해 주세요."


class PromptBuilder:
    """
    프롬프트 빌더

    ResponseFormat의 format_id에 따라 적절한 시스템 프롬프트와 사용자 프롬프트를 생성합니다.
    """

    # format_id → 시스템 프롬프트 빌더 메서드 매핑
    _SYSTEM_PROMPT_BUILDERS = {
        "law_response": "_build_law_response_system_prompt",
        "law_onboarding": "_build_law_onboarding_system_prompt",
        "criteria_response": "_build_criteria_response_system_prompt",
        "case_response": "_build_case_response_system_prompt",
        "comprehensive_dispute": "_build_comprehensive_dispute_system_prompt",
        "general_greeting": "_build_general_greeting_system_prompt",
        "info_only": "_build_info_only_system_prompt",
    }

    # format_id → 사용자 프롬프트 빌더 메서드 매핑
    _USER_PROMPT_BUILDERS = {
        "law_response": "_build_law_response_user_prompt",
        "law_onboarding": "_build_law_onboarding_user_prompt",
        "criteria_response": "_build_criteria_response_user_prompt",
        "case_response": "_build_case_response_user_prompt",
        "comprehensive_dispute": "_build_comprehensive_dispute_user_prompt",
        "general_greeting": "_build_general_greeting_user_prompt",
        "info_only": "_build_info_only_user_prompt",
    }

    def build_system_prompt(self, response_format: ResponseFormat) -> str:
        """
        시스템 프롬프트를 생성합니다.

        Args:
            response_format: 답변 형식

        Returns:
            시스템 프롬프트 문자열
        """
        method_name = self._SYSTEM_PROMPT_BUILDERS.get(response_format.format_id)
        if method_name is None:
            # 알 수 없는 format_id → comprehensive_dispute 기본값
            method_name = "_build_comprehensive_dispute_system_prompt"

        builder = getattr(self, method_name)
        base_prompt = builder(response_format)
        return base_prompt + get_security_instructions()

    def build_user_prompt(
        self,
        response_format: ResponseFormat,
        query: str,
        retrieval: Dict,
        agency_info: Dict,
        context: Dict,
        onboarding: Optional[Dict] = None,
        conversation_history: Optional[List] = None,
    ) -> str:
        """
        사용자 프롬프트를 생성합니다.

        Args:
            response_format: 답변 형식
            query: 사용자 질문
            retrieval: 검색 결과
            agency_info: 기관 정보
            context: 컨텍스트 (has_cases, has_laws 등)
            onboarding: 온보딩 정보 (품목, 구매일, 분쟁 내용 등)
            conversation_history: 이전 대화 히스토리 (최근 턴들)

        Returns:
            사용자 프롬프트 문자열
        """
        method_name = self._USER_PROMPT_BUILDERS.get(response_format.format_id)
        if method_name is None:
            method_name = "_build_comprehensive_dispute_user_prompt"

        builder = getattr(self, method_name)

        # 대화 히스토리 섹션 (general_greeting 제외)
        history_section = ""
        if conversation_history and response_format.format_id != "general_greeting":
            history_lines = self._build_conversation_history_section(
                conversation_history
            )
            if history_lines:
                history_section = "\n".join(history_lines) + "\n"

        # 사용자 쿼리 sanitization (L1-L3)
        query = wrap_user_input(query)

        # 각 빌더에 필요한 인자를 전달
        if response_format.format_id == "general_greeting":
            return builder(query)
        elif response_format.format_id == "law_response":
            base = builder(query, retrieval)
        elif response_format.format_id == "law_onboarding":
            base = builder(query, retrieval, onboarding)
        elif response_format.format_id == "criteria_response":
            base = builder(query, retrieval)
        elif response_format.format_id == "case_response":
            base = builder(query, retrieval)
        elif response_format.format_id == "comprehensive_dispute":
            base = builder(query, retrieval, agency_info, onboarding)
        elif response_format.format_id == "info_only":
            base = builder(query, retrieval, agency_info, context)
        else:
            # fallback
            base = builder(query, retrieval, agency_info, onboarding)

        # 히스토리를 프롬프트 앞부분에 추가
        if history_section:
            return history_section + base
        return base

    def _build_conversation_history_section(
        self, history: List, max_turns: int = 3
    ) -> List[str]:
        """
        최근 대화 히스토리를 프롬프트 섹션으로 변환합니다.

        Args:
            history: 대화 히스토리 리스트 (각 항목: {'role': str, 'content': str})
            max_turns: 포함할 최대 턴 수

        Returns:
            포맷팅된 문자열 리스트
        """
        if not history:
            return []

        recent = history[-max_turns:]
        lines = ["[이전 대화]"]
        for turn in recent:
            if isinstance(turn, dict):
                role = turn.get("role", "user")
                content = turn.get("content", "")[:200]
            else:
                continue
            prefix = "사용자" if role == "user" else "상담사"
            lines.append(f"{prefix}: {content}")
        lines.append("")
        return lines

    # ============================================================
    # law_response 프롬프트 (법령 계층적 안내)
    # ============================================================

    def _build_law_response_system_prompt(self, response_format: ResponseFormat) -> str:
        """law_response 형식의 시스템 프롬프트"""
        disclaimer_section = (
            f"\n\n---\n*{DISCLAIMER}*" if response_format.include_disclaimer else ""
        )

        return f"""당신은 한국 소비자 관련 법령 전문 상담 어시스턴트입니다.

역할:
- 검색된 법령을 계층적으로 정리하여 제공합니다
- 법령명 → 장/편 → 조문 순서로 구조화합니다
- 조문 내용은 원문에 충실하게 인용합니다

답변 구조:
## 관련 법령 안내
   법령별로 그룹화하여 표시:
   - **법령명**
     - 제X조 (조문 제목): 조문 내용

## 요약
   핵심 조항을 2-3문장으로 요약

마지막에 반드시: "더 자세한 정보를 원하시나요?"
{disclaimer_section}

금지 사항:
- 단정적 표현 ("~해야 합니다")
- 법률 판단이나 예측
- 개인정보 요구
"""

    def _build_law_response_user_prompt(self, query: str, retrieval: Dict) -> str:
        """law_response 형식의 사용자 프롬프트"""
        lines = [f"사용자 질문: {query}\n"]

        lines.append("[검색된 법령 정보]")
        law_lines = self._format_laws_only_section(retrieval)
        lines.extend(law_lines)

        lines.append("\n위 법령 정보를 계층적으로 정리하여 사용자에게 안내해 주세요.")

        return "\n".join(lines)

    # ============================================================
    # law_onboarding 프롬프트 (사용자 상황 기반 법령 안내)
    # ============================================================

    def _build_law_onboarding_system_prompt(
        self, response_format: ResponseFormat
    ) -> str:
        """law_onboarding 형식의 시스템 프롬프트"""
        disclaimer_section = (
            f"\n\n---\n*{DISCLAIMER}*" if response_format.include_disclaimer else ""
        )

        return f"""당신은 사용자의 구체적인 상황에 맞춰 관련 법령을 안내하는 소비자 분쟁 상담 어시스턴트입니다.

역할:
- 사용자의 구매 정보와 분쟁 상황을 파악하여 적용 가능한 법령을 안내합니다
- 법령/조항이 사용자 상황에 어떻게 적용되는지 구체적으로 설명합니다

답변 구조:
## 사용자 상황 요약
   사용자가 제공한 정보(품목, 구매일, 분쟁 내용)를 1-2문장으로 요약

## 적용 가능한 법령 및 조항
   상황에 맞는 법령/조항을 구체적으로 인용
   - 각 법령/조항이 사용자 상황에 어떻게 적용되는지 설명

## 근거 설명
   왜 이 법령이 사용자 상황에 적용되는지 논리적으로 설명
{disclaimer_section}

금지 사항:
- 단정적 표현
- 법률 판단이나 예측
"""

    def _build_law_onboarding_user_prompt(
        self, query: str, retrieval: Dict, onboarding: Optional[Dict]
    ) -> str:
        """law_onboarding 형식의 사용자 프롬프트"""
        lines = [f"사용자 질문: {query}\n"]

        # 온보딩 정보
        lines.append("[사용자 상황]")
        if onboarding:
            lines.extend(self._format_onboarding_section(onboarding))
        else:
            lines.append("사용자 상황 정보가 제공되지 않았습니다.")

        # 법령 정보
        lines.append("\n[검색된 법령 정보]")
        law_lines = self._format_laws_only_section(retrieval)
        lines.extend(law_lines)

        lines.append("\n사용자 상황에 맞춰 적용 가능한 법령을 설명해 주세요.")

        return "\n".join(lines)

    # ============================================================
    # criteria_response 프롬프트 (분쟁해결기준 품목별 안내)
    # ============================================================

    def _build_criteria_response_system_prompt(
        self, response_format: ResponseFormat
    ) -> str:
        """criteria_response 형식의 시스템 프롬프트"""
        disclaimer_section = (
            f"\n\n---\n*{DISCLAIMER}*" if response_format.include_disclaimer else ""
        )

        return f"""당신은 소비자 분쟁해결기준 전문 상담 어시스턴트입니다.

역할:
- 검색된 분쟁해결기준을 품목별로 구조화하여 안내합니다
- 품질보증기간, 교환/환불 기준을 명확한 목록으로 정리합니다

답변 구조:
## [품목명] 소비자분쟁해결기준 핵심 내용
   - **품질보증기간**: 해당 품목의 보증 기간
   - **하자 교환 및 환불 기준**:
     - 하자 발생 시 처리 방법
     - 수리 불가능 시 처리 방법
     - 동일 하자 반복 시 처리 방법
   - **교환/환불 금액 계산**:
     - 교환 시 기준
     - 환불 시 기준

## 주의사항 및 절차
   - 소비자 과실 관련 주의사항
   - 분쟁조정 신청 방법
{disclaimer_section}

금지 사항:
- 단정적 표현
- 법률 판단이나 예측
"""

    def _build_criteria_response_user_prompt(self, query: str, retrieval: Dict) -> str:
        """criteria_response 형식의 사용자 프롬프트"""
        lines = [f"사용자 질문: {query}\n"]

        lines.append("[검색된 분쟁해결기준]")
        criteria_lines = self._format_criteria_only_section(retrieval)
        lines.extend(criteria_lines)

        lines.append(
            "\n위 기준을 품질보증기간, 교환/환불 기준, 주의사항으로 구조화하여 안내해 주세요."
        )

        return "\n".join(lines)

    # ============================================================
    # case_response 프롬프트 (사례 분석)
    # ============================================================

    def _build_case_response_system_prompt(
        self, response_format: ResponseFormat
    ) -> str:
        """case_response 형식의 시스템 프롬프트"""
        disclaimer_section = (
            f"\n\n---\n*{DISCLAIMER}*" if response_format.include_disclaimer else ""
        )

        return f"""당신은 소비자 분쟁 조정 사례 분석 전문 상담 어시스턴트입니다.

역할:
- 검색된 유사 사례를 분석하여 시사점을 제공합니다
- 조정/해결 사례와 상담 사례를 구분하여 안내합니다

답변 구조:
## 조정/해결 사례
   최대 3건. 각 사례별:
   - **[출처기관] 사례 제목** (결정일: YYYY-MM-DD)
   - 분쟁 요약: 1-2문장
   - 조정 결과: 1-2문장

## 상담 사례 (참고용)
   최대 2건. 각 사례별:
   - **사례 제목**
   - 상담 요약: 1-2문장

## 시사점
   사례들에서 도출할 수 있는 종합 시사점 요약
{disclaimer_section}
"""

    def _build_case_response_user_prompt(self, query: str, retrieval: Dict) -> str:
        """case_response 형식의 사용자 프롬프트"""
        lines = [f"사용자 질문: {query}\n"]
        disputes = retrieval.get("disputes", [])
        counsels = retrieval.get("counsels", [])

        # 분쟁조정사례
        lines.append("[분쟁조정사례]")
        if disputes:
            for i, case in enumerate(disputes[:3], 1):
                source_org = case.get("source_org", "알 수 없음")
                doc_title = case.get("doc_title", "제목 없음")
                decision_date = case.get("decision_date", "날짜 미상")
                content = case.get("content", "")[:300]
                lines.append(f"{i}. [{source_org}] {doc_title}")
                lines.append(f"   결정일: {decision_date}")
                lines.append(f"   내용: {content}")
        else:
            lines.append("관련 분쟁조정사례를 찾지 못했습니다.")

        # 상담사례
        lines.append("\n[상담사례]")
        if counsels:
            for i, case in enumerate(counsels[:2], 1):
                doc_title = case.get("doc_title", "제목 없음")
                content = case.get("content", "")[:200]
                lines.append(f"{i}. {doc_title}")
                lines.append(f"   내용: {content}")
        else:
            lines.append("관련 상담사례를 찾지 못했습니다.")

        lines.append(
            "\n위 사례들을 요약하고 시사점을 분석하여 사용자에게 안내해 주세요."
        )

        return "\n".join(lines)

    # ============================================================
    # comprehensive_dispute 프롬프트 (종합 분쟁 상담)
    # ============================================================

    def _build_comprehensive_dispute_system_prompt(
        self, response_format: ResponseFormat
    ) -> str:
        """comprehensive_dispute 형식의 시스템 프롬프트"""
        return """당신은 한국 소비자 분쟁 조정 종합 상담 어시스턴트 '똑소리'입니다.

역할:
- 사용자의 분쟁 상황에 공감하고, 관련 규정과 유사 사례를 안내합니다
- 반드시 제공된 검색 결과만 인용하세요 (허위 조문 생성 금지)

답변 구조 (반드시 이 순서와 형식을 따르세요):

1. **공감 문장** (1-2문장)
   - 사용자의 상황에 대한 공감을 먼저 표현합니다
   - 예: "온라인으로 구매한 제품이 마음에 들지 않으셨군요. 환불을 거부당하셨다니 답답하셨을 것 같습니다."

2. **[규정]**
   - 적용되는 법률이나 분쟁해결기준을 보여줍니다
   - 법령명과 조항을 명확히 인용합니다 (예: 『전자상거래법』 제17조)
   - 규정을 토대로 사용자 상황에 어떻게 적용되는지 설명합니다

3. **[유사 사례]**
   - 검색된 분쟁조정/상담 사례 중 유사한 사례를 최대 3개 보여줍니다
   - 각 사례의 핵심 내용과 결과를 요약합니다
   - 사례를 토대로 사용자에게 시사점을 설명합니다
   - 사례가 없으면 이 섹션을 생략합니다

4. **[면책 문구]**
   - "본 답변은 정보 제공 목적이며 법률 자문이 아닙니다. 구체적인 사안은 한국소비자원(1372) 또는 전문가 상담을 권장합니다."

5. **-----** (구분선)

6. **[출처]**
   - 위에서 인용한 법령, 기준, 사례의 출처를 나열합니다
   - 형식: ¹ 출처명, ² 출처명 ...

금지 사항:
- "~해야 합니다" 같은 단정적 표현 → "~하는 것이 권장됩니다"로 대체
- "불법입니다", "승소합니다" 같은 법적 판단
- 검색 결과에 없는 허위 조문 번호 생성
- 개인정보 요청
"""

    def _build_comprehensive_dispute_user_prompt(
        self, query: str, retrieval: Dict, agency_info: Dict, onboarding: Optional[Dict]
    ) -> str:
        """comprehensive_dispute 형식의 사용자 프롬프트"""
        lines = [f"사용자 질문: {query}\n"]

        # 온보딩 정보 (있는 경우)
        if onboarding:
            lines.append("[사용자 상황]")
            lines.extend(self._format_onboarding_section(onboarding))
            lines.append("")

        # 법령 정보 (있는 경우)
        laws = retrieval.get("laws", [])
        if laws:
            lines.append("[관련 법령 - 규정 섹션에 활용]")
            lines.extend(self._format_laws_only_section(retrieval))
            lines.append("")

        # 분쟁해결기준 (있는 경우)
        criteria = retrieval.get("criteria", [])
        if criteria:
            lines.append("[분쟁해결기준 - 규정 섹션에 활용]")
            lines.extend(self._format_criteria_only_section(retrieval))
            lines.append("")

        # 유사 사례 (분쟁조정/상담 사례)
        disputes = retrieval.get("disputes", [])
        counsels = retrieval.get("counsels", [])
        if disputes or counsels:
            lines.append("[유사 사례 - 유사 사례 섹션에 활용]")
            lines.extend(self._format_cases_section(retrieval, max_count=3))
            lines.append("")

        # 기관 정보
        lines.append("[참고 기관 정보]")
        lines.extend(self._format_agency_section(agency_info))

        lines.append("\n위 정보를 시스템 프롬프트의 답변 구조에 맞춰 작성해 주세요.")
        lines.append(
            "반드시 공감 → [규정] → [유사 사례] → [면책 문구] → ----- → [출처] 순서를 따르세요."
        )

        return "\n".join(lines)

    # ============================================================
    # general_greeting 프롬프트 (자연스러운 대화)
    # ============================================================

    def _build_general_greeting_system_prompt(
        self, response_format: ResponseFormat
    ) -> str:
        """general_greeting 형식의 시스템 프롬프트"""
        return """당신은 친근하고 도움이 되는 소비자 분쟁 상담 어시스턴트 '똑소리'입니다.

역할:
- 사용자와 자연스럽게 대화합니다
- 분쟁 상담으로 자연스럽게 유도합니다

대화 스타일:
- 친근하고 공감적인 톤
- 쉬운 표현 사용
- 형식적인 섹션 구조를 사용하지 마세요

핵심 규칙:
- 인사에는 자연스럽게 인사로 응답
- 인사를 제외한 모든 대화에서는 마지막에 분쟁 상담 유도 질문을 자연스럽게 포함:
  예) "혹시 제품이나 서비스 관련 불편한 경험이 있으셨나요? 관련 법령과 해결 방법을 안내해 드릴 수 있어요!"

주의 사항:
- 면책 문구를 포함하지 마세요
"""

    def _build_general_greeting_user_prompt(self, query: str) -> str:
        """general_greeting 형식의 사용자 프롬프트"""
        return f"""사용자가 다음과 같이 말했습니다:

{query}

자연스럽고 친근하게 응답하되, 소비자 분쟁 상담으로 자연스럽게 유도하는 질문을 포함해 주세요."""

    # ============================================================
    # info_only 프롬프트 (기관 안내 중심)
    # ============================================================

    def _build_info_only_system_prompt(self, response_format: ResponseFormat) -> str:
        """info_only 형식의 시스템 프롬프트"""
        disclaimer_section = (
            f"\n\n---\n*{DISCLAIMER}*" if response_format.include_disclaimer else ""
        )

        return f"""당신은 한국 소비자 분쟁 조정 전문 상담 어시스턴트입니다.

역할:
- 전문 기관에 대한 정보를 제공합니다
- 법률 자문이나 확정적인 판단을 하지 않습니다
- 안전하고 정확한 정보를 전달합니다

답변 구조:

## 1. 담당 기관 안내
   - 해당 분쟁을 처리하는 전문 기관 정보
   - 웹사이트, 연락처 등

## 2. 관련 사례 (선택)
   - 참고할 수 있는 유사 사례 (있는 경우)
{disclaimer_section}

주의 사항:
- 전문 기관 상담을 권장합니다
- 법률 판단을 내리지 마세요
"""

    def _build_info_only_user_prompt(
        self, query: str, retrieval: Dict, agency_info: Dict, context: Dict
    ) -> str:
        """info_only 형식의 사용자 프롬프트"""
        lines = [f"사용자 질문: {query}\n"]

        lines.append("=" * 50)
        lines.append("[담당 기관 정보]")
        lines.extend(self._format_agency_section(agency_info))

        if context.get("has_cases"):
            lines.append("\n" + "=" * 50)
            lines.append("[관련 사례 (참고용)]")
            lines.extend(self._format_cases_section(retrieval, max_count=2))

        lines.append("\n" + "=" * 50)
        lines.append("\n위 정보를 바탕으로 사용자에게 전문 기관 상담을 안내해 주세요.")

        return "\n".join(lines)

    # ============================================================
    # 헬퍼 메서드
    # ============================================================

    def _format_onboarding_section(self, onboarding: Dict) -> List[str]:
        """
        온보딩 정보 포맷팅

        Args:
            onboarding: 온보딩 정보 딕셔너리
                - item_name: 품목명
                - purchase_date: 구매일
                - dispute_content: 분쟁 내용
                - purchase_price: 구매 금액 (선택)
                - purchase_channel: 구매 채널 (선택)
                - days_since_purchase: 구매 후 경과일 (선택)

        Returns:
            포맷팅된 문자열 리스트
        """
        lines = []

        item_name = onboarding.get("item_name", "")
        purchase_date = onboarding.get("purchase_date", "")
        dispute_content = onboarding.get("dispute_content", "")
        purchase_price = onboarding.get("purchase_price", "")
        purchase_channel = onboarding.get("purchase_channel", "")
        days_since_purchase = onboarding.get("days_since_purchase")

        if item_name:
            lines.append(f"- 품목: {item_name}")
        if purchase_date:
            lines.append(f"- 구매일: {purchase_date}")
        if purchase_price:
            lines.append(f"- 구매 금액: {purchase_price}")
        if purchase_channel:
            lines.append(f"- 구매 채널: {purchase_channel}")
        if dispute_content:
            lines.append(f"- 분쟁 내용: {dispute_content}")

        # 청약철회 기간 체크 (14일 이내)
        if days_since_purchase is not None:
            try:
                days = int(days_since_purchase)
                if days <= 14:
                    lines.append(
                        f"- 참고: 구매 후 {days}일 경과 (청약철회 가능 기간 내)"
                    )
                else:
                    lines.append(f"- 참고: 구매 후 {days}일 경과 (청약철회 기간 초과)")
            except (ValueError, TypeError):
                pass

        if not lines:
            lines.append("상세 상황 정보가 제공되지 않았습니다.")

        return lines

    def _format_laws_only_section(self, retrieval: Dict) -> List[str]:
        """
        법령 정보만 포맷팅 (law_response, law_onboarding용)

        Args:
            retrieval: 검색 결과 딕셔너리

        Returns:
            포맷팅된 문자열 리스트
        """
        lines = []
        laws = retrieval.get("laws", [])

        if laws:
            for law in laws[:5]:
                law_name = law.get("law_name", "법령")
                full_path = law.get("full_path", "")
                text = wrap_retrieved_context(
                    law.get("text", law.get("content", "")), max_length=500
                )
                similarity = law.get("similarity", 0)
                lines.append(f"\n### {law_name} {full_path}")
                lines.append(f"내용: {text}")
                lines.append(f"유사도: {similarity:.2%}")
        else:
            lines.append("관련 법령을 찾지 못했습니다.")

        return lines

    def _format_criteria_only_section(self, retrieval: Dict) -> List[str]:
        """
        분쟁해결기준 정보만 포맷팅 (criteria_response용)

        Args:
            retrieval: 검색 결과 딕셔너리

        Returns:
            포맷팅된 문자열 리스트
        """
        lines = []
        criteria = retrieval.get("criteria", [])

        if criteria:
            for crit in criteria[:5]:
                source_label = crit.get("source_label", "기준")
                category = crit.get("category", "")
                item = crit.get("item", crit.get("item_group", ""))
                path = (
                    f"{category} > {item}"
                    if category and item
                    else category or item or ""
                )
                unit_text = wrap_retrieved_context(
                    crit.get("unit_text", crit.get("content", "")), max_length=500
                )
                similarity = crit.get("similarity", 0)

                lines.append(f"\n### [{source_label}] {path}")
                lines.append(f"내용: {unit_text}")
                lines.append(f"유사도: {similarity:.2%}")
        else:
            lines.append("관련 분쟁해결기준을 찾지 못했습니다.")

        return lines

    def _format_cases_section(self, retrieval: Dict, max_count: int = 3) -> List[str]:
        """유사 사례 섹션 포맷팅"""
        lines = []
        disputes = retrieval.get("disputes", [])
        counsels = retrieval.get("counsels", [])

        lines.append("\n### 분쟁조정사례 (법적 효력 있음)")
        if disputes:
            for i, case in enumerate(disputes[:max_count], 1):
                lines.append(
                    f"\n{i}. [{case.get('source_org', '알 수 없음')}] {case.get('doc_title', '제목 없음')}"
                )
                if case.get("decision_date"):
                    lines.append(f"   결정일: {case['decision_date']}")
                lines.append(f"   유사도: {case.get('similarity', 0):.2%}")
                content = case.get("content", "")[:300]
                lines.append(f"   내용: {content}...")
        else:
            lines.append("   관련 분쟁조정사례를 찾지 못했습니다.")

        lines.append("\n### 상담사례 (참고용)")
        if counsels:
            for i, case in enumerate(counsels[:max_count], 1):
                lines.append(f"\n{i}. {case.get('doc_title', '제목 없음')}")
                lines.append(f"   유사도: {case.get('similarity', 0):.2%}")
                content = case.get("content", "")[:200]
                lines.append(f"   내용: {content}...")
        else:
            lines.append("   관련 상담사례를 찾지 못했습니다.")

        return lines

    def _format_legal_section(self, retrieval: Dict) -> List[str]:
        """법령 및 기준 섹션 포맷팅 (comprehensive_dispute 내부용)"""
        lines = []
        laws = retrieval.get("laws", [])
        criteria = retrieval.get("criteria", [])

        lines.append("\n### 관련 법령")
        if laws:
            for i, law in enumerate(laws[:3], 1):
                law_name = law.get("law_name", "법령")
                full_path = law.get("full_path", "")
                lines.append(f"\n{i}. {law_name} {full_path}")
                lines.append(f"   유사도: {law.get('similarity', 0):.2%}")
                text = law.get("text", law.get("content", ""))[:300]
                lines.append(f"   내용: {text}...")
        else:
            lines.append("   관련 법령을 찾지 못했습니다.")

        lines.append("\n### 분쟁해결기준")
        if criteria:
            for i, crit in enumerate(criteria[:3], 1):
                source_label = crit.get("source_label", "기준")
                category = crit.get("category", "")
                item = crit.get("item", crit.get("item_group", ""))
                path = (
                    f"{category} > {item}"
                    if category and item
                    else category or item or ""
                )

                lines.append(f"\n{i}. [{source_label}] {path}")
                lines.append(f"   유사도: {crit.get('similarity', 0):.2%}")
                text = crit.get("unit_text", crit.get("content", ""))[:300]
                lines.append(f"   내용: {text}...")
        else:
            lines.append("   관련 기준을 찾지 못했습니다.")

        return lines

    def _format_agency_section(self, agency_info: Dict) -> List[str]:
        """기관 정보 섹션 포맷팅"""
        lines = []
        info = agency_info.get("agency_info", {})

        lines.append(f"\n담당 기관: {info.get('full_name', '한국소비자원')}")
        lines.append(f"분쟁 유형: {agency_info.get('dispute_type', '1:N')}")
        lines.append(f"추천 이유: {agency_info.get('reason', '')}")
        agency_url = info.get("url", "")
        if agency_url:
            lines.append(f"웹사이트: {agency_url}")

        return lines


__all__ = ["PromptBuilder", "DISCLAIMER"]
