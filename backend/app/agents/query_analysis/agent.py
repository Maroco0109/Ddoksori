"""
똑소리 프로젝트 - 질의분석 노드 (Query Analysis Node)

작성일: 2026-01-14
최종 수정: 2026-01-28 (PR#2 Intent Classifier 고도화)

[역할 및 책임]
사용자의 자연어 질문을 분석하여 시스템이 처리 가능한 구조화된 데이터로 변환합니다.
RAG 검색이 필요한지, 어떤 정보를 검색해야 하는지, 혹은 사용자에게 되물어야 하는지를 결정합니다.

[State Flow]
Input State:
    - user_query (str): 사용자의 최신 발화
    - chat_type (str): 이전 턴까지의 대화 유형 (default: general)
    - onboarding (OnboardingInfo): 사용자 초기 입력 정보 (선택)

Output State:
    - query_analysis (QueryAnalysisResult): 분석 결과 (v1 호환)
    - mode (RoutingMode): 라우팅 모드
    - mode (RoutingMode): 다음 단계 라우팅 결정 (NEED_RAG, NO_RETRIEVAL, NEED_USER_CLARIFICATION, RESTRICTED_DOMAIN)

[주요 로직]
1. 정규화: 불필요한 어미, 특수문자 제거
2. 유형 분류: Hybrid (Rule-based Fast Path + LLM Function Calling)
   - dispute: 분쟁 상담 (환불, 교환 등)
   - law: 법령 문의
   - criteria: 분쟁조정기준 문의
   - procedure: 분쟁조정 신청 절차 안내
   - restricted: 전문기관 도메인 (금융, 의료, 개인정보, 부동산, 건설)
   - general: 일반 대화
   - system_meta: 봇 정체성 질문
   - ambiguous: 의도 불명확 (되묻기 필요)
3. 키워드 추출: 검색 효율을 위한 불용어 제거 및 동의어 정규화
4. 쿼리 확장: HyDE, LLM Rewrite 등을 통한 검색 쿼리 다변화
"""

import logging
import os
import re
from typing import Dict, List, Literal, Optional, Any

from ...supervisor.state import (
    ChatState,
    QueryAnalysisResult,
    OnboardingInfo,
    RoutingMode,
)

logger = logging.getLogger(__name__)

# OpenAI import for fallback
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


# ============================================================
# === PR-2: Selective Retrieval 시작 ===
# 검색 우선순위: 법령 → 기준 → 사례
# ============================================================
QUERY_TYPE_TO_RETRIEVERS = {
    "law": ["law"],                                  # 법령만
    "criteria": ["law", "criteria"],                 # 법령 + 기준 (기준은 법령의 구체화)
    "dispute": ["law", "criteria", "case", "counsel"],  # P2.2: counsel 추가 (13,544 cases)
    "procedure": ["law", "criteria"],                # 절차 안내: 법령 + 기준 (템플릿 + RAG 보강)
    "restricted": ["case"],                          # 전문기관 도메인: 유사 사례만 검색
    "general": [],                                   # 검색 불필요
    "system_meta": [],                               # 검색 불필요
    "ambiguous": ["law", "criteria"],                # 법령 + 기준 (사례는 나중에)
}
# === PR-2: Selective Retrieval 끝 ===


# ============================================================
# [Keyword & Pattern Definitions]
# 규칙 기반 분류(Rule-based Classification)를 위한 키워드 및 패턴 정의입니다.
# 빠른 응답 속도와 예측 가능한 동작을 위해 1차적으로 사용됩니다.
# ============================================================

