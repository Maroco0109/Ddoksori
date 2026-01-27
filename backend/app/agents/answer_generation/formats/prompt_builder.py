"""
똑소리 프로젝트 - 프롬프트 빌더

작성일: 2026-01-28

[역할 및 책임]
ResponseFormat에 따라 시스템 프롬프트와 사용자 프롬프트를 생성합니다.

[프롬프트 유형]
1. full_dispute: 구조화된 3섹션 프롬프트 (유사사례 → 법령기준 → 추가안내)
2. simple_general: 대화형 프롬프트 (자연스러운 대화체)
3. info_only: 정보제공 프롬프트 (기관 안내 중심)
"""

from typing import Dict, List
from .config import ResponseFormat


# 면책 문구
DISCLAIMER = "본 답변은 정보 제공 목적이며 법률 자문이 아닙니다. 최종 판단·결정은 관련 기관 또는 전문가와 상담하여 진행해 주세요."


class PromptBuilder:
    """
    프롬프트 빌더

    ResponseFormat에 따라 적절한 시스템 프롬프트와 사용자 프롬프트를 생성합니다.
    """

    def build_system_prompt(self, response_format: ResponseFormat) -> str:
        """
        시스템 프롬프트를 생성합니다.

        Args:
            response_format: 답변 형식

        Returns:
            시스템 프롬프트 문자열
        """
        if response_format.format_id == 'simple_general':
            return self._build_simple_general_system_prompt(response_format)
        elif response_format.format_id == 'info_only':
            return self._build_info_only_system_prompt(response_format)
        else:
            # full_dispute (기본)
            return self._build_full_dispute_system_prompt(response_format)

    def build_user_prompt(
        self,
        response_format: ResponseFormat,
        query: str,
        retrieval: Dict,
        agency_info: Dict,
        context: Dict
    ) -> str:
        """
        사용자 프롬프트를 생성합니다.

        Args:
            response_format: 답변 형식
            query: 사용자 질문
            retrieval: 검색 결과
            agency_info: 기관 정보
            context: 컨텍스트 (has_cases, has_laws 등)

        Returns:
            사용자 프롬프트 문자열
        """
        if response_format.format_id == 'simple_general':
            return self._build_simple_general_user_prompt(query)
        elif response_format.format_id == 'info_only':
            return self._build_info_only_user_prompt(
                query, retrieval, agency_info, context
            )
        else:
            # full_dispute (기본)
            return self._build_full_dispute_user_prompt(
                query, retrieval, agency_info, context, response_format
            )

    # ============================================================
    # full_dispute 프롬프트 (구조화된 3섹션)
    # ============================================================

    def _build_full_dispute_system_prompt(self, response_format: ResponseFormat) -> str:
        """full_dispute 형식의 시스템 프롬프트"""
        disclaimer_section = f"\n\n---\n*{DISCLAIMER}*" if response_format.include_disclaimer else ""

        return f"""당신은 한국 소비자 분쟁 조정 전문 상담 어시스턴트입니다.

역할:
- 검색된 사례, 법령, 기준을 기반으로 정보를 제공합니다
- 법률 자문이나 확정적인 판단을 하지 않습니다
- 근거가 부족할 경우 추가 질문을 통해 정보를 수집합니다

답변 구조 (반드시 아래 순서와 형식을 따르세요):

## 1. 유사 사례 분석
   - 분쟁조정사례: 법적 효력이 있는 조정 결과 (출처, 결정일 명시)
   - 상담사례: 참고용 정보

## 2. 관련 법령 및 기준
   - 관련 법령: 법령명과 조항을 정확히 인용
   - 분쟁해결기준: 해당 품목의 분쟁조정기준(별표) 안내

## 3. 추가 안내
   - 담당 기관: 분쟁 유형에 맞는 기관 안내
   - 연락처 및 웹사이트 정보
{disclaimer_section}

금지 사항:
- "~해야 합니다", "~입니다" 같은 단정적 표현
- 법률 판단이나 예측
- 개인정보 요구
"""

    def _build_full_dispute_user_prompt(
        self,
        query: str,
        retrieval: Dict,
        agency_info: Dict,
        context: Dict,
        response_format: ResponseFormat
    ) -> str:
        """full_dispute 형식의 사용자 프롬프트"""
        lines = [f"사용자 질문: {query}\n"]

        # 섹션별로 검색 결과 포맷팅
        for section in response_format.sections:
            if not section.should_include(context):
                continue

            if section.section_id == 'similar_cases':
                lines.append("=" * 50)
                lines.append("[섹션 1: 유사 사례 분석]")
                lines.extend(self._format_cases_section(retrieval))

            elif section.section_id == 'legal_basis':
                lines.append("\n" + "=" * 50)
                lines.append("[섹션 2: 관련 법령 및 기준]")
                lines.extend(self._format_legal_section(retrieval))

            elif section.section_id == 'agency_info':
                lines.append("\n" + "=" * 50)
                lines.append("[섹션 3: 추가 안내]")
                lines.extend(self._format_agency_section(agency_info))

        lines.append("\n" + "=" * 50)
        lines.append("\n위 정보를 바탕으로 사용자의 질문에 답변해 주세요.")
        lines.append("각 섹션별로 정리하여 답변하고, 출처를 명확히 밝혀 주세요.")
        if response_format.include_disclaimer:
            lines.append("답변 마지막에 면책 문구를 포함하세요.")

        return "\n".join(lines)

    # ============================================================
    # simple_general 프롬프트 (자연스러운 대화체)
    # ============================================================

    def _build_simple_general_system_prompt(self, response_format: ResponseFormat) -> str:
        """simple_general 형식의 시스템 프롬프트"""
        return """당신은 친근하고 도움이 되는 소비자 분쟁 상담 어시스턴트 '똑소리'입니다.

역할:
- 사용자와 자연스럽게 대화하며 소비자 분쟁 상담을 돕습니다
- 친근하고 공감적인 톤으로 소통합니다
- 복잡한 법률 용어 대신 쉬운 표현을 사용합니다

대화 스타일:
- 인사: "안녕하세요! 똑소리입니다. 어떻게 도와드릴까요?"
- 감사: "도움이 되셨다니 다행이에요. 또 궁금한 점이 있으시면 언제든 물어보세요!"
- 안내: "궁금하신 분쟁이나 문제가 있으시면 말씀해 주세요. 최선을 다해 도와드릴게요."

주의 사항:
- 형식적인 섹션 구조를 사용하지 마세요
- 자연스러운 대화체로 응답하세요
- 면책 문구를 포함하지 마세요
"""

    def _build_simple_general_user_prompt(self, query: str) -> str:
        """simple_general 형식의 사용자 프롬프트"""
        return f"""사용자가 다음과 같이 말했습니다:

"{query}"

자연스럽고 친근하게 응답해 주세요. 형식적인 섹션 구조 없이 대화하듯이 답변하세요."""

    # ============================================================
    # info_only 프롬프트 (기관 안내 중심)
    # ============================================================

    def _build_info_only_system_prompt(self, response_format: ResponseFormat) -> str:
        """info_only 형식의 시스템 프롬프트"""
        disclaimer_section = f"\n\n---\n*{DISCLAIMER}*" if response_format.include_disclaimer else ""

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
        self,
        query: str,
        retrieval: Dict,
        agency_info: Dict,
        context: Dict
    ) -> str:
        """info_only 형식의 사용자 프롬프트"""
        lines = [f"사용자 질문: {query}\n"]

        lines.append("=" * 50)
        lines.append("[담당 기관 정보]")
        lines.extend(self._format_agency_section(agency_info))

        if context.get('has_cases'):
            lines.append("\n" + "=" * 50)
            lines.append("[관련 사례 (참고용)]")
            lines.extend(self._format_cases_section(retrieval, max_count=2))

        lines.append("\n" + "=" * 50)
        lines.append("\n위 정보를 바탕으로 사용자에게 전문 기관 상담을 안내해 주세요.")

        return "\n".join(lines)

    # ============================================================
    # 헬퍼 메서드
    # ============================================================

    def _format_cases_section(self, retrieval: Dict, max_count: int = 3) -> List[str]:
        """유사 사례 섹션 포맷팅"""
        lines = []
        disputes = retrieval.get('disputes', [])
        counsels = retrieval.get('counsels', [])

        lines.append("\n### 분쟁조정사례 (법적 효력 있음)")
        if disputes:
            for i, case in enumerate(disputes[:max_count], 1):
                lines.append(f"\n{i}. [{case.get('source_org', '알 수 없음')}] {case.get('doc_title', '제목 없음')}")
                if case.get('decision_date'):
                    lines.append(f"   결정일: {case['decision_date']}")
                lines.append(f"   유사도: {case.get('similarity', 0):.2%}")
                content = case.get('content', '')[:300]
                lines.append(f"   내용: {content}...")
        else:
            lines.append("   관련 분쟁조정사례를 찾지 못했습니다.")

        lines.append("\n### 상담사례 (참고용)")
        if counsels:
            for i, case in enumerate(counsels[:max_count], 1):
                lines.append(f"\n{i}. {case.get('doc_title', '제목 없음')}")
                lines.append(f"   유사도: {case.get('similarity', 0):.2%}")
                content = case.get('content', '')[:200]
                lines.append(f"   내용: {content}...")
        else:
            lines.append("   관련 상담사례를 찾지 못했습니다.")

        return lines

    def _format_legal_section(self, retrieval: Dict) -> List[str]:
        """법령 및 기준 섹션 포맷팅"""
        lines = []
        laws = retrieval.get('laws', [])
        criteria = retrieval.get('criteria', [])

        lines.append("\n### 관련 법령")
        if laws:
            for i, law in enumerate(laws[:3], 1):
                law_name = law.get('law_name', '법령')
                full_path = law.get('full_path', '')
                lines.append(f"\n{i}. {law_name} {full_path}")
                lines.append(f"   유사도: {law.get('similarity', 0):.2%}")
                text = law.get('text', law.get('content', ''))[:300]
                lines.append(f"   내용: {text}...")
        else:
            lines.append("   관련 법령을 찾지 못했습니다.")

        lines.append("\n### 분쟁해결기준")
        if criteria:
            for i, crit in enumerate(criteria[:3], 1):
                source_label = crit.get('source_label', '기준')
                category = crit.get('category', '')
                item = crit.get('item', crit.get('item_group', ''))
                path = f"{category} > {item}" if category and item else category or item or ''

                lines.append(f"\n{i}. [{source_label}] {path}")
                lines.append(f"   유사도: {crit.get('similarity', 0):.2%}")
                text = crit.get('unit_text', crit.get('content', ''))[:300]
                lines.append(f"   내용: {text}...")
        else:
            lines.append("   관련 기준을 찾지 못했습니다.")

        return lines

    def _format_agency_section(self, agency_info: Dict) -> List[str]:
        """기관 정보 섹션 포맷팅"""
        lines = []
        info = agency_info.get('agency_info', {})

        lines.append(f"\n담당 기관: {info.get('full_name', '한국소비자원')}")
        lines.append(f"분쟁 유형: {agency_info.get('dispute_type', '1:N')}")
        lines.append(f"추천 이유: {agency_info.get('reason', '')}")
        agency_url = info.get('url', '')
        if agency_url:
            lines.append(f"웹사이트: {agency_url}")

        return lines


__all__ = ['PromptBuilder', 'DISCLAIMER']
