"""
Unit tests for ConversationManager (Conversation Phase System).

Tests the rule-based phase transitions, slot management, and yes/no detection
that form the core of the progressive dispute consultation flow.
"""

import pytest

from app.supervisor.conversation_manager import (
    detect_yes_no,
    detect_dispute_intent,
    extract_dispute_type,
    merge_slots,
    compute_slot_status,
    are_required_slots_filled,
    get_missing_slot_questions,
    compute_phase_transition,
    update_slots_and_phase,
    get_next_questions,
    should_trigger_clarification,
    get_retriever_types_for_phase,
    REQUIRED_SLOTS,
    OPTIONAL_SLOTS,
    ALL_SLOTS,
)
from app.supervisor.state import create_initial_state


class TestYesNoDetection:
    """Test yes/no detection patterns."""

    @pytest.mark.parametrize("text,expected", [
        ("네", True),
        ("예", True),
        ("응", True),
        ("그래", True),
        ("좋아", True),
        ("알려줘", True),
        ("보여줘", True),
        ("알고 싶어", True),
        ("궁금해요", True),
        ("보고 싶어요", True),
        ("알려 주세요", True),
        ("부탁드립니다", True),
    ])
    def test_yes_patterns(self, text, expected):
        assert detect_yes_no(text) == expected

    @pytest.mark.parametrize("text,expected", [
        ("아니요", False),
        ("아니", False),
        ("괜찮아요", False),
        ("됐어요", False),
        ("안해도 돼요", False),
        ("필요 없어요", False),
        ("다음에요", False),
        ("나중에 할게요", False),
        ("싫어", False),
    ])
    def test_no_patterns(self, text, expected):
        assert detect_yes_no(text) == expected

    @pytest.mark.parametrize("text", [
        "뭐라고요?",
        "잘 모르겠어요",
        "헬스장 환불 문의입니다",
        "그게 뭐예요?",
    ])
    def test_unclear_returns_none(self, text):
        assert detect_yes_no(text) is None


class TestDisputeIntentDetection:
    """Test dispute intent detection patterns."""

    @pytest.mark.parametrize("text", [
        "환불받고 싶어요",
        "반품 요청합니다",
        "교환해주세요",
        "수리 비용 문의",
        "취소하려고요",
        "해지하고 싶습니다",
        "청약철회 가능한가요",
        "분쟁 상담 원해요",
        "피해 보상 문의",
        "소비자 권리",
    ])
    def test_dispute_intent_detected(self, text):
        assert detect_dispute_intent(text) is True

    @pytest.mark.parametrize("text", [
        "안녕하세요",
        "오늘 날씨가 좋네요",
        "고마워요",
        "그냥 질문이요",
    ])
    def test_no_dispute_intent(self, text):
        assert detect_dispute_intent(text) is False


class TestDisputeTypeExtraction:
    """Test dispute type extraction from keywords."""

    @pytest.mark.parametrize("text,expected", [
        ("환불 원해요", "refund"),
        ("반품하고 싶어요", "refund"),
        ("교환해주세요", "exchange"),
        ("수리 요청합니다", "repair"),
        ("취소하려고요", "cancellation"),
        ("해지하고 싶습니다", "cancellation"),
        ("청약철회 가능한가요", "withdrawal"),
    ])
    def test_dispute_type_extraction(self, text, expected):
        assert extract_dispute_type(text) == expected

    def test_no_dispute_type(self):
        assert extract_dispute_type("안녕하세요") is None


class TestSlotMerge:
    """Test slot merging from multiple sources."""

    def test_merge_with_empty_sources(self):
        result = merge_slots({}, None, None)
        assert result['purchase_item'] is None
        assert result['problem_details'] is None

    def test_merge_with_onboarding(self):
        onboarding = {
            'purchase_item': '헬스장 회원권',
            'dispute_details': '환불 요청',
        }
        result = merge_slots({}, onboarding, None)
        assert result['purchase_item'] == '헬스장 회원권'
        assert result['problem_details'] == '환불 요청'

    def test_merge_with_extracted_info(self):
        extracted = {
            'purchase_item': '노트북',
            'dispute_type': 'refund',
        }
        result = merge_slots({}, None, extracted)
        assert result['purchase_item'] == '노트북'
        assert result['dispute_type'] == 'refund'

    def test_extracted_info_overrides_onboarding(self):
        onboarding = {'purchase_item': '헬스장'}
        extracted = {'purchase_item': '노트북'}
        result = merge_slots({}, onboarding, extracted)
        assert result['purchase_item'] == '노트북'

    def test_existing_slots_preserved(self):
        existing = {'purchase_date': '2025-01-01'}
        result = merge_slots(existing, None, None)
        assert result['purchase_date'] == '2025-01-01'


