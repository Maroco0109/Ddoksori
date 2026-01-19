"""
똑소리 프로젝트 - 쿼리 캐시 모듈
작성일: 2026-01-17
S2-10: LLM 기반 쿼리 재작성 (Phase 3)

LLM 기반 쿼리 재작성 결과를 캐싱하여 지연시간을 줄이고,
자주 사용되는 법률 용어 변환을 pre-seed하여 캐시 히트율을 높임.
"""

import hashlib
import logging
import re
import threading
from collections import OrderedDict
from typing import Optional

logger = logging.getLogger(__name__)


# Pre-seeded 법률 용어 → 일상어 매핑 (50+ common patterns)
COMMON_REWRITES = {
    # 계약 관련
    "청약철회": "구매 취소 환불",
    "청약철회권": "구매 취소 권리 환불",
    "청약철회권 행사": "구매 취소 환불 요청",
    "계약해제": "계약 취소",
    "계약해지": "계약 종료 해지",
    "중도해지": "중간에 해지 취소",
    "채무불이행": "약속 안 지킴 계약 위반",
    "이행지체": "약속 시간 지연 늦음",
    "이행불능": "약속 이행 불가",

    # 책임 관련
    "하자담보책임": "불량 제품 책임 수리 교환",
    "손해배상": "피해 보상",
    "손해배상 청구": "피해 보상 요청",
    "연대책임": "함께 책임",
    "면책": "책임 없음 면제",
    "면책 조항": "책임 면제 조건",

    # 보상/배상 관련
    "위약금": "취소 수수료 벌금",
    "위약벌": "취소 벌금",
    "지연손해금": "늦어서 내는 이자",
    "원상회복": "원래대로 돌려놓기",

    # 기간 관련
    "소멸시효": "청구 기한 만료",
    "제척기간": "권리 행사 기한",
    "유예기간": "기다리는 기간",

    # 거래 관련
    "전자상거래": "온라인 쇼핑 인터넷 구매",
    "통신판매": "전화 인터넷 판매",
    "방문판매": "집으로 찾아와서 판매",
    "할부거래": "나눠서 결제",
    "선불식할부거래": "미리 돈 내고 나중에 받기",

    # 소비자 권리
    "소비자 기본권": "소비자 권리",
    "약관": "계약 조건 규정",
    "불공정약관": "불공정한 계약 조건",
    "표시광고": "광고 표시",
    "허위과장광고": "거짓 과장 광고",

    # 분쟁 해결
    "분쟁조정": "분쟁 해결 조정",
    "피해구제": "피해 해결 보상",
    "합의": "서로 동의 협의",
    "조정결정": "조정 결과 결정",

    # 금융 관련
    "채권": "돈 받을 권리",
    "채무": "돈 갚을 의무",
    "채권자": "돈 받을 사람",
    "채무자": "돈 갚을 사람",
    "담보": "보증 담보물",
    "보증": "책임 보장",

    # 기타 법률 용어
    "준거법": "적용되는 법",
    "관할법원": "담당 법원",
    "제소": "소송 제기",
    "내용증명": "공식 통보 서류",
}


