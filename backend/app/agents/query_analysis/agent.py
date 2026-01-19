"""
똑소리 프로젝트 - 질의분석 노드
작성일: 2026-01-14
S2-3: 사용자 질문 분류 및 키워드 추출
S2-10: LLM 기반 쿼리 재작성 (Phase 3) 통합
Sprint 1: _v2 스키마 적용 + mode 분류 로직 추가

질의분석 노드의 역할:
1. 라우팅 모드 결정 (NO_RETRIEVAL/NEED_RAG/NEED_USER_CLARIFICATION)
2. 질의 유형 분류 (dispute, general, law, criteria)
3. 검색에 사용할 핵심 키워드 추출
4. 추천 기관 힌트 생성 (KCA/ECMC/KCDRC)
5. 온보딩 정보 누락 여부 탐지
6. LLM 기반 쿼리 재작성 (복잡한 법률 용어 -> 일상어)
"""

import logging
import os
import re
from typing import Dict, List, Literal, Optional, Any

from ...orchestrator.state import (
    ChatState,
    QueryAnalysisResult,
    QueryAnalysisResult_v2,
    OnboardingInfo,
    RoutingMode,
)

# S2-10: LLM 기반 쿼리 재작성
try:
    from app.llm import get_query_rewriter
    LLM_REWRITE_AVAILABLE = True
except ImportError:
    LLM_REWRITE_AVAILABLE = False
    get_query_rewriter = None

logger = logging.getLogger(__name__)

# 환경 변수로 LLM 재작성 활성화 여부 제어
USE_LLM_REWRITE = os.getenv('QUERY_REWRITE_ENABLED', 'true').lower() == 'true'


# 콘텐츠 관련 키워드 (KCDRC)
CONTENT_KEYWORDS = [
    "게임", "영화", "콘텐츠", "앱", "어플", "애플리케이션",
    "음악", "웹툰", "만화", "동영상", "영상", "스트리밍",
    "OTT", "넷플릭스", "왓챠", "디즈니", "유튜브",
    "인앱", "결제", "아이템", "캐시", "다이아", "루비",
    "디지털", "다운로드", "구독", "VOD", "e북", "전자책"
]

# 개인간 거래 키워드 (ECMC)
INDIVIDUAL_KEYWORDS = [
    "중고", "직거래", "당근", "당근마켓", "번개장터", "중고나라",
    "개인간", "개인거래", "개인 판매", "개인판매자",
    "직접 거래", "직접거래", "만나서", "택배거래",
    "중고거래", "중고 거래", "세컨핸드", "second hand"
]

# 법령 관련 키워드
LAW_KEYWORDS = [
    "법", "법률", "법령", "조항", "조문", "제조", "항", "호",
    "소비자보호법", "전자상거래법", "약관규제법", "할부거래법",
    "방문판매법", "표시광고법", "제조물책임법"
]

# 분쟁조정기준 관련 키워드
CRITERIA_KEYWORDS = [
    "기준", "분쟁조정기준", "별표", "해제", "해지", "위약금",
    "환불", "보상", "배상", "수리", "교환", "반품"
]

# 분쟁 상담 필수 정보 필드 (dispute 타입일 때)
REQUIRED_DISPUTE_FIELDS = [
    "purchase_item",       # 구매 품목 (필수)
    "dispute_details",     # 분쟁 상세 내용 (필수)
]

# 분쟁 상담 권장 정보 필드
RECOMMENDED_DISPUTE_FIELDS = [
    "purchase_date",       # 구매일자
    "purchase_place",      # 구매처
    "purchase_amount",     # 구매 금액
]

# 필드별 한국어 이름 매핑
FIELD_KOREAN_NAMES = {
    'purchase_item': '구매 품목',
    'dispute_details': '분쟁 상세 내용',
    'purchase_date': '구매일자',
    'purchase_place': '구매처',
    'purchase_platform': '플랫폼',
    'purchase_amount': '구매금액',
}


