"""
똑소리 프로젝트 - 후속 질문 생성 모듈 테스트

작성일: 2026-01-28

QuestionTemplate, FollowupQuestionGenerator의 단위 테스트입니다.
"""

import pytest
from app.agents.followup import (
    QUESTION_TEMPLATES,
    QuestionTemplate,
    FollowupQuestionGenerator,
)
from app.agents.followup.templates import (
    get_templates_by_dispute_type,
    get_templates_by_question_type,
)


# ============================================================
# QuestionTemplate 테스트
# ============================================================

@pytest.mark.unit
def test_question_templates_exist():
    """질문 템플릿이 최소 20개 이상 존재"""
    assert len(QUESTION_TEMPLATES) >= 20


@pytest.mark.unit
def test_question_template_structure():
    """질문 템플릿 구조 검증"""
    template = QUESTION_TEMPLATES[0]
    assert hasattr(template, 'template_id')
    assert hasattr(template, 'question_type')
    assert hasattr(template, 'dispute_types')
    assert hasattr(template, 'question_text')
    assert hasattr(template, 'conditions')
    assert hasattr(template, 'priority')


@pytest.mark.unit
def test_get_templates_by_dispute_type_refund():
    """환불 관련 템플릿 조회"""
    templates = get_templates_by_dispute_type('환불')
    assert len(templates) > 0
    # 환불 관련 템플릿이거나 일반 템플릿
    for template in templates:
        assert '환불' in template.dispute_types or '일반' in template.dispute_types


@pytest.mark.unit
def test_get_templates_by_question_type_followup():
    """후속 질문 타입 템플릿 조회"""
    templates = get_templates_by_question_type('followup')
    assert len(templates) > 0
    for template in templates:
        assert template.question_type == 'followup'


@pytest.mark.unit
def test_get_templates_by_question_type_clarifying():
    """명확화 질문 타입 템플릿 조회"""
    templates = get_templates_by_question_type('clarifying')
    assert len(templates) > 0
    for template in templates:
        assert template.question_type == 'clarifying'


# ============================================================
# FollowupQuestionGenerator 테스트
# ============================================================

@pytest.mark.unit
def test_followup_generator_initialization():
    """생성기 초기화"""
    generator = FollowupQuestionGenerator(
        max_followup_questions=3,
        max_clarifying_questions=2
    )
    assert generator.max_followup_questions == 3
    assert generator.max_clarifying_questions == 2


@pytest.mark.unit
def test_followup_generator_build_context():
    """컨텍스트 생성"""
    generator = FollowupQuestionGenerator()

    query_analysis = {
        'dispute_type': '환불',
        'missing_fields': ['purchase_date', 'amount']
    }
    retrieval = {
        'disputes': [{'doc_id': '123'}],
        'counsels': [],
        'laws': [{'unit_id': '456'}],
        'criteria': [],
        'agency': {'agency': 'KCA'}
    }
    answer = "환불은 14일 이내에 가능합니다."

    context = generator._build_context(query_analysis, retrieval, answer)

    assert context['dispute_type'] == '환불'
    assert context['has_cases'] is True
    assert context['has_laws'] is True
    assert context['has_criteria'] is False
    assert context['has_agency_recommendation'] is True
    assert context['missing_purchase_date'] is True
    assert context['missing_amount'] is True


@pytest.mark.unit
def test_followup_generator_check_no_timeline():
    """답변에 기간 정보 없음 확인"""
    generator = FollowupQuestionGenerator()

    answer_without_timeline = "환불이 가능합니다."
    assert generator._check_no_timeline(answer_without_timeline) is True

    answer_with_timeline = "환불은 14일 이내에 가능합니다."
    assert generator._check_no_timeline(answer_with_timeline) is False


@pytest.mark.unit
def test_followup_generator_check_no_procedure():
    """답변에 절차 정보 없음 확인"""
    generator = FollowupQuestionGenerator()

    answer_without_procedure = "환불이 가능합니다."
    assert generator._check_no_procedure(answer_without_procedure) is True

    answer_with_procedure = "환불 신청은 고객센터를 통해 진행합니다."
    assert generator._check_no_procedure(answer_with_procedure) is False


