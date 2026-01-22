"""
똑소리 프로젝트 - LLM 기반 쿼리 재작성 모듈
작성일: 2026-01-17
S2-10: LLM 기반 쿼리 재작성 (Phase 3)

EXAONE 3.5 2.4B를 사용하여 복잡한 법률 용어를 일상어로 변환.
100ms 하드 타임아웃으로 지연시간 제약 보장.
타임아웃/에러 시 규칙 기반 폴백.
"""

import asyncio
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Tuple

from .exaone_client import ExaoneLLMClient, LLMUnavailableError
from .query_cache import QueryCache, COMMON_REWRITES

logger = logging.getLogger(__name__)

# 설정 (환경 변수)
QUERY_REWRITE_ENABLED = os.getenv('QUERY_REWRITE_ENABLED', 'true').lower() == 'true'
QUERY_REWRITE_CACHE_SIZE = int(os.getenv('QUERY_REWRITE_CACHE_SIZE', '1000'))
QUERY_REWRITE_TIMEOUT_MS = int(os.getenv('QUERY_REWRITE_TIMEOUT', '10000'))  # 10초
QUERY_REWRITE_MIN_COMPLEXITY = int(os.getenv('QUERY_REWRITE_MIN_COMPLEXITY', '1'))

# 법률 용어 목록 (복잡도 판단용)
LEGAL_TERMS = {
    # 계약/거래
    "청약철회", "청약철회권", "계약해제", "계약해지", "중도해지",
    "채무불이행", "이행지체", "이행불능", "불완전이행",

    # 책임
    "하자담보책임", "하자담보", "손해배상", "연대책임", "면책",
    "담보책임", "귀책사유", "과실상계",

    # 보상/배상
    "위약금", "위약벌", "지연손해금", "원상회복", "부당이득",

    # 기간
    "소멸시효", "제척기간", "유예기간", "숙려기간", "철회기간",

    # 거래 유형
    "전자상거래", "통신판매", "방문판매", "할부거래",
    "선불식할부거래", "다단계판매", "후원방문판매",

    # 약관/계약
    "약관", "불공정약관", "표시광고", "허위과장광고",
    "부당한표시광고", "기만적광고",

    # 분쟁
    "분쟁조정", "피해구제", "조정결정", "합의",
    "이의신청", "재조정",

    # 금융
    "채권", "채무", "채권자", "채무자", "담보", "보증",
    "연대보증", "근저당", "질권",

    # 법률 절차
    "준거법", "관할법원", "제소", "내용증명",
    "민사조정", "소액사건", "지급명령",

    # 기타
    "소비자기본법", "전자상거래법", "할부거래법", "방문판매법",
    "표시광고법", "약관규제법", "제조물책임법",
}

# 시스템 프롬프트
QUERY_REWRITE_SYSTEM_PROMPT = """당신은 소비자 분쟁 상담 검색 시스템의 쿼리 변환기입니다.
사용자의 법률 용어나 복잡한 표현을 일반인이 사용하는 쉬운 한국어로 변환하세요.

규칙:
1. 법률 용어를 일상어로 변환: 청약철회권 → 구매 취소, 채무불이행 → 약속 안 지킴
2. 핵심 키워드 유지: 품목명, 금액, 기간 등은 그대로 유지
3. 검색에 최적화된 짧은 문장으로 변환 (10-30자)
4. 원래 의도를 왜곡하지 않음
5. 반드시 변환된 쿼리만 출력 (설명 없이)

예시:
입력: "전자상거래 등에서의 소비자보호에 관한 법률 제17조에 따른 청약철회권 행사 가능 여부"
출력: 온라인 쇼핑 구매 취소 환불 가능한지

입력: "채무불이행으로 인한 손해배상 청구 가능한가요"
출력: 약속 안 지켜서 피해 보상 받을 수 있나요

입력: "하자담보책임 기간이 지났는데 환불 가능한지"
출력: 불량 제품 책임 기간 지났는데 환불 가능한지"""


