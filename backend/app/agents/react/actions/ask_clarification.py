from typing import List

from ..action_registry import BaseAction, ActionResult
from ....orchestrator.state import ChatState


class AskClarificationAction(BaseAction):
    name = "ask_clarification"
    description = "사용자에게 추가 정보 요청"

    FIELD_QUESTIONS = {
        'purchase_item': "어떤 제품/서비스에 대한 문의인가요?",
        'purchase_date': "구매 또는 계약한 날짜는 언제인가요?",
        'purchase_amount': "구매 금액은 얼마인가요?",
        'dispute_details': "구체적으로 어떤 문제가 발생했나요?",
        'purchase_place': "판매자(업체) 이름을 알려주세요.",
    }

    DEFAULT_QUESTIONS = [
        "상황을 더 자세히 설명해 주시겠어요?",
        "어떤 해결을 원하시나요? (환불, 교환, 수리 등)",
    ]

    def execute(self, state: ChatState, query: str) -> ActionResult:
        questions = self._generate_questions(state)
        observation = f"사용자에게 {len(questions)}개 질문 생성"

        return ActionResult(
            observation=observation,
            clarifying_questions=questions,
            awaiting_user_choice=True,
            should_continue=False,
        )

    def _generate_questions(self, state: ChatState) -> List[str]:
        query_analysis = state.get('query_analysis') or {}
        missing_fields = query_analysis.get('missing_fields', [])
        onboarding = state.get('onboarding') or {}
        onboarding_dict = dict(onboarding) if onboarding else {}

        questions = []
        for field in missing_fields:
            if field in self.FIELD_QUESTIONS and not onboarding_dict.get(field):
                questions.append(self.FIELD_QUESTIONS[field])
                if len(questions) >= 3:
                    break

        return questions if questions else self.DEFAULT_QUESTIONS
