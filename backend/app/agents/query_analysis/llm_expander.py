"""
LLM 기반 쿼리 확장 모듈 (v2)

작성일: 2026-01-28

[역할 및 책임]
gpt-4o-mini를 사용하여 사용자 쿼리를 다중 검색 쿼리로 확장합니다.
- 동의어 확장: '환불' → ['청약철회', '계약해제', '반품']
- 개념 확장: '헬스장' → ['체육시설', '피트니스센터', '스포츠센터']
- 법률 용어 매핑: 일상어 → 법률 전문 용어
"""

import asyncio
import logging
from typing import List, Optional

from openai import AsyncOpenAI

from ...common.config import get_config

logger = logging.getLogger(__name__)

# LLM 쿼리 확장 프롬프트
QUERY_EXPANSION_SYSTEM_PROMPT = """당신은 소비자 분쟁 해결 시스템의 검색 쿼리 확장 전문가입니다.

사용자의 질문을 분석하여 관련 법령, 분쟁해결기준, 사례를 효과적으로 검색할 수 있도록
다양한 검색 쿼리로 확장해주세요.

확장 규칙:
1. 동의어 확장: 일상 용어를 법률/행정 용어로 변환
   - 환불 → 청약철회, 계약해제, 반환, 환급
   - 수리 → 수선, 하자보수, A/S
   - 교환 → 대체급부, 대품
   - 취소 → 계약해지, 철회

2. 품목 확장: 품목을 상위/유사 개념으로 확장
   - 헬스장 → 체육시설, 피트니스센터, 스포츠센터
   - 핸드폰 → 휴대전화, 이동통신단말기, 스마트폰
   - 자동차 → 승용차, 차량, 자동차

3. 상황 확장: 분쟁 상황을 다양한 표현으로 확장
   - 불량 → 하자, 결함, 고장
   - 피해 → 손해, 손실

주의사항:
- 최대 5개의 검색 쿼리를 생성하세요
- 각 쿼리는 30자 이내로 간결하게 작성하세요
- 원본 쿼리의 의미를 벗어나지 마세요
- JSON 배열 형식으로만 응답하세요 (예: ["쿼리1", "쿼리2", ...])"""

QUERY_EXPANSION_USER_PROMPT = """다음 사용자 질문을 확장해주세요:

원본 질문: {query}
추출된 키워드: {keywords}

JSON 배열 형식으로 확장된 검색 쿼리 목록을 반환하세요:"""


async def expand_query_with_llm(
    query: str,
    keywords: List[str],
    max_queries: int = 5,
    timeout: float = 3.0,
) -> Optional[List[str]]:
    """
    LLM을 사용하여 쿼리를 다중 검색 쿼리로 확장합니다.

    Args:
        query: 원본 사용자 쿼리
        keywords: 추출된 키워드 목록
        max_queries: 최대 생성 쿼리 수
        timeout: LLM 호출 타임아웃 (초)

    Returns:
        확장된 쿼리 목록 또는 None (실패 시)
    """
    config = get_config()

    try:
        client = AsyncOpenAI(api_key=config.llm.openai_api_key)

        user_prompt = QUERY_EXPANSION_USER_PROMPT.format(
            query=query, keywords=", ".join(keywords) if keywords else "없음"
        )

        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=config.models.query_expander,
                messages=[
                    {"role": "system", "content": QUERY_EXPANSION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=200,
            ),
            timeout=timeout,
        )

        content = response.choices[0].message.content.strip()

        # JSON 파싱
        import json

        expanded_queries = json.loads(content)

        if isinstance(expanded_queries, list):
            # 최대 개수 제한 및 원본 쿼리 포함
            result = [query]  # 원본 쿼리를 첫 번째로
            for eq in expanded_queries:
                if isinstance(eq, str) and eq not in result:
                    result.append(eq)
                if len(result) >= max_queries:
                    break

            logger.info(
                f"[LLM Expander] Expanded '{query[:30]}...' to {len(result)} queries"
            )
            return result

        logger.warning(f"[LLM Expander] Invalid response format: {content}")
        return None

    except asyncio.TimeoutError:
        logger.warning(
            f"[LLM Expander] Timeout after {timeout}s for query: {query[:30]}..."
        )
        return None

    except Exception as e:
        logger.warning(f"[LLM Expander] Error: {e}")
        return None