class QueryRewriter:
    """
    LLM 기반 쿼리 재작성기

    복잡한 법률 용어가 포함된 사용자 쿼리를 일상어로 변환하여
    검색 품질을 향상시킴.

    주요 기능:
    1. 복잡도 판단: 법률 용어, 쿼리 길이, 문체 분석
    2. 캐시: LRU 캐시 + pre-seeded 법률 용어 매핑
    3. 타임아웃: 90ms 하드 타임아웃, 초과 시 규칙 기반 폴백
    4. 폴백: LLM 에러/타임아웃 시 규칙 기반 대체 결과 반환

    Attributes:
        enabled: 기능 활성화 여부 (환경 변수)
        cache: QueryCache 인스턴스
        client: ExaoneLLMClient 인스턴스

    Example:
        >>> rewriter = QueryRewriter()
        >>> if rewriter.is_complex_query("청약철회권 행사", "dispute"):
        ...     result = rewriter.rewrite("청약철회권 행사 가능한가요", {})
        ...     print(result)
        '구매 취소 환불 가능한가요'
    """

    def __init__(self):
        """QueryRewriter 초기화"""
        self.enabled = QUERY_REWRITE_ENABLED
        self.cache = QueryCache(maxsize=QUERY_REWRITE_CACHE_SIZE)
        self.timeout_ms = QUERY_REWRITE_TIMEOUT_MS
        self.min_complexity = QUERY_REWRITE_MIN_COMPLEXITY

        # LLM 클라이언트는 지연 초기화 (필요할 때만)
        self._client: Optional[ExaoneLLMClient] = None
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="query_rewrite")

        logger.info(
            f"[QueryRewriter] Initialized - enabled={self.enabled}, "
            f"timeout={self.timeout_ms}ms, min_complexity={self.min_complexity}"
        )

    def _get_client(self) -> ExaoneLLMClient:
        """LLM 클라이언트 반환 (지연 초기화)"""
        if self._client is None:
            self._client = ExaoneLLMClient()
        return self._client

    def is_complex_query(self, query: str, query_type: str) -> bool:
        """
        쿼리가 LLM 재작성이 필요할 만큼 복잡한지 판단

        복잡한 쿼리의 기준:
        1. 법률 용어가 1개 이상 포함 (설정 가능)
        2. 쿼리 길이가 50자 초과
        3. 격식체 문장 종결 표현 사용

        Args:
            query: 사용자 쿼리
            query_type: 쿼리 유형 ('dispute', 'law', 'criteria', 'general')

        Returns:
            LLM 재작성이 필요하면 True
        """
        # 기능 비활성화 시 항상 False
        if not self.enabled:
            return False

        # 일반 대화는 재작성 불필요
        if query_type == 'general':
            return False

        # 법률 용어 개수 확인
        legal_term_count = sum(1 for term in LEGAL_TERMS if term in query)
        if legal_term_count >= self.min_complexity:
            logger.debug(f"[QueryRewriter] Complex - legal terms: {legal_term_count}")
            return True

        # 긴 쿼리는 복잡할 가능성 높음
        if len(query) > 50:
            logger.debug(f"[QueryRewriter] Complex - long query: {len(query)} chars")
            return True

        # 격식체 종결 표현 (공식 문서 스타일)
        formal_endings = ['입니다', '습니다', '하는지', '인지', '여부', '가능한지']
        if any(ending in query for ending in formal_endings):
            logger.debug(f"[QueryRewriter] Complex - formal style detected")
            return True

        return False

    def _rule_based_rewrite(self, query: str, context: Dict) -> Tuple[str, bool]:
        """
        규칙 기반 쿼리 재작성 (폴백용)

        LLM 타임아웃/에러 시 사용되는 간단한 규칙 기반 대체.
        pre-seeded 법률 용어 매핑을 활용하여 부분 치환.

        Args:
            query: 원본 쿼리
            context: 추가 컨텍스트 (미사용)

        Returns:
            (재작성된 쿼리, 변경 여부)
        """
        result = query
        changed = False

        # COMMON_REWRITES에서 용어 치환
        for term, replacement in COMMON_REWRITES.items():
            if term in result:
                result = result.replace(term, replacement)
                changed = True

        # 불필요한 접미사 제거
        suffix_patterns = [
            r'[해주세요|알려주세요|싶어요]$',
            r'[?？!！。]+$',
        ]
        for pattern in suffix_patterns:
            new_result = re.sub(pattern, '', result)
            if new_result != result:
                result = new_result.strip()
                changed = True

        return result, changed

    def _call_exaone(self, query: str, context: Dict) -> str:
        """
        EXAONE LLM 호출 (동기)

        ThreadPoolExecutor에서 실행될 동기 메서드.

        Args:
            query: 재작성할 쿼리
            context: 추가 컨텍스트 (query_type 등)

        Returns:
            재작성된 쿼리
        """
        client = self._get_client()

        # 컨텍스트 정보 추가 (있는 경우)
        user_prompt = query
        if context.get('query_type'):
            user_prompt = f"[질의 유형: {context['query_type']}] {query}"

        response = client.generate(
            system_prompt=QUERY_REWRITE_SYSTEM_PROMPT,
            user_prompt=user_prompt
        )

        # 응답 정리 (앞뒤 공백, 따옴표 제거)
        result = response.strip().strip('"\'')

        # 너무 긴 응답은 잘라내기 (검색 쿼리는 짧아야 함)
        if len(result) > 100:
            result = result[:100]

        return result

    async def rewrite_async(self, query: str, context: Dict) -> str:
        """
        비동기 쿼리 재작성 (타임아웃 적용)

        90ms 하드 타임아웃으로 LLM 호출.
        타임아웃/에러 시 규칙 기반 폴백.

        Args:
            query: 재작성할 쿼리
            context: 추가 컨텍스트

        Returns:
            재작성된 쿼리
        """
        start_time = time.time()

        # 1. 캐시 확인 (1-2ms)
        cached = self.cache.get(query)
        if cached:
            elapsed = (time.time() - start_time) * 1000
            logger.debug(f"[QueryRewriter] Cache hit in {elapsed:.1f}ms")
            return cached

        # 2. LLM 기능 비활성화 시 규칙 기반만 사용
        if not self.enabled:
            result, _ = self._rule_based_rewrite(query, context)
            return result

        # 3. LLM 호출 (타임아웃 적용)
        timeout_sec = self.timeout_ms / 1000.0

        try:
            loop = asyncio.get_event_loop()
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    self._executor,
                    self._call_exaone,
                    query, context
                ),
                timeout=timeout_sec
            )

            # 캐시에 저장
            self.cache.set(query, result)

            elapsed = (time.time() - start_time) * 1000
            logger.info(f"[QueryRewriter] LLM rewrite in {elapsed:.1f}ms: {query[:30]}... -> {result[:30]}...")

            return result

        except asyncio.TimeoutError:
            elapsed = (time.time() - start_time) * 1000
            logger.warning(f"[QueryRewriter] Timeout ({elapsed:.1f}ms > {self.timeout_ms}ms), using rule-based")

            result, _ = self._rule_based_rewrite(query, context)
            return result

        except LLMUnavailableError as e:
            logger.warning(f"[QueryRewriter] LLM unavailable: {e}, using rule-based")
            result, _ = self._rule_based_rewrite(query, context)
            return result

        except Exception as e:
            logger.error(f"[QueryRewriter] Unexpected error: {e}, using rule-based")
            result, _ = self._rule_based_rewrite(query, context)
            return result

    def rewrite(self, query: str, context: Dict) -> str:
        """
        동기 쿼리 재작성 (기존 코드 호환용)

        내부적으로 비동기 메서드를 호출.
        이미 이벤트 루프가 실행 중이면 ThreadPool 사용.

        Args:
            query: 재작성할 쿼리
            context: 추가 컨텍스트

        Returns:
            재작성된 쿼리
        """
        start_time = time.time()

        # 1. 캐시 확인
        cached = self.cache.get(query)
        if cached:
            elapsed = (time.time() - start_time) * 1000
            logger.debug(f"[QueryRewriter] Cache hit in {elapsed:.1f}ms")
            return cached

        # 2. LLM 기능 비활성화 시 규칙 기반만 사용
        if not self.enabled:
            result, _ = self._rule_based_rewrite(query, context)
            return result

        # 3. 이벤트 루프 확인 및 실행
        try:
            loop = asyncio.get_running_loop()
            # 이미 루프가 실행 중이면 ThreadPool에서 동기 호출
            import concurrent.futures
            future = self._executor.submit(self._sync_rewrite_with_timeout, query, context)
            try:
                result = future.result(timeout=self.timeout_ms / 1000.0 + 0.01)
                return result
            except concurrent.futures.TimeoutError:
                logger.warning(f"[QueryRewriter] Sync timeout, using rule-based")
                result, _ = self._rule_based_rewrite(query, context)
                return result
        except RuntimeError:
            # 루프가 없으면 새로 생성
            return asyncio.run(self.rewrite_async(query, context))

    def _sync_rewrite_with_timeout(self, query: str, context: Dict) -> str:
        """내부용 동기 재작성 (타임아웃 없음)"""
        try:
            result = self._call_exaone(query, context)
            self.cache.set(query, result)
            return result
        except Exception as e:
            logger.warning(f"[QueryRewriter] LLM error in sync: {e}")
            result, _ = self._rule_based_rewrite(query, context)
            return result

    def get_stats(self) -> dict:
        """
        통계 반환

        Returns:
            dict: {
                'enabled': 기능 활성화 여부,
                'timeout_ms': 타임아웃 설정,
                'cache': 캐시 통계
            }
        """
        return {
            'enabled': self.enabled,
            'timeout_ms': self.timeout_ms,
            'cache': self.cache.get_stats()
        }


# 싱글톤 인스턴스 (지연 초기화)
_rewriter_instance: Optional[QueryRewriter] = None
_rewriter_lock = asyncio.Lock() if hasattr(asyncio, 'Lock') else None


def get_query_rewriter() -> QueryRewriter:
    """
    QueryRewriter 싱글톤 인스턴스 반환

    애플리케이션 전체에서 단일 인스턴스를 공유하여
    캐시 효율성 극대화.

    Returns:
        QueryRewriter 인스턴스
    """
    global _rewriter_instance

    if _rewriter_instance is None:
        _rewriter_instance = QueryRewriter()

    return _rewriter_instance