COMMON_PRODUCTS = [
    "노트북", "컴퓨터", "PC", "스마트폰", "휴대폰", "핸드폰", "아이폰", "갤럭시",
    "태블릿", "아이패드", "에어팟", "이어폰", "헤드폰", "스피커", "TV", "텔레비전",
    "냉장고", "세탁기", "에어컨", "청소기", "전자레인지", "오븐", "건조기",
    "모니터", "키보드", "마우스", "프린터", "카메라", "렌즈", "드론", "로봇청소기",
    "공기청정기", "제습기", "가습기", "전기밥솥", "믹서기", "커피머신",
    "침대", "소파", "책상", "의자", "옷장", "매트리스", "가구",
    "헬스장", "PT", "피티", "수영장", "필라테스", "요가", "학원", "영어",
    "웨딩", "결혼", "스튜디오", "여행", "항공권", "호텔", "숙박",
    "옷", "신발", "가방", "지갑", "시계", "악세서리",
    "자동차", "차량", "중고차", "오토바이", "자전거", "킥보드", "전동킥보드",
]

DISPUTE_VERBS = [
    "환불", "반품", "교환", "수리", "취소", "해지", "해약",
    "피해", "하자", "불량", "고장", "파손",
    "분쟁", "보상", "배상", "위약금",
]

QUERY_EXPANSION_TEMPLATES = {
    'dispute': "{item} {verb} 분쟁조정 피해구제 소비자",
    'law': "{query} 소비자보호법 전자상거래법 관련 조항",
    'criteria': "{item} 분쟁해결기준 교환 환불 수리 기간",
}

VERB_SYNONYMS = {
    "환불": ["환불", "반환", "취소", "청약철회"],
    "교환": ["교환", "대체", "바꿈"],
    "수리": ["수리", "A/S", "AS", "무상수리", "유상수리"],
    "해지": ["해지", "해약", "중도해지", "계약해지", "취소"],
}

FAST_PATH_PROMOTION_KEYWORDS = [
    "위법", "불법", "합법", "소송", "고소", "고발",
    "청약철회", "환불기간", "보증기간", "제척기간", "소멸시효",
    "손해배상", "위약금", "분쟁조정", "피해구제",
    "법원", "판결", "판례", "조정위원회",
]

ENABLE_FAST_PATH_PROMOTION = os.getenv('ENABLE_FAST_PATH_PROMOTION', 'true').lower() == 'true'


def _should_promote_to_rag(query: str) -> bool:
    if not ENABLE_FAST_PATH_PROMOTION:
        return False
    query_lower = query.lower()
    return any(kw in query_lower for kw in FAST_PATH_PROMOTION_KEYWORDS)


def _classify_mode(
    query_type: Literal['dispute', 'general', 'law', 'criteria'],
    needs_clarification: bool,
    query: str,
) -> RoutingMode:
    if query_type == 'general':
        if _should_promote_to_rag(query):
            logger.info("[QueryAnalysis] Fast Path promotion triggered for general query")
            return 'NEED_RAG'
        return 'NO_RETRIEVAL'
    
    if needs_clarification:
        return 'NEED_USER_CLARIFICATION'
    
    return 'NEED_RAG'


