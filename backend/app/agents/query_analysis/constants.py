"""
Query Analysis Constants

키워드, 패턴, 매핑 등 질의분석에 사용되는 모든 상수 정의.
"""

import os
from typing import Dict, List

# ============================================================
# Feature Flags
# ============================================================
ENABLE_FAST_PATH_PROMOTION = (
    os.getenv("ENABLE_FAST_PATH_PROMOTION", "true").lower() == "true"
)

ENABLE_AMBIGUOUS_DETECTION = (
    os.getenv("ENABLE_AMBIGUOUS_DETECTION", "true").lower() == "true"
)

# LLM fallback 트리거 조건 (짧지만 패턴에 안 걸린 경우)
LLM_AMBIGUITY_CHECK_MAX_LENGTH = 30  # 30자 이하면 LLM 판단 요청


# ============================================================
# PR-2: Selective Retrieval
# 검색 우선순위: 법령 → 기준 → 사례
# ============================================================
QUERY_TYPE_TO_RETRIEVERS: Dict[str, List[str]] = {
    "law": ["law"],                                  # 법령만
    "criteria": ["law", "criteria"],                 # 법령 + 기준 (기준은 법령의 구체화)
    "dispute": ["law", "criteria", "case", "counsel"],  # P2.2: counsel 추가 (13,544 cases)
    "procedure": ["law", "criteria"],                # 절차 안내: 법령 + 기준 (템플릿 + RAG 보강)
    "restricted": ["case"],                          # 전문기관 도메인: 유사 사례만 검색
    "general": [],                                   # 검색 불필요
    "system_meta": [],                               # 검색 불필요
    "ambiguous": ["law", "criteria"],                # 법령 + 기준 (사례는 나중에)
    "meta_conversational": [],                       # 검색 불필요 - 가이드 응답만
}


# ============================================================
# Restricted Domain Keywords (전문기관 도메인)
# KCA/ECMC 관할 외 전문분쟁조정기관 안내 필요
# ============================================================
RESTRICTED_DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "finance": [  # 금융감독원 · 금융분쟁조정위원회
        "대출", "보험", "카드", "신용카드", "주식", "펀드", "은행", "예금", "적금",
        "증권", "투자", "금융", "채권", "보험사", "저축", "대출금리", "금융상품",
        "보험금", "보험료", "해지환급금", "보험해지", "금융회사",
    ],
    "medical": [  # 한국의료분쟁조정중재원 · 의료분쟁조정위원회
        "병원", "진료", "수술", "의사", "의료사고", "의료", "치료", "약", "처방",
        "입원", "퇴원", "간호사", "의원", "클리닉", "성형", "성형외과", "피부과",
        "치과", "한의원", "약국", "의료비", "진료비", "오진", "의료과실",
    ],
    "privacy": [  # 개인정보보호위원회 · 개인정보분쟁조정위원회
        "개인정보", "유출", "정보보호", "개인정보유출", "정보유출", "해킹",
        "개인정보보호", "정보침해", "동의없이", "개인정보처리",
    ],
    "realestate": [  # 한국부동산원 · 임대차분쟁조정위원회
        "임대차", "전세", "월세", "집주인", "보증금", "임대인", "임차인",
        "주택임대", "전월세", "보증금반환", "퇴거", "계약갱신",
    ],
    "construction": [  # 국토교통부 · 건설/건축분쟁조정위원회
        "공사", "시공", "건축", "아파트하자", "건설", "건물", "시공사",
        "하자보수", "건축물", "입주", "준공", "건축주", "시공불량",
    ],
}

# Restricted 도메인별 전문기관 정보
RESTRICTED_DOMAIN_AGENCIES: Dict[str, Dict[str, str]] = {
    "finance": {
        "name": "금융분쟁조정위원회",
        "organization": "금융감독원",
        "url": "https://www.fcsc.kr",
        "phone": "1332",
    },
    "medical": {
        "name": "의료분쟁조정위원회",
        "organization": "한국의료분쟁조정중재원",
        "url": "https://www.k-medi.or.kr",
        "phone": "1670-2545",
    },
    "privacy": {
        "name": "개인정보분쟁조정위원회",
        "organization": "개인정보보호위원회",
        "url": "https://www.kopico.go.kr",
        "phone": "1833-6972",
    },
    "realestate": {
        "name": "임대차분쟁조정위원회",
        "organization": "한국부동산원",
        "url": "https://www.reb.or.kr",
        "phone": "1644-2828",
    },
    "construction": {
        "name": "건설분쟁조정위원회",
        "organization": "국토교통부",
        "url": "https://www.molit.go.kr",
        "phone": "1599-0001",
    },
}