def expand_query_with_llm_sync(
    query: str,
    keywords: List[str],
    max_queries: int = 5,
    timeout: float = 3.0,
) -> Optional[List[str]]:
    """
    LLM 쿼리 확장의 동기 버전.

    기존 동기 코드와의 호환성을 위해 제공됩니다.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 이미 이벤트 루프가 실행 중인 경우 (FastAPI 등)
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    expand_query_with_llm(query, keywords, max_queries, timeout),
                )
                return future.result(timeout=timeout + 1)
        else:
            return loop.run_until_complete(
                expand_query_with_llm(query, keywords, max_queries, timeout)
            )
    except Exception as e:
        logger.warning(f"[LLM Expander Sync] Error: {e}")
        return None


# ============================================================================
# 법령 검색 전용 쿼리 확장 (Phase 2-10)
# ============================================================================

# 일상어 → 법률 용어 매핑 테이블
LEGAL_TERM_MAPPING = {
    # 환불/취소 관련
    "환불": ["청약철회", "계약해제", "대금환급"],
    "취소": ["청약철회", "계약해지", "철회권"],
    "반품": ["청약철회", "반환청구"],
    "교환": ["대체급부", "교환청구"],
    # 구매 채널 관련
    "온라인": ["통신판매", "전자상거래"],
    "인터넷": ["전자상거래", "통신판매"],
    "쿠팡": ["통신판매업자", "온라인플랫폼"],
    "배달앱": ["통신판매중개", "플랫폼사업자"],
    "홈쇼핑": ["전화권유판매", "통신판매"],
    "방문판매": ["방문판매", "직접판매"],
    # 하자/결함 관련
    "불량": ["하자", "결함", "부적합"],
    "고장": ["하자", "수선", "하자보수"],
    "결함": ["하자", "부적합", "계약부적합"],
    # 기간 관련
    "7일": ["7일 이내", "청약철회기간"],
    "14일": ["14일 이내", "방문판매 철회기간"],
    "30일": ["30일 이내", "품질보증기간"],
    # 품목 관련
    "노트북": ["컴퓨터", "전자제품", "정보통신기기"],
    "핸드폰": ["이동통신단말장치", "휴대전화"],
    "가전": ["가전제품", "전기용품"],
    "차": ["자동차", "자동차관리법"],
    # 분쟁 관련
    "사기": ["기망", "부당표시광고", "허위과장광고"],
    "피해": ["손해", "손해배상", "피해구제"],
}

# 상황별 관련 법률 매핑
SITUATION_TO_LAWS = {
    "온라인구매": ["전자상거래법", "전자상거래 등에서의 소비자보호에 관한 법률"],
    "환불": ["전자상거래법 제17조", "청약철회", "소비자기본법"],
    "방문판매": ["방문판매법", "방문판매 등에 관한 법률"],
    "할부": ["할부거래법", "할부거래에 관한 법률"],
    "결함": ["제조물책임법", "소비자기본법", "하자담보책임"],
    "표시광고": ["표시광고법", "표시·광고의 공정화에 관한 법률"],
    "개인정보": ["개인정보보호법", "정보통신망법"],
    "중고거래": ["민법", "채권법", "하자담보책임"],
    "헬스장": ["체육시설법", "소비자분쟁해결기준"],
    "여행": ["여행업법", "소비자분쟁해결기준"],
}

LAW_QUERY_EXPANSION_SYSTEM_PROMPT = """당신은 소비자 분쟁 해결을 위한 법령 검색 전문가입니다.

사용자의 자연어 질문을 법령 데이터베이스에서 효과적으로 검색할 수 있는 쿼리로 변환해주세요.

## 핵심 변환 규칙

1. **일상어 → 법률 용어 변환**:
   - 환불/반품 → 청약철회, 계약해제
   - 취소 → 청약철회권, 계약해지
   - 온라인 구매 → 통신판매, 전자상거래
   - 불량/고장 → 하자, 결함, 부적합
   - 사기 → 기망, 허위표시

