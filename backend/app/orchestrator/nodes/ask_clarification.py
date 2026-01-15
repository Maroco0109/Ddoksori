"""
똑소리 프로젝트 - 추가 질문 노드
작성일: 2026-01-14
S2-3: 정보 부족 시 사용자에게 되묻기

추가 질문 노드의 역할:
1. query_analysis에서 누락된 필드 확인
2. 각 필드에 대한 친절한 질문 생성
3. 사용자에게 추가 정보 요청 메시지 반환
"""

from typing import Dict, List

from langchain_core.messages import AIMessage

from ..state import ChatState


# 필드별 질문 템플릿
FIELD_QUESTIONS = {
    'purchase_item': {
        'question': '어떤 제품이나 서비스에 대한 분쟁인가요?',
        'examples': '예: 헬스장 회원권, 스마트폰, 렌터카 등',
        'priority': 1,
    },
    'dispute_details': {
        'question': '어떤 문제가 발생했는지 자세히 설명해 주시겠어요?',
        'examples': '예: 환불 거부, 계약 해지, 제품 하자 등',
        'priority': 2,
    },
    'purchase_date': {
        'question': '언제 구매하셨나요?',
        'examples': '예: 2026년 1월, 작년 여름, 3개월 전 등',
        'priority': 3,
    },
    'purchase_place': {
        'question': '어디서 구매하셨나요?',
        'examples': '예: 쿠팡, 네이버 스마트스토어, 오프라인 매장 등',
        'priority': 4,
    },
    'purchase_amount': {
        'question': '구매 금액은 얼마인가요?',
        'examples': '예: 50만원, 월 9,900원 등',
        'priority': 5,
    },
}


def _build_clarification_message(missing_fields: List[str]) -> str:
    """
    누락 필드에 대한 추가 질문 메시지 생성
    """
    if not missing_fields:
        return ""
    
    # 우선순위로 정렬
    sorted_fields = sorted(
        missing_fields,
        key=lambda f: FIELD_QUESTIONS.get(f, {}).get('priority', 99)
    )
    
    lines = [
        "정확한 안내를 위해 몇 가지 추가 정보가 필요합니다.",
        ""
    ]
    
    for i, field in enumerate(sorted_fields[:3], 1):  # 최대 3개
        field_info = FIELD_QUESTIONS.get(field, {})
        question = field_info.get('question', f'{field}에 대해 알려주세요.')
        examples = field_info.get('examples', '')
        
        lines.append(f"{i}. {question}")
        if examples:
            lines.append(f"   ({examples})")
        lines.append("")
    
    lines.append("알려주시면 더 정확한 정보를 안내해 드릴 수 있습니다.")
    
    return "\n".join(lines)


def _extract_clarifying_questions(missing_fields: List[str]) -> List[str]:
    """
    누락 필드에서 질문 목록 추출
    """
    questions = []
    
    sorted_fields = sorted(
        missing_fields,
        key=lambda f: FIELD_QUESTIONS.get(f, {}).get('priority', 99)
    )
    
    for field in sorted_fields[:5]:  # 최대 5개
        field_info = FIELD_QUESTIONS.get(field, {})
        question = field_info.get('question', f'{field}에 대해 알려주세요.')
        questions.append(question)
    
    return questions


def ask_clarification_node(state: ChatState) -> Dict:
    """
    추가 질문 노드 함수
    
    query_analysis에서 확인된 누락 필드에 대해
    사용자에게 추가 정보를 요청하는 메시지 생성.
    
    조건부 엣지에서 needs_clarification=True일 때 호출됨.
    
    Args:
        state: 현재 ChatState
        
    Returns:
        부분 상태 업데이트 dict:
        {
            'final_answer': str,
            'clarifying_questions': List[str],
            'messages': List[AIMessage]
        }
    """
    query_analysis = state.get('query_analysis')
    
    # query_analysis가 없으면 기본 질문
    if not query_analysis:
        default_message = (
            "분쟁 상담을 위해 몇 가지 정보가 필요합니다.\n\n"
            "1. 어떤 제품이나 서비스에 대한 분쟁인가요?\n"
            "2. 어떤 문제가 발생했나요?\n\n"
            "알려주시면 도움을 드릴 수 있습니다."
        )
        default_questions = [
            "어떤 제품이나 서비스에 대한 분쟁인가요?",
            "어떤 문제가 발생했나요?"
        ]
        return {
            'final_answer': default_message,
            'clarifying_questions': default_questions,
            'messages': [AIMessage(content=default_message)],
        }
    
    missing_fields = query_analysis.get('missing_fields', [])
    
    if not missing_fields:
        # 누락 필드 없음 - 이 노드가 호출되면 안 됨 (방어 코드)
        fallback = "추가 정보가 필요하지 않습니다. 질문을 입력해 주세요."
        return {
            'final_answer': fallback,
            'clarifying_questions': [],
            'messages': [AIMessage(content=fallback)],
        }
    
    # 추가 질문 메시지 생성
    clarification_message = _build_clarification_message(missing_fields)
    clarifying_questions = _extract_clarifying_questions(missing_fields)
    
    return {
        'final_answer': clarification_message,
        'clarifying_questions': clarifying_questions,
        'messages': [AIMessage(content=clarification_message)],
    }