# ============================================================
# Keyword Definitions
# ============================================================

# 절차 안내 키워드 (Procedure)
PROCEDURE_KEYWORDS: List[str] = [
    "신청 방법", "신청방법", "접수", "분쟁조정 신청", "분쟁조정신청",
    "어떻게 신청", "절차", "서류", "기간", "분쟁해결 절차", "조정신청",
    "피해구제 신청", "신고", "신고방법", "제출서류", "필요서류",
    "온라인 신청", "방문 신청", "조정 절차", "구비서류",
]

# 개인간 거래 키워드 (ECMC - 전자문서·전자거래분쟁조정위원회 관할)
INDIVIDUAL_KEYWORDS: List[str] = [
    "중고", "직거래", "당근", "당근마켓", "번개장터", "중고나라",
    "개인간", "개인거래", "개인 판매", "개인판매자", "직접 거래", "직접거래",
    "만나서", "택배거래", "중고거래", "중고 거래", "세컨핸드", "second hand",
]

# 법령 관련 키워드 (법률 DB 검색 트리거)
LAW_KEYWORDS: List[str] = [
    "법", "법률", "법령", "조항", "조문", "제조", "항", "호",
    "소비자보호법", "전자상거래법", "약관규제법", "할부거래법",
    "방문판매법", "표시광고법", "제조물책임법",
]

# 분쟁조정기준 관련 키워드 (공정위 고시 검색 트리거)
CRITERIA_KEYWORDS: List[str] = [
    "기준", "분쟁조정기준", "별표", "해제", "해지", "위약금",
    "환불", "보상", "배상", "수리", "교환", "반품",
]

# 시스템/봇 관련 질문 키워드 (검색 불필요 -> RAG Skip) - 소문자로 통일
SYSTEM_META_KEYWORDS: List[str] = [
    "모델명", "모델 이름", "어떤 모델", "버전",
    "네 이름", "니 이름", "너 이름", "만든 사람", "개발자", "누가 만들",
    "네가 뭐야", "니가 뭐야", "너 뭐야", "뭐하는 봇", "뭐하는 ai",
    "어떤 ai", "어떤 봇", "기능", "할 수 있", "할수있", "사용법", "사용 방법",
    "gpt", "chatgpt", "클로드", "claude", "gemini", "제미나이",
    "exaone", "llm", "언어모델", "챗봇", "ai야", "ai인지",
]

# 시스템/봇 관련 질문 패턴 (정규식)
SYSTEM_META_PATTERNS: List[str] = [
    r"(네가?|니가?|당신|너|넌)\s*(누구|뭐|무엇)",
    r"(무슨|어떤|뭔)\s*(모델|AI|봇|챗봇)",
    r"모델\s*이?름|모델명",
    r"(네|니|당신)\s*(정체|이름)",
    r"(소개|자기소개)\s*(해|좀)",
]


# ============================================================
# Dispute Fields
# ============================================================

# 분쟁 상담 필수 정보 필드 (dispute 타입일 때 정보 누락 확인용)
REQUIRED_DISPUTE_FIELDS: List[str] = [
    "purchase_item",  # 구매 품목 (필수)
    "dispute_details",  # 분쟁 상세 내용 (필수)
]

# 분쟁 상담 권장 정보 필드
RECOMMENDED_DISPUTE_FIELDS: List[str] = [
    "purchase_date",  # 구매일자
    "purchase_place",  # 구매처
    "purchase_amount",  # 구매 금액
]

# 필드별 한국어 이름 매핑 (사용자에게 되물을 때 사용)
FIELD_KOREAN_NAMES: Dict[str, str] = {
    "purchase_item": "구매 품목",
    "dispute_details": "분쟁 상세 내용",
    "purchase_date": "구매일자",
    "purchase_place": "구매처",
    "purchase_platform": "플랫폼",
    "purchase_amount": "구매금액",
}


# ============================================================
# Product & Verb Definitions
# ============================================================

