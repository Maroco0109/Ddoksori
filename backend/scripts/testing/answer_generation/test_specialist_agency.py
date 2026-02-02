"""
PR-3: 전문기관 안내 응답 처리 테스트

restricted 도메인에 대한 전문기관 안내 응답 생성을 테스트합니다.
"""

import pytest

from app.agents.answer_generation.agent import (
    DOMAIN_KOREAN_NAMES,
    SPECIALIST_AGENCY_RESPONSE_TEMPLATE,
    _build_specialist_agency_response,
    _format_similar_cases_for_specialist,
)


class TestSpecialistAgencyResponse:
    """전문기관 안내 응답 생성 테스트"""

    @pytest.mark.parametrize(
        "domain,expected_name",
        [
            ("finance", "금융"),
            ("medical", "의료"),
            ("privacy", "개인정보"),
            ("realestate", "부동산 임대차"),
            ("construction", "건설/건축"),
        ],
    )
    def test_domain_korean_names(self, domain, expected_name):
        """도메인별 한국어 명칭 매핑 테스트"""
        assert DOMAIN_KOREAN_NAMES.get(domain) == expected_name

    def test_build_specialist_response_finance(self):
        """금융 도메인 전문기관 응답 생성"""
        query_analysis = {
            "query_type": "restricted",
            "restricted_domain": "finance",
            "restricted_agency_info": {
                "name": "금융분쟁조정위원회",
                "organization": "금융감독원",
                "url": "https://www.fcsc.kr",
                "phone": "1332",
            },
        }

        result = _build_specialist_agency_response(
            user_query="보험금 청구가 거절됐어요",
            query_analysis=query_analysis,
            retrieval={},
        )

        assert result["is_restricted"] is True
        assert result["restricted_domain"] == "finance"
        assert result["generation_model_used"] == "specialist_template"
        assert "금융분쟁조정위원회" in result["draft_answer"]
        assert "금융감독원" in result["draft_answer"]
        assert "1332" in result["draft_answer"]

    def test_build_specialist_response_medical(self):
        """의료 도메인 전문기관 응답 생성"""
        query_analysis = {
            "query_type": "restricted",
            "restricted_domain": "medical",
            "restricted_agency_info": {
                "name": "의료분쟁조정위원회",
                "organization": "한국의료분쟁조정중재원",
                "url": "https://www.k-medi.or.kr",
                "phone": "1670-2545",
            },
        }

        result = _build_specialist_agency_response(
            user_query="수술 부작용이 있어요",
            query_analysis=query_analysis,
            retrieval={},
        )

        assert result["is_restricted"] is True
        assert "의료분쟁조정위원회" in result["draft_answer"]
        assert "한국의료분쟁조정중재원" in result["draft_answer"]

    def test_build_specialist_response_with_similar_cases(self):
        """유사 사례가 있는 경우 응답 생성"""
        query_analysis = {
            "query_type": "restricted",
            "restricted_domain": "realestate",
            "restricted_agency_info": {
                "name": "임대차분쟁조정위원회",
                "organization": "한국부동산원",
                "url": "https://www.reb.or.kr",
                "phone": "1644-2828",
            },
        }

        retrieval = {
            "disputes": [
                {
                    "doc_title": "전세보증금 반환 분쟁 사례",
                    "source_org": "한국부동산원",
                    "summary": "임대인이 전세보증금 반환을 거부한 사례",
                },
                {
                    "doc_title": "임대료 인상 분쟁 사례",
                    "source_org": "한국부동산원",
                },
            ],
        }

        result = _build_specialist_agency_response(
            user_query="전세보증금을 안 돌려줘요",
            query_analysis=query_analysis,
            retrieval=retrieval,
        )

        assert result["is_restricted"] is True
        assert result["has_sufficient_evidence"] is True
        assert "전세보증금 반환 분쟁 사례" in result["draft_answer"]
        assert "유사 사례" in result["draft_answer"]

    def test_build_specialist_response_without_similar_cases(self):
        """유사 사례가 없는 경우 응답 생성"""
        query_analysis = {
            "query_type": "restricted",
            "restricted_domain": "construction",
            "restricted_agency_info": {
                "name": "건설분쟁조정위원회",
                "organization": "국토교통부",
                "url": "https://www.molit.go.kr",
                "phone": "1599-0001",
            },
        }

        result = _build_specialist_agency_response(
            user_query="아파트 하자 보수가 안 돼요",
            query_analysis=query_analysis,
            retrieval={},
        )

        assert result["is_restricted"] is True
        assert result["has_sufficient_evidence"] is False
        assert "건설분쟁조정위원회" in result["draft_answer"]
        # 유사 사례 섹션이 비어있어야 함
        assert "## 참고: 유사 사례" not in result["draft_answer"]

    def test_build_specialist_response_without_agency_info(self):
        """agency_info가 없는 경우 기본값 사용"""
        query_analysis = {
            "query_type": "restricted",
            "restricted_domain": "privacy",
            "restricted_agency_info": None,
        }

        result = _build_specialist_agency_response(
            user_query="개인정보가 유출됐어요",
            query_analysis=query_analysis,
            retrieval={},
        )

        # 기본값이 사용되어야 함
        assert result["is_restricted"] is True
        assert result["draft_answer"] is not None
        assert len(result["draft_answer"]) > 0


class TestFormatSimilarCasesForSpecialist:
    """유사 사례 포맷팅 테스트"""

    def test_format_with_cases(self):
        """사례가 있는 경우 포맷팅"""
        cases = [
            {
                "doc_title": "테스트 사례 1",
                "source_org": "테스트 기관",
                "summary": "테스트 요약입니다.",
            },
        ]

        result = _format_similar_cases_for_specialist(cases)

        assert "## 참고: 유사 사례" in result
        assert "테스트 사례 1" in result
        assert "테스트 기관" in result

    def test_format_without_cases(self):
        """사례가 없는 경우 빈 문자열 반환"""
        result = _format_similar_cases_for_specialist([])
        assert result == ""

    def test_format_max_three_cases(self):
        """최대 3개 사례만 포함"""
        cases = [{"doc_title": f"사례 {i}", "source_org": "기관"} for i in range(5)]

        result = _format_similar_cases_for_specialist(cases)

        assert "사례 0" in result
        assert "사례 1" in result
        assert "사례 2" in result
        assert "사례 3" not in result
        assert "사례 4" not in result