2. **관련 법률명 추가**:
   - 온라인 구매 → 전자상거래법, 전자상거래 등에서의 소비자보호에 관한 법률
   - 방문판매 → 방문판매법, 방문판매 등에 관한 법률
   - 할부 → 할부거래법
   - 제품 결함 → 제조물책임법

3. **관련 조문 키워드 추가**:
   - 청약철회 7일 → "제17조", "청약철회"
   - 손해배상 → "손해배상", "배상책임"

## 출력 형식
JSON 배열로 3-5개의 검색 쿼리를 생성하세요.
- 첫 번째: 핵심 법률 용어 + 관련 법률명
- 두 번째: 법률 조항 관련 키워드
- 세 번째: 분쟁해결기준 검색용 쿼리
- 나머지: 대안적 표현

예시 입력: "온라인에서 노트북 샀는데 환불 안해줘요"
예시 출력: ["전자상거래법 청약철회 통신판매", "전자상거래 제17조 청약철회권", "컴퓨터 환불 분쟁해결기준", "통신판매 계약해제 대금환급"]"""

LAW_QUERY_EXPANSION_USER_PROMPT = """다음 소비자 질문을 법령 검색에 적합한 쿼리로 변환해주세요:

원본 질문: {query}
추출된 정보:
- 품목: {item}
- 구매채널: {channel}
- 분쟁유형: {dispute_type}
- 키워드: {keywords}

