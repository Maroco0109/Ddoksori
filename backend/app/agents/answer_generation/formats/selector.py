"""
똑소리 프로젝트 - 답변 형식 선택기

작성일: 2026-01-28

[역할 및 책임]
쿼리 분석 결과와 검색 결과를 기반으로 적절한 답변 형식을 선택합니다.

[선택 로직]
1. query_type 우선 매칭
2. retrieval 결과 확인 (has_cases, has_laws)
3. 기본값: full_dispute
"""

from typing import Dict, Optional
from .config import ResponseFormat, RESPONSE_FORMATS, get_format_by_query_type


class FormatSelector:
    """
    답변 형식 선택기

    쿼리 타입과 검색 결과를 기반으로 최적의 답변 형식을 선택합니다.
    """

    def select_format(
        self,
        query_analysis: Dict,
        retrieval: Dict
    ) -> ResponseFormat:
        """
        답변 형식을 선택합니다.

        Args:
            query_analysis: 쿼리 분석 결과
                - query_type: str (dispute, general, restricted 등)
            retrieval: 검색 결과
                - disputes: List
                - counsels: List
                - laws: List
                - criteria: List

        Returns:
            선택된 ResponseFormat

        Example:
            >>> selector = FormatSelector()
            >>> query_analysis = {'query_type': 'dispute'}
            >>> retrieval = {'disputes': [...], 'laws': [...]}
            >>> format = selector.select_format(query_analysis, retrieval)
            >>> print(format.format_id)
            'full_dispute'
        """
        # 1. query_type 기반 형식 선택
        query_type = query_analysis.get('query_type', 'dispute')
        selected_format = get_format_by_query_type(query_type)

        if selected_format:
            return selected_format

        # 2. 기본값: full_dispute
        return RESPONSE_FORMATS['full_dispute']

    def build_context(self, retrieval: Dict) -> Dict[str, bool]:
        """
        검색 결과를 기반으로 컨텍스트를 생성합니다.

        Args:
            retrieval: 검색 결과

        Returns:
            컨텍스트 딕셔너리
                - has_cases: bool (분쟁사례 or 상담사례 존재)
                - has_laws: bool (법령 존재)
                - has_criteria: bool (기준 존재)
                - has_agency: bool (기관 추천 존재)

        Example:
            >>> selector = FormatSelector()
            >>> retrieval = {'disputes': [{'doc_id': '123'}], 'laws': []}
            >>> context = selector.build_context(retrieval)
            >>> print(context)
            {'has_cases': True, 'has_laws': False, 'has_criteria': False, 'has_agency': False}
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
        }


__all__ = ['FormatSelector']
