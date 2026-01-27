"""
똑소리 프로젝트 - 후속 질문 템플릿 라이브러리

작성일: 2026-01-28

[역할 및 책임]
분쟁 유형별 후속 질문 템플릿을 관리합니다.

[질문 유형]
1. followup: 현재 답변을 기반으로 더 알아볼 수 있는 질문
2. clarifying: 불명확한 정보를 명확히 하기 위한 질문

[분쟁 유형]
- 환불 (refund)
- 교환 (exchange)
- 수리 (repair)
- 배송 (delivery)
- 품질 (quality)
- 계약해지 (cancellation)
- 일반 (general)
"""

from typing import List, Dict, Literal
from dataclasses import dataclass


@dataclass
class QuestionTemplate:
    """
    질문 템플릿

    Attributes:
        template_id: 템플릿 식별자
        question_type: 질문 유형 (followup | clarifying)
        dispute_types: 적용 가능한 분쟁 유형 목록
        question_text: 질문 텍스트
        conditions: 표시 조건 (예: {'has_cases': True})
        priority: 우선순위 (높을수록 우선)
    """
    template_id: str
    question_type: Literal['followup', 'clarifying']
    dispute_types: List[str]
    question_text: str
    conditions: Dict[str, bool]
    priority: int = 1


# ============================================================
# 환불 (Refund) 관련 질문
# ============================================================

REFUND_TEMPLATES = [
    QuestionTemplate(
        template_id='refund_timeline',
        question_type='followup',
        dispute_types=['환불', 'refund'],
        question_text='환불 처리 기간은 얼마나 걸리나요?',
        conditions={'no_timeline_mentioned': True},
        priority=3
    ),
    QuestionTemplate(
        template_id='refund_documents',
        question_type='followup',
        dispute_types=['환불', 'refund'],
        question_text='환불 신청 시 어떤 서류가 필요한가요?',
        conditions={},
        priority=2
    ),
    QuestionTemplate(
        template_id='partial_refund',
        question_type='followup',
        dispute_types=['환불', 'refund'],
        question_text='부분 환불도 가능한가요?',
        conditions={'has_cases': True},
        priority=2
    ),
    QuestionTemplate(
        template_id='refund_rejection',
        question_type='followup',
        dispute_types=['환불', 'refund'],
        question_text='환불이 거부되면 어떻게 대응해야 하나요?',
        conditions={},
        priority=2
    ),
]

# ============================================================
# 교환 (Exchange) 관련 질문
# ============================================================

EXCHANGE_TEMPLATES = [
    QuestionTemplate(
        template_id='exchange_period',
        question_type='followup',
        dispute_types=['교환', 'exchange'],
        question_text='교환 가능 기간은 얼마나 되나요?',
        conditions={'no_timeline_mentioned': True},
        priority=3
    ),
    QuestionTemplate(
        template_id='exchange_shipping',
        question_type='followup',
        dispute_types=['교환', 'exchange'],
        question_text='교환 시 배송비는 누가 부담하나요?',
        conditions={},
        priority=2
    ),
    QuestionTemplate(
        template_id='exchange_different_item',
        question_type='followup',
        dispute_types=['교환', 'exchange'],
        question_text='다른 제품으로 교환할 수 있나요?',
        conditions={},
        priority=1
    ),
]

# ============================================================
# 수리 (Repair) 관련 질문
# ============================================================

REPAIR_TEMPLATES = [
    QuestionTemplate(
        template_id='repair_warranty',
        question_type='followup',
        dispute_types=['수리', 'repair', 'AS'],
        question_text='무상 AS 기간이 얼마나 남았나요?',
        conditions={'no_timeline_mentioned': True},
        priority=3
    ),
    QuestionTemplate(
        template_id='repair_cost',
        question_type='followup',
        dispute_types=['수리', 'repair', 'AS'],
        question_text='유상 수리 비용은 얼마나 나올까요?',
        conditions={},
        priority=2
    ),
    QuestionTemplate(
        template_id='repair_impossible',
        question_type='followup',
        dispute_types=['수리', 'repair', 'AS'],
        question_text='수리가 불가능하면 환불받을 수 있나요?',
        conditions={'has_cases': True},
        priority=2
    ),
]