# ============================================================
# === Restricted Domain Keywords (전문기관 도메인) ===
# KCA/ECMC 관할 외 전문분쟁조정기관 안내 필요
# ============================================================
RESTRICTED_DOMAIN_KEYWORDS = {
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
RESTRICTED_DOMAIN_AGENCIES = {
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

# 절차 안내 키워드 (Procedure)
PROCEDURE_KEYWORDS = [
    "신청 방법", "신청방법", "접수", "분쟁조정 신청", "분쟁조정신청",
    "어떻게 신청", "절차", "서류", "기간", "분쟁해결 절차", "조정신청",
    "피해구제 신청", "신고", "신고방법", "제출서류", "필요서류",
    "온라인 신청", "방문 신청", "조정 절차", "구비서류",
]

# 개인간 거래 키워드 (ECMC - 전자문서·전자거래분쟁조정위원회 관할)
INDIVIDUAL_KEYWORDS = [
    "중고",
    "직거래",
    "당근",
    "당근마켓",
    "번개장터",
    "중고나라",
    "개인간",
    "개인거래",
    "개인 판매",
    "개인판매자",
    "직접 거래",
    "직접거래",
    "만나서",
    "택배거래",
    "중고거래",
    "중고 거래",
    "세컨핸드",
    "second hand",
]

# 법령 관련 키워드 (법률 DB 검색 트리거)
LAW_KEYWORDS = [
    "법",
    "법률",
    "법령",
    "조항",
    "조문",
    "제조",
    "항",
    "호",
    "소비자보호법",
    "전자상거래법",
    "약관규제법",
    "할부거래법",
    "방문판매법",
    "표시광고법",
    "제조물책임법",
]

# 분쟁조정기준 관련 키워드 (공정위 고시 검색 트리거)
CRITERIA_KEYWORDS = [
    "기준",
    "분쟁조정기준",
    "별표",
    "해제",
    "해지",
    "위약금",
    "환불",
    "보상",
    "배상",
    "수리",
    "교환",
    "반품",
]

# Phase 4: 시스템/봇 관련 질문 키워드 (검색 불필요 -> RAG Skip) - 소문자로 통일
SYSTEM_META_KEYWORDS = [
    "모델명",
    "모델 이름",
    "어떤 모델",
    "버전",
    "네 이름",
    "니 이름",
    "너 이름",
    "만든 사람",
    "개발자",
    "누가 만들",
    "네가 뭐야",
    "니가 뭐야",
    "너 뭐야",
    "뭐하는 봇",
    "뭐하는 ai",
    "어떤 ai",
    "어떤 봇",
    "기능",
    "할 수 있",
    "할수있",
    "사용법",
    "사용 방법",
    "gpt",
    "chatgpt",
    "클로드",
    "claude",
    "gemini",
    "제미나이",
    "exaone",
    "llm",
    "언어모델",
    "챗봇",
    "ai야",
    "ai인지",
]

# 시스템/봇 관련 질문 패턴 (정규식)
SYSTEM_META_PATTERNS = [
    r"(네가?|니가?|당신|너|넌)\s*(누구|뭐|무엇)",
    r"(무슨|어떤|뭔)\s*(모델|AI|봇|챗봇)",
    r"모델\s*이?름|모델명",
    r"(네|니|당신)\s*(정체|이름)",
    r"(소개|자기소개)\s*(해|좀)",
]

# 분쟁 상담 필수 정보 필드 (dispute 타입일 때 정보 누락 확인용)
REQUIRED_DISPUTE_FIELDS = [
    "purchase_item",  # 구매 품목 (필수)
    "dispute_details",  # 분쟁 상세 내용 (필수)
]

# 분쟁 상담 권장 정보 필드
RECOMMENDED_DISPUTE_FIELDS = [
    "purchase_date",  # 구매일자
    "purchase_place",  # 구매처
    "purchase_amount",  # 구매 금액
]

# 필드별 한국어 이름 매핑 (사용자에게 되물을 때 사용)
FIELD_KOREAN_NAMES = {
    "purchase_item": "구매 품목",
    "dispute_details": "분쟁 상세 내용",
    "purchase_date": "구매일자",
    "purchase_place": "구매처",
    "purchase_platform": "플랫폼",
    "purchase_amount": "구매금액",
}

# 흔한 구매 품목 리스트 (엔티티 추출 보완용)
COMMON_PRODUCTS = [
    "노트북",
    "컴퓨터",
    "PC",
    "스마트폰",
    "휴대폰",
    "핸드폰",
    "아이폰",
    "갤럭시",
    "태블릿",
    "아이패드",
    "에어팟",
    "이어폰",
    "헤드폰",
    "스피커",
    "TV",
    "텔레비전",
    "냉장고",
    "세탁기",
    "에어컨",
    "청소기",
    "전자레인지",
    "오븐",
    "건조기",
    "모니터",
    "키보드",
    "마우스",
    "프린터",
    "카메라",
    "렌즈",
    "드론",
    "로봇청소기",
    "공기청정기",
    "제습기",
    "가습기",
    "전기밥솥",
    "믹서기",
    "커피머신",
    "침대",
    "소파",
    "책상",
    "의자",
    "옷장",
    "매트리스",
    "가구",
    "헬스장",
    "PT",
    "피티",
    "수영장",
    "필라테스",
    "요가",
    "학원",
    "영어",
    "웨딩",
    "결혼",
    "스튜디오",
    "여행",
    "항공권",
    "호텔",
    "숙박",
    "옷",
    "신발",
    "가방",
    "지갑",
    "시계",
    "악세서리",
    "자동차",
    "차량",
    "중고차",
    "오토바이",
    "자전거",
    "킥보드",
    "전동킥보드",
]

# 분쟁 관련 주요 동사
DISPUTE_VERBS = [
    "환불",
    "반품",
    "교환",
    "수리",
    "취소",
    "해지",
    "해약",
    "피해",
    "하자",
    "불량",
    "고장",
    "파손",
    "분쟁",
    "보상",
    "배상",
    "위약금",
]

# 쿼리 확장 템플릿 (HyDE와 유사하지만 규칙 기반)
QUERY_EXPANSION_TEMPLATES = {
    "dispute": "{item} {verb} 분쟁조정 피해구제 소비자",
    "law": "{query} 소비자보호법 전자상거래법 관련 조항",
    "criteria": "{item} 분쟁해결기준 교환 환불 수리 기간",
}

# 동의어 사전 (구어체 -> 표준어 매핑 및 검색어 확장용)
VERB_SYNONYMS = {
    "환불": [
        "환불",
        "반환",
        "취소",
        "청약철회",
        "돈 돌려받기",
        "환급",
        "반품",
        "결제 취소",
        "환불받기",
    ],
    "교환": ["교환", "대체", "바꿈", "다른 제품으로", "교체", "변경", "바꿔줘"],
    "수리": [
        "수리",
        "고침",
        "AS",
        "애프터서비스",
        "보수",
        "고장",
        "수선",
        "무상수리",
        "유상수리",
        "고쳐줘",
    ],
    "해지": ["해지", "해약", "중도해지", "계약해지", "취소", "탈퇴", "그만두기"],
    "보상": ["보상", "배상", "물어내", "변상", "보상받기", "배상받기"],
}

# Fast Path (Review Skip) 승격 키워드
# 일반 대화로 분류되었더라도 이 키워드가 있으면 '법적/분쟁' 성격이 강하므로 RAG를 수행합니다.
FAST_PATH_PROMOTION_KEYWORDS = [
    "위법",
    "불법",
    "합법",
    "소송",
    "고소",
    "고발",
    "청약철회",
    "환불기간",
    "보증기간",
    "제척기간",
    "소멸시효",
    "손해배상",
    "위약금",
    "분쟁조정",
    "피해구제",
    "법원",
    "판결",
    "판례",
    "조정위원회",
]

ENABLE_FAST_PATH_PROMOTION = (
    os.getenv("ENABLE_FAST_PATH_PROMOTION", "true").lower() == "true"
)

# ============================================================
# Phase: Hybrid Ambiguous Query Detection (Pattern + LLM Fallback)
# ============================================================

# Feature Flag for ambiguous detection
ENABLE_AMBIGUOUS_DETECTION = (
    os.getenv("ENABLE_AMBIGUOUS_DETECTION", "true").lower() == "true"
)

# Layer 1: 명시적 패턴 (빠른 매칭) - 모호한 쿼리 패턴
AMBIGUOUS_QUERY_PATTERNS = [
    r"^(요약|정리|알려줘|알려주세요|도와줘|도와주세요)$",  # 단독 모호 동사
    r"^(이거|저거|그거)\s*(어떻게|뭐야|뭐예요|어떡해)\??$",  # 지시대명사+질문
    r"^(뭐|뭘|어떻게|어떡해|무엇|무엇을)\s*해?\??$",  # 단일 질문어
    r"^.{1,2}$",  # 매우 짧은 쿼리 (1-2자)
]

# Layer 2: 의도 명확 키워드 (있으면 NOT ambiguous)
DISPUTE_INTENT_KEYWORDS = [
    "환불",
    "반품",
    "교환",
    "수리",
    "취소",
    "해지",
    "해약",
    "피해",
    "하자",
    "불량",
    "고장",
    "파손",
    "사기",
    "배송",
    "지연",
    "미배송",
    "오배송",
    "누락",
    "계약",
    "위약금",
    "보상",
    "배상",
    "청약철회",
    "카드",
    "결제",
    "청구",
    "문의",
    "상담",
]

# Layer 3: LLM fallback 트리거 조건 (짧지만 패턴에 안 걸린 경우)
LLM_AMBIGUITY_CHECK_MAX_LENGTH = 30  # 30자 이하면 LLM 판단 요청


def _should_promote_to_rag(query: str) -> bool:
    """일반 대화(General)로 분류되었지만, RAG 검색이 필요한지 확인합니다."""
    if not ENABLE_FAST_PATH_PROMOTION:
        return False
    query_lower = query.lower()
    return any(kw in query_lower for kw in FAST_PATH_PROMOTION_KEYWORDS)


def _check_ambiguity_with_llm(query: str) -> bool:
    """
    LLM을 사용해 쿼리가 모호한지 판단 (Layer 3 fallback)

    규칙 기반으로 판단하기 어려운 짧은 쿼리에 대해 LLM의 상식을 활용합니다.
    비용 절감을 위해 모든 쿼리에 사용하지 않고, Layer 1, 2를 통과한 경우에만 호출합니다.

    Fallback 체인:
    1. EXAONE (Primary) - 도메인 특화 모델
    2. gpt-4o-mini Function Calling (Fallback) - 구조화된 분류

    Args:
        query: 사용자 쿼리

    Returns:
        True if query is ambiguous and needs clarification
    """
    system_prompt = "당신은 소비자 분쟁 상담 시스템의 쿼리 분류기입니다. 사용자 질문이 구체적인지 모호한지 판단하세요."
    user_prompt = f"""사용자 질문: "{query}"
판단 기준:
- 구체적: 제품/서비스 종류, 문제 상황(환불/교환/배송 등)이 명확함
- 모호함: 무엇을 원하는지 불명확, 맥락 없는 단순 요청

응답: "구체적" 또는 "모호함" 중 하나만 출력하세요."""

    # 1. EXAONE 시도 (Primary)
    try:
        from app.llm.exaone_client import ExaoneLLMClient, LLMUnavailableError

        client = ExaoneLLMClient()
        if client.is_available():
            response = client.generate(system_prompt, user_prompt)
            is_ambiguous = "모호" in response.lower()
            logger.info(
                f"[QueryAnalysis] EXAONE ambiguity check: '{query[:20]}...' -> {response.strip()} (ambiguous={is_ambiguous})"
            )
            return is_ambiguous
        else:
            logger.info("[QueryAnalysis] EXAONE not available, trying fallback...")
    except Exception as e:
        logger.warning(f"[QueryAnalysis] EXAONE ambiguity check failed: {e}, trying fallback...")

    # 2. gpt-4o-mini Function Calling Fallback (PR-2 IntentClassifier 통합)
    try:
        from .classifier import IntentClassifier

        classifier = IntentClassifier(model="gpt-4o-mini", timeout=3.0)
        result = classifier.classify(query)

        # ambiguous로 분류되었거나 confidence가 낮으면 모호한 것으로 판단
        is_ambiguous = result.query_type == "ambiguous" or result.confidence < 0.8
        logger.info(
            f"[QueryAnalysis] gpt-4o-mini intent check: '{query[:20]}...' -> "
            f"type={result.query_type}, conf={result.confidence:.2f} (ambiguous={is_ambiguous})"
        )
        return is_ambiguous

    except ImportError:
        logger.warning("[QueryAnalysis] IntentClassifier import failed, using legacy fallback")
    except Exception as e:
        logger.warning(f"[QueryAnalysis] IntentClassifier failed: {e}, using legacy fallback...")

    # 3. Legacy fallback (텍스트 기반)
    try:
        from openai import OpenAI

        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.warning("[QueryAnalysis] OpenAI API key not found, skipping LLM check")
            return False

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            max_tokens=20
        )

        result = response.choices[0].message.content.strip()
        is_ambiguous = "모호" in result.lower()
        logger.info(
            f"[QueryAnalysis] gpt-4o-mini ambiguity check: '{query[:20]}...' -> {result} (ambiguous={is_ambiguous})"
        )
        return is_ambiguous

    except Exception as e:
        logger.warning(f"[QueryAnalysis] gpt-4o-mini fallback failed: {e}")
        return False  # 모든 LLM 실패 시 보수적으로 RAG 진행


def _is_ambiguous_query(query: str) -> bool:
    """
    하이브리드 방식으로 모호한 쿼리 탐지

    사용자가 "그냥 도와줘" 처럼 맥락 없는 질문을 했을 때,
    무리하게 검색하지 않고 "어떤 도움이 필요하신가요?"라고 되물어보기 위함입니다.

    Layer 0: Intent 키워드/제품명 체크 (있으면 즉시 NOT ambiguous)
    Layer 1: Pattern 매칭 (명시적 모호 패턴)
    Layer 2: LLM fallback (짧은 쿼리, 의도 불명확)

    Args:
        query: 사용자 쿼리

    Returns:
        True if query is ambiguous and needs pre-clarification
    """
    if not ENABLE_AMBIGUOUS_DETECTION:
        return False

    query_stripped = query.strip()
    query_lower = query_stripped.lower()

    # Layer 0: 의도 키워드 있으면 → 즉시 NOT ambiguous (최우선 체크)
    has_intent = any(kw in query_lower for kw in DISPUTE_INTENT_KEYWORDS)
    if has_intent:
        return False

    # Layer 0.5: 제품명 있으면 → NOT ambiguous (제품 + 문제없음도 일단 RAG 시도)
    has_product = any(p.lower() in query_lower for p in COMMON_PRODUCTS)
    if has_product:
        return False

    # Layer 0.6: 법령명 패턴 있으면 → NOT ambiguous (예: "소비자기본법", "전자상거래법")
    law_pattern_match = re.search(r'\S+법', query_lower)
    logger.info(f"[DEBUG Line 566] query_lower='{query_lower}', law_pattern_match={law_pattern_match}")
    if law_pattern_match:
        return False

    # Layer 0.7: 법령/기준 관련 키워드 있으면 → NOT ambiguous
    has_law_keywords = any(kw in query_lower for kw in LAW_KEYWORDS)
    has_criteria_keywords = any(kw in query_lower for kw in CRITERIA_KEYWORDS)
    if has_law_keywords or has_criteria_keywords:
        return False

    # Layer 1: 명시적 패턴 매칭 (의도/제품 없는 경우에만)
    for pattern in AMBIGUOUS_QUERY_PATTERNS:
        if re.search(pattern, query_stripped, re.IGNORECASE):
            logger.info(f"[QueryAnalysis] Ambiguous by pattern: '{query[:20]}'")
            return True

    # Layer 2: 짧은 쿼리인데 의도 불명확 → LLM 판단
    if len(query_stripped) <= LLM_AMBIGUITY_CHECK_MAX_LENGTH:
        is_ambiguous = _check_ambiguity_with_llm(query)
        if is_ambiguous:
            logger.info(f"[QueryAnalysis] Ambiguous by LLM: '{query[:20]}'")
        return is_ambiguous

    return False


def _classify_mode(
    query_type: Literal[
        "dispute", "general", "law", "criteria", "procedure", "restricted", "system_meta", "ambiguous"
    ],
    needs_clarification: bool,
    query: str,
) -> RoutingMode:
    """
    분석된 정보를 바탕으로 오케스트레이터의 라우팅 경로를 결정합니다.

    - NO_RETRIEVAL: 검색 없이 바로 답변 (일반 대화, 시스템 질문)
    - NEED_USER_CLARIFICATION: 정보가 부족하거나 모호해서 사용자에게 되물어야 함
    - NEED_RAG: 정보 검색이 필요함
    - RESTRICTED_DOMAIN: 전문기관 도메인 (유사 사례 검색 + 전문기관 안내)
    """
    # Phase 4: 시스템 관련 질문은 검색 불필요
    if query_type == "system_meta":
        logger.info("[QueryAnalysis] System meta query detected, skipping retrieval")
        return "NO_RETRIEVAL"

    # NEW: 모호한 쿼리는 사전 명확화 필요
    if query_type == "ambiguous":
        logger.info(
            "[QueryAnalysis] Ambiguous query detected, requesting pre-clarification"
        )
        return "NEED_USER_CLARIFICATION"

    if query_type == "general":
        # 일반 대화라도 특정 키워드(소송, 환불기간 등)가 있으면 검색 수행
        if _should_promote_to_rag(query):
            logger.info(
                "[QueryAnalysis] Fast Path promotion triggered for general query"
            )
            return "NEED_RAG"
        return "NO_RETRIEVAL"

    # NEW: Restricted 도메인은 전문기관 안내 + 유사 사례 검색
    if query_type == "restricted":
        logger.info("[QueryAnalysis] Restricted domain detected, routing to specialist agency guidance")
        return "RESTRICTED_DOMAIN"

    if needs_clarification:
        return "NEED_USER_CLARIFICATION"

    # procedure, law, criteria, dispute 모두 RAG 필요
    return "NEED_RAG"


def _extract_info_from_message(query: str) -> Dict[str, str]:
    """
    메시지 내용에서 정규식(Regex)을 사용하여 온보딩 정보를 추출합니다.
    사용자가 "아이폰15 환불 관련 문의입니다"라고 했을 때 'purchase_item': '아이폰15'를 추출하기 위함입니다.
    """
    info: Dict[str, str] = {}

    patterns = {
        "purchase_item": [
            r"구매\s*품목[:\s]+([^\n,]+)",
            r"품목[:\s]+([^\n,]+)",
            r"제품[:\s]+([^\n,]+)",
        ],
        "dispute_details": [
            r"분쟁\s*상세[:\s]+([^\n]+)",
            r"문제[:\s]+([^\n]+)",
            r"상황[:\s]+([^\n]+)",
        ],
        "purchase_date": [
            r"구매\s*일자[:\s]+([^\n,]+)",
            r"구매일[:\s]+([^\n,]+)",
        ],
        "purchase_place": [
            r"구매처[:\s]+([^\n,]+)",
            r"판매처[:\s]+([^\n,]+)",
        ],
        "purchase_platform": [
            r"플랫폼[:\s]+([^\n,]+)",
        ],
        "purchase_amount": [
            r"구매\s*금액[:\s]+([^\n,]+)",
            r"금액[:\s]+([^\n,]+)",
            r"(\d{1,}(?:만\s*)?원(?:에|에서|을|를)?)",
        ],
    }

    for field, field_patterns in patterns.items():
        for pattern in field_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if value and value not in ["없음", "모름", "-"]:
                    info[field] = value
                break

    # 패턴 매칭에 실패했다면, 일반 명사 리스트(COMMON_PRODUCTS)에서 검색
    if "purchase_item" not in info:
        query_lower = query.lower()
        for product in COMMON_PRODUCTS:
            if product.lower() in query_lower:
                info["purchase_item"] = product
                break

    # 분쟁 동사가 있고 품목이 식별되었다면, 분쟁 상세 내용을 자동으로 구성
    if "dispute_details" not in info:
        found_verbs = [v for v in DISPUTE_VERBS if v in query]
        if found_verbs and "purchase_item" in info:
            verb = found_verbs[0]
            item = info["purchase_item"]
            info["dispute_details"] = f"{item} {verb} 관련 문의"
    
    # 금액 정규화: "150만원" → "1500000"
    if "purchase_amount" in info:
        amount_str = info["purchase_amount"]
        if "만" in amount_str:
            base_match = re.search(r'(\d+(?:\.\d+)?)', amount_str)
            if base_match:
                amount = int(float(base_match.group(1)) * 10000)
                info["purchase_amount"] = str(amount)

    return info


def _get_missing_fields_description(
    missing_fields: List[str], extracted_info: Dict[str, str]
) -> str:
    """
    부족한 정보에 대한 구체적인 설명 문자열을 생성합니다.
    LLM이 사용자에게 되물을 때 Context로 제공됩니다.
    """
    lines = []

    if extracted_info:
        lines.append("**입력하신 정보:**")
        for field, value in extracted_info.items():
            korean_name = FIELD_KOREAN_NAMES.get(field, field)
            lines.append(f"  • {korean_name}: {value}")
        lines.append("")

    if missing_fields:
        lines.append("**추가로 필요한 정보:**")
        for field in missing_fields:
            korean_name = FIELD_KOREAN_NAMES.get(field, field)
            lines.append(f"  • {korean_name}")

    return "\n".join(lines)


def _is_system_meta_query(query: str) -> bool:
    """
    시스템/봇 관련 질문인지 확인 (Phase 4)
    예: "네 모델명이 뭐야?", "니가 뭔데?", "어떤 AI야?"

    이런 질문은 RAG 검색 없이 미리 정의된 시스템 프롬프트로 답변하는 것이 효율적입니다.
    """
    query_lower = query.lower()

    # 키워드 기반 체크
    meta_keyword_count = sum(1 for kw in SYSTEM_META_KEYWORDS if kw in query_lower)
    if meta_keyword_count >= 1:
        return True

    # 패턴 기반 체크
    for pattern in SYSTEM_META_PATTERNS:
        if re.search(pattern, query_lower):
            return True

    return False


def _detect_restricted_domain(query: str) -> Optional[str]:
    """
    전문기관 도메인 감지

    KCA/ECMC 관할 외 전문분쟁조정기관으로 안내해야 하는 도메인인지 확인합니다.

    Returns:
        도메인 키 (finance, medical, privacy, realestate, construction) 또는 None
    """
    query_lower = query.lower()

    # 핵심 키워드 (1개만 있어도 해당 도메인으로 판단)
    core_keywords = {
        "finance": ["금융분쟁", "보험분쟁", "대출분쟁", "대출", "보험금", "보험료", "은행", "금융회사", "증권", "펀드"],
        "medical": ["의료사고", "의료분쟁", "의료과실", "진료", "수술", "병원", "의사", "오진"],
        "privacy": ["개인정보유출", "개인정보침해", "개인정보", "정보유출", "해킹"],
        "realestate": ["임대차분쟁", "전세분쟁", "보증금분쟁", "전세", "월세", "임대차", "보증금반환", "집주인"],
        "construction": ["건축분쟁", "시공분쟁", "하자분쟁", "시공불량", "시공", "건축", "아파트하자"],
    }

    # 우선순위: 핵심 키워드 먼저 체크
    for domain, keywords in core_keywords.items():
        if any(kw in query_lower for kw in keywords):
            logger.info(f"[QueryAnalysis] Restricted domain detected by core keyword: {domain}")
            return domain

    # 일반 키워드 2개 이상 매칭 체크
    for domain, keywords in RESTRICTED_DOMAIN_KEYWORDS.items():
        match_count = sum(1 for kw in keywords if kw in query_lower)
        if match_count >= 2:
            logger.info(f"[QueryAnalysis] Restricted domain detected: {domain} (matches: {match_count})")
            return domain

    return None


def _is_procedure_query(query: str) -> bool:
    """
    절차 안내 질문인지 확인

    분쟁조정 신청 절차, 서류, 기간 등에 대한 질문인지 판단합니다.
    """
    query_lower = query.lower()

    # 절차 키워드 매칭
    procedure_match = sum(1 for kw in PROCEDURE_KEYWORDS if kw in query_lower)
    if procedure_match >= 1:
        logger.info(f"[QueryAnalysis] Procedure query detected (matches: {procedure_match})")
        return True

    # 절차 질문 패턴
    procedure_patterns = [
        r"어떻게\s*(신청|접수|신고)",
        r"(신청|접수|신고)\s*방법",
        r"(절차|과정).*알려",
        r"뭐\s*필요해",
        r"서류.*뭐",
        r"기간.*얼마나",
    ]
    for pattern in procedure_patterns:
        if re.search(pattern, query_lower):
            return True

    return False


def _classify_query_type(
    query: str,
) -> Literal["dispute", "general", "law", "criteria", "procedure", "restricted", "system_meta", "ambiguous"]:
    """
    사용자의 질문을 8가지 유형 중 하나로 분류합니다.
    우선순위(Priority) 기반의 Rule-based 로직을 사용합니다.

    Priority:
    1. System Meta (시스템 질문) -> 검색 Skip
    2. General (인사/잡담) -> 검색 Skip
    3. Definitional (정의 질문) -> General로 분류
    4. Restricted (전문기관 도메인) -> 전문기관 안내 + 유사 사례 검색
    5. Procedure (절차 안내) -> 절차 템플릿 + RAG 보강
    6. Law (법령 질문) -> 관련 법령 검색
    7. Criteria (기준 질문) -> 고시/기준 검색
    8. Ambiguous (모호함) -> 사용자 확인 요청
    9. Dispute (분쟁 상담) -> Default (유사 사례 검색)

    Returns:
        분류된 질의 유형 문자열
    """
    query_lower = query.lower()

    # Phase 4: 시스템/봇 관련 질문 (검색 불필요)
    if _is_system_meta_query(query):
        return "system_meta"

    # 일반 대화 패턴 (인사, 감사 등)
    general_patterns = [
        r"^안녕",
        r"^반갑",
        r"^감사",
        r"^고마",
        r"^네$",
        r"^예$",
        r"^알겠",
        r"^네\s*알겠",
        r"^네,?\s*알겠",
        r"^ㅋ+$",
        r"^ㅎ+$",
        r"^ㅇㅇ$",
        r"^오케이",
        r"^ok",
        r"^hello",
        r"^hi$",
        r"^bye",
        r"^thanks",
    ]
    for pattern in general_patterns:
        if re.search(pattern, query_lower):
            return "general"

    # "환불이 뭐예요?" 같은 정의형 질문은 일반 대화로 처리
    definitional_patterns = [
        r"(이|가|는|란)\s*(뭐예요|뭐야|무엇|무슨|어떤)\??",
        r"(이|가)\s*뭔가요\??",
        r"(이|가|는)\s*무엇인가요\??",
        r"(은|는)\s*어떻게\s+되나요\??",
    ]
    for pattern in definitional_patterns:
        if re.search(pattern, query_lower):
            return "general"

    # NEW: Restricted 도메인 체크 (전문기관 안내 필요)
    # 금융, 의료, 개인정보, 부동산, 건설 분야는 전문기관 안내
    restricted_domain = _detect_restricted_domain(query)
    if restricted_domain:
        return "restricted"

    # NEW: Procedure 체크 (절차 안내 질문)
    if _is_procedure_query(query):
        return "procedure"

    # 법령 문의 (법령 키워드가 명시적으로 포함)
    # Pattern 1: 법률명 패턴 (예: "소비자기본법", "전자상거래법")
    law_pattern_match = re.search(r'\S+법', query_lower)
    if law_pattern_match:
        return "law"

    # Pattern 2: 키워드 카운트 (2개 이상) 또는 특정 패턴
    law_count = sum(1 for kw in LAW_KEYWORDS if kw in query_lower)
    if law_count >= 2 or any(
        kw in query_lower for kw in ["몇조", "법 조항", "법령 조회"]
    ):
        return "law"

    # 분쟁조정기준 문의
    criteria_count = sum(1 for kw in CRITERIA_KEYWORDS if kw in query_lower)
    if criteria_count >= 2 or "분쟁조정기준" in query_lower:
        return "criteria"

    # NEW: 하이브리드 ambiguous 체크 (dispute default 전에)
    if _is_ambiguous_query(query):
        return "ambiguous"

    # 기본값: 분쟁 상담
    return "dispute"


def _extract_keywords(query: str) -> List[str]:
    """
    검색 정확도 향상을 위해 핵심 키워드를 추출합니다.

    [로직]
    1. 불용어(Stopwords) 제거: 조사, 접속사 등 검색에 방해되는 단어 제외
    2. 동의어 정규화: "돈 돌려받고" -> "환불"과 같이 표준 용어로 변환 (PR 2 강화)
    3. 구어체 처리: 어간 추출 및 부분 매칭으로 다양한 표현 대응
    """
    stopwords = {
        "저",
        "제",
        "것",
        "수",
        "등",
        "더",
        "좀",
        "잘",
        "못",
        "안",
        "이",
        "그",
        "저",
        "때",
        "경우",
        "어떻게",
        "무엇",
        "어디",
        "왜",
        "알려",
        "주세요",
        "해주세요",
        "싶어요",
        "있나요",
        "있어요",
        "하고",
        "그리고",
        "그래서",
        "하지만",
        "그런데",
        "근데",
    }

    query_normalized = query.replace(" ", "")

    # 동의어 사전 기반 어간 매칭
    matched_base_verbs = set()
    for base_verb, synonyms in VERB_SYNONYMS.items():
        for synonym in synonyms:
            synonym_stem = synonym.replace(" ", "").rstrip("기").rstrip("줘")
            if len(synonym_stem) >= 3 and synonym_stem in query_normalized:
                matched_base_verbs.add(base_verb)
                break

    words = re.sub(r"[^\w\s]", " ", query).split()
    keywords = [w for w in words if len(w) >= 2 and w not in stopwords]

    normalized_keywords = list(matched_base_verbs)

    # 키워드별 동의어 매칭 확인
    for kw in keywords:
        matched = False
        for base_verb, synonyms in VERB_SYNONYMS.items():
            if kw in synonyms:
                normalized_keywords.append(base_verb)
                matched = True
                break
            for synonym in synonyms:
                if synonym in kw and len(synonym) >= 2:
                    normalized_keywords.append(base_verb)
                    matched = True
                    break
            if matched:
                break

        if not matched:
            normalized_keywords.append(kw)

    # 중복 제거
    seen = set()
    unique_keywords = []
    for kw in normalized_keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)

    return unique_keywords[:10]