@pytest.mark.unit
def test_followup_generator_generate_questions_refund():
    """환불 분쟁 후속 질문 생성"""
    generator = FollowupQuestionGenerator(max_followup_questions=3)

    query_analysis = {'dispute_type': '환불', 'missing_fields': []}
    retrieval = {
        'disputes': [{'doc_id': '123'}],
        'counsels': [],
        'laws': [],
        'criteria': [],
        'agency': {}
    }
    answer = "환불은 가능합니다."

    result = generator.generate_questions(query_analysis, retrieval, answer)

    assert 'followup_questions' in result
    assert 'clarifying_questions' in result
    assert len(result['followup_questions']) <= 3
    # 환불 관련 질문이 포함되어야 함
    assert len(result['followup_questions']) > 0


@pytest.mark.unit
def test_followup_generator_generate_questions_with_missing_fields():
    """누락 정보가 있을 때 명확화 질문 생성"""
    generator = FollowupQuestionGenerator(max_clarifying_questions=2)

    query_analysis = {
        'dispute_type': '환불',
        'missing_fields': ['purchase_date', 'product_name']
    }
    retrieval = {
        'disputes': [],
        'counsels': [],
        'laws': [],
        'criteria': [],
        'agency': {}
    }
    answer = "환불이 가능합니다."

    result = generator.generate_questions(query_analysis, retrieval, answer)

    assert len(result['clarifying_questions']) > 0
    assert len(result['clarifying_questions']) <= 2


@pytest.mark.unit
def test_followup_generator_match_templates():
    """템플릿 매칭 로직 검증"""
    generator = FollowupQuestionGenerator()

    templates = [
        QuestionTemplate(
            template_id='test1',
            question_type='followup',
            dispute_types=['환불'],
            question_text='질문1',
            conditions={'has_cases': True},
            priority=2
        ),
        QuestionTemplate(
            template_id='test2',
            question_type='followup',
            dispute_types=['환불'],
            question_text='질문2',
            conditions={'has_cases': False},
            priority=1
        ),
    ]

    context = {'has_cases': True}

    matched = generator._match_templates(templates, context)

    assert len(matched) == 1
    assert matched[0].template_id == 'test1'


@pytest.mark.unit
def test_followup_generator_priority_sorting():
    """우선순위에 따른 정렬 검증"""
    generator = FollowupQuestionGenerator(max_followup_questions=2)

    query_analysis = {'dispute_type': '일반', 'missing_fields': []}
    retrieval = {
        'disputes': [{'doc_id': '123'}],
        'counsels': [],
        'laws': [],
        'criteria': [],
        'agency': {'agency': 'KCA'}
    }
    answer = "분쟁 해결이 가능합니다."

    result = generator.generate_questions(query_analysis, retrieval, answer)

    # 최대 2개까지만 반환
    assert len(result['followup_questions']) <= 2


# ============================================================
# 통합 테스트
# ============================================================

@pytest.mark.unit
def test_followup_generator_full_workflow():
    """후속 질문 생성 전체 워크플로우"""
    generator = FollowupQuestionGenerator(
        max_followup_questions=3,
        max_clarifying_questions=2
    )

    query_analysis = {
        'dispute_type': '환불',
        'missing_fields': ['purchase_date']
    }
    retrieval = {
        'disputes': [{'doc_id': '123'}],
        'counsels': [{'doc_id': '456'}],
        'laws': [{'unit_id': '789'}],
        'criteria': [{'unit_id': '101'}],
        'agency': {'agency': 'KCA'}
    }
    answer = "환불은 가능합니다. 사업자에게 먼저 연락해보세요."

    result = generator.generate_questions(query_analysis, retrieval, answer)

    # 결과 구조 검증
    assert isinstance(result, dict)
    assert 'followup_questions' in result
    assert 'clarifying_questions' in result

    # 후속 질문 검증
    assert isinstance(result['followup_questions'], list)
    assert len(result['followup_questions']) <= 3

    # 명확화 질문 검증
    assert isinstance(result['clarifying_questions'], list)
    assert len(result['clarifying_questions']) <= 2

    # 최소 하나 이상의 질문 생성
    assert len(result['followup_questions']) + len(result['clarifying_questions']) > 0
