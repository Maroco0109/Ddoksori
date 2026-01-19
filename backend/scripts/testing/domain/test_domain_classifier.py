import pytest
from app.domain.classifier import DomainClassifier, classify_domain, ClassificationResult


@pytest.fixture
def classifier():
    return DomainClassifier()


class TestRestrictedDomains:
    """FSS, K_MEDI, KOPICO should all be restricted and have equal priority."""
    
    @pytest.mark.parametrize("query,expected_agency", [
        ("보험 가입했는데 해약환급금이 너무 적어요", "FSS"),
        ("펀드 투자 원금 손실 보상받을 수 있나요", "FSS"),
        ("신용카드 리볼빙 이자가 너무 높아요", "FSS"),
        ("대출 상환 연체이자 계산이 잘못된 것 같아요", "FSS"),
        ("보험설계사가 설명 없이 가입시켰어요", "FSS"),
    ])
    def test_finance_domain_fss(self, classifier, query, expected_agency):
        result = classifier.classify(query)
        assert result.agency == expected_agency
        assert result.is_restricted is True
        assert result.dispute_type == "finance"
    
    @pytest.mark.parametrize("query,expected_agency", [
        ("수술 후 합병증이 생겼어요", "K_MEDI"),
        ("병원에서 오진으로 치료가 늦어졌어요", "K_MEDI"),
        ("의료비 청구가 과다한 것 같아요", "K_MEDI"),
        ("임플란트 시술 후 문제가 생겼어요", "K_MEDI"),
        ("병원 진료 기록 열람을 거부당했어요", "K_MEDI"),
    ])
    def test_medical_domain_k_medi(self, classifier, query, expected_agency):
        result = classifier.classify(query)
        assert result.agency == expected_agency
        assert result.is_restricted is True
        assert result.dispute_type == "medical"
    
    @pytest.mark.parametrize("query,expected_agency", [
        ("개인정보가 유출되었어요", "KOPICO"),
        ("동의 없이 마케팅동의 문자가 와요", "KOPICO"),
        ("개인정보 정보삭제 요청을 거부당했어요", "KOPICO"),
        ("CCTV 개인정보 무단수집 동의 없이 사용했어요", "KOPICO"),
        ("제3자제공으로 개인정보가 제공됐어요", "KOPICO"),
    ])
    def test_privacy_domain_kopico(self, classifier, query, expected_agency):
        result = classifier.classify(query)
        assert result.agency == expected_agency
        assert result.is_restricted is True
        assert result.dispute_type == "privacy"


class TestNonRestrictedDomains:
    """KCDRC, ECMC, KCA should not be restricted."""
    
    @pytest.mark.parametrize("query,expected_agency", [
        ("게임 아이템 환불 안 해줘요", "KCDRC"),
        ("넷플릭스 구독 취소가 안 돼요", "KCDRC"),
        ("인앱결제 취소하고 싶어요", "KCDRC"),
        ("웹툰 이용권 환불받고 싶어요", "KCDRC"),
        ("음원 스트리밍 서비스 해지가 어려워요", "KCDRC"),
    ])
    def test_content_domain_kcdrc(self, classifier, query, expected_agency):
        result = classifier.classify(query)
        assert result.agency == expected_agency
        assert result.is_restricted is False
        assert result.dispute_type == "contents"
    
    @pytest.mark.parametrize("query,expected_agency", [
        ("당근마켓에서 사기당했어요", "ECMC"),
        ("중고나라 직거래 물건이 불량이에요", "ECMC"),
        ("번개장터에서 허위 판매 신고", "ECMC"),
        ("개인 판매자가 환불을 안 해줘요", "ECMC"),
        ("중고거래 택배가 안 와요", "ECMC"),
    ])
    def test_individual_domain_ecmc(self, classifier, query, expected_agency):
        result = classifier.classify(query)
        assert result.agency == expected_agency
        assert result.is_restricted is False
        assert result.dispute_type == "1:1"
    
    @pytest.mark.parametrize("query,expected_agency", [
        ("노트북 환불받고 싶어요", "KCA"),
        ("에어컨 AS가 제대로 안 돼요", "KCA"),
        ("헬스장 중도 해지하고 싶어요", "KCA"),
        ("가구 배송이 한 달째 안 와요", "KCA"),
        ("옷 교환해달라고 했는데 거절당했어요", "KCA"),
    ])
    def test_general_domain_kca(self, classifier, query, expected_agency):
        result = classifier.classify(query)
        assert result.agency == expected_agency
        assert result.is_restricted is False
        assert result.dispute_type == "1:N"


class TestEqualPriorityForRestricted:
    """When multiple restricted domains match, highest score wins."""
    
    def test_mixed_finance_and_medical_prefers_higher_score(self, classifier):
        query_more_finance = "보험 가입 후 수술 합병증 보험금 청구"
        result = classifier.classify(query_more_finance)
        assert result.agency == "FSS"
        assert result.is_restricted is True
        
    def test_mixed_medical_and_finance_prefers_medical(self, classifier):
        query_more_medical = "병원에서 수술받고 의료비 보험금 청구"
        result = classifier.classify(query_more_medical)
        assert result.agency == "K_MEDI"
        assert result.is_restricted is True


class TestClassificationResult:
    """Test ClassificationResult structure."""
    
    def test_result_has_all_fields(self, classifier):
        result = classifier.classify("노트북 환불")
        
        assert hasattr(result, 'agency')
        assert hasattr(result, 'dispute_type')
        assert hasattr(result, 'reason')
        assert hasattr(result, 'confidence')
        assert hasattr(result, 'matched_keywords')
        assert hasattr(result, 'is_restricted')
    
    def test_confidence_is_bounded(self, classifier):
        result = classifier.classify("보험 펀드 주식 대출 카드 은행 이자 금리")
        assert 0.0 <= result.confidence <= 1.0
    
    def test_matched_keywords_not_empty_for_specific_domain(self, classifier):
        result = classifier.classify("보험 해약환급금")
        assert len(result.matched_keywords) > 0


class TestEdgeCases:
    """Edge cases and boundary conditions."""
    
    def test_empty_query_defaults_to_kca(self, classifier):
        result = classifier.classify("")
        assert result.agency == "KCA"
    
    def test_single_keyword_below_threshold(self, classifier):
        result = classifier.classify("보험")
        assert result.agency == "KCA"
    
    def test_case_insensitive(self, classifier):
        result_lower = classifier.classify("ott 서비스")
        result_upper = classifier.classify("OTT 서비스")
        assert result_lower.agency == result_upper.agency


class TestClassifyDomainFunction:
    """Test the module-level classify_domain function."""
    
    def test_classify_domain_returns_result(self):
        result = classify_domain("노트북 환불")
        assert isinstance(result, ClassificationResult)
    
    def test_classify_domain_singleton_behavior(self):
        r1 = classify_domain("보험 해약")
        r2 = classify_domain("보험 해약")
        assert r1.agency == r2.agency