def _determine_agency_hint(query: str) -> Optional[str]:
    """
    질의 내용을 바탕으로 적절한 분쟁조정 기관을 추측합니다.
    - ECMC: 전자거래/개인간 거래 키워드
    - KCA: 그 외 일반 소비자 분쟁 (Default)
    - None: restricted 도메인 (전문기관 안내 필요)

    Note: KCDRC(콘텐츠분쟁조정위원회) 분류는 Phase 9에서 제거됨.
          콘텐츠 분쟁도 KCA로 통합 처리.
    """
    query_lower = query.lower()

    # Restricted 도메인인 경우 agency_hint는 None
    restricted_domain = _detect_restricted_domain(query)
    if restricted_domain:
        return None

    # 전자거래/개인간 거래 → ECMC
    individual_matches = [kw for kw in INDIVIDUAL_KEYWORDS if kw in query_lower]
    if individual_matches:
        return "ECMC"

    # 기본값: KCA (한국소비자원)
    return "KCA"


def _normalize_query(query: str) -> str:
    """
    쿼리의 불필요한 접미사나 문장 부호를 제거합니다.
    "환불해주세요ㅠㅠ" -> "환불" 형태로 만들어 분석 정확도를 높입니다.
    """
    normalized = query.strip()

    suffix_patterns = [
        r"[~해주세요|알려주세요|싶어요|인가요|할까요|있나요|있어요|될까요]$",
        r"[?？!！。\.]+$",
    ]
    for pattern in suffix_patterns:
        normalized = re.sub(pattern, "", normalized)

    return normalized.strip()