class QueryCache:
    """
    쿼리 재작성 결과 LRU 캐시

    LLM 기반 쿼리 재작성 결과를 캐싱하여:
    1. 동일 쿼리에 대한 반복 LLM 호출 방지
    2. 캐시 히트 시 1-2ms 이내 응답
    3. Pre-seeded 법률 용어로 초기 캐시 히트율 향상

    Thread-safe 구현으로 동시 요청 처리 가능.

    Attributes:
        maxsize: 최대 캐시 크기 (기본: 1000)

    Example:
        >>> cache = QueryCache(maxsize=500)
        >>> cache.get("청약철회권")  # Pre-seeded
        '구매 취소 권리 환불'
        >>> cache.set("복잡한 법률 질문", "간단한 질문")
        >>> cache.get("복잡한 법률 질문")
        '간단한 질문'
    """

    def __init__(self, maxsize: int = 1000):
        """
        캐시 초기화

        Args:
            maxsize: 최대 캐시 크기 (기본: 1000)
        """
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._maxsize = maxsize
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0

        # Pre-seed 법률 용어 매핑
        self._preseed_common_rewrites()

        logger.info(f"[QueryCache] Initialized with maxsize={maxsize}, pre-seeded={len(COMMON_REWRITES)}")

    def _preseed_common_rewrites(self) -> None:
        """Pre-seed 공통 법률 용어 매핑"""
        for term, rewrite in COMMON_REWRITES.items():
            key = self._hash_query(term)
            self._cache[key] = rewrite

    def _hash_query(self, query: str) -> str:
        """
        쿼리 정규화 및 해시

        쿼리를 정규화하여 약간의 변형도 같은 캐시 키로 매핑:
        1. 소문자 변환 (한글은 영향 없음)
        2. 연속 공백 제거
        3. 앞뒤 공백 제거
        4. 일반적인 접미사 제거

        Args:
            query: 원본 쿼리

        Returns:
            정규화된 쿼리의 MD5 해시
        """
        # 정규화
        normalized = query.lower().strip()
        normalized = re.sub(r'\s+', ' ', normalized)

        # 일반적인 접미사 제거 (캐시 히트율 향상)
        suffix_patterns = [
            r'[해주세요|알려주세요|싶어요|인가요|할까요|있나요|있어요|될까요]$',
            r'[?？!！。\.]+$',
        ]
        for pattern in suffix_patterns:
            normalized = re.sub(pattern, '', normalized)

        normalized = normalized.strip()

        # MD5 해시 (빠른 조회용)
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()

    def get(self, query: str) -> Optional[str]:
        """
        캐시에서 재작성된 쿼리 조회

        LRU 동작: 조회된 항목은 가장 최근 사용으로 이동.

        Args:
            query: 원본 쿼리

        Returns:
            캐시된 재작성 결과, 없으면 None
        """
        key = self._hash_query(query)

        with self._lock:
            if key in self._cache:
                # LRU: 가장 최근 사용으로 이동
                self._cache.move_to_end(key)
                self._hits += 1
                result = self._cache[key]
                logger.debug(f"[QueryCache] Hit: {query[:30]}... -> {result[:30]}...")
                return result
            else:
                self._misses += 1
                return None

    def set(self, query: str, rewritten: str) -> None:
        """
        재작성 결과를 캐시에 저장

        LRU 동작: 캐시가 가득 차면 가장 오래된 항목 제거.

        Args:
            query: 원본 쿼리
            rewritten: 재작성된 쿼리
        """
        key = self._hash_query(query)

        with self._lock:
            if key in self._cache:
                # 기존 항목 업데이트 및 최근 사용으로 이동
                self._cache.move_to_end(key)
                self._cache[key] = rewritten
            else:
                # 새 항목 추가
                self._cache[key] = rewritten

                # LRU: 크기 초과 시 가장 오래된 항목 제거
                while len(self._cache) > self._maxsize:
                    oldest = next(iter(self._cache))
                    del self._cache[oldest]

        logger.debug(f"[QueryCache] Set: {query[:30]}... -> {rewritten[:30]}...")

    def get_stats(self) -> dict:
        """
        캐시 통계 반환

        Returns:
            dict: {
                'size': 현재 캐시 크기,
                'maxsize': 최대 크기,
                'hits': 캐시 히트 수,
                'misses': 캐시 미스 수,
                'hit_rate': 히트율 (0.0-1.0)
            }
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0

            return {
                'size': len(self._cache),
                'maxsize': self._maxsize,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': hit_rate
            }

    def clear(self) -> None:
        """캐시 초기화 (통계 유지)"""
        with self._lock:
            self._cache.clear()
            # Pre-seed 다시 로드
            self._preseed_common_rewrites()

        logger.info("[QueryCache] Cleared (pre-seeded rewrites restored)")