def _extract_info_from_message(query: str) -> Dict[str, str]:
    """
    메시지 내용에서 온보딩 정보 추출
    "[분쟁 정보]" 형식 또는 자연어에서 정보 추출
    """
    info: Dict[str, str] = {}
    
    patterns = {
        'purchase_item': [
            r'구매\s*품목[:\s]+([^\n,]+)',
            r'품목[:\s]+([^\n,]+)',
            r'제품[:\s]+([^\n,]+)',
        ],
        'dispute_details': [
            r'분쟁\s*상세[:\s]+([^\n]+)',
            r'문제[:\s]+([^\n]+)',
            r'상황[:\s]+([^\n]+)',
        ],
        'purchase_date': [
            r'구매\s*일자[:\s]+([^\n,]+)',
            r'구매일[:\s]+([^\n,]+)',
        ],
        'purchase_place': [
            r'구매처[:\s]+([^\n,]+)',
            r'판매처[:\s]+([^\n,]+)',
        ],
        'purchase_platform': [
            r'플랫폼[:\s]+([^\n,]+)',
        ],
        'purchase_amount': [
            r'구매\s*금액[:\s]+([^\n,]+)',
            r'금액[:\s]+([^\n,]+)',
        ],
    }
    
    for field, field_patterns in patterns.items():
        for pattern in field_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if value and value not in ['없음', '모름', '-']:
                    info[field] = value
                break
    
    if 'purchase_item' not in info:
        query_lower = query.lower()
        for product in COMMON_PRODUCTS:
            if product.lower() in query_lower:
                info['purchase_item'] = product
                break
    
    if 'dispute_details' not in info:
        found_verbs = [v for v in DISPUTE_VERBS if v in query]
        if found_verbs and 'purchase_item' in info:
            verb = found_verbs[0]
            item = info['purchase_item']
            info['dispute_details'] = f"{item} {verb} 관련 문의"
    
    return info