def _expand_query_by_type(
    query: str,
    query_type: Literal[
        "dispute", "general", "law", "criteria", "procedure", "restricted", "system_meta", "ambiguous"
    ],
    onboarding: Optional[OnboardingInfo],
    extracted_info: Dict[str, str],
    keywords: List[str],
    use_llm: bool = True,
) -> tuple[str, str]:
    """
    질의 유형별 쿼리 확장 (Query Expansion)

    [전략]
    1. LLM Rewrite (S2-10): 복잡한 법률 용어가 포함된 쿼리는 EXAONE으로 일상어 변환
       - 100ms 타임아웃으로 지연시간 제약 보장
       - 타임아웃/에러 시 기존 규칙 기반 확장으로 폴백
    2. Rule-based Expansion (Phase 1):
       - dispute: {품목} {동사} 분쟁조정 피해구제 소비자
       - law: {쿼리} 관련 조항 조문
       - criteria: {품목} 분쟁해결기준 기간
       - procedure: {쿼리} 분쟁조정 신청 절차 서류
       - restricted: {쿼리} 분쟁 사례 (유사 사례 검색용)

    Returns:
        (확장된 쿼리, 적용된 확장 방식)
    """
    # Phase 4: 시스템 관련 질문은 확장 불필요
    if query_type == "system_meta":
        return query, "system_meta_no_expansion"

    if query_type == "general":
        return query, "general_no_expansion"

    # 모호한 쿼리는 확장 불필요 (clarification 먼저)
    if query_type == "ambiguous":
        return query, "ambiguous_no_expansion"

    # 기존 규칙 기반 확장 (Phase 1)
    item = extracted_info.get("purchase_item", "")
    if not item and onboarding:
        item = onboarding.get("purchase_item", "")

    found_verbs = [v for v in DISPUTE_VERBS if v in query]
    verb = found_verbs[0] if found_verbs else ""

    expanded_verbs = []
    if verb and verb in VERB_SYNONYMS:
        expanded_verbs = VERB_SYNONYMS[verb][:2]

    if query_type == "dispute":
        if item and verb:
            verb_str = " ".join(expanded_verbs) if expanded_verbs else verb
            expanded = f"{item} {verb_str} 분쟁조정 피해구제 소비자"
            return expanded, f"dispute_item_verb: {item}+{verb}"
        elif item:
            expanded = f"{item} 분쟁 환불 교환 수리 피해구제"
            return expanded, f"dispute_item_only: {item}"
        elif verb:
            expanded = f"{verb} 분쟁조정 피해구제 소비자 사례"
            return expanded, f"dispute_verb_only: {verb}"
        else:
            return query, "dispute_no_context"

    elif query_type == "law":
        law_names = [kw for kw in keywords if "법" in kw]
        if law_names:
            expanded = f"{query} {' '.join(law_names)} 관련 조항 조문"
            return expanded, f"law_expansion: {','.join(law_names)}"
        return f"{query} 소비자보호법 전자상거래법 조항", "law_default"

    elif query_type == "criteria":
        if item:
            expanded = f"{item} 분쟁해결기준 교환 환불 수리 보상 기간"
            return expanded, f"criteria_item: {item}"
        return f"{query} 분쟁해결기준 품목 기준", "criteria_default"

    # NEW: procedure (절차 안내)
    elif query_type == "procedure":
        expanded = f"{query} 분쟁조정 신청 절차 서류 기간 방법"
        return expanded, "procedure_expansion"

    # NEW: restricted (전문기관 도메인 - 유사 사례 검색용)
    elif query_type == "restricted":
        # 도메인 키워드를 추출하여 유사 사례 검색에 활용
        domain = _detect_restricted_domain(query)
        if domain:
            domain_keywords = RESTRICTED_DOMAIN_KEYWORDS.get(domain, [])[:3]
            expanded = f"{query} {' '.join(domain_keywords)} 분쟁 사례"
            return expanded, f"restricted_expansion: {domain}"
        return f"{query} 분쟁 사례", "restricted_default"

    return query, "unknown_type"


