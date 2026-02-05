"""
똑소리 프로젝트 - 후속 질문 생성기

작성일: 2026-01-28

[역할 및 책임]
쿼리 분석 결과, 검색 결과, 생성된 답변을 기반으로
적절한 후속 질문과 명확화 질문을 생성합니다.

[생성 로직]
1. 컨텍스트 구축 (dispute_type, missing_fields, has_cases 등)
2. 템플릿 매칭 (조건 검사)
3. 우선순위 정렬
4. 최대 3-5개 질문 선택
"""

from typing import Dict, List, Optional

from .templates import (
    QuestionTemplate,
    get_templates_by_dispute_type,
)


class FollowupQuestionGenerator:
    """
    후속 질문 생성기

    쿼리 분석 결과와 검색 결과를 기반으로
    사용자에게 유용한 후속 질문과 명확화 질문을 생성합니다.
    """

    def __init__(
        self, max_followup_questions: int = 3, max_clarifying_questions: int = 2
    ):
        """
        Args:
            max_followup_questions: 최대 후속 질문 개수
            max_clarifying_questions: 최대 명확화 질문 개수
        """
        self.max_followup_questions = max_followup_questions
        self.max_clarifying_questions = max_clarifying_questions

    def generate_questions(
        self,
        query_analysis: Dict,
        retrieval: Dict,
        answer: str,
        format_id: Optional[str] = None,
        is_fallback: bool = False,
        template_key: Optional[str] = None,
    ) -> Dict[str, List[str]]:
        """
        후속 질문과 명확화 질문을 생성합니다.

        Args:
            query_analysis: 쿼리 분석 결과
                - dispute_type: str (환불, 교환, 수리 등)
                - missing_fields: List[str] (누락된 정보 목록)
                - query_type: str (dispute, general, etc.)
            retrieval: 검색 결과
                - disputes: List
                - counsels: List
                - laws: List
                - criteria: List
                - agency: Dict
            answer: 생성된 답변
            format_id: 답변 형식 식별자 (format 기반 필터링에 사용)
            is_fallback: fallback 모드 여부 (rule_based, safe_fallback 사용 시)
            template_key: 프롬프트 템플릿 키 (solution, action, execution 등)

        Returns:
            {
                'followup_questions': List[str],
                'clarifying_questions': List[str]
            }

        Example:
            >>> generator = FollowupQuestionGenerator()
            >>> query_analysis = {'dispute_type': '환불', 'missing_fields': []}
            >>> retrieval = {'disputes': [...], 'laws': [...]}
            >>> answer = "환불은 14일 이내..."
            >>> questions = generator.generate_questions(query_analysis, retrieval, answer)
            >>> print(questions)
            {
                'followup_questions': ['환불 처리 기간은 얼마나 걸리나요?', ...],
                'clarifying_questions': []
            }
        """
        # 1. 컨텍스트 구축
        context = self._build_context(
            query_analysis, retrieval, answer, format_id, is_fallback
        )

        # 2. 프롬프트 파일에서 동적 추출 시도 (inquiry, reject 제외)
        if template_key:
            # Lazy import to avoid circular dependency
            from ..answer_generation.template_loader import extract_followup_questions

            prompt_questions = extract_followup_questions(template_key)
            if prompt_questions:
                return {
                    "followup_questions": prompt_questions,
                    "clarifying_questions": self._generate_clarifying_questions(
                        context
                    ),
                }

        # 3. 기존 로직으로 후속 질문 생성
        followup_questions = self._generate_followup_questions(context)

        # 4. 명확화 질문 생성
        clarifying_questions = self._generate_clarifying_questions(context)

        return {
            "followup_questions": followup_questions,
            "clarifying_questions": clarifying_questions,
        }

    def _build_context(
        self,
        query_analysis: Dict,
        retrieval: Dict,
        answer: str,
        format_id: Optional[str] = None,
        is_fallback: bool = False,
    ) -> Dict:
        """
        템플릿 매칭을 위한 컨텍스트를 구축합니다.

        Args:
            query_analysis: 쿼리 분석 결과
            retrieval: 검색 결과
            answer: 생성된 답변
            format_id: 답변 형식 식별자

        Returns:
            컨텍스트 딕셔너리
        """
        disputes = retrieval.get("disputes", [])
        counsels = retrieval.get("counsels", [])
        laws = retrieval.get("laws", [])
        criteria = retrieval.get("criteria", [])
        agency = retrieval.get("agency", {})

        # 온보딩 컨텍스트에서 enriched 데이터 접근
        onboarding_ctx = query_analysis.get("onboarding_context", {})
        missing_fields = query_analysis.get("missing_fields", [])

        return {
            # 분쟁 유형
            "dispute_type": query_analysis.get("dispute_type", "일반"),
            # 검색 결과 존재 여부
            "has_cases": bool(disputes or counsels),
            "has_laws": bool(laws),
            "has_criteria": bool(criteria),
            "has_agency_recommendation": bool(agency),
            # 답변 내용 분석
            "no_timeline_mentioned": self._check_no_timeline(answer),
            "no_procedure_mentioned": self._check_no_procedure(answer),
            # 온보딩에 이미 있는 정보는 질문하지 않음
            "has_purchase_date": bool(onboarding_ctx.get("days_since_purchase")),
            "has_purchase_item": bool(onboarding_ctx.get("purchase_item")),
            "has_item_category": bool(onboarding_ctx.get("purchase_item_category")),
            # 답변에서 다룬 내용도 질문하지 않음
            "answered_refund_period": "청약철회" in answer or "14일" in answer,
            "answered_warranty": "품질보증" in answer or "보증기간" in answer,
            # 누락된 정보 (legacy fallback: 온보딩 컨텍스트 없으면 사용)
            "missing_purchase_date": (
                "purchase_date" in missing_fields
                and not onboarding_ctx.get("days_since_purchase")
            ),
            "missing_product_name": (
                "product_name" in missing_fields
                and not onboarding_ctx.get("purchase_item")
            ),
            "missing_issue_detail": "issue_detail" in missing_fields,
            "missing_seller_response": "seller_response" in missing_fields,
            "missing_amount": "amount" in missing_fields,
            # 답변 형식
            "format_id": format_id,
            # Fallback 여부 (rule_based 또는 safe_fallback 사용 시)
            "is_fallback": is_fallback,
        }

    def _select_questions_by_context(self, context: Dict) -> List[str]:
        """상황에 따라 적절한 질문 선택 (우선순위 로직)"""
        has_criteria = context.get("has_criteria", False)
        has_laws = context.get("has_laws", False)
        has_cases = context.get("has_cases", False)
        is_fallback = context.get("is_fallback", False)

        # Case 1: 이상한 말 (fallback) - 3개 버튼
        if is_fallback:
            return [
                "특정 품목의 환불 기준이 궁금하신가요?",
                "관련 법령을 확인해 드릴까요?",
                "유사한 분쟁 사례를 찾아볼까요?",
            ]

        # Case 2: 기준만 제공됨 - 2개 버튼
        if has_criteria and not has_laws and not has_cases:
            return [
                "이 기준의 법적 근거가 궁금하신가요?",
                "유사한 분쟁 사례를 확인해 보시겠어요?",
            ]

        # Case 3: 품목만 질의 - 2개 버튼
        if context.get("product_only", False):
            return [
                "관련 법령을 확인해 드릴까요?",
                "비슷한 사례를 찾아볼까요?",
            ]

        # Default: 빈 리스트 반환 (기존 템플릿 기반 로직 사용)
        return []

    def _generate_followup_questions(self, context: Dict) -> List[str]:
        """
        후속 질문을 생성합니다.

        Args:
            context: 컨텍스트

        Returns:
            후속 질문 목록 (최대 max_followup_questions개)
        """
        # 0. 상황별 템플릿 우선 적용 (fallback, 기준만, 품목만)
        context_based = self._select_questions_by_context(context)
        if context_based:
            return context_based

        dispute_type = context.get("dispute_type", "일반")
        format_id = context.get("format_id")

        # 1. 분쟁 유형에 맞는 템플릿 필터링
        candidate_templates = get_templates_by_dispute_type(dispute_type)

        # 2. followup 타입만 필터링
        followup_templates = [
            t for t in candidate_templates if t.question_type == "followup"
        ]

        # 3. format_id 기반 우선 필터링
        if format_id:
            format_preferred = self._get_format_preferred_templates(format_id)
            if format_preferred:
                # format 전용 템플릿 중 조건 매칭
                preferred_matched = self._match_templates(format_preferred, context)
                # 일반 템플릿 중 조건 매칭
                general_matched = self._match_templates(
                    [t for t in followup_templates if t not in format_preferred],
                    context,
                )
                # format 전용 우선, 나머지 보충
                matched_templates = preferred_matched + general_matched
            else:
                matched_templates = self._match_templates(followup_templates, context)
        else:
            # 4. 조건 매칭 (기존 로직)
            matched_templates = self._match_templates(followup_templates, context)

        # 5. 우선순위 정렬
        matched_templates.sort(key=lambda t: t.priority, reverse=True)

        # 6. 최대 개수 제한
        selected_templates = matched_templates[: self.max_followup_questions]

        return [t.question_text for t in selected_templates]

    def _generate_clarifying_questions(self, context: Dict) -> List[str]:
        """
        명확화 질문을 생성합니다.

        Args:
            context: 컨텍스트

        Returns:
            명확화 질문 목록 (최대 max_clarifying_questions개)
        """
        dispute_type = context.get("dispute_type", "일반")

        # 1. 분쟁 유형에 맞는 템플릿 필터링
        candidate_templates = get_templates_by_dispute_type(dispute_type)

        # 2. clarifying 타입만 필터링
        clarifying_templates = [
            t for t in candidate_templates if t.question_type == "clarifying"
        ]

        # 3. 조건 매칭
        matched_templates = self._match_templates(clarifying_templates, context)

        # 4. 우선순위 정렬
        matched_templates.sort(key=lambda t: t.priority, reverse=True)

        # 5. 최대 개수 제한
        selected_templates = matched_templates[: self.max_clarifying_questions]

        return [t.question_text for t in selected_templates]

    def _match_templates(
        self, templates: List[QuestionTemplate], context: Dict
    ) -> List[QuestionTemplate]:
        """
        조건에 맞는 템플릿을 필터링합니다.

        Args:
            templates: 템플릿 목록
            context: 컨텍스트

        Returns:
            조건에 맞는 템플릿 목록
        """
        matched = []

        for template in templates:
            if self._check_conditions(template.conditions, context):
                matched.append(template)

        return matched

    def _check_conditions(self, conditions: Dict, context: Dict) -> bool:
        """
        템플릿 조건을 검사합니다.

        Args:
            conditions: 템플릿 조건
            context: 컨텍스트

        Returns:
            조건 만족 여부
        """
        if not conditions:
            return True

        # 모든 조건을 만족해야 함
        for key, expected_value in conditions.items():
            actual_value = context.get(key, False)
            if actual_value != expected_value:
                return False

        return True

    def _check_no_timeline(self, answer: str) -> bool:
        """
        답변에 기간/일수 정보가 없는지 확인합니다.

        Args:
            answer: 생성된 답변

        Returns:
            기간 정보가 없으면 True
        """
        timeline_keywords = ["기간", "일", "주", "개월", "년", "시간", "날짜"]
        answer_lower = answer.lower()

        for keyword in timeline_keywords:
            if keyword in answer_lower:
                return False

        return True

    def _check_no_procedure(self, answer: str) -> bool:
        """
        답변에 절차 정보가 없는지 확인합니다.

        Args:
            answer: 생성된 답변

        Returns:
            절차 정보가 없으면 True
        """
        procedure_keywords = ["신청", "절차", "방법", "단계", "순서", "진행"]
        answer_lower = answer.lower()

        for keyword in procedure_keywords:
            if keyword in answer_lower:
                return False

        return True

    def _get_format_preferred_templates(self, format_id: str) -> List[QuestionTemplate]:
        """
        format_id에 맞는 우선 템플릿을 반환합니다.

        Args:
            format_id: 답변 형식 식별자

        Returns:
            해당 format에 우선 적용할 템플릿 목록
        """
        from .templates import FORMAT_GUIDED_TEMPLATES

        FORMAT_TEMPLATE_MAP = {
            "general_greeting": ["guide_to_dispute", "guide_onboarding"],
            "comprehensive_dispute": ["ask_similar_cases"],
            "law_response": ["ask_law_detail", "ask_situation_apply"],
            "criteria_response": ["ask_criteria_cases"],
        }

        preferred_ids = FORMAT_TEMPLATE_MAP.get(format_id, [])
        if not preferred_ids:
            return []

        return [t for t in FORMAT_GUIDED_TEMPLATES if t.template_id in preferred_ids]


__all__ = ["FollowupQuestionGenerator"]
