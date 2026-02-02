"""
똑소리 프로젝트 - 답변 형식 선택기

작성일: 2026-01-28
업데이트: 2026-02-01 (온보딩 인식 우선순위 기반 선택 로직)

[역할 및 책임]
쿼리 분석 결과, 검색 결과, 온보딩 정보를 기반으로 적절한 답변 형식을 선택합니다.

[선택 로직 - 우선순위 기반 매칭]
1. query_type in ['general', 'system_meta', 'meta_conversational'] → general_greeting
2. query_type == 'restricted' → info_only
3. query_type == 'law' + has_onboarding + has_laws → law_onboarding
4. query_type == 'law' → law_response
5. query_type == 'criteria' → criteria_response
6. query_type == 'dispute' + has_onboarding + (has_laws OR has_criteria) → comprehensive_dispute
7. query_type == 'dispute' + has_cases + NOT has_laws + NOT has_criteria → case_response
8. fallback (dispute/procedure/ambiguous/anything else) → comprehensive_dispute
"""

from typing import Dict, Optional
from .config import ResponseFormat, RESPONSE_FORMATS


class FormatSelector:
    """
    답변 형식 선택기

    쿼리 타입, 검색 결과, 온보딩 정보를 기반으로 최적의 답변 형식을 우선순위 매칭으로 선택합니다.
    """

    def select_format(
        self,
        query_analysis: Dict,
        retrieval: Dict,
        onboarding: Optional[Dict] = None,
    ) -> ResponseFormat:
        """
        답변 형식을 선택합니다 (온보딩 인식 우선순위 기반).

        Args:
            query_analysis: 쿼리 분석 결과
                - query_type: str (dispute, law, criteria, general, restricted 등)
            retrieval: 검색 결과
                - disputes: List
                - counsels: List
                - laws: List
                - criteria: List
                - agency: Dict
            onboarding: 온보딩 정보 (optional)
                - purchase_item: str

        Returns:
            선택된 ResponseFormat

        Example:
            >>> selector = FormatSelector()
            >>> query_analysis = {'query_type': 'law'}
            >>> retrieval = {'laws': [...]}
            >>> onboarding = {'purchase_item': '노트북'}
            >>> format = selector.select_format(query_analysis, retrieval, onboarding)
            >>> print(format.format_id)
            'law_onboarding'
        """
        query_type = query_analysis.get('query_type', 'dispute')
        context = self.build_context(retrieval, onboarding)

        # Priority-based matching (top-down, first match wins)

        # 1. General/Meta/System queries → general_greeting
        if query_type in ['general', 'system_meta', 'meta_conversational']:
            return RESPONSE_FORMATS['general_greeting']

        # 2. Restricted domain → info_only
        if query_type == 'restricted':
            return RESPONSE_FORMATS['info_only']

        # 3. Law query + onboarding + has laws → law_onboarding
        if query_type == 'law' and context['has_onboarding'] and context['has_laws']:
            return RESPONSE_FORMATS['law_onboarding']

        # 4. Law query → law_response
        if query_type == 'law':
            return RESPONSE_FORMATS['law_response']

        # 5. Criteria query → criteria_response
        if query_type == 'criteria':
            return RESPONSE_FORMATS['criteria_response']

        # 6. Dispute + onboarding + (laws OR criteria) → comprehensive_dispute
        if query_type == 'dispute' and context['has_onboarding']:
            if context['has_laws'] or context['has_criteria']:
                return RESPONSE_FORMATS['comprehensive_dispute']

        # 7. Dispute + cases only (no laws, no criteria) → case_response
        if query_type == 'dispute' and context['has_cases']:
            if not context['has_laws'] and not context['has_criteria']:
                return RESPONSE_FORMATS['case_response']

        # 8. Fallback (dispute/procedure/ambiguous/anything else) → comprehensive_dispute
        return RESPONSE_FORMATS['comprehensive_dispute']

    def build_context(self, retrieval: Dict, onboarding: Optional[Dict] = None) -> Dict[str, bool]:
        """
        검색 결과와 온보딩 정보를 기반으로 컨텍스트를 생성합니다.

        Args:
            retrieval: 검색 결과
            onboarding: 온보딩 정보 (optional)

        Returns:
            컨텍스트 딕셔너리
                - has_cases: bool (분쟁사례 or 상담사례 존재)
                - has_laws: bool (법령 존재)
                - has_criteria: bool (기준 존재)
                - has_agency: bool (기관 추천 존재)
                - has_onboarding: bool (온보딩 정보 존재)

        Example:
            >>> selector = FormatSelector()
            >>> retrieval = {'disputes': [{'doc_id': '123'}], 'laws': []}
            >>> onboarding = {'purchase_item': '노트북'}
            >>> context = selector.build_context(retrieval, onboarding)
            >>> print(context)
            {'has_cases': True, 'has_laws': False, 'has_criteria': False, 'has_agency': False, 'has_onboarding': True}
        """
        disputes = retrieval.get('disputes', [])
        counsels = retrieval.get('counsels', [])
        laws = retrieval.get('laws', [])
        criteria = retrieval.get('criteria', [])
        agency = retrieval.get('agency', {})

        return {
            'has_cases': bool(disputes or counsels),
            'has_laws': bool(laws),
            'has_criteria': bool(criteria),
            'has_agency': bool(agency),
            'has_onboarding': bool(onboarding and onboarding.get('purchase_item')),
        }


__all__ = ['FormatSelector']