class TestSlotStatus:
    """Test slot status computation."""

    def test_filled_status(self):
        slots = {'purchase_item': '헬스장 회원권'}
        status = compute_slot_status(slots)
        assert status['purchase_item']['status'] == 'filled'
        assert status['purchase_item']['confidence'] == 1.0

    def test_partial_status(self):
        slots = {'purchase_item': 'TV'}
        status = compute_slot_status(slots)
        assert status['purchase_item']['status'] == 'partial'
        assert status['purchase_item']['confidence'] == 0.5

    def test_missing_status(self):
        slots = {'purchase_item': None}
        status = compute_slot_status(slots)
        assert status['purchase_item']['status'] == 'missing'
        assert status['purchase_item']['confidence'] == 0.0


class TestRequiredSlotsFilled:
    """Test required slots filled check."""

    def test_required_slots_filled(self):
        status = {
            'purchase_item': {'status': 'filled', 'slot_name': 'purchase_item', 'evidence_chunk_ids': [], 'confidence': 1.0},
            'problem_details': {'status': 'filled', 'slot_name': 'problem_details', 'evidence_chunk_ids': [], 'confidence': 1.0},
        }
        assert are_required_slots_filled(status) is True

    def test_required_slots_missing(self):
        status = {
            'purchase_item': {'status': 'filled', 'slot_name': 'purchase_item', 'evidence_chunk_ids': [], 'confidence': 1.0},
            'problem_details': {'status': 'missing', 'slot_name': 'problem_details', 'evidence_chunk_ids': [], 'confidence': 0.0},
        }
        assert are_required_slots_filled(status) is False


class TestMissingSlotQuestions:
    """Test question generation for missing slots."""

    def test_generates_questions_for_missing_required_slots(self):
        status = {
            'purchase_item': {'status': 'missing', 'slot_name': 'purchase_item', 'evidence_chunk_ids': [], 'confidence': 0.0},
            'problem_details': {'status': 'missing', 'slot_name': 'problem_details', 'evidence_chunk_ids': [], 'confidence': 0.0},
        }
        questions = get_missing_slot_questions(status)
        assert len(questions) >= 2
        assert "어떤 제품/서비스에 대한 문의인가요?" in questions
        assert "어떤 문제가 있었는지 한두 문장으로 설명해 주세요." in questions

    def test_max_3_questions(self):
        status = {slot: {'status': 'missing', 'slot_name': slot, 'evidence_chunk_ids': [], 'confidence': 0.0} for slot in ALL_SLOTS}
        questions = get_missing_slot_questions(status, max_questions=3)
        assert len(questions) == 3


class TestPhaseTransitions:
    """Test phase transition logic."""

    def test_initial_to_info_gathering(self):
        slot_status = {
            'purchase_item': {'status': 'missing', 'slot_name': 'purchase_item', 'evidence_chunk_ids': [], 'confidence': 0.0},
            'problem_details': {'status': 'missing', 'slot_name': 'problem_details', 'evidence_chunk_ids': [], 'confidence': 0.0},
        }
        phase, reason = compute_phase_transition('initial', '환불 문의입니다', slot_status)
        assert phase == 'info_gathering'
        assert 'dispute_intent_detected' in reason

    def test_initial_no_dispute_stays_initial(self):
        slot_status = {}
        phase, reason = compute_phase_transition('initial', '안녕하세요', slot_status)
        assert phase == 'initial'

    def test_info_gathering_to_ready(self):
        slot_status = {
            'purchase_item': {'status': 'filled', 'slot_name': 'purchase_item', 'evidence_chunk_ids': [], 'confidence': 1.0},
            'problem_details': {'status': 'filled', 'slot_name': 'problem_details', 'evidence_chunk_ids': [], 'confidence': 1.0},
        }
        phase, reason = compute_phase_transition('info_gathering', '헬스장 환불', slot_status)
        assert phase == 'ready_for_analysis'
        assert 'required_slots_filled' in reason

    def test_ready_to_providing_law(self):
        phase, reason = compute_phase_transition('ready_for_analysis', '', {})
        assert phase == 'providing_law'

    def test_providing_law_to_awaiting_case(self):
        phase, reason = compute_phase_transition('providing_law', '', {})
        assert phase == 'awaiting_case_confirm'

    def test_awaiting_case_yes_to_providing_case(self):
        phase, reason = compute_phase_transition('awaiting_case_confirm', '네', {})
        assert phase == 'providing_case'

    def test_awaiting_case_no_to_awaiting_procedure(self):
        phase, reason = compute_phase_transition('awaiting_case_confirm', '아니요', {})
        assert phase == 'awaiting_procedure_confirm'

    def test_providing_case_to_awaiting_procedure(self):
        phase, reason = compute_phase_transition('providing_case', '', {})
        assert phase == 'awaiting_procedure_confirm'

    def test_awaiting_procedure_yes_to_providing_procedure(self):
        phase, reason = compute_phase_transition('awaiting_procedure_confirm', '알려줘', {})
        assert phase == 'providing_procedure'

    def test_awaiting_procedure_no_to_completed(self):
        phase, reason = compute_phase_transition('awaiting_procedure_confirm', '괜찮아요', {})
        assert phase == 'completed'

    def test_providing_procedure_to_completed(self):
        phase, reason = compute_phase_transition('providing_procedure', '', {})
        assert phase == 'completed'


