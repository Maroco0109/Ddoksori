"""
똑소리 프로젝트 - 낮은 유사도 처리 노드
유사도가 낮을 때 사용자에게 선택지 제공
"""

from typing import Dict, List

from langchain_core.messages import AIMessage

from ....supervisor.state import ChatState

SIMILARITY_THRESHOLD_LOW = 0.40

FIELD_KOREAN_NAMES = {
    "purchase_item": "구매 품목",
    "dispute_details": "분쟁 상세",
    "purchase_date": "구매일자",
    "purchase_place": "구매처",
    "purchase_platform": "플랫폼",
    "purchase_amount": "구매금액",
}

FIELD_QUESTIONS = {
    "purchase_item": "어떤 제품/서비스인가요?",
    "dispute_details": "어떤 문제가 발생했나요?",
    "purchase_date": "언제 구매하셨나요?",
    "purchase_place": "어디서 구매하셨나요?",
    "purchase_amount": "구매 금액은 얼마인가요?",
}


def _build_low_similarity_message(
    max_similarity: float,
    missing_fields: List[str],
    extracted_info: Dict[str, str],
    has_results: bool,
) -> str:
    sim_percent = int(max_similarity * 100)
    lines = []

    if has_results:
        lines.append(f"🔍 **검색 결과 유사도: {sim_percent}%**")
        lines.append("")

        if max_similarity < SIMILARITY_THRESHOLD_LOW:
            lines.append("현재 검색된 결과의 유사도가 낮습니다.")
            lines.append("더 정확한 정보를 위해 추가 정보가 필요합니다.")
        else:
            lines.append("검색 결과가 있지만 유사도가 다소 낮습니다.")
            lines.append("현재 결과를 먼저 보여드릴 수 있습니다.")

        lines.append("")
        lines.append("**선택해 주세요:**")
        lines.append('1️⃣ "출력해줘" - 현재 검색 결과로 답변 제공')
        lines.append('2️⃣ "다시 검색해줘" - 추가 정보 입력 후 재검색')
    else:
        lines.append("🔍 **관련 검색 결과를 찾지 못했습니다.**")
        lines.append("")
        lines.append("더 정확한 검색을 위해 추가 정보가 필요합니다.")

    if extracted_info:
        lines.append("")
        lines.append("📋 **현재 입력된 정보:**")
        for field, value in extracted_info.items():
            korean_name = FIELD_KOREAN_NAMES.get(field, field)
            lines.append(f"   • {korean_name}: {value}")

    if missing_fields:
        lines.append("")
        lines.append("❓ **추가하면 좋을 정보:**")
        for field in missing_fields[:3]:
            question = FIELD_QUESTIONS.get(field, f"{field}?")
            lines.append(f"   • {question}")

    return "\n".join(lines)


def low_similarity_prompt_node(state: ChatState) -> Dict:
    retrieval = state.get("retrieval") or {}
    query_analysis = state.get("query_analysis") or {}

    max_sim = retrieval.get("max_similarity", 0.0)
    disputes = retrieval.get("disputes", [])
    counsels = retrieval.get("counsels", [])
    has_results = bool(disputes or counsels)

    missing_fields = query_analysis.get("missing_fields", [])
    extracted_info = query_analysis.get("extracted_info", {})

    message = _build_low_similarity_message(
        max_similarity=max_sim,
        missing_fields=missing_fields,
        extracted_info=extracted_info,
        has_results=has_results,
    )

    return {
        "final_answer": message,
        "has_sufficient_evidence": False,
        "clarifying_questions": [
            "출력해줘 - 현재 결과로 답변 받기",
            "다시 검색해줘 - 추가 정보 입력 후 재검색",
        ],
        "messages": [AIMessage(content=message)],
        "awaiting_user_choice": True,
        "low_similarity_mode": True,
    }
