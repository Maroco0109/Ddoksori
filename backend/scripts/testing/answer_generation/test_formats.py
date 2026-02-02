"""
똑소리 프로젝트 - 답변 형식 모듈 테스트

작성일: 2026-01-28

ResponseFormat, FormatSelector, PromptBuilder의 단위 테스트입니다.
"""

import pytest

from app.agents.answer_generation.formats import (
    RESPONSE_FORMATS,
    FormatSelector,
    PromptBuilder,
    ResponseFormat,
    SectionConfig,
)

# ============================================================
# SectionConfig 테스트
# ============================================================


@pytest.mark.unit
def test_section_config_should_include_no_conditions():
    """조건이 없는 섹션은 항상 포함됨"""
    section = SectionConfig(section_id="test_section", required=True)
    context = {}
    assert section.should_include(context) is True


@pytest.mark.unit
def test_section_config_should_include_with_conditions():
    """조건을 만족하는 섹션은 포함됨"""
    section = SectionConfig(
        section_id="test_section", required=True, conditions={"has_cases": True}
    )
    context = {"has_cases": True}
    assert section.should_include(context) is True


@pytest.mark.unit
def test_section_config_should_not_include_when_condition_not_met():
    """조건을 만족하지 않는 섹션은 제외됨"""
    section = SectionConfig(
        section_id="test_section", required=True, conditions={"has_cases": True}
    )
    context = {"has_cases": False}
    assert section.should_include(context) is False


# ============================================================
# ResponseFormat 테스트
# ============================================================


@pytest.mark.unit
def test_response_formats_defined():
    """RESPONSE_FORMATS가 정의되어 있음"""
    assert "full_dispute" in RESPONSE_FORMATS
    assert "simple_general" in RESPONSE_FORMATS
    assert "info_only" in RESPONSE_FORMATS


@pytest.mark.unit
def test_full_dispute_format():
    """full_dispute 형식 검증"""
    fmt = RESPONSE_FORMATS["full_dispute"]
    assert fmt.format_id == "full_dispute"
    assert "dispute" in fmt.query_types
    assert fmt.include_disclaimer is True
    assert fmt.tone == "formal"
    assert len(fmt.sections) > 0


@pytest.mark.unit
def test_simple_general_format():
    """simple_general 형식 검증"""
    fmt = RESPONSE_FORMATS["simple_general"]
    assert fmt.format_id == "simple_general"
    assert "general" in fmt.query_types
    assert fmt.include_disclaimer is False
    assert fmt.tone == "friendly"
    assert len(fmt.sections) == 0


@pytest.mark.unit
def test_info_only_format():
    """info_only 형식 검증"""
    fmt = RESPONSE_FORMATS["info_only"]
    assert fmt.format_id == "info_only"
    assert "restricted" in fmt.query_types
    assert fmt.include_disclaimer is True
    assert fmt.tone == "informative"


# ============================================================
# FormatSelector 테스트
# ============================================================


@pytest.mark.unit
def test_format_selector_dispute_query():
    """분쟁 쿼리는 full_dispute 형식 선택"""
    selector = FormatSelector()
    query_analysis = {"query_type": "dispute"}
    retrieval = {"disputes": [{"doc_id": "123"}], "laws": []}

    fmt = selector.select_format(query_analysis, retrieval)
    assert fmt.format_id == "full_dispute"


@pytest.mark.unit
def test_format_selector_general_query():
    """일반 쿼리는 simple_general 형식 선택"""
    selector = FormatSelector()
    query_analysis = {"query_type": "general"}
    retrieval = {}

    fmt = selector.select_format(query_analysis, retrieval)
    assert fmt.format_id == "simple_general"


@pytest.mark.unit
def test_format_selector_restricted_query():
    """제한 영역 쿼리는 info_only 형식 선택"""
    selector = FormatSelector()
    query_analysis = {"query_type": "restricted"}
    retrieval = {}

    fmt = selector.select_format(query_analysis, retrieval)
    assert fmt.format_id == "info_only"


