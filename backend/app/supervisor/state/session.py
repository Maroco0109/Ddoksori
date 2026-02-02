"""
똑소리 프로젝트 - 세션 상태 스키마

세션 메타데이터와 사용자 온보딩 정보를 관리합니다.
대화 유형(일반/분쟁)과 온보딩 폼 데이터를 포함합니다.
"""

from typing import Literal, Optional

from typing_extensions import TypedDict


class OnboardingInfo(TypedDict, total=False):
    """
    온보딩 폼 데이터 (분쟁 상담용)

    프론트엔드 DisputeFormData와 매핑:
    - purchase_date: 구매일자 (예: "2026-01-15")
    - purchase_place: 구매처 (판매자 상호/브랜드)
    - purchase_platform: 구매 플랫폼 (온라인/오프라인)
    - purchase_item: 구매 품목 (예: "헬스장 회원권")
    - purchase_amount: 구매 금액 (예: "500000")
    - dispute_details: 분쟁 상세 내용
    - days_since_purchase: 구매 후 경과 일수 (자동 계산)
    - product_category: 품목 카테고리 (전자제품, 의류 등)

    Example:
        >>> onboarding: OnboardingInfo = {
        ...     'purchase_item': '헬스장 회원권',
        ...     'purchase_amount': '500000',
        ...     'dispute_details': '환불 거부당함'
        ... }
    """

    purchase_date: Optional[str]
    purchase_place: Optional[str]
    purchase_platform: Optional[str]
    purchase_item: Optional[str]
    purchase_amount: Optional[str]
    dispute_details: Optional[str]
    days_since_purchase: Optional[int]  # 구매 후 경과 일수 (자동 계산)
    product_category: Optional[str]  # 품목 카테고리 (전자제품, 의류 등)


# 대화 유형 타입 정의
ChatType = Literal["dispute", "general"]


class SessionState(TypedDict, total=False):
    """
    세션 메타데이터 상태

    대화 세션의 기본 정보를 담고 있습니다.
    thread_id(=session_id)별로 checkpointer에 저장됩니다.

    Attributes:
        chat_type: 상담 유형 ('dispute': 분쟁 상담, 'general': 일반 상담)
        onboarding: 온보딩 폼 데이터 (분쟁 상담 시 필수 정보)
        user_query: 현재 턴의 사용자 질문
    """

    chat_type: ChatType
    onboarding: Optional[OnboardingInfo]
    user_query: str


__all__ = [
    "OnboardingInfo",
    "ChatType",
    "SessionState",
]