JSON 배열 형식으로 법령 검색 쿼리 3-5개를 반환하세요:"""


async def expand_query_for_law_search(
    query: str,
    item: str = "",
    channel: str = "",
    dispute_type: str = "",
    keywords: List[str] = None,
    timeout: float = 3.0,
) -> List[str]:
    """
    법령 검색에 특화된 쿼리 확장 (Phase 2-10)

    자연어 쿼리를 법률 용어가 포함된 검색 쿼리로 변환합니다.

    Args:
        query: 원본 사용자 쿼리
        item: 품목 (예: 노트북, 핸드폰)
        channel: 구매채널 (예: 온라인, 방문판매)
        dispute_type: 분쟁유형 (예: 환불, 교환)
        keywords: 추출된 키워드 목록
        timeout: LLM 호출 타임아웃 (초)

    Returns:
        법령 검색에 최적화된 쿼리 목록
    """
    keywords = keywords or []
    config = get_config()

    # 1단계: 규칙 기반 법률 용어 변환 (빠른 처리)
    rule_based_queries = _generate_law_queries_rule_based(
        query, item, channel, dispute_type, keywords
    )

    # 2단계: LLM 기반 확장 (더 정교한 변환)
    try:
        client = AsyncOpenAI(api_key=config.llm.openai_api_key)

        user_prompt = LAW_QUERY_EXPANSION_USER_PROMPT.format(
            query=query,
            item=item or "미지정",
            channel=channel or "미지정",
            dispute_type=dispute_type or "미지정",
            keywords=", ".join(keywords) if keywords else "없음",
        )

        response = await asyncio.wait_for(
            client.chat.completions.create(
                model=config.models.query_expander,
                messages=[
                    {"role": "system", "content": LAW_QUERY_EXPANSION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=300,
            ),
            timeout=timeout,
        )

        content = response.choices[0].message.content.strip()

        import json
        llm_queries = json.loads(content)

        if isinstance(llm_queries, list):
            # 규칙 기반 + LLM 결과 병합 (중복 제거)
            all_queries = rule_based_queries.copy()
            for q in llm_queries:
                if isinstance(q, str) and q not in all_queries:
                    all_queries.append(q)

            logger.info(
                f"[LLM Law Expander] Generated {len(all_queries)} law queries "
                f"(rule: {len(rule_based_queries)}, llm: {len(llm_queries)})"
            )
            return all_queries[:6]

    except asyncio.TimeoutError:
        logger.warning(f"[LLM Law Expander] Timeout, using rule-based only")
    except Exception as e:
        logger.warning(f"[LLM Law Expander] Error: {e}, using rule-based only")

    return rule_based_queries


def _generate_law_queries_rule_based(
    query: str,
    item: str,
    channel: str,
    dispute_type: str,
    keywords: List[str],
) -> List[str]:
    """
    규칙 기반 법률 쿼리 생성 (LLM 폴백용)

    핵심 전략: 자주 사용되는 법률 조문을 직접 검색하는 쿼리 생성
    """
    queries = []
    legal_terms = []
    law_names = []

    query_lower = query.lower()
    keywords_str = " ".join(keywords).lower()

    # 1. 일상어 → 법률 용어 변환
    for word, terms in LEGAL_TERM_MAPPING.items():
        if word in query_lower or word in keywords_str:
            legal_terms.extend(terms[:2])

    # 2. 상황별 관련 법률 추가
    for situation, laws in SITUATION_TO_LAWS.items():
        if situation in query_lower or situation in channel or situation in dispute_type:
            law_names.extend(laws[:2])

    # ============================================================
    # 3. 핵심 케이스별 직접 쿼리 생성 (가장 중요!)
    # ============================================================

    # 온라인/통신판매 + 환불/취소 → 전자상거래법 제17조 청약철회
    is_online = any(kw in query_lower for kw in ["온라인", "인터넷", "쿠팡", "배달", "통신판매", "앱", "웹", "사이트"])
    is_refund = any(kw in query_lower for kw in ["환불", "취소", "반품", "철회", "안해줘", "거부"])

    if is_online and is_refund:
        # 가장 중요한 쿼리: 전자상거래법 제17조 직접 검색
        queries.append("전자상거래법 제17조 청약철회")
        queries.append("전자상거래 등에서의 소비자보호에 관한 법률 청약철회권")
        queries.append("통신판매 청약철회 7일 이내")
        law_names = ["전자상거래법"]
        legal_terms = ["청약철회", "제17조", "청약철회권"]

    # 온라인 구매만 (환불 언급 없어도)
    elif is_online:
        queries.append("전자상거래법 통신판매 소비자보호")
        if "전자상거래법" not in law_names:
            law_names.append("전자상거래법")
        if "청약철회" not in legal_terms:
            legal_terms.append("청약철회")

    # 환불/취소만 (채널 불명)
    elif is_refund:
        queries.append("청약철회권 계약해제 소비자")
        queries.append("전자상거래법 제17조 청약철회")
        if "청약철회" not in legal_terms:
            legal_terms.append("청약철회")
            legal_terms.append("제17조")

    # 방문판매
    if any(kw in query_lower for kw in ["방문", "집으로 와서", "직접 와서"]):
        queries.append("방문판매법 청약철회 14일")
        queries.append("방문판매 등에 관한 법률 제8조")

    # 할부거래
    if any(kw in query_lower for kw in ["할부", "분할", "월납"]):
        queries.append("할부거래법 청약철회 항변권")

    # 결함/하자
    if any(kw in query_lower for kw in ["결함", "불량", "고장", "하자"]):
        queries.append("하자담보책임 민법 소비자보호")
        queries.append("제조물책임법 결함")

    # ============================================================
    # 4. 일반적인 쿼리 조합 생성
    # ============================================================
    if law_names and legal_terms and len(queries) < 4:
        queries.append(f"{law_names[0]} {' '.join(legal_terms[:3])}")

    if legal_terms and len(queries) < 5:
        queries.append(f"{' '.join(legal_terms[:4])} 소비자")

    if item and legal_terms and len(queries) < 5:
        item_legal = LEGAL_TERM_MAPPING.get(item, [item])
        queries.append(f"{item_legal[0] if item_legal else item} {legal_terms[0]} 소비자보호")

    # 기본 폴백
    if not queries:
        queries = [
            "전자상거래법 청약철회 통신판매",
            "소비자보호법 환불 청약철회",
            "소비자기본법 피해구제",
        ]

    # 중복 제거
    seen = set()
    unique_queries = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique_queries.append(q)

    logger.info(f"[Rule-based Law Queries] Generated {len(unique_queries)} queries: {unique_queries[:3]}")

    return unique_queries[:5]


# ============================================================================
# 분쟁해결기준 검색 전용 쿼리 확장 (Phase 2-10)
# ============================================================================

# 품목별 분쟁해결기준 카테고리 매핑
PRODUCT_TO_CRITERIA_CATEGORY = {
    # 전자제품
    "노트북": ["컴퓨터", "전자제품", "정보통신기기", "휴대용컴퓨터"],
    "컴퓨터": ["컴퓨터", "전자제품", "정보통신기기"],
    "핸드폰": ["이동전화기", "휴대전화", "정보통신기기", "이동통신단말장치"],
    "스마트폰": ["이동전화기", "휴대전화", "정보통신기기"],
    "TV": ["텔레비전", "전자제품", "영상기기"],
    "냉장고": ["냉장고", "가전제품", "주방가전"],
    "세탁기": ["세탁기", "가전제품", "생활가전"],
    "에어컨": ["에어컨", "가전제품", "계절가전"],
    # 의류/패션
    "옷": ["의류", "섬유제품", "패션"],
    "신발": ["신발", "의류", "패션잡화"],
    "가방": ["가방", "잡화", "패션잡화"],
    # 가구/생활
    "가구": ["가구", "생활용품"],
    "침대": ["가구", "침구", "생활용품"],
    "소파": ["가구", "생활용품"],
    # 서비스
    "헬스장": ["체육시설", "스포츠센터", "휘트니스"],
    "피트니스": ["체육시설", "스포츠센터", "휘트니스"],
    "학원": ["교육서비스", "학원"],
    "여행": ["여행", "관광", "여행서비스"],
    "이사": ["이사", "포장이사", "운송서비스"],
    # 자동차
    "자동차": ["자동차", "승용차", "차량"],
    "중고차": ["중고자동차", "자동차"],
}

# 분쟁유형별 기준 키워드 매핑
DISPUTE_TYPE_TO_CRITERIA = {
    "환불": ["환급", "청약철회", "계약해제", "대금환급", "구입가 환급"],
    "교환": ["교환", "제품교환", "동종제품 교환", "대체급부"],
    "수리": ["수리", "무상수리", "수리비", "하자보수", "A/S"],
    "보상": ["보상", "손해배상", "배상", "피해보상"],
    "해지": ["해지", "중도해지", "계약해지", "위약금"],
    "품질": ["품질불량", "하자", "성능불량", "품질보증"],
}

# 분쟁해결기준 특화 키워드
CRITERIA_KEYWORDS = [
    "분쟁해결기준",
    "소비자분쟁해결기준",
    "품목별 기준",
    "보상기준",
    "환급기준",
    "교환기준",
    "수리기준",
]


async def expand_query_for_criteria_search(
    query: str,
    item: str = "",
    channel: str = "",
    dispute_type: str = "",
    keywords: List[str] = None,
    timeout: float = 5.0,
) -> List[str]:
    """
    분쟁해결기준 검색에 특화된 쿼리 확장 (Phase 2-10)

    품목별 분쟁해결기준을 효과적으로 검색하기 위한 쿼리 변환

    Args:
        query: 원본 사용자 쿼리
        item: 품목 (예: 노트북, 핸드폰)
        channel: 구매채널 (예: 온라인, 방문판매)
        dispute_type: 분쟁유형 (예: 환불, 교환)
        keywords: 추출된 키워드 목록
        timeout: LLM 호출 타임아웃 (초)

    Returns:
        분쟁해결기준 검색에 최적화된 쿼리 목록
    """
    keywords = keywords or []

    # 규칙 기반 쿼리 생성 (빠르고 안정적)
    rule_based_queries = _generate_criteria_queries_rule_based(
        query, item, channel, dispute_type, keywords
    )

    return rule_based_queries


def _generate_criteria_queries_rule_based(
    query: str,
    item: str,
    channel: str,
    dispute_type: str,
    keywords: List[str],
) -> List[str]:
    """
    규칙 기반 분쟁해결기준 쿼리 생성

    핵심 전략: 품목 카테고리 + 분쟁유형으로 직접 검색
    """
    queries = []
    query_lower = query.lower()

    # 1. 품목에서 분쟁해결기준 카테고리 추출
    criteria_categories = []
    detected_item = item

    # 쿼리에서 품목 감지
    if not detected_item:
        for product, categories in PRODUCT_TO_CRITERIA_CATEGORY.items():
            if product in query_lower:
                detected_item = product
                criteria_categories = categories
                break

    # item 파라미터로 카테고리 찾기
    if detected_item and not criteria_categories:
        criteria_categories = PRODUCT_TO_CRITERIA_CATEGORY.get(detected_item, [detected_item])

    # 2. 분쟁유형에서 기준 키워드 추출
    criteria_keywords = []
    detected_dispute = dispute_type

    # 쿼리에서 분쟁유형 감지
    if not detected_dispute:
        if any(kw in query_lower for kw in ["환불", "반품", "취소"]):
            detected_dispute = "환불"
        elif any(kw in query_lower for kw in ["교환", "바꿔"]):
            detected_dispute = "교환"
        elif any(kw in query_lower for kw in ["수리", "고장", "A/S", "as"]):
            detected_dispute = "수리"
        elif any(kw in query_lower for kw in ["보상", "배상", "피해"]):
            detected_dispute = "보상"
        elif any(kw in query_lower for kw in ["해지", "탈퇴", "취소"]):
            detected_dispute = "해지"

    if detected_dispute:
        criteria_keywords = DISPUTE_TYPE_TO_CRITERIA.get(detected_dispute, [detected_dispute])

    # ============================================================
    # 3. 핵심 쿼리 생성
    # ============================================================

    # 품목 + 분쟁유형 조합 (가장 중요)
    if criteria_categories and criteria_keywords:
        queries.append(f"{criteria_categories[0]} {criteria_keywords[0]} 분쟁해결기준")
        queries.append(f"{criteria_categories[0]} {criteria_keywords[0]} 소비자분쟁해결기준")

    # 품목 기반 검색
    if criteria_categories:
        queries.append(f"{criteria_categories[0]} 분쟁해결기준 보상")
        if len(criteria_categories) > 1:
            queries.append(f"{criteria_categories[1]} 품목별 기준")

    # 분쟁유형 기반 검색
    if criteria_keywords:
        queries.append(f"소비자분쟁해결기준 {criteria_keywords[0]}")

    # 전자상거래 특화 (온라인 구매인 경우)
    is_online = any(kw in query_lower for kw in ["온라인", "인터넷", "쿠팡", "배달", "통신판매"])
    if is_online:
        queries.append("전자상거래 청약철회 분쟁해결기준")
        queries.append("통신판매 환불 기준 7일")

    # 품질보증 관련
    if any(kw in query_lower for kw in ["품질", "하자", "불량", "고장"]):
        queries.append("품질보증기간 하자 분쟁해결기준")

    # 기본 폴백
    if not queries:
        if detected_item:
            queries = [
                f"{detected_item} 분쟁해결기준",
                f"{detected_item} 환불 교환 기준",
                "소비자분쟁해결기준 품목별",
            ]
        else:
            queries = [
                "소비자분쟁해결기준 환불 교환",
                "품목별 분쟁해결기준",
                "청약철회 분쟁해결기준",
            ]

    # 중복 제거
    seen = set()
    unique_queries = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique_queries.append(q)

    logger.info(f"[Rule-based Criteria Queries] Generated {len(unique_queries)} queries: {unique_queries[:3]}")

    return unique_queries[:5]


__all__ = [
    "expand_query_with_llm",
    "expand_query_with_llm_sync",
    "QUERY_EXPANSION_SYSTEM_PROMPT",
    "QUERY_EXPANSION_USER_PROMPT",
    # Phase 2-10: 법령 검색 전용 확장
    "expand_query_for_law_search",
    "LEGAL_TERM_MAPPING",
    "SITUATION_TO_LAWS",
    # Phase 2-10: 분쟁해결기준 검색 전용 확장
    "expand_query_for_criteria_search",
    "PRODUCT_TO_CRITERIA_CATEGORY",
    "DISPUTE_TYPE_TO_CRITERIA",
]