# ============================================================
# 배송 (Delivery) 관련 질문
# ============================================================

DELIVERY_TEMPLATES = [
    QuestionTemplate(
        template_id='delivery_delay_compensation',
        question_type='followup',
        dispute_types=['배송', 'delivery', '지연배송'],
        question_text='배송 지연 시 보상을 받을 수 있나요?',
        conditions={'has_laws': True},
        priority=3
    ),
    QuestionTemplate(
        template_id='delivery_lost',
        question_type='followup',
        dispute_types=['배송', 'delivery'],
        question_text='택배가 분실되면 어떻게 대응해야 하나요?',
        conditions={},
        priority=2
    ),
    QuestionTemplate(
        template_id='delivery_damage',
        question_type='followup',
        dispute_types=['배송', 'delivery', '파손'],
        question_text='배송 중 파손된 경우 배상 범위는 어떻게 되나요?',
        conditions={'has_cases': True},
        priority=2
    ),
]

# ============================================================
# 품질 (Quality) 관련 질문
# ============================================================

QUALITY_TEMPLATES = [
    QuestionTemplate(
        template_id='quality_defect_criteria',
        question_type='followup',
        dispute_types=['품질', 'quality', '하자', '불량'],
        question_text='품질 하자는 어떻게 판단하나요?',
        conditions={'has_criteria': True},
        priority=3
    ),
    QuestionTemplate(
        template_id='quality_inspection',
        question_type='followup',
        dispute_types=['품질', 'quality', '하자'],
        question_text='품질 검사는 어디서 받을 수 있나요?',
        conditions={},
        priority=2
    ),
    QuestionTemplate(
        template_id='quality_compensation',
        question_type='followup',
        dispute_types=['품질', 'quality'],
        question_text='품질 문제로 인한 보상 범위는 어떻게 되나요?',
        conditions={'has_cases': True},
        priority=2
    ),
]

# ============================================================
# 계약해지 (Cancellation) 관련 질문
# ============================================================

CANCELLATION_TEMPLATES = [
    QuestionTemplate(
        template_id='cancellation_penalty',
        question_type='followup',
        dispute_types=['계약해지', 'cancellation', '해지'],
        question_text='계약 해지 시 위약금은 얼마나 나오나요?',
        conditions={},
        priority=3
    ),
    QuestionTemplate(
        template_id='cancellation_procedure',
        question_type='followup',
        dispute_types=['계약해지', 'cancellation'],
        question_text='계약 해지 절차는 어떻게 되나요?',
        conditions={'no_procedure_mentioned': True},
        priority=3
    ),
    QuestionTemplate(
        template_id='cancellation_refund',
        question_type='followup',
        dispute_types=['계약해지', 'cancellation'],
        question_text='해지 후 환급받을 수 있는 금액은 얼마인가요?',
        conditions={'has_criteria': True},
        priority=2
    ),
]

# ============================================================
# 일반 (General) 질문
# ============================================================

GENERAL_TEMPLATES = [
    QuestionTemplate(
        template_id='general_mediation_apply',
        question_type='followup',
        dispute_types=['일반', 'general'],
        question_text='분쟁조정 신청은 어떻게 하나요?',
        conditions={'no_procedure_mentioned': True, 'has_agency_recommendation': True},
        priority=3
    ),
    QuestionTemplate(
        template_id='general_lawsuit',
        question_type='followup',
        dispute_types=['일반', 'general'],
        question_text='소송을 진행하려면 어떻게 해야 하나요?',
        conditions={'has_cases': True},
        priority=2
    ),
    QuestionTemplate(
        template_id='general_evidence',
        question_type='followup',
        dispute_types=['일반', 'general'],
        question_text='어떤 증거 자료를 준비해야 하나요?',
        conditions={},
        priority=2
    ),
    QuestionTemplate(
        template_id='general_timeline',
        question_type='followup',
        dispute_types=['일반', 'general'],
        question_text='분쟁 해결까지 얼마나 걸리나요?',
        conditions={'no_timeline_mentioned': True},
        priority=2
    ),
    QuestionTemplate(
        template_id='general_cost',
        question_type='followup',
        dispute_types=['일반', 'general'],
        question_text='분쟁조정 신청 비용이 드나요?',
        conditions={'has_agency_recommendation': True},
        priority=1
    ),
]

