"""
Rule-based Conversation Phase Manager for DDOKSORI.

Implements deterministic phase transitions and slot management
without LLM calls for cost-efficient progressive dispute consultation.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

# LEGACY: Phase System removed. This module is kept for backward compatibility.
# SlotStatus and ConversationPhase are defined locally for legacy code.
from typing_extensions import TypedDict


class SlotStatus(TypedDict):
    slot_name: str
    status: str  # 'filled' | 'partial' | 'missing'
    evidence_chunk_ids: List[str]
    confidence: float


ConversationPhase = str  # Was a Literal type, now just str for legacy compat

from .state import ChatState

REQUIRED_SLOTS = ["purchase_item", "problem_details"]
OPTIONAL_SLOTS = ["dispute_type", "purchase_date", "purchase_place"]
ALL_SLOTS = REQUIRED_SLOTS + OPTIONAL_SLOTS

SLOT_QUESTION_TEMPLATES = {
    "purchase_item": "어떤 제품/서비스에 대한 문의인가요?",
    "dispute_type": "어떤 요청이신가요? (환불/교환/수리/취소/해지 중)",
    "problem_details": "어떤 문제가 있었는지 한두 문장으로 설명해 주세요.",
    "purchase_date": "구매(계약) 시기가 언제인지 대략 알려주실 수 있을까요?",
    "purchase_place": "구매처가 어디인지 알려주실 수 있을까요? (온라인/오프라인, 판매처)",
}

YES_PATTERNS = [
    r"^네$",
    r"^예$",
    r"^응$",
    r"^어$",
    r"^그래$",
    r"^좋아$",
    r"^알려\s*줘",
    r"^보여\s*줘",
    r"^알고\s*싶",
    r"^궁금",
    r"보고\s*싶",
    r"알려\s*주세요",
    r"부탁",
]
NO_PATTERNS = [
    r"^아니",
    r"^괜찮",
    r"^됐",
    r"^안\s*해도",
    r"^필요\s*없",
    r"다음에",
    r"나중에",
    r"^싫",
]

DISPUTE_INTENT_PATTERNS = [
    r"환불",
    r"반품",
    r"교환",
    r"수리",
    r"취소",
    r"해지",
    r"청약철회",
    r"분쟁",
    r"피해",
    r"보상",
    r"배상",
    r"소비자",
]

DISPUTE_TYPE_MAPPING = {
    "환불": "refund",
    "반품": "refund",
    "교환": "exchange",
    "수리": "repair",
    "취소": "cancellation",
    "해지": "cancellation",
    "청약철회": "withdrawal",
}


def detect_yes_no(text: str) -> Optional[bool]:
    """Detect yes/no intent from user message using rule-based patterns."""
    text = text.strip().lower()

    for pattern in YES_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    for pattern in NO_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return False

    return None


def detect_dispute_intent(text: str) -> bool:
    """Detect if user message contains dispute-related intent."""
    for pattern in DISPUTE_INTENT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def extract_dispute_type(text: str) -> Optional[str]:
    """Extract dispute type from user message using keyword matching."""
    for korean_keyword, dispute_type in DISPUTE_TYPE_MAPPING.items():
        if korean_keyword in text:
            return dispute_type
    return None


def merge_slots(
    existing_slots: Dict[str, Optional[str]],
    onboarding: Optional[Dict[str, Any]],
    extracted_info: Optional[Dict[str, Any]],
) -> Dict[str, Optional[str]]:
    """
    Merge slot values from multiple sources with precedence:
    1. extracted_info (current turn extraction) - highest priority
    2. onboarding (frontend form data)
    3. existing_slots (memory) - lowest priority
    """
    merged = (
        dict(existing_slots) if existing_slots else {slot: None for slot in ALL_SLOTS}
    )

    if onboarding:
        if onboarding.get("purchase_item"):
            merged["purchase_item"] = onboarding["purchase_item"]
        if onboarding.get("dispute_details"):
            merged["problem_details"] = onboarding["dispute_details"]

    if extracted_info:
        for slot in ALL_SLOTS:
            value = extracted_info.get(slot)
            if value:
                merged[slot] = value
        if extracted_info.get("dispute_details") and not merged.get("problem_details"):
            merged["problem_details"] = extracted_info["dispute_details"]

    return merged


def compute_slot_status(slots: Dict[str, Optional[str]]) -> Dict[str, SlotStatus]:
    """Compute status for each slot based on its value."""
    status = {}
    for slot_name in ALL_SLOTS:
        value = slots.get(slot_name)
        if value and len(str(value).strip()) > 2:
            status[slot_name] = SlotStatus(
                slot_name=slot_name,
                status="filled",
                evidence_chunk_ids=[],
                confidence=1.0,
            )
        elif value:
            status[slot_name] = SlotStatus(
                slot_name=slot_name,
                status="partial",
                evidence_chunk_ids=[],
                confidence=0.5,
            )
        else:
            status[slot_name] = SlotStatus(
                slot_name=slot_name,
                status="missing",
                evidence_chunk_ids=[],
                confidence=0.0,
            )
    return status


def are_required_slots_filled(slot_status: Dict[str, SlotStatus]) -> bool:
    """Check if all required slots are filled."""
    for slot_name in REQUIRED_SLOTS:
        status = slot_status.get(slot_name)
        if not status or status["status"] != "filled":
            return False
    return True


def get_missing_slot_questions(
    slot_status: Dict[str, SlotStatus], max_questions: int = 3
) -> List[str]:
    """Generate questions for missing required slots first, then optional slots."""
    questions = []

    for slot_name in REQUIRED_SLOTS:
        if len(questions) >= max_questions:
            break
        status = slot_status.get(slot_name)
        if not status or status["status"] in ("missing", "partial"):
            template = SLOT_QUESTION_TEMPLATES.get(slot_name)
            if template:
                questions.append(template)

    for slot_name in OPTIONAL_SLOTS:
        if len(questions) >= max_questions:
            break
        status = slot_status.get(slot_name)
        if not status or status["status"] == "missing":
            template = SLOT_QUESTION_TEMPLATES.get(slot_name)
            if template:
                questions.append(template)

    return questions


def is_new_topic(user_query: str, current_phase: ConversationPhase) -> bool:
    """
    사용자가 새로운 주제를 질문하는지 판단합니다.
    awaiting_* phase에서 단순 긍정/부정이 아닌 새로운 키워드가 포함된 경우.
    """
    if current_phase not in ("awaiting_law_confirm", "awaiting_procedure_confirm"):
        return False
    # 긍정/부정 응답이 아니면서 길이가 충분한 경우 새 토픽으로 판단
    yes_no = detect_yes_no(user_query)
    if yes_no is not None:
        return False
    return len(user_query.strip()) > 5


def compute_phase_transition(
    current_phase: ConversationPhase,
    user_query: str,
    slot_status: Dict[str, SlotStatus],
    query_type: Optional[str] = None,
) -> Tuple[ConversationPhase, str]:
    """
    Progressive Disclosure 기반 대화 phase 전이를 계산합니다.

    흐름:
    - initial → info_gathering (슬롯 미충족) 또는 providing_case_summary (슬롯 충족/NEED_RAG)
    - providing_case_summary → awaiting_law_confirm (사례 제공 완료)
    - awaiting_law_confirm → providing_law_detail (긍정) / initial (새 토픽) / awaiting_procedure_confirm (부정)
    - providing_law_detail → awaiting_procedure_confirm (법령 제공 완료)
    - awaiting_procedure_confirm → providing_procedure (긍정) / completed (부정) / initial (새 토픽)
    - providing_procedure → completed
    """
    if current_phase == "initial":
        if detect_dispute_intent(user_query) or query_type not in (
            None,
            "general",
            "system_meta",
        ):
            if are_required_slots_filled(slot_status):
                return "providing_case_summary", "ready_for_case_summary"
            return "info_gathering", "dispute_intent_detected"
        # NEED_RAG 쿼리는 슬롯과 무관하게 사례 요약부터 시작
        if query_type and query_type not in ("general", "system_meta"):
            return "providing_case_summary", "need_rag_query"
        return "initial", "no_dispute_intent"

    if current_phase == "info_gathering":
        if are_required_slots_filled(slot_status):
            return "providing_case_summary", "required_slots_filled"
        return "info_gathering", "slots_still_missing"

    if current_phase == "providing_case_summary":
        return "awaiting_law_confirm", "case_summary_provided"

    if current_phase == "awaiting_law_confirm":
        if is_new_topic(user_query, current_phase):
            return "initial", "new_topic_detected"
        yes_no = detect_yes_no(user_query)
        if yes_no is True:
            return "providing_law_detail", "user_requested_law_detail"
        if yes_no is False:
            return "awaiting_procedure_confirm", "user_declined_law_detail"
        return "awaiting_law_confirm", "awaiting_user_response"

    if current_phase == "providing_law_detail":
        return "awaiting_procedure_confirm", "law_detail_provided"

    if current_phase == "awaiting_procedure_confirm":
        if is_new_topic(user_query, current_phase):
            return "initial", "new_topic_detected"
        yes_no = detect_yes_no(user_query)
        if yes_no is True:
            return "providing_procedure", "user_requested_procedure"
        if yes_no is False:
            return "completed", "user_declined_procedure"
        return "awaiting_procedure_confirm", "awaiting_user_response"

    if current_phase == "providing_procedure":
        return "completed", "procedure_provided"

    if current_phase == "completed":
        # 완료 후 새 질문 시 초기화
        return "initial", "restart_from_completed"

    return current_phase, "no_transition"


def update_slots_and_phase(state: ChatState) -> Dict[str, Any]:
    """
    Main entry point for conversation manager.
    Merges slots, computes status, and determines phase transition.
    Returns partial state updates for LangGraph.
    """
    user_query = state.get("user_query", "")
    current_phase = state.get("conversation_phase", "initial")
    existing_slots = state.get("dispute_slots", {})
    onboarding = state.get("onboarding")
    query_analysis = state.get("query_analysis") or {}
    extracted_info = query_analysis.get("extracted_info")

    if user_query and not extracted_info:
        extracted_info = {}
        dispute_type = extract_dispute_type(user_query)
        if dispute_type:
            extracted_info["dispute_type"] = dispute_type

    merged_slots = merge_slots(existing_slots, onboarding, extracted_info)
    slot_status = compute_slot_status(merged_slots)

    query_type = query_analysis.get("query_type")
    new_phase, reason = compute_phase_transition(
        current_phase, user_query, slot_status, query_type
    )

    return {
        "dispute_slots": merged_slots,
        "dispute_slot_status": slot_status,
        "conversation_phase": new_phase,
        "last_phase_transition_reason": reason,
    }


def get_next_questions(state: ChatState) -> List[str]:
    """Phase별 후속 질문을 반환합니다."""
    phase = state.get("conversation_phase", "initial")
    slot_status = state.get("dispute_slot_status", {})

    if phase in ("initial", "info_gathering"):
        return get_missing_slot_questions(slot_status)

    if phase == "awaiting_law_confirm":
        return ["관련 법령과 분쟁해결기준도 상세히 알려드릴까요?"]

    if phase == "awaiting_procedure_confirm":
        return ["분쟁 해결 절차(한국소비자원, 전자거래분쟁조정 등)도 안내해 드릴까요?"]

    return []


def should_trigger_clarification(state: ChatState) -> bool:
    """Determine if clarification node should be triggered."""
    phase = state.get("conversation_phase", "initial")
    return phase in (
        "info_gathering",
        "awaiting_law_confirm",
        "awaiting_procedure_confirm",
    )


def get_retriever_types_for_phase(phase: ConversationPhase) -> List[str]:
    """
    Phase별 Retrieval 에이전트 타입을 반환합니다.

    Progressive Disclosure:
    - providing_case_summary: 전체 검색 (첫 턴에 모든 소스 캐싱)
    - providing_law_detail: 캐시 사용 (재검색 불필요)
    - providing_procedure: 캐시 사용 (재검색 불필요)
    """
    if phase == "providing_case_summary":
        return ["law", "criteria", "case"]  # 전체 검색 (캐싱용)
    if phase in ("providing_law_detail", "providing_procedure"):
        return []  # 캐시 사용, 재검색 불필요
    return ["law", "criteria", "case"]  # 기본값


__all__ = [
    "REQUIRED_SLOTS",
    "OPTIONAL_SLOTS",
    "ALL_SLOTS",
    "SLOT_QUESTION_TEMPLATES",
    "detect_yes_no",
    "detect_dispute_intent",
    "extract_dispute_type",
    "is_new_topic",
    "merge_slots",
    "compute_slot_status",
    "are_required_slots_filled",
    "get_missing_slot_questions",
    "compute_phase_transition",
    "update_slots_and_phase",
    "get_next_questions",
    "should_trigger_clarification",
    "get_retriever_types_for_phase",
]