@pytest.mark.unit
def test_format_selector_build_context():
    """컨텍스트 생성 검증"""
    selector = FormatSelector()
    retrieval = {
        "disputes": [{"doc_id": "123"}],
        "counsels": [],
        "laws": [{"unit_id": "456"}],
        "criteria": [],
        "agency": {"agency": "KCA"},
    }

    context = selector.build_context(retrieval)

    assert context["has_cases"] is True
    assert context["has_laws"] is True
    assert context["has_criteria"] is False
    assert context["has_agency"] is True


# ============================================================
# PromptBuilder 테스트
# ============================================================


@pytest.mark.unit
def test_prompt_builder_full_dispute_system_prompt():
    """full_dispute 시스템 프롬프트 생성"""
    builder = PromptBuilder()
    fmt = RESPONSE_FORMATS["full_dispute"]

    system_prompt = builder.build_system_prompt(fmt)

    assert "한국 소비자 분쟁 조정 전문 상담 어시스턴트" in system_prompt
    assert "유사 사례 분석" in system_prompt
    assert "관련 법령 및 기준" in system_prompt
    assert "추가 안내" in system_prompt
    assert "본 답변은 정보 제공 목적" in system_prompt  # disclaimer


@pytest.mark.unit
def test_prompt_builder_simple_general_system_prompt():
    """simple_general 시스템 프롬프트 생성"""
    builder = PromptBuilder()
    fmt = RESPONSE_FORMATS["simple_general"]

    system_prompt = builder.build_system_prompt(fmt)

    assert "똑소리" in system_prompt
    assert "친근" in system_prompt
    assert "본 답변은 정보 제공 목적" not in system_prompt  # no disclaimer


@pytest.mark.unit
def test_prompt_builder_user_prompt():
    """사용자 프롬프트 생성"""
    builder = PromptBuilder()
    fmt = RESPONSE_FORMATS["full_dispute"]
    query = "헬스장 환불 문제입니다"
    retrieval = {
        "disputes": [
            {
                "source_org": "KCA",
                "doc_title": "헬스장 환불 사례",
                "decision_date": "2024-01-01",
                "similarity": 0.85,
                "content": "헬스장 환불 관련 조정 결과입니다.",
            }
        ],
        "counsels": [],
        "laws": [],
        "criteria": [],
    }
    agency_info = {
        "agency": "KCA",
        "agency_info": {"full_name": "한국소비자원", "url": "https://www.kca.go.kr"},
        "dispute_type": "1:N",
        "reason": "일반 소비자 분쟁",
    }
    context = {
        "has_cases": True,
        "has_laws": False,
        "has_criteria": False,
        "has_agency": True,
    }

    user_prompt = builder.build_user_prompt(fmt, query, retrieval, agency_info, context)

    assert query in user_prompt
    assert "헬스장 환불 사례" in user_prompt
    assert "KCA" in user_prompt


# ============================================================
# 통합 테스트
# ============================================================


@pytest.mark.unit
def test_format_selection_and_prompt_building_integration():
    """형식 선택 → 프롬프트 생성 통합 테스트"""
    selector = FormatSelector()
    builder = PromptBuilder()

    query_analysis = {"query_type": "dispute"}
    retrieval = {
        "disputes": [
            {
                "doc_id": "123",
                "doc_title": "사례1",
                "source_org": "KCA",
                "decision_date": "2024-01-01",
                "similarity": 0.85,
                "content": "내용",
            }
        ],
        "counsels": [],
        "laws": [],
        "criteria": [],
    }
    agency_info = {
        "agency": "KCA",
        "agency_info": {"full_name": "한국소비자원", "url": "https://www.kca.go.kr"},
        "dispute_type": "1:N",
        "reason": "일반 소비자 분쟁",
    }

    # 1. 형식 선택
    fmt = selector.select_format(query_analysis, retrieval)
    assert fmt.format_id == "full_dispute"

    # 2. 컨텍스트 생성
    context = selector.build_context(retrieval)
    assert context["has_cases"] is True

    # 3. 프롬프트 생성
    system_prompt = builder.build_system_prompt(fmt)
    user_prompt = builder.build_user_prompt(
        fmt, "헬스장 환불", retrieval, agency_info, context
    )

    assert len(system_prompt) > 0
    assert len(user_prompt) > 0
    assert "헬스장 환불" in user_prompt