# ============================================================
# 명확화 질문 (Clarifying) - 정보 부족 시
# ============================================================

CLARIFYING_TEMPLATES = [
    QuestionTemplate(
        template_id='clarify_purchase_date',
        question_type='clarifying',
        dispute_types=['환불', 'refund', '교환', 'exchange', '일반', 'general'],
        question_text='제품을 언제 구매하셨나요?',
        conditions={'missing_purchase_date': True},
        priority=3
    ),
    QuestionTemplate(
        template_id='clarify_product_name',
        question_type='clarifying',
        dispute_types=['일반', 'general'],
        question_text='정확한 제품명이나 서비스명을 알려주시겠어요?',
        conditions={'missing_product_name': True},
        priority=3
    ),
    QuestionTemplate(
        template_id='clarify_issue_detail',
        question_type='clarifying',
        dispute_types=['일반', 'general'],
        question_text='어떤 문제가 발생했는지 자세히 설명해 주시겠어요?',
        conditions={'missing_issue_detail': True},
        priority=3
    ),
    QuestionTemplate(
        template_id='clarify_seller_response',
        question_type='clarifying',
        dispute_types=['환불', 'refund', '교환', 'exchange'],
        question_text='판매자에게 연락해 보셨나요? 어떤 답변을 받으셨나요?',
        conditions={'missing_seller_response': True},
        priority=2
    ),
    QuestionTemplate(
        template_id='clarify_amount',
        question_type='clarifying',
        dispute_types=['환불', 'refund', '계약해지', 'cancellation'],
        question_text='구매 금액이나 계약 금액은 얼마인가요?',
        conditions={'missing_amount': True},
        priority=2
    ),
]


# ============================================================
# 통합 템플릿 라이브러리
# ============================================================

QUESTION_TEMPLATES: List[QuestionTemplate] = (
    REFUND_TEMPLATES +
    EXCHANGE_TEMPLATES +
    REPAIR_TEMPLATES +
    DELIVERY_TEMPLATES +
    QUALITY_TEMPLATES +
    CANCELLATION_TEMPLATES +
    GENERAL_TEMPLATES +
    CLARIFYING_TEMPLATES
)


def get_templates_by_dispute_type(dispute_type: str) -> List[QuestionTemplate]:
    """
    분쟁 유형별 템플릿을 조회합니다.

    Args:
        dispute_type: 분쟁 유형 (환불, 교환, 수리 등)

    Returns:
        해당 분쟁 유형에 적용 가능한 템플릿 목록
    """
    return [
        template for template in QUESTION_TEMPLATES
        if dispute_type in template.dispute_types or '일반' in template.dispute_types
    ]


def get_templates_by_question_type(
    question_type: Literal['followup', 'clarifying']
) -> List[QuestionTemplate]:
    """
    질문 유형별 템플릿을 조회합니다.

    Args:
        question_type: 질문 유형 (followup | clarifying)

    Returns:
        해당 질문 유형의 템플릿 목록
    """
    return [
        template for template in QUESTION_TEMPLATES
        if template.question_type == question_type
    ]


__all__ = [
    'QuestionTemplate',
    'QUESTION_TEMPLATES',
    'REFUND_TEMPLATES',
    'EXCHANGE_TEMPLATES',
    'REPAIR_TEMPLATES',
    'DELIVERY_TEMPLATES',
    'QUALITY_TEMPLATES',
    'CANCELLATION_TEMPLATES',
    'GENERAL_TEMPLATES',
    'CLARIFYING_TEMPLATES',
    'get_templates_by_dispute_type',
    'get_templates_by_question_type',
]