# 흔한 구매 품목 리스트 (엔티티 추출 보완용)
COMMON_PRODUCTS: List[str] = [
    "노트북", "컴퓨터", "PC", "스마트폰", "휴대폰", "핸드폰", "아이폰", "갤럭시",
    "태블릿", "아이패드", "에어팟", "이어폰", "헤드폰", "스피커", "TV", "텔레비전",
    "냉장고", "세탁기", "에어컨", "청소기", "전자레인지", "오븐", "건조기",
    "모니터", "키보드", "마우스", "프린터", "카메라", "렌즈", "드론",
    "로봇청소기", "공기청정기", "제습기", "가습기", "전기밥솥", "믹서기", "커피머신",
    "침대", "소파", "책상", "의자", "옷장", "매트리스", "가구",
    "헬스장", "PT", "피티", "수영장", "필라테스", "요가", "학원", "영어",
    "웨딩", "결혼", "스튜디오", "여행", "항공권", "호텔", "숙박",
    "옷", "신발", "가방", "지갑", "시계", "악세서리",
    "자동차", "차량", "중고차", "오토바이", "자전거", "킥보드", "전동킥보드",
]

# 분쟁 관련 주요 동사
DISPUTE_VERBS: List[str] = [
    "환불", "반품", "교환", "수리", "취소", "해지", "해약",
    "피해", "하자", "불량", "고장", "파손", "분쟁", "보상", "배상", "위약금",
]

# 동의어 사전 (구어체 -> 표준어 매핑 및 검색어 확장용)
VERB_SYNONYMS: Dict[str, List[str]] = {
    "환불": [
        "환불", "반환", "취소", "청약철회", "돈 돌려받기", "환급", "반품", "결제 취소", "환불받기",
    ],
    "교환": ["교환", "대체", "바꿈", "다른 제품으로", "교체", "변경", "바꿔줘"],
    "수리": [
        "수리", "고침", "AS", "애프터서비스", "보수", "고장", "수선", "무상수리", "유상수리", "고쳐줘",
    ],
    "해지": ["해지", "해약", "중도해지", "계약해지", "취소", "탈퇴", "그만두기"],
    "보상": ["보상", "배상", "물어내", "변상", "보상받기", "배상받기"],
}


# ============================================================
# Query Expansion Templates
# ============================================================

# 쿼리 확장 템플릿 (HyDE와 유사하지만 규칙 기반)
QUERY_EXPANSION_TEMPLATES: Dict[str, str] = {
    "dispute": "{item} {verb} 분쟁조정 피해구제 소비자",
    "law": "{query} 소비자보호법 전자상거래법 관련 조항",
    "criteria": "{item} 분쟁해결기준 교환 환불 수리 기간",
}


# ============================================================
# Fast Path & Ambiguity Detection
# ============================================================

# Fast Path (Review Skip) 승격 키워드
FAST_PATH_PROMOTION_KEYWORDS: List[str] = [
    "위법", "불법", "합법", "소송", "고소", "고발", "청약철회", "환불기간",
    "보증기간", "제척기간", "소멸시효", "손해배상", "위약금", "분쟁조정",
    "피해구제", "법원", "판결", "판례", "조정위원회",
]

# Layer 1: 명시적 패턴 (빠른 매칭) - 모호한 쿼리 패턴
AMBIGUOUS_QUERY_PATTERNS: List[str] = [
    r"^(요약|정리|알려줘|알려주세요|도와줘|도와주세요)$",  # 단독 모호 동사
    r"^(이거|저거|그거)\s*(어떻게|뭐야|뭐예요|어떡해)\??$",  # 지시대명사+질문
    r"^(뭐|뭘|어떻게|어떡해|무엇|무엇을)\s*해?\??$",  # 단일 질문어
    r"^.{1,2}$",  # 매우 짧은 쿼리 (1-2자)
]

# Layer 2: 의도 명확 키워드 (있으면 NOT ambiguous)
DISPUTE_INTENT_KEYWORDS: List[str] = [
    "환불", "반품", "교환", "수리", "취소", "해지", "해약",
    "피해", "하자", "불량", "고장", "파손", "사기", "배송", "지연",
    "미배송", "오배송", "누락", "계약", "위약금", "보상", "배상",
    "청약철회", "카드", "결제", "청구", "문의", "상담",
]


# ============================================================
# General Conversation Patterns
# ============================================================

