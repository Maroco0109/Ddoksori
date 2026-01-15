from typing import List, TypedDict


class GoldenSetItem(TypedDict):
    query: str
    expected_agency: str
    is_restricted: bool


GOLDEN_SET: List[GoldenSetItem] = [
    # FSS (금융) - 12개
    {"query": "자동차보험 보험금 청구가 거부됐어요", "expected_agency": "FSS", "is_restricted": True},
    {"query": "은행 대출 금리 인상이 불합리해요", "expected_agency": "FSS", "is_restricted": True},
    {"query": "신용카드 연회비 환불 요청했는데 거절당함", "expected_agency": "FSS", "is_restricted": True},
    {"query": "보험 해약환급금이 너무 적어요", "expected_agency": "FSS", "is_restricted": True},
    {"query": "P2P 투자 원금 손실 보상 요청", "expected_agency": "FSS", "is_restricted": True},
    {"query": "적금 중도해지 이자 계산이 이상해요", "expected_agency": "FSS", "is_restricted": True},
    {"query": "리볼빙 서비스 몰래 가입시켜놨어요", "expected_agency": "FSS", "is_restricted": True},
    {"query": "펀드 불완전판매 피해 보상", "expected_agency": "FSS", "is_restricted": True},
    {"query": "대출 상환 수수료가 과다해요", "expected_agency": "FSS", "is_restricted": True},
    {"query": "보험설계사가 설명 안하고 가입시킴", "expected_agency": "FSS", "is_restricted": True},
    {"query": "증권사에서 부당하게 수수료를 청구했어요", "expected_agency": "FSS", "is_restricted": True},
    {"query": "저축은행 예금 이자가 약속과 다릅니다", "expected_agency": "FSS", "is_restricted": True},

    # K_MEDI (의료) - 12개
    {"query": "수술 후 합병증으로 장애가 생겼어요", "expected_agency": "K_MEDI", "is_restricted": True},
    {"query": "오진으로 치료 시기 놓쳤어요", "expected_agency": "K_MEDI", "is_restricted": True},
    {"query": "성형수술 결과가 처음 설명과 다릅니다", "expected_agency": "K_MEDI", "is_restricted": True},
    {"query": "의료비가 과다 청구된 것 같아요", "expected_agency": "K_MEDI", "is_restricted": True},
    {"query": "병원에서 감염이 됐어요", "expected_agency": "K_MEDI", "is_restricted": True},
    {"query": "치과 임플란트 시술 후 문제 발생", "expected_agency": "K_MEDI", "is_restricted": True},
    {"query": "의사가 충분한 설명 없이 수술함", "expected_agency": "K_MEDI", "is_restricted": True},
    {"query": "입원 중 낙상사고가 발생했어요", "expected_agency": "K_MEDI", "is_restricted": True},
    {"query": "약 처방 오류로 부작용이 생겼어요", "expected_agency": "K_MEDI", "is_restricted": True},
    {"query": "한의원 치료 후 상태가 악화됐어요", "expected_agency": "K_MEDI", "is_restricted": True},
    {"query": "진료비 영수증이 실제와 다릅니다", "expected_agency": "K_MEDI", "is_restricted": True},
    {"query": "마취 후유증으로 고통받고 있어요", "expected_agency": "K_MEDI", "is_restricted": True},

    # KCDRC (콘텐츠) - 8개
    {"query": "게임 아이템 결제 환불 요청", "expected_agency": "KCDRC", "is_restricted": False},
    {"query": "미성년자 앱 결제 취소하고 싶어요", "expected_agency": "KCDRC", "is_restricted": False},
    {"query": "넷플릭스 구독 해지가 안돼요", "expected_agency": "KCDRC", "is_restricted": False},
    {"query": "웹툰 서비스 환불 거부당함", "expected_agency": "KCDRC", "is_restricted": False},
    {"query": "인앱결제 취소 요청했는데 거절", "expected_agency": "KCDRC", "is_restricted": False},
    {"query": "OTT 서비스 자동결제 취소 방법", "expected_agency": "KCDRC", "is_restricted": False},
    {"query": "모바일 게임 캐시 환불 문제", "expected_agency": "KCDRC", "is_restricted": False},
    {"query": "e북 구매 후 환불이 안됩니다", "expected_agency": "KCDRC", "is_restricted": False},

    # ECMC (개인간 거래) - 6개
    {"query": "당근마켓 중고거래 사기당했어요", "expected_agency": "ECMC", "is_restricted": False},
    {"query": "번개장터에서 물건 받았는데 불량", "expected_agency": "ECMC", "is_restricted": False},
    {"query": "중고나라 직거래 후 연락두절", "expected_agency": "ECMC", "is_restricted": False},
    {"query": "개인간 거래로 산 제품이 가품이에요", "expected_agency": "ECMC", "is_restricted": False},
    {"query": "중고거래 택배로 받았는데 파손됨", "expected_agency": "ECMC", "is_restricted": False},
    {"query": "직거래로 만나서 샀는데 하자 발견", "expected_agency": "ECMC", "is_restricted": False},

    # KCA (일반 소비자) - 12개
    {"query": "헬스장 환불 거부당했어요", "expected_agency": "KCA", "is_restricted": False},
    {"query": "세탁기 수리비 환불 요청", "expected_agency": "KCA", "is_restricted": False},
    {"query": "호텔 예약 취소 위약금 문제", "expected_agency": "KCA", "is_restricted": False},
    {"query": "온라인 쇼핑몰 배송 지연 보상", "expected_agency": "KCA", "is_restricted": False},
    {"query": "에어컨 설치 불량으로 피해 입음", "expected_agency": "KCA", "is_restricted": False},
    {"query": "학원비 환불 거부 문제", "expected_agency": "KCA", "is_restricted": False},
    {"query": "결혼식장 계약 취소 위약금", "expected_agency": "KCA", "is_restricted": False},
    {"query": "렌터카 사고 보상 분쟁", "expected_agency": "KCA", "is_restricted": False},
    {"query": "가전제품 AS 불만족", "expected_agency": "KCA", "is_restricted": False},
    {"query": "여행사 일정 변경 보상 요청", "expected_agency": "KCA", "is_restricted": False},
    {"query": "이사업체 물품 파손 보상", "expected_agency": "KCA", "is_restricted": False},
    {"query": "통신사 요금제 변경 문제", "expected_agency": "KCA", "is_restricted": False},
]