def _generate_search_queries(
    original: str, expanded: str, keywords: List[str]
) -> List[str]:
    """
    Multi-Query Expansion (PR 2)

    다양한 검색 전략으로 Recall(재현율)을 높입니다.
    하나의 질문이라도 여러 가지 방식으로 표현하여 검색엔진에 질의합니다.

    전략:
    1. 원본 쿼리: 사용자의 날 것 그대로의 질문
    2. 확장 쿼리: 규칙/LLM으로 보강된 쿼리 (법률 용어 등 추가)
    3. 키워드 조합 쿼리: 불필요한 조사 등을 제거한 순수 키워드 나열
    4. 동의어 변형 쿼리: "환불" -> "반환/청약철회" 등으로 치환
    """
    queries = [original]

    if expanded and expanded != original:
        queries.append(expanded)

    if len(keywords) >= 3:
        keyword_query = " ".join(keywords[:5])
        if keyword_query not in queries:
            queries.append(keyword_query)

    synonym_query = _create_synonym_variant_query(original, keywords)
    if synonym_query and synonym_query not in queries:
        queries.append(synonym_query)

    return queries[:4]


def _create_synonym_variant_query(original: str, keywords: List[str]) -> Optional[str]:
    """
    동의어 변형 쿼리 생성
    예: "노트북 환불" -> "노트북 반환 청약철회"
    """
    variant_parts = []
    for kw in keywords[:3]:
        if kw in VERB_SYNONYMS:
            synonyms = VERB_SYNONYMS[kw][:2]
            variant_parts.append(" ".join(synonyms))
        else:
            variant_parts.append(kw)

    variant = " ".join(variant_parts)
    return variant if variant != original else None


