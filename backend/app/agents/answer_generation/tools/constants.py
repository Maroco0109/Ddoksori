"""
Answer Generation Constants

답변 생성에 사용되는 상수, 템플릿, 기관 정보 정의.
"""

from typing import Dict, List

# S1-1 MVP Answer Template
DISCLAIMER = "본 답변은 정보 제공 목적이며 법률 자문이 아닙니다. 최종 판단·결정은 관련 기관 또는 전문가와 상담하여 진행해 주세요."

# 4섹션 구조화 응답용 섹션 (Legacy)
SECTIONS = [
    "1. 추천 기관 및 사유",
    "2. 유사 사례",
    "3. 관련 법적 근거",
    "4. 다음 행동 체크리스트"
]

# 3섹션 구조화 응답용 섹션 (PR-6: 2026-01-20)
# 변경: 유사 사례 → 법령/기준 → 추가 안내 (권장 조치 제외)
STRUCTURED_SECTIONS = [
    "1. 유사 사례 분석",
    "2. 관련 법령 및 기준",
    "3. 추가 안내"
]

# 기관 추천을 위한 콘텐츠 키워드
CONTENT_KEYWORDS: List[str] = [
    "게임", "영화", "콘텐츠", "앱", "어플", "애플리케이션",
    "음악", "웹툰", "만화", "동영상", "영상", "스트리밍",
    "OTT", "넷플릭스", "왓챠", "디즈니", "유튜브",
    "인앱", "결제", "아이템", "캐시", "다이아", "루비",
    "디지털", "다운로드", "구독", "VOD", "e북", "전자책"
]

# 개인간 거래 키워드
INDIVIDUAL_KEYWORDS: List[str] = [
    "중고", "직거래", "당근", "당근마켓", "번개장터", "중고나라",
    "개인간", "개인거래", "개인 판매", "개인판매자",
    "직접 거래", "직접거래", "만나서", "택배거래",
    "중고거래", "중고 거래", "세컨핸드", "second hand"
]

# 기관 정보
AGENCY_INFO: Dict[str, Dict[str, str]] = {
    'KCA': {
        'name': '한국소비자원',
        'full_name': '한국소비자원 소비자분쟁조정위원회',
        'description': '일반 소비자 분쟁 조정 (사업자 대 소비자)',
        'url': 'https://www.kca.go.kr'
    },
    'ECMC': {
        'name': '전자거래분쟁조정위원회',
        'full_name': '전자거래분쟁조정위원회',
        'description': '전자거래 및 개인간 거래 분쟁 조정',
        'url': 'https://www.ecmc.or.kr'
    },
    'KCDRC': {
        'name': '콘텐츠분쟁조정위원회',
        'full_name': '콘텐츠분쟁조정위원회',
        'description': '콘텐츠(게임, 영화, 음악 등) 관련 분쟁 조정',
        'url': 'https://www.kcdrc.kr'
    }
}

# claim_evidence_map 생성용 핵심 용어
EVIDENCE_KEY_TERMS: List[str] = [
    '소비자', '분쟁', '환불', '조정', '법', '기준', '신청', '피해', '배상'
]


__all__ = [
    "DISCLAIMER",
    "SECTIONS",
    "STRUCTURED_SECTIONS",
    "CONTENT_KEYWORDS",
    "INDIVIDUAL_KEYWORDS",
    "AGENCY_INFO",
    "EVIDENCE_KEY_TERMS",
]