class TestUpdateSlotsAndPhase:
    """Test the main update_slots_and_phase function."""

    def test_full_flow_with_complete_info(self):
        state = create_initial_state('헬스장 환불 원해요', chat_type='dispute')
        state['onboarding'] = {
            'purchase_item': '헬스장 회원권',
            'dispute_details': '3개월 이용 후 환불 요청',
        }
        updates = update_slots_and_phase(state)
        assert updates['conversation_phase'] == 'ready_for_analysis'
        assert updates['dispute_slots']['purchase_item'] == '헬스장 회원권'

    def test_full_flow_with_incomplete_info(self):
        state = create_initial_state('환불 원해요', chat_type='dispute')
        updates = update_slots_and_phase(state)
        assert updates['conversation_phase'] == 'info_gathering'


class TestGetNextQuestions:
    """Test get_next_questions for different phases."""

    def test_info_gathering_returns_slot_questions(self):
        state = create_initial_state('환불', chat_type='dispute')
        state['conversation_phase'] = 'info_gathering'
        state['dispute_slot_status'] = {
            'purchase_item': {'status': 'missing', 'slot_name': 'purchase_item', 'evidence_chunk_ids': [], 'confidence': 0.0},
        }
        questions = get_next_questions(state)
        assert len(questions) > 0

    def test_awaiting_case_confirm_returns_case_question(self):
        state = create_initial_state('', chat_type='dispute')
        state['conversation_phase'] = 'awaiting_case_confirm'
        questions = get_next_questions(state)
        assert '관련 분쟁조정 사례도 보여드릴까요?' in questions

    def test_awaiting_procedure_confirm_returns_procedure_question(self):
        state = create_initial_state('', chat_type='dispute')
        state['conversation_phase'] = 'awaiting_procedure_confirm'
        questions = get_next_questions(state)
        assert '분쟁 해결 절차' in questions[0]


class TestShouldTriggerClarification:
    """Test clarification trigger logic."""

    def test_info_gathering_triggers_clarification(self):
        state = {'conversation_phase': 'info_gathering'}
        assert should_trigger_clarification(state) is True

    def test_awaiting_case_confirm_triggers_clarification(self):
        state = {'conversation_phase': 'awaiting_case_confirm'}
        assert should_trigger_clarification(state) is True

    def test_providing_law_does_not_trigger(self):
        state = {'conversation_phase': 'providing_law'}
        assert should_trigger_clarification(state) is False


class TestGetRetrieverTypesForPhase:
    """Test retriever type selection per phase."""

    def test_providing_law_returns_law_criteria(self):
        types = get_retriever_types_for_phase('providing_law')
        assert 'law' in types
        assert 'criteria' in types
        assert 'case' not in types

    def test_providing_case_returns_case_only(self):
        types = get_retriever_types_for_phase('providing_case')
        assert types == ['case']

    def test_providing_procedure_returns_procedure(self):
        types = get_retriever_types_for_phase('providing_procedure')
        assert types == ['procedure']
