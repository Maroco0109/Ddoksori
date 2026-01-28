"""
똑소리 프로젝트 - 도메인 설정 상수
S2-4: 기관 정보 및 키워드 상수 정의
"""

from typing import Dict, List, Literal, TypedDict


class AgencyInfoDict(TypedDict, total=False):
    name: str
    full_name: str
    description: str
    url: str
    is_restricted: bool
    restriction_reason: str


AgencyCode = Literal['KCA', 'ECMC', 'KCDRC', 'FSS', 'K_MEDI', 'KOPICO', 'KLAB', 'MOLIT']

AGENCY_CODES: List[AgencyCode] = ['KCA', 'ECMC', 'KCDRC', 'FSS', 'K_MEDI', 'KOPICO', 'KLAB', 'MOLIT']

AGENCY_INFO: Dict[AgencyCode, AgencyInfoDict] = {
    'KCA': {
        'name': '한국소비자원',
        'full_name': '한국소비자원 소비자분쟁조정위원회',
        'description': '일반 소비자 분쟁 조정 (사업자 대 소비자)',
        'url': 'https://www.kca.go.kr',
        'is_restricted': False,
    },
    'ECMC': {
        'name': '전자거래분쟁조정위원회',
        'full_name': '전자거래분쟁조정위원회',
        'description': '전자거래 및 개인간 거래 분쟁 조정',
        'url': 'https://www.ecmc.or.kr',
        'is_restricted': False,
    },
    'KCDRC': {
        'name': '콘텐츠분쟁조정위원회',
        'full_name': '콘텐츠분쟁조정위원회',
        'description': '콘텐츠(게임, 영화, 음악 등) 관련 분쟁 조정',
        'url': 'https://www.kcdrc.kr',
        'is_restricted': False,
    },
    'FSS': {
        'name': '금융감독원',
        'full_name': '금융감독원 금융분쟁조정위원회',
        'description': '금융 관련 분쟁 조정 (보험, 은행, 증권, 카드 등)',
        'url': 'https://www.fss.or.kr',
        'is_restricted': True,
        'restriction_reason': '금융 분쟁은 복잡하고 전문적인 영역으로, 전문가 상담 후 진행을 권장합니다.',
    },
    'K_MEDI': {
        'name': '한국의료분쟁조정중재원',
        'full_name': '한국의료분쟁조정중재원',
        'description': '의료 관련 분쟁 조정 (의료사고, 진료비 등)',
        'url': 'https://www.k-medi.or.kr',
        'is_restricted': True,
        'restriction_reason': '의료 분쟁은 복잡하고 전문적인 영역으로, 전문가 상담 후 진행을 권장합니다.',
    },
    'KOPICO': {
        'name': '개인정보분쟁조정위원회',
        'full_name': '개인정보분쟁조정위원회',
        'description': '개인정보 침해 관련 분쟁 조정 (정보유출, 무단수집, 동의 없는 제3자 제공 등)',
        'url': 'https://www.kopico.go.kr',
        'is_restricted': True,
        'restriction_reason': '개인정보 분쟁은 복잡하고 전문적인 영역으로, 전문가 상담 후 진행을 권장합니다.',
    },
    'KLAB': {
        'name': '임대차분쟁조정위원회',
        'full_name': '한국부동산원 임대차분쟁조정위원회',
        'description': '주택 임대차 관련 분쟁 조정 (보증금 반환, 임대료 분쟁, 계약 해지 등)',
        'url': 'https://www.reb.or.kr',
        'phone': '1644-2828',
        'is_restricted': True,
        'restriction_reason': '부동산 임대차 분쟁은 복잡하고 전문적인 영역으로, 전문가 상담 후 진행을 권장합니다.',
    },
    'MOLIT': {
        'name': '건설분쟁조정위원회',
        'full_name': '국토교통부 건설분쟁조정위원회',
        'description': '건설/건축 관련 분쟁 조정 (공사 하자, 시공 불량, 계약 분쟁 등)',
        'url': 'https://www.molit.go.kr',
        'phone': '1599-0001',
        'is_restricted': True,
        'restriction_reason': '건설/건축 분쟁은 복잡하고 전문적인 영역으로, 전문가 상담 후 진행을 권장합니다.',
    },
}

CONTENT_KEYWORDS: List[str] = [
    "게임", "영화", "콘텐츠", "앱", "어플", "애플리케이션",
    "음악", "웹툰", "만화", "동영상", "영상", "스트리밍",
    "OTT", "넷플릭스", "왓챠", "디즈니", "유튜브", "티빙", "쿠팡플레이", "웨이브",
    "인앱", "아이템", "캐시", "다이아", "루비",
    "디지털", "다운로드", "구독", "VOD", "e북", "전자책",
]

INDIVIDUAL_KEYWORDS: List[str] = [
    "중고", "직거래", "당근", "당근마켓", "번개장터", "중고나라",
    "개인간", "개인거래", "개인 판매", "개인판매자",
    "직접 거래", "직접거래", "만나서", "택배거래",
    "중고거래", "중고 거래", "세컨핸드", "second hand",
]

FINANCE_KEYWORDS: List[str] = [
    "보험", "생명보험", "손해보험", "자동차보험", "실손보험", "암보험",
    "적금", "예금", "대출", "신용대출", "담보대출", "주택담보", "전세대출",
    "펀드", "주식", "증권", "투자", "채권", "ETF", "ELS",
    "카드", "신용카드", "체크카드", "리볼빙", "현금서비스",
    "은행", "저축은행", "보험사", "증권사", "카드사",
    "대부업", "캐피탈", "P2P", "핀테크",
    "이자", "금리", "연체", "채무", "상환",
    "보험금", "보험료", "해약", "해지환급금", "약관대출",
    "불완전판매", "설명의무", "적합성원칙", "금융사기",
    "보험설계사", "원금손실", "원금", "가입",
]

MEDICAL_KEYWORDS: List[str] = [
    "수술", "진료", "치료", "입원", "검사", "처방", "투약",
    "진단", "오진", "의료사고", "의료과실", "부작용", "후유증",
    "병원", "의원", "한의원", "치과", "안과", "성형외과", "피부과",
    "대학병원", "종합병원", "요양병원", "정형외과",
    "의료비", "진료비", "수술비", "입원비", "치료비",
    "의료분쟁", "의료소송", "의사", "간호사", "의료진",
    "감염", "합병증", "사망", "장애", "낙상",
    "임플란트", "성형", "시술", "마취", "청구",
]

LAW_KEYWORDS: List[str] = [
    "법", "법률", "법령", "조항", "조문", "제조", "항", "호",
    "소비자보호법", "전자상거래법", "약관규제법", "할부거래법",
    "방문판매법", "표시광고법", "제조물책임법",
]

CRITERIA_KEYWORDS: List[str] = [
    "기준", "분쟁조정기준", "별표", "해제", "해지", "위약금",
    "환불", "보상", "배상", "수리", "교환", "반품",
]

PRIVACY_KEYWORDS: List[str] = [
    "개인정보", "정보유출", "정보침해", "개인정보보호",
    "유출", "해킹", "스팸", "스미싱", "보이스피싱",
    "동의", "정보동의", "마케팅동의", "수집동의",
    "정보삭제", "정보파기", "정보열람", "정보정정",
    "CCTV", "얼굴인식", "위치정보", "통화기록",
    "주민번호", "신용정보", "민감정보", "건강정보",
    "제3자제공", "정보이전", "정보처리",
]
