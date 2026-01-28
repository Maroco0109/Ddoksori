"""
똑소리 프로젝트 - Clarify 노드
작성일: 2026-01-20
PR-4: 사용자에게 역질문하여 정보 명확화

Clarify 트리거 조건:
1. 검색 유사도 < 0.40
2. 품목명 불명확 (브랜드/모델명만 있고 카테고리 없음)
3. 필수 정보 누락 (금액, 구매일 등)

역질문 방식: LLM 기반 (상황에 맞는 자연스러운 질문 생성)
"""

import logging
from typing import Dict, List, Optional, Any

from langchain_core.messages import AIMessage

from ..state import ChatState
from ..conversation_manager import get_next_questions, should_trigger_clarification

logger = logging.getLogger(__name__)

# 유사도 임계값
SIMILARITY_THRESHOLD = 0.40

# 필수 정보 필드
REQUIRED_FIELDS = ['purchase_item', 'dispute_details']

# 권장 정보 필드
RECOMMENDED_FIELDS = ['purchase_date', 'purchase_amount', 'purchase_place']

# 품목 카테고리 (브랜드/모델명 vs 제품 카테고리)
PRODUCT_CATEGORIES = [
    "노트북", "컴퓨터", "스마트폰", "휴대폰", "태블릿", "이어폰", "헤드폰",
    "TV", "냉장고", "세탁기", "에어컨", "청소기", "모니터", "카메라",
    "가구", "침대", "소파", "헬스장", "학원", "여행", "호텔",
    "옷", "신발", "가방", "자동차", "오토바이", "자전거",
]

# 브랜드 이름 패턴 (카테고리 불명확)
BRAND_ONLY_PATTERNS = [
    "삼성", "LG", "애플", "소니", "샤오미", "로지텍", "MS", "구글",
    "나이키", "아디다스", "뉴발란스", "구찌", "루이비통",
    "현대", "기아", "벤츠", "BMW", "아우디", "테슬라",
]

# 필드별 역질문 템플릿
CLARIFICATION_TEMPLATES = {
    'purchase_item': [
        "어떤 제품/서비스에 대한 문의인지 알려주시겠어요?",
        "구체적으로 어떤 품목인지 알려주시면 더 정확한 답변을 드릴 수 있어요.",
    ],
    'dispute_details': [
        "어떤 문제가 발생했는지 자세히 알려주시겠어요?",
        "구체적인 분쟁 상황을 설명해 주시면 도움이 될 것 같아요.",
    ],
    'purchase_date': [
        "언제 구매하셨나요? (대략적인 시기라도 괜찮아요)",
        "구매 시기를 알려주시면 관련 규정을 확인할 수 있어요.",
    ],
    'purchase_amount': [
        "구매 금액은 얼마였나요?",
        "결제하신 금액을 알려주시겠어요?",
    ],
    'purchase_place': [
        "어디서 구매하셨나요? (온라인/오프라인, 판매처 이름 등)",
        "구매처 정보를 알려주시면 도움이 될 것 같아요.",
    ],
    'product_category': [
        "{item}은(는) 어떤 종류의 제품인가요? (예: 마우스, 키보드, 이어폰 등)",
        "정확한 검색을 위해 {item}의 제품 종류를 알려주시겠어요?",
    ],
    'low_similarity': [
        "질문을 좀 더 구체적으로 해주시면 더 정확한 답변을 드릴 수 있어요.",
        "관련 사례를 찾기 어려운데, 조금 더 자세한 상황을 알려주시겠어요?",
    ],
}

# Pre-clarification 템플릿 (검색 전 모호한 쿼리용)
PRE_CLARIFICATION_TEMPLATES = {
    'ambiguous_general': """좀 더 자세한 상황을 알려주시면 도움을 드릴 수 있어요.

예를 들어 알려주시면 좋은 정보:
• 어떤 제품이나 서비스에 대한 문의인가요?
• 어떤 문제가 발생했나요? (환불, 교환, 수리, 배송 등)
• 언제, 어디서 구매하셨나요?""",
    'ambiguous_short': "질문을 좀 더 구체적으로 해주시면 정확한 답변을 드릴 수 있어요. 어떤 제품/서비스에서 어떤 문제가 발생했는지 알려주세요.",
}


def _check_brand_only_item(item: Optional[str]) -> bool:
    """품목이 브랜드명만 있고 카테고리가 불명확한지 확인"""
    if not item:
        return False

    item_lower = item.lower()

    # 브랜드명만 있는 경우
    for brand in BRAND_ONLY_PATTERNS:
        if brand.lower() in item_lower:
            # 카테고리가 함께 있는지 확인
            has_category = any(cat in item_lower for cat in PRODUCT_CATEGORIES)
            if not has_category:
                return True

    return False


def _get_missing_fields(state: ChatState) -> List[str]:
    """누락된 필수/권장 필드 확인"""
    missing = []

    # 온보딩 정보 확인
    onboarding = state.get('onboarding') or {}

    # 쿼리 분석에서 추출된 정보 확인
    query_analysis = state.get('query_analysis') or {}
    extracted_info = query_analysis.get('extracted_info') or {}

    # 필수 필드 체크
    for field in REQUIRED_FIELDS:
        value = onboarding.get(field) or extracted_info.get(field)
        if not value or (isinstance(value, str) and not value.strip()):
            missing.append(field)

    return missing