def _get_missing_fields_description(
    missing_fields: List[str],
    extracted_info: Dict[str, str]
) -> str:
    """
    부족한 정보에 대한 구체적인 설명 생성
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


def _classify_query_type(query: str) -> Literal['dispute', 'general', 'law', 'criteria']:
    """
    질의 유형 분류
    
    Returns:
        'dispute': 분쟁 상담 (환불, 피해 등)
        'general': 일반 대화 (인사, 안부 등)
        'law': 법령 문의
        'criteria': 분쟁조정기준 문의
    """
    query_lower = query.lower()
    
    # 일반 대화 패턴 (인사, 감사 등)
    general_patterns = [
        r'^안녕', r'^반갑', r'^감사', r'^고마', r'^네$', r'^예$',
        r'^알겠', r'^ㅋ+$', r'^ㅎ+$', r'^ㅇㅇ$', r'^오케이', r'^ok',
        r'^hello', r'^hi$', r'^bye', r'^thanks'
    ]
    for pattern in general_patterns:
        if re.search(pattern, query_lower):
            return 'general'
    
    # 법령 문의 (법령 키워드가 명시적으로 포함)
    law_count = sum(1 for kw in LAW_KEYWORDS if kw in query_lower)
    if law_count >= 2 or any(kw in query_lower for kw in ["몇조", "법 조항", "법령 조회"]):
        return 'law'
    
    # 분쟁조정기준 문의
    criteria_count = sum(1 for kw in CRITERIA_KEYWORDS if kw in query_lower)
    if criteria_count >= 2 or "분쟁조정기준" in query_lower:
        return 'criteria'
    
    # 기본값: 분쟁 상담
    return 'dispute'


def _extract_keywords(query: str) -> List[str]:
    """
    검색에 사용할 핵심 키워드 추출
    
    간단한 규칙 기반 추출:
    - 명사형 단어 추출 (2글자 이상)
    - 불용어 제거
    """
    # 불용어
    stopwords = {
        "저", "제", "것", "수", "등", "더", "좀", "잘", "못", "안",
        "이", "그", "저", "때", "경우", "어떻게", "무엇", "어디", "왜",
        "알려", "주세요", "해주세요", "싶어요", "있나요", "있어요",
        "하고", "그리고", "그래서", "하지만", "그런데", "근데"
    }
    
    # 특수문자 제거 및 공백 분리
    words = re.sub(r'[^\w\s]', ' ', query).split()
    
    # 2글자 이상, 불용어 제외
    keywords = [w for w in words if len(w) >= 2 and w not in stopwords]
    
    # 중복 제거, 순서 유지
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)
    
    return unique_keywords[:10]  # 최대 10개


def _determine_agency_hint(query: str) -> Optional[str]:
    query_lower = query.lower()
    
    content_matches = [kw for kw in CONTENT_KEYWORDS if kw in query_lower]
    if content_matches:
        return 'KCDRC'
    
    individual_matches = [kw for kw in INDIVIDUAL_KEYWORDS if kw in query_lower]
    if individual_matches:
        return 'ECMC'
    
    return 'KCA'


def _normalize_query(query: str) -> str:
    normalized = query.strip()
    
    suffix_patterns = [
        r'[~해주세요|알려주세요|싶어요|인가요|할까요|있나요|있어요|될까요]$',
        r'[?？!！。\.]+$',
    ]
    for pattern in suffix_patterns:
        normalized = re.sub(pattern, '', normalized)
    
    return normalized.strip()


def _expand_query_by_type(
    query: str,
    query_type: Literal['dispute', 'general', 'law', 'criteria'],
    onboarding: Optional[OnboardingInfo],
    extracted_info: Dict[str, str],
    keywords: List[str],
    use_llm: bool = True
) -> tuple[str, str]:
    """
    질의 유형별 쿼리 확장

    S2-10: LLM 기반 쿼리 재작성 통합
    - 복잡한 법률 용어가 포함된 쿼리는 EXAONE으로 일상어 변환
    - 100ms 타임아웃으로 지연시간 제약 보장
    - 타임아웃/에러 시 기존 규칙 기반 확장으로 폴백

    Args:
        query: 정규화된 쿼리
        query_type: 질의 유형
        onboarding: 온보딩 정보
        extracted_info: 메시지에서 추출한 정보
        keywords: 추출된 키워드
        use_llm: LLM 재작성 사용 여부 (기본: True)

    Returns:
        (확장된 쿼리, 적용된 확장 방식)
    """
    if query_type == 'general':
        return query, "general_no_expansion"

    # S2-10: LLM 기반 쿼리 재작성 시도
    if use_llm and USE_LLM_REWRITE and LLM_REWRITE_AVAILABLE:
        try:
            rewriter = get_query_rewriter()
            if rewriter and rewriter.is_complex_query(query, query_type):
                llm_rewritten = rewriter.rewrite(query, {
                    'query_type': query_type,
                    'keywords': keywords,
                    'extracted_info': extracted_info
                })
                if llm_rewritten and llm_rewritten != query:
                    logger.info(f"[QueryAnalysis] LLM rewrite: {query[:30]}... -> {llm_rewritten[:30]}...")
                    return llm_rewritten, f"llm_rewrite: {query[:20]}..."
        except Exception as e:
            logger.warning(f"[QueryAnalysis] LLM rewrite failed: {e}, using rule-based")

    # 기존 규칙 기반 확장 (Phase 1)
    item = extracted_info.get('purchase_item', '')
    if not item and onboarding:
        item = onboarding.get('purchase_item', '')

    found_verbs = [v for v in DISPUTE_VERBS if v in query]
    verb = found_verbs[0] if found_verbs else ''

    expanded_verbs = []
    if verb and verb in VERB_SYNONYMS:
        expanded_verbs = VERB_SYNONYMS[verb][:2]

    if query_type == 'dispute':
        if item and verb:
            verb_str = ' '.join(expanded_verbs) if expanded_verbs else verb
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

    elif query_type == 'law':
        law_names = [kw for kw in keywords if '법' in kw]
        if law_names:
            expanded = f"{query} {' '.join(law_names)} 관련 조항 조문"
            return expanded, f"law_expansion: {','.join(law_names)}"
        return f"{query} 소비자보호법 전자상거래법 조항", "law_default"

    elif query_type == 'criteria':
        if item:
            expanded = f"{item} 분쟁해결기준 교환 환불 수리 보상 기간"
            return expanded, f"criteria_item: {item}"
        return f"{query} 분쟁해결기준 품목 기준", "criteria_default"

    return query, "unknown_type"


def _generate_search_queries(
    original: str,
    expanded: str,
    keywords: List[str]
) -> List[str]:
    queries = [original]
    
    if expanded and expanded != original:
        queries.append(expanded)
    
    if len(keywords) >= 3:
        keyword_query = ' '.join(keywords[:5])
        if keyword_query not in queries:
            queries.append(keyword_query)
    
    return queries[:3]


def _check_missing_onboarding_fields(
    chat_type: Literal['dispute', 'general'],
    onboarding: Optional[OnboardingInfo],
    extracted_info: Optional[Dict[str, str]] = None
) -> List[str]:
    """
    온보딩 필수 정보 누락 확인
    
    분쟁 상담(dispute)일 때만 체크.
    onboarding과 메시지에서 추출한 정보를 합쳐서 확인.
    
    Returns:
        누락된 필드명 리스트
    """
    if chat_type == 'general':
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
    질의분석 노드 함수
    
    ChatState에서 user_query, chat_type, onboarding을 분석하여
    QueryAnalysisResult를 생성.
    
    쿼리 재생성 (Query Rewriting) 포함:
    1. 쿼리 정규화 - 불필요한 접미사 제거
    2. 유형별 쿼리 확장 - 검색 효과 향상을 위한 동의어/관련어 추가
    3. 다중 검색 쿼리 생성 - 원본 + 확장 + 키워드 조합
    """
    user_query = state.get('user_query', '')
    chat_type = state.get('chat_type', 'general')
    onboarding = state.get('onboarding')
    
    # Step 1: 쿼리 정규화
    normalized_query = _normalize_query(user_query)
    
    # Step 2: 질의 유형 분류
    query_type = _classify_query_type(normalized_query)
    
    if chat_type == 'general':
        query_type = 'general'
    
    # Step 3: 키워드 추출
    keywords = _extract_keywords(normalized_query)
    
    # Step 4: 기관 추천 힌트
    agency_hint = _determine_agency_hint(normalized_query) if query_type == 'dispute' else None
    
    # Step 5: 메시지에서 정보 추출
    extracted_info = _extract_info_from_message(user_query)
    
    # Step 6: 쿼리 확장 (Query Expansion)
    rewritten_query, expansion_applied = _expand_query_by_type(
        query=normalized_query,
        query_type=query_type,
        onboarding=onboarding,
        extracted_info=extracted_info,
        keywords=keywords
    )
    
    # Step 7: 다중 검색 쿼리 생성
    search_queries = _generate_search_queries(
        original=normalized_query,
        expanded=rewritten_query,
        keywords=keywords
    )
    
    # Step 8: 누락 필드 확인
    missing_fields = _check_missing_onboarding_fields(chat_type, onboarding, extracted_info)
    missing_fields_description = _get_missing_fields_description(missing_fields, extracted_info)
    
    has_minimal_info = bool(
        extracted_info.get('purchase_item') or 
        extracted_info.get('dispute_details') or
        (onboarding and (onboarding.get('purchase_item') or onboarding.get('dispute_details')))
    )
    needs_clarification = not has_minimal_info and query_type == 'dispute'
    
    mode = _classify_mode(query_type, needs_clarification, user_query)
    
    logger.info(f"[QueryAnalysis] mode={mode}, query_type={query_type}, needs_clarification={needs_clarification}")
    
    analysis_result: QueryAnalysisResult = {
        'query_type': query_type,
        'keywords': keywords,
        'agency_hint': agency_hint,
        'needs_clarification': needs_clarification,
        'missing_fields': missing_fields,
        'extracted_info': extracted_info,
        'missing_fields_description': missing_fields_description,
        'rewritten_query': rewritten_query,
        'search_queries': search_queries,
        'expansion_applied': expansion_applied,
    }
    
    analysis_result_v2: QueryAnalysisResult_v2 = {
        'mode': mode,
        'uncertainties': missing_fields,
        'need_evidence': mode == 'NEED_RAG',
        'required_slots': missing_fields,
        'filters_candidate': {},
        'sql_params_candidate': {},
        'query_type': query_type,
        'keywords': keywords,
        'agency_hint': agency_hint,
        'rewritten_query': rewritten_query,
        'search_queries': search_queries,
    }
    
    return {
        'query_analysis': analysis_result,
        'query_analysis_v2': analysis_result_v2,
        'mode': mode,
    }