def _check_missing_onboarding_fields(
    chat_type: Literal["dispute", "general"],
    onboarding: Optional[OnboardingInfo],
    extracted_info: Optional[Dict[str, str]] = None,
) -> List[str]:
    """
    온보딩 필수 정보 누락 확인

    분쟁 상담(dispute)일 때만 체크합니다.
    onboarding 정보와 이번 턴에 추출된 정보를 합쳐서 필수 필드가 있는지 확인합니다.

    Returns:
        누락된 필드명 리스트
    """
    if chat_type == "general":
        return []

    combined: Dict[str, str] = {}
    if onboarding:
        for k, v in dict(onboarding).items():
            if v and isinstance(v, str):
                combined[k] = v
    if extracted_info:
        combined.update(extracted_info)

    if not combined:
        return REQUIRED_DISPUTE_FIELDS.copy()

    missing = []
    for field in REQUIRED_DISPUTE_FIELDS:
        value = combined.get(field)
        if not value or (isinstance(value, str) and not value.strip()):
            missing.append(field)

    return missing


def query_analysis_node(state: ChatState) -> Dict:
    """
    [질의분석 노드 진입점]
    LangGraph에서 호출되는 메인 함수입니다.

    ChatState에서 user_query, chat_type, onboarding을 입력받아
    분석 프로세스를 수행하고 결과를 반환합니다.

    [프로세스]
    1. 쿼리 정규화
    2. 유형 분류 (Rule + Hybrid)
    3. 키워드 추출
    4. 정보 추출 (엔티티)
    5. 쿼리 확장 & 다중 검색 쿼리 생성
    6. 필수 정보 누락 확인
    7. 라우팅 모드 결정
    """
    user_query = state.get("user_query", "")
    chat_type = state.get("chat_type", "general")
    onboarding = state.get("onboarding")

    # === PR-6: L2 캐시 체크 ===
    from ...supervisor.cache import QueryAnalysisCache

    cached = QueryAnalysisCache.get(user_query)
    if cached:
        logger.info(f"[QueryAnalysis] Cache HIT for: {user_query[:30]}...")
        return {
            'query_analysis': cached,
            'mode': cached.get('mode', 'NEED_RAG'),
            '_qa_cache_hit': True,
        }
    # === PR-6 끝 ===

    # Step 1: 쿼리 정규화
    normalized_query = _normalize_query(user_query)

    # Step 2: 질의 유형 분류
    query_type = _classify_query_type(normalized_query)

    # PR-7: 일반 채팅에서도 분쟁 의도 키워드가 있으면 dispute로 처리 (Safety Net)
    if chat_type == "general":
        # 법령/기준 쿼리는 유지 (더 구체적인 분류이므로 우선순위 높음)
        if query_type in ("law", "criteria"):
            pass  # Keep the specific classification
        else:
            has_dispute_intent = any(
                kw in normalized_query for kw in DISPUTE_INTENT_KEYWORDS
            )
            if has_dispute_intent:
                query_type = "dispute"
                logger.info(
                    f"[QueryAnalysis] General chat with dispute intent: '{normalized_query[:30]}'"
                )
            else:
                # 나머지는 general
                query_type = "general"

    # Step 3: 키워드 추출
    keywords = _extract_keywords(normalized_query)

    # Step 4: 기관 추천 힌트 및 Restricted 도메인 감지
    restricted_domain = _detect_restricted_domain(normalized_query) if query_type == "restricted" else None
    agency_hint = (
        _determine_agency_hint(normalized_query)
        if query_type in ("dispute", "procedure", "criteria")
        else None
    )

    # Step 5: 메시지에서 정보 추출
    extracted_info = _extract_info_from_message(user_query)

    # Step 6: 쿼리 확장 (Query Expansion)
    rewritten_query, expansion_applied = _expand_query_by_type(
        query=normalized_query,
        query_type=query_type,
        onboarding=onboarding,
        extracted_info=extracted_info,
        keywords=keywords,
    )

    # Step 7: 다중 검색 쿼리 생성
    search_queries = _generate_search_queries(
        original=normalized_query, expanded=rewritten_query, keywords=keywords
    )

    # Step 8: 누락 필드 확인
    missing_fields = _check_missing_onboarding_fields(
        chat_type, onboarding, extracted_info
    )
    missing_fields_description = _get_missing_fields_description(
        missing_fields, extracted_info
    )

    # 최소 정보가 있는지 확인 (품목이나 상세 내용 중 하나라도 있으면 진행)
    has_minimal_info = bool(
        extracted_info.get("purchase_item")
        or extracted_info.get("dispute_details")
        or (
            onboarding
            and (onboarding.get("purchase_item") or onboarding.get("dispute_details"))
        )
    )
    needs_clarification = not has_minimal_info and query_type == "dispute"

    # 라우팅 모드 결정
    mode = _classify_mode(query_type, needs_clarification, user_query)

    logger.info(
        f"[QueryAnalysis] mode={mode}, query_type={query_type}, needs_clarification={needs_clarification}"
    )

    # v1 호환 결과 구조
    analysis_result: QueryAnalysisResult = {
        "query_type": query_type,
        "keywords": keywords,
        "agency_hint": agency_hint,
        "needs_clarification": needs_clarification,
        "missing_fields": missing_fields,
        "extracted_info": extracted_info,
        "missing_fields_description": missing_fields_description,
        "rewritten_query": rewritten_query,
        "search_queries": search_queries,
        "expansion_applied": expansion_applied,

        # === PR-2: Selective Retrieval 시작 ===
        "retriever_types": QUERY_TYPE_TO_RETRIEVERS.get(query_type, ["law", "criteria"]),
        # === PR-2: Selective Retrieval 끝 ===

        # === Phase 9: Restricted Domain 정보 ===
        "restricted_domain": restricted_domain,
        "restricted_agency_info": RESTRICTED_DOMAIN_AGENCIES.get(restricted_domain) if restricted_domain else None,
    }

    # === PR-6: L2 캐시 저장 ===
    from ...supervisor.cache import QueryAnalysisCache

    cache_data = dict(analysis_result)
    cache_data['mode'] = mode
    QueryAnalysisCache.set(user_query, cache_data)
    # === PR-6 끝 ===

    return {
        "query_analysis": analysis_result,
        "mode": mode,
    }