# 일반 대화 패턴 (인사, 감사 등)
GENERAL_PATTERNS: List[str] = [
    r"^안녕", r"^반갑", r"^감사", r"^고마", r"^네$", r"^예$",
    r"^알겠", r"^네\s*알겠", r"^네,?\s*알겠", r"^ㅋ+$", r"^ㅎ+$", r"^ㅇㅇ$",
    r"^ㅎㅇ$", r"^ㅎ2$", r"^ㅎㅇ\s*ㅎㅇ$",  # 인사말 약어
    r"^오케이", r"^ok", r"^hello", r"^hi$", r"^하이$", r"^bye", r"^thanks",
]

# 정의형 질문 패턴 ("환불이 뭐예요?" 같은)
DEFINITIONAL_PATTERNS: List[str] = [
    r"(이|가|는|란)\s*(뭐예요|뭐야|무엇|무슨|어떤)\??",
    r"(이|가)\s*뭔가요\??",
    r"(이|가|는)\s*무엇인가요\??",
    r"(은|는)\s*어떻게\s+되나요\??",
]

# 절차 질문 패턴
PROCEDURE_PATTERNS: List[str] = [
    r"어떻게\s*(신청|접수|신고)",
    r"(신청|접수|신고)\s*방법",
    r"(절차|과정).*알려",
    r"뭐\s*필요해",
    r"서류.*뭐",
    r"기간.*얼마나",
]


# ============================================================
# Meta-Conversational Patterns (대화형 안내 쿼리)
# "뭘 물어봐야 할까?", "도와줘", "어떻게 시작해?" 등
# RAG 없이 가이드 응답을 생성해야 하는 메타 쿼리 패턴
# ============================================================
META_CONVERSATIONAL_PATTERNS: List[str] = [
    r"(뭘|무엇을?|어떤\s*걸?)\s*(물어|질문|문의)",
    r"(도와|도움)\s*(줘|주세요|줄래|필요)",
    r"(어떻게|뭐부터)\s*(시작|해야|하면)",
    r"(알려|가르쳐)\s*(줘|주세요)",
    r"^(안내|설명|소개)\s*(해|좀|부탁)",
    r"(뭘|무엇을?|어떤)\s*(알아야|준비|필요)",
    r"(상담|문의)\s*(하고\s*싶|받고\s*싶|하려)",
]

META_CONVERSATIONAL_KEYWORDS: List[str] = [
    # 주의: system_meta(SYSTEM_META_KEYWORDS)가 우선 체크됨.
    # "사용법"은 system_meta에도 있으므로 여기에 포함하지 않음.
    "뭘 물어봐야", "무엇을 물어", "어떤 걸 물어",
    "도와줘", "도와주세요", "도움이 필요",
    "어떻게 시작", "뭐부터 해야", "뭐부터 하면",
    "어떻게 이용", "이용법",
    "상담하고 싶", "문의하고 싶", "문의하려",
]


__all__ = [
    # Feature Flags
    "ENABLE_FAST_PATH_PROMOTION",
    "ENABLE_AMBIGUOUS_DETECTION",
    "LLM_AMBIGUITY_CHECK_MAX_LENGTH",
    # Retriever Mapping
    "QUERY_TYPE_TO_RETRIEVERS",
    # Restricted Domain
    "RESTRICTED_DOMAIN_KEYWORDS",
    "RESTRICTED_DOMAIN_AGENCIES",
    # Keywords
    "PROCEDURE_KEYWORDS",
    "INDIVIDUAL_KEYWORDS",
    "LAW_KEYWORDS",
    "CRITERIA_KEYWORDS",
    "SYSTEM_META_KEYWORDS",
    "SYSTEM_META_PATTERNS",
    # Dispute Fields
    "REQUIRED_DISPUTE_FIELDS",
    "RECOMMENDED_DISPUTE_FIELDS",
    "FIELD_KOREAN_NAMES",
    # Products & Verbs
    "COMMON_PRODUCTS",
    "DISPUTE_VERBS",
    "VERB_SYNONYMS",
    # Query Expansion
    "QUERY_EXPANSION_TEMPLATES",
    # Fast Path & Ambiguity
    "FAST_PATH_PROMOTION_KEYWORDS",
    "AMBIGUOUS_QUERY_PATTERNS",
    "DISPUTE_INTENT_KEYWORDS",
    # Patterns
    "GENERAL_PATTERNS",
    "DEFINITIONAL_PATTERNS",
    "PROCEDURE_PATTERNS",
    # Meta-Conversational
    "META_CONVERSATIONAL_PATTERNS",
    "META_CONVERSATIONAL_KEYWORDS",
]