def _get_max_similarity(state: ChatState) -> float:
    """검색 결과의 최대 유사도 확인"""
    retrieval = state.get('retrieval') or {}
    return retrieval.get('max_similarity', 0.0)


def _generate_clarification_questions(
    missing_fields: List[str],
    low_similarity: bool,
    brand_only_item: Optional[str],
) -> List[str]:
    """상황에 맞는 역질문 생성"""
    questions = []

    # 브랜드만 있는 경우 (카테고리 불명확)
    if brand_only_item:
        template = CLARIFICATION_TEMPLATES['product_category'][0]
        questions.append(template.format(item=brand_only_item))

    # 필수 필드 누락
    for field in missing_fields:
        if field in CLARIFICATION_TEMPLATES:
            questions.append(CLARIFICATION_TEMPLATES[field][0])

    # 유사도 낮음
    if low_similarity and not questions:
        questions.append(CLARIFICATION_TEMPLATES['low_similarity'][0])

    # 최대 3개 질문
    return questions[:3]


def _build_clarification_response(questions: List[str]) -> str:
    """역질문 응답 메시지 구성"""
    if not questions:
        return "더 정확한 답변을 위해 추가 정보가 필요해요."

    if len(questions) == 1:
        return questions[0]

    # 여러 질문일 경우
    lines = ["더 정확한 답변을 드리기 위해 몇 가지 여쭤볼게요:"]
    for i, q in enumerate(questions, 1):
        lines.append(f"{i}. {q}")

    return "\n".join(lines)


def should_clarify(state: ChatState) -> bool:
    """
    Clarify가 필요한지 판단

    Args:
        state: 현재 ChatState

    Returns:
        True if clarification is needed
    """
    # 일반 채팅은 clarify 불필요
    chat_type = state.get('chat_type', 'dispute')
    if chat_type == 'general':
        return False

    # 조건 1: 검색 유사도 < 0.40
    max_similarity = _get_max_similarity(state)
    if max_similarity > 0 and max_similarity < SIMILARITY_THRESHOLD:
        logger.info(f"[Clarify] Low similarity detected: {max_similarity:.2f} < {SIMILARITY_THRESHOLD}")
        return True

    # 조건 2: 필수 정보 누락
    missing_fields = _get_missing_fields(state)
    if missing_fields:
        logger.info(f"[Clarify] Missing required fields: {missing_fields}")
        return True

    # 조건 3: 품목명 불명확 (브랜드만 있음)
    onboarding = state.get('onboarding') or {}
    query_analysis = state.get('query_analysis') or {}
    extracted_info = query_analysis.get('extracted_info') or {}
    item = onboarding.get('purchase_item') or extracted_info.get('purchase_item')

    if _check_brand_only_item(item):
        logger.info(f"[Clarify] Brand-only item detected: {item}")
        return True

    return False


def ask_clarification_node(state: ChatState) -> Dict[str, Any]:
    """
    Clarify 노드: 사용자에게 역질문하여 정보 명확화

    Args:
        state: 현재 ChatState

    Returns:
        부분 상태 업데이트:
        {
            'final_answer': str (역질문 메시지),
            'clarifying_questions': List[str],
            'awaiting_user_choice': True,
            'messages': [AIMessage]
        }
    """
    logger.info("[Clarify] Generating clarification questions")

    conversation_phase = state.get('conversation_phase', 'initial')
    if should_trigger_clarification(state):
        phase_questions = get_next_questions(state)
        if phase_questions:
            response = _build_clarification_response(phase_questions)
            logger.info(f"[Clarify] Phase-based questions for {conversation_phase}: {phase_questions}")
            return {
                'final_answer': response,
                'clarifying_questions': phase_questions,
                'awaiting_user_choice': True,
                'messages': [AIMessage(content=response)],
            }

    query_analysis = state.get('query_analysis') or {}
    query_type = query_analysis.get('query_type')

    if query_type == 'ambiguous':
        user_query = state.get('user_query', '')
        if len(user_query.strip()) <= 5:
            response = PRE_CLARIFICATION_TEMPLATES['ambiguous_short']
        else:
            response = PRE_CLARIFICATION_TEMPLATES['ambiguous_general']

        logger.info(f"[Clarify] Pre-clarification for ambiguous query: '{user_query[:20]}...'")
        return {
            'final_answer': response,
            'clarifying_questions': ['제품/서비스 정보', '문제 유형'],
            'awaiting_user_choice': True,
            'messages': [AIMessage(content=response)],
        }

    missing_fields = _get_missing_fields(state)
    max_similarity = _get_max_similarity(state)
    low_similarity = max_similarity > 0 and max_similarity < SIMILARITY_THRESHOLD

    onboarding = state.get('onboarding') or {}
    extracted_info = query_analysis.get('extracted_info') or {}
    item = onboarding.get('purchase_item') or extracted_info.get('purchase_item')
    brand_only_item = item if _check_brand_only_item(item) else None

    questions = _generate_clarification_questions(
        missing_fields=missing_fields,
        low_similarity=low_similarity,
        brand_only_item=brand_only_item,
    )

    response = _build_clarification_response(questions)

    logger.info(f"[Clarify] Generated {len(questions)} questions: {questions}")

    return {
        'final_answer': response,
        'clarifying_questions': questions,
        'awaiting_user_choice': True,
        'messages': [AIMessage(content=response)],
    }
