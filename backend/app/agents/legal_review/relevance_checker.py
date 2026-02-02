"""
똑소리 프로젝트 - 관련성 검증 모듈 (Relevance Checker)

작성일: 2026-01-27

[역할 및 책임]
Query-Answer, Query-Retrieval 간의 의미적 관련성을 검증합니다.
text-embedding-3-large (1536d) 임베딩 기반 cosine similarity를 사용합니다.

[주요 기능]
1. Query-Answer 관련성 검증: 답변이 질문에 적절히 답하고 있는지 확인
2. Query-Retrieval 관련성 검증: 검색된 문서가 질문과 관련있는지 확인
3. Answer-Source 관련성 검증: 답변이 검색된 출처에 기반하는지 확인
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RelevanceResult:
    """
    관련성 검증 결과

    Attributes:
        passed: 임계값 이상 통과 여부
        score: 유사도 점수 (0.0 ~ 1.0)
        threshold: 적용된 임계값
        message: 검증 결과 메시지 (실패 시 상세 설명)
    """

    passed: bool
    score: float
    threshold: float
    message: Optional[str] = None


@dataclass
class CitationVerifyResult:
    """
    인용 정확성 검증 결과

    Attributes:
        passed: 모든 인용이 유효한지 여부
        cited_laws: 답변에서 발견된 법령/조문 리스트
        verified_laws: 검색 결과에서 확인된 법령/조문 리스트
        unverified_laws: 검색 결과에서 확인되지 않은 법령/조문 (Hallucination 의심)
        accuracy: 인용 정확도 (verified / cited)
    """

    passed: bool
    cited_laws: List[str]
    verified_laws: List[str]
    unverified_laws: List[str]
    accuracy: float


class RelevanceChecker:
    """
    의미적 관련성 검증기

    text-embedding-3-large (1536d)를 사용하여 텍스트 간 유사도를 측정합니다.

    Usage:
        checker = RelevanceChecker()
        result = checker.check_query_answer_relevance(query, answer)
        if not result.passed:
            # 관련성 부족 처리
    """

    def __init__(self, use_openai: bool = True):
        """
        RelevanceChecker 초기화

        Args:
            use_openai: OpenAI 임베딩 사용 여부 (True: text-embedding-3-large)
        """
        self._client = None
        self._use_openai = use_openai

    def _get_client(self):
        """지연 초기화로 EmbeddingClient 로드"""
        if self._client is None:
            try:
                from app.agents.retrieval.tools.embedding_client import EmbeddingClient

                self._client = EmbeddingClient()
                logger.info(
                    "[RelevanceChecker] EmbeddingClient initialized (text-embedding-3-large)"
                )
            except Exception as e:
                logger.error(
                    f"[RelevanceChecker] Failed to initialize EmbeddingClient: {e}"
                )
                raise
        return self._client

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        두 벡터 간 코사인 유사도 계산

        Args:
            vec1: 첫 번째 임베딩 벡터
            vec2: 두 번째 임베딩 벡터

        Returns:
            유사도 점수 (0.0 ~ 1.0)
        """
        a = np.array(vec1)
        b = np.array(vec2)

        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(dot_product / (norm_a * norm_b))

    def check_query_answer_relevance(
        self, query: str, answer: str, threshold: float = 0.5
    ) -> RelevanceResult:
        """
        Query-Answer 관련성 검증

        사용자 질문과 생성된 답변 간의 의미적 유사도를 측정합니다.
        임계값 미달 시 주제 이탈(off-topic) 가능성이 있습니다.

        Args:
            query: 사용자 질문
            answer: 생성된 답변
            threshold: 통과 임계값 (기본: 0.5)

        Returns:
            RelevanceResult: 검증 결과
        """
        if not query or not answer:
            return RelevanceResult(
                passed=False,
                score=0.0,
                threshold=threshold,
                message="Query 또는 Answer가 비어있습니다.",
            )

        try:
            client = self._get_client()

            # 임베딩 생성 (배치로 한 번에)
            embeddings = client.embed([query, answer])
            q_emb = embeddings[0]
            a_emb = embeddings[1]

            # 코사인 유사도 계산
            similarity = self._cosine_similarity(q_emb, a_emb)

            passed = similarity >= threshold
            message = (
                None
                if passed
                else f"Query-Answer 관련성 부족 (score={similarity:.3f} < threshold={threshold})"
            )

            logger.debug(
                f"[RelevanceChecker] Query-Answer relevance: "
                f"score={similarity:.3f}, threshold={threshold}, passed={passed}"
            )

            return RelevanceResult(
                passed=passed, score=similarity, threshold=threshold, message=message
            )

        except Exception as e:
            logger.error(f"[RelevanceChecker] Query-Answer relevance check failed: {e}")
            # 임베딩 실패 시 통과 처리 (graceful degradation)
            return RelevanceResult(
                passed=True,
                score=0.0,
                threshold=threshold,
                message=f"임베딩 실패로 검증 생략: {str(e)}",
            )

    def check_retrieval_relevance(
        self, query: str, chunks: List[str], threshold: float = 0.4
    ) -> RelevanceResult:
        """
        Query-Retrieval 관련성 검증

        사용자 질문과 검색된 문서 청크 간의 관련성을 측정합니다.
        검색 결과가 질문과 무관할 경우 잘못된 정보 기반 답변 생성 위험이 있습니다.

        Args:
            query: 사용자 질문
            chunks: 검색된 문서 청크 텍스트 리스트
            threshold: 통과 임계값 (기본: 0.4)

        Returns:
            RelevanceResult: 검증 결과 (최고 유사도 기준)
        """
        if not query:
            return RelevanceResult(
                passed=False,
                score=0.0,
                threshold=threshold,
                message="Query가 비어있습니다.",
            )

        if not chunks:
            # 검색 결과가 없는 경우 통과 (검색 실패는 별도 처리)
            return RelevanceResult(
                passed=True, score=0.0, threshold=threshold, message="검색 결과 없음"
            )

        try:
            client = self._get_client()

            # 쿼리 임베딩
            q_emb = client.embed_query(query)

            # 청크 임베딩 (배치)
            chunk_embeddings = client.embed(chunks)

            # 각 청크와의 유사도 계산
            similarities = [
                self._cosine_similarity(q_emb, c_emb) for c_emb in chunk_embeddings
            ]

            max_similarity = max(similarities) if similarities else 0.0
            avg_similarity = (
                sum(similarities) / len(similarities) if similarities else 0.0
            )

            passed = max_similarity >= threshold
            message = (
                None
                if passed
                else (
                    f"검색 결과와 Query 관련성 부족 "
                    f"(max={max_similarity:.3f} < threshold={threshold})"
                )
            )

            logger.debug(
                f"[RelevanceChecker] Query-Retrieval relevance: "
                f"max={max_similarity:.3f}, avg={avg_similarity:.3f}, passed={passed}"
            )

            return RelevanceResult(
                passed=passed,
                score=max_similarity,
                threshold=threshold,
                message=message,
            )

        except Exception as e:
            logger.error(
                f"[RelevanceChecker] Query-Retrieval relevance check failed: {e}"
            )
            return RelevanceResult(
                passed=True,
                score=0.0,
                threshold=threshold,
                message=f"임베딩 실패로 검증 생략: {str(e)}",
            )

    def check_answer_source_relevance(
        self, answer: str, chunks: List[str], threshold: float = 0.45
    ) -> RelevanceResult:
        """
        Answer-Source 관련성 검증

        생성된 답변이 검색된 출처 문서에 기반하는지 검증합니다.
        유사도가 낮으면 Hallucination 가능성이 있습니다.

        Args:
            answer: 생성된 답변
            chunks: 검색된 문서 청크 텍스트 리스트
            threshold: 통과 임계값 (기본: 0.45)

        Returns:
            RelevanceResult: 검증 결과 (최고 유사도 기준)
        """
        if not answer:
            return RelevanceResult(
                passed=False,
                score=0.0,
                threshold=threshold,
                message="Answer가 비어있습니다.",
            )

        if not chunks:
            # 출처가 없는 경우 (일반 대화 등) 통과
            return RelevanceResult(
                passed=True, score=0.0, threshold=threshold, message="출처 문서 없음"
            )

        try:
            client = self._get_client()

            # 답변 임베딩
            a_emb = client.embed_query(answer)

            # 청크 임베딩 (배치)
            chunk_embeddings = client.embed(chunks)

            # 각 청크와의 유사도 계산
            similarities = [
                self._cosine_similarity(a_emb, c_emb) for c_emb in chunk_embeddings
            ]

            max_similarity = max(similarities) if similarities else 0.0

            passed = max_similarity >= threshold
            message = (
                None
                if passed
                else (
                    f"Answer가 출처와 관련성 부족 - Hallucination 의심 "
                    f"(max={max_similarity:.3f} < threshold={threshold})"
                )
            )

            logger.debug(
                f"[RelevanceChecker] Answer-Source relevance: "
                f"max={max_similarity:.3f}, passed={passed}"
            )

            return RelevanceResult(
                passed=passed,
                score=max_similarity,
                threshold=threshold,
                message=message,
            )

        except Exception as e:
            logger.error(
                f"[RelevanceChecker] Answer-Source relevance check failed: {e}"
            )
            return RelevanceResult(
                passed=True,
                score=0.0,
                threshold=threshold,
                message=f"임베딩 실패로 검증 생략: {str(e)}",
            )


# 싱글톤 인스턴스
_relevance_checker: Optional[RelevanceChecker] = None


def get_relevance_checker() -> RelevanceChecker:
    """
    RelevanceChecker 싱글톤 인스턴스 반환

    Returns:
        RelevanceChecker: 관련성 검증기 인스턴스
    """
    global _relevance_checker
    if _relevance_checker is None:
        _relevance_checker = RelevanceChecker()
    return _relevance_checker


__all__ = [
    "RelevanceResult",
    "CitationVerifyResult",
    "RelevanceChecker",
    "get_relevance_checker",
]
