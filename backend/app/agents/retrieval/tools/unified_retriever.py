"""
UnifiedRetriever - SQL search_hybrid_rrf() 기반 통합 검색

모든 Retrieval Agent가 동일한 검색 로직을 사용합니다.
- BM25 + Vector + RRF 하이브리드 검색
- PostgreSQL search_hybrid_rrf() 함수 호출
- OpenAI text-embedding-3-large (1536-dim) 임베딩

사전 조건:
- vector_chunks 테이블 존재
- search_hybrid_rrf SQL 함수 생성 (004_add_rrf_search_functions.sql)
"""

import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, cast

import psycopg2
from psycopg2.extras import RealDictCursor

from .retriever import SearchResult, _to_category_path

logger = logging.getLogger(__name__)


# ============================================================
# Phase 2-1: 동적 RRF k값 결정 함수
# ============================================================
def determine_rrf_k(query: str, query_analysis: Optional[Dict] = None) -> int:
    """
    쿼리 유형에 따른 RRF k값 동적 결정

    - k값 낮음 → BM25(키워드) 가중치 ↑ (법령 직접 참조에 적합)
    - k값 높음 → Vector(의미) 가중치 ↑ (일반 질문에 적합)

    Args:
        query: 사용자 쿼리
        query_analysis: 쿼리 분석 결과 (mode, query_type 등)

    Returns:
        int: 40~80 범위의 k값
    """
    # 1. 법령 직접 참조 패턴 (BM25 우선 → k 낮춤)
    law_patterns = [
        r"제?\d+조",  # 제16조, 16조
        r"법\s*제?\d+",  # 법 제16
        r"시행령|시행규칙",
        r"소비자기본법|전자상거래법|할부거래법|방문판매법",
        r"별표\s*\d+",  # 별표 1
    ]

    for pattern in law_patterns:
        if re.search(pattern, query):
            logger.debug(f"[RRF-k] Law pattern matched: k=40")
            return 40

    # 2. query_analysis 기반 판단
    if query_analysis:
        mode = query_analysis.get("mode", "")
        query_type = query_analysis.get("query_type", "")

        if query_type == "law_direct":
            logger.debug(f"[RRF-k] query_type=law_direct: k=40")
            return 40
        elif query_type == "criteria":
            logger.debug(f"[RRF-k] query_type=criteria: k=50")
            return 50
        elif mode in ["case_search", "general"]:
            logger.debug(f"[RRF-k] mode={mode}: k=80")
            return 80

    # 3. 기본값
    logger.debug(f"[RRF-k] Default: k=60")
    return 60


# ============================================================
# Phase 2-1: 동적 유사도 임계값 함수
# ============================================================
def adaptive_similarity_threshold(
    results: List["SearchResult"],
    min_results: int = 3,
    min_threshold: float = 0.35,
    max_threshold: float = 0.70,
) -> float:
    """
    검색 결과 품질 기반 동적 유사도 임계값 결정

    최고 유사도의 70%를 기준으로 하되, 최소 결과 수를 보장합니다.

    Args:
        results: 검색 결과 리스트
        min_results: 최소 반환 결과 수
        min_threshold: 최소 임계값
        max_threshold: 최대 임계값

    Returns:
        float: 0.35 ~ 0.70 범위의 임계값
    """
    if not results:
        return min_threshold

    # 유사도 점수 추출
    similarities = [r.similarity for r in results if r.similarity > 0]
    if not similarities:
        return min_threshold

    max_sim = max(similarities)

    # 최고 유사도의 70%를 기준
    dynamic_threshold = max_sim * 0.70

    # 최소 결과 수 보장
    sorted_by_sim = sorted(results, key=lambda x: x.similarity, reverse=True)
    if len(sorted_by_sim) >= min_results:
        # min_results번째 결과의 유사도보다 약간 낮게 설정
        nth_sim = sorted_by_sim[min_results - 1].similarity
        if dynamic_threshold > nth_sim:
            dynamic_threshold = nth_sim - 0.01

    final_threshold = max(min(dynamic_threshold, max_threshold), min_threshold)
    logger.debug(
        f"[Threshold] max_sim={max_sim:.3f} → dynamic={dynamic_threshold:.3f} → final={final_threshold:.3f}"
    )
    return final_threshold


def filter_by_threshold(
    results: List["SearchResult"],
    threshold: float,
    min_results: int = 3,
) -> List["SearchResult"]:
    """
    유사도 임계값 기반 필터링 (최소 결과 수 보장)

    Args:
        results: 검색 결과 리스트
        threshold: 유사도 임계값
        min_results: 최소 반환 결과 수

    Returns:
        필터링된 결과 리스트
    """
    if not results:
        return results

    filtered = [r for r in results if r.similarity >= threshold]

    # 최소 결과 수 보장
    if len(filtered) < min_results and len(results) >= min_results:
        sorted_results = sorted(results, key=lambda x: x.rrf_score or x.similarity, reverse=True)
        return sorted_results[:min_results]

    return filtered if filtered else results[:min_results]


class UnifiedRetriever:
    """
    Unified Retriever - SQL search_hybrid_rrf() 함수 직접 호출

    Architecture:
    - Embedding: OpenAI text-embedding-3-large (1536-dim)
    - Search: PostgreSQL search_hybrid_rrf() SQL function
    - Fusion: BM25 + Vector + RRF (k=configurable, default=10) at SQL level
    """

    def __init__(
        self,
        db_config: Dict[str, str],
        openai_api_key: Optional[str] = None,
    ):
        self.db_config = db_config
        self.conn: Any = None
        self._openai_client: Any = None
        self._openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY", "")

    def connect(self):
        """DB 연결 + HNSW ef_search 최적화 설정"""
        self.conn = psycopg2.connect(
            **cast(Any, self.db_config),
            cursor_factory=RealDictCursor,
            connect_timeout=10,
        )
        # Phase 2-2: HNSW 검색 품질 향상 (ef_search: 40 → 100)
        # ef_search 값이 클수록 정확도 증가, 속도 감소
        try:
            with self.conn.cursor() as cur:
                cur.execute("SET hnsw.ef_search = 100;")
            self.conn.commit()
            logger.debug("[UnifiedRetriever] SET hnsw.ef_search = 100")
        except Exception as e:
            logger.warning(f"[UnifiedRetriever] Failed to set ef_search: {e}")

    def close(self):
        """DB 연결 종료"""
        if self.conn:
            self.conn.close()
            self.conn = None

    def search(
        self,
        query: str,
        top_k: int = 10,
        dataset_filter: Optional[str] = None,
        category_filter: Optional[str] = None,
        document_type_filter: Optional[str] = None,
        year_filter: Optional[int] = None,
        rrf_k: Optional[int] = None,
        hyde_query: Optional[str] = None,
        query_analysis: Optional[Dict] = None,
        apply_threshold: bool = True,
    ) -> List[SearchResult]:
        """
        통합 하이브리드 검색 (BM25 + Vector + RRF)

        Args:
            query: 검색 쿼리 텍스트
            top_k: 반환할 결과 수
            dataset_filter: 데이터셋 필터 ('law_guide' | 'case')
            category_filter: 카테고리 필터 ('상담' | '해결' | '조정')
            document_type_filter: 문서 유형 필터 ('법률' | '시행령' | '행정규칙' | '별표')
            year_filter: 연도 필터
            hyde_query: HyDE 가상 답변 (제공 시 벡터 검색에 사용)
            query_analysis: 쿼리 분석 결과 (동적 RRF k 결정에 사용)
            apply_threshold: 유사도 임계값 필터링 적용 여부

        Returns:
            List[SearchResult]: RRF 점수 기준 정렬된 검색 결과
        """
        start_time = time.time()

        # 1. 쿼리 임베딩 생성 (HyDE: 가상 답변 임베딩 사용)
        embed_text = hyde_query if hyde_query else query
        query_embedding = self._create_embedding(embed_text)
        if hyde_query:
            logger.info(
                f"[UnifiedRetriever] HyDE embedding used (length={len(hyde_query)})"
            )

        # Phase 2-1: 동적 RRF k 결정
        from ....common.config import get_config

        if rrf_k is not None:
            effective_rrf_k = rrf_k
        else:
            # 동적 RRF k 사용 (query_analysis 기반)
            effective_rrf_k = determine_rrf_k(query, query_analysis)
            logger.info(f"[UnifiedRetriever] Dynamic RRF k={effective_rrf_k}")

        # 2. SQL search_hybrid_rrf() 호출
        rows = self._execute_rrf_search(
            query_text=query,
            query_embedding=query_embedding,
            dataset_filter=dataset_filter,
            category_filter=category_filter,
            document_type_filter=document_type_filter,
            year_filter=year_filter,
            top_k=top_k,
            rrf_k=effective_rrf_k,
        )

        # 3. dict → SearchResult 변환
        results = self._to_search_results(rows)

        # Phase 2-1: 동적 유사도 임계값 필터링
        original_count = len(results)
        if apply_threshold and results:
            threshold = adaptive_similarity_threshold(results)
            results = filter_by_threshold(results, threshold)
            logger.info(
                f"[UnifiedRetriever] Threshold filter: {original_count} → {len(results)} (threshold={threshold:.3f})"
            )

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            f"[UnifiedRetriever] query={query[:50]!r} "
            f"dataset={dataset_filter} category={category_filter} "
            f"doc_type={document_type_filter} rrf_k={effective_rrf_k} "
            f"results={len(results)} time={elapsed_ms:.1f}ms"
        )

        return results

    def search_multi(
        self,
        queries: List[str],
        top_k: int = 10,
        rrf_k: Optional[int] = None,
        **filters,
    ) -> List[SearchResult]:
        """
        다중 쿼리 검색 + Python-level RRF fusion.

        expanded_queries 기반으로 여러 쿼리를 실행하고 RRF로 병합합니다.

        Args:
            queries: 검색 쿼리 리스트
            top_k: 최종 반환 결과 수
            rrf_k: RRF k 파라미터 (None이면 config.retrieval.rrf_k_python 사용)
            **filters: search()에 전달할 필터 인자

        Returns:
            RRF 점수 기준 정렬된 검색 결과
        """
        if len(queries) <= 1:
            return self.search(queries[0] if queries else "", top_k=top_k, **filters)

        from ....common.config import get_config

        effective_rrf_k = (
            rrf_k if rrf_k is not None else get_config().retrieval.rrf_k_python
        )

        per_query_k = max(top_k, 12)

        all_results = [self.search(q, top_k=per_query_k, **filters) for q in queries]

        # RRF Fusion
        fused_scores: Dict[str, float] = {}
        fused_results: Dict[str, SearchResult] = {}
        for results in all_results:
            for rank, result in enumerate(results, start=1):
                key = result.chunk_id
                fused_scores[key] = fused_scores.get(key, 0.0) + 1.0 / (
                    effective_rrf_k + rank
                )
                if key not in fused_results:
                    fused_results[key] = result

        # Update similarity scores to fused scores
        for chunk_id, score in fused_scores.items():
            fused_results[chunk_id].similarity = score

        ranked = sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
        return [fused_results[cid] for cid, _ in ranked[:top_k]]

    def _create_embedding(self, query: str) -> List[float]:
        """OpenAI text-embedding-3-large 임베딩 생성 (1536-dim)"""
        if self._openai_client is None:
            from openai import OpenAI

            self._openai_client = OpenAI(api_key=self._openai_api_key)

        response = self._openai_client.embeddings.create(
            model="text-embedding-3-large",
            input=query,
            dimensions=1536,
        )
        return response.data[0].embedding

    def _execute_rrf_search(
        self,
        query_text: str,
        query_embedding: List[float],
        dataset_filter: Optional[str],
        category_filter: Optional[str],
        document_type_filter: Optional[str],
        year_filter: Optional[int],
        top_k: int,
        rrf_k: int = 10,
    ) -> List[Dict]:
        """SQL search_hybrid_rrf() 함수 호출"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM search_hybrid_rrf(
                    %s::text,
                    %s::vector(1536),
                    %s::varchar(20),
                    %s::varchar(50),
                    %s::varchar(20),
                    %s::integer,
                    %s::integer,
                    %s::integer
                )
                """,
                (
                    query_text,
                    str(query_embedding),
                    dataset_filter,
                    category_filter,
                    document_type_filter,
                    year_filter,
                    top_k,
                    rrf_k,
                ),
            )
            return cur.fetchall()

    def _to_search_results(self, rows: List[Dict]) -> List[SearchResult]:
        """RealDictCursor 결과 → SearchResult 변환"""
        results = []
        for i, row in enumerate(rows):
            metadata = row.get("metadata") or {}
            dataset_type = row.get("dataset_type", "")
            category = row.get("category")

            # doc_type 매핑
            if dataset_type == "law_guide":
                doc_type = "law"
            elif dataset_type == "case":
                if category == "조정":
                    doc_type = "mediation_case"
                elif category == "상담":
                    doc_type = "counsel_case"
                elif category == "해결":
                    doc_type = "criteria"
                else:
                    doc_type = "case"
            else:
                doc_type = dataset_type or "unknown"

            # doc_title 결정
            title = None
            if isinstance(metadata, dict):
                title = metadata.get("title")
            if not title and dataset_type == "law_guide":
                law_name = row.get("law_name", "")
                article_no = (
                    metadata.get("조문번호", "") if isinstance(metadata, dict) else ""
                )
                article_title = (
                    metadata.get("조문제목", "") if isinstance(metadata, dict) else ""
                )
                parts = [p for p in [law_name, article_no, article_title] if p]
                title = (
                    " ".join(parts) if parts else (law_name or row.get("chunk_id", ""))
                )

            # doc_id 결정
            doc_id = row.get("chunk_id", "")
            if isinstance(metadata, dict) and metadata.get("number"):
                doc_id = str(metadata["number"])

            # source 정보
            url = row.get("source_url") or (
                metadata.get("url") if isinstance(metadata, dict) else None
            )
            if dataset_type == "law_guide":
                source_org = "statute"
            elif isinstance(metadata, dict):
                source_org = metadata.get("source")
            else:
                source_org = None

            decision_date = (
                metadata.get("decision_date") if isinstance(metadata, dict) else None
            )

            # PDF source information
            source_file = row.get("source_file")
            printed_page = row.get("printed_page")

            # DEBUG: printed_page 값 확인
            if i < 3:  # 첫 3개만 로그
                logger.info(f"[UnifiedRetriever] Row {i}: printed_page={printed_page}, source_file={source_file}, doc_title={title[:50] if title else 'None'}")

            results.append(
                SearchResult(
                    chunk_id=row.get("chunk_id", ""),
                    doc_id=doc_id,
                    chunk_type=(
                        metadata.get("chunk_type", "")
                        if isinstance(metadata, dict)
                        else ""
                    ),
                    content=row.get("text", ""),
                    doc_title=title or "",
                    doc_type=doc_type,
                    category_path=_to_category_path(category),
                    similarity=float(row.get("vector_similarity", 0)),
                    rrf_score=float(row.get("rrf_score", 0)),
                    source_org=source_org,
                    url=url,
                    decision_date=decision_date,
                    collected_at=None,
                    source_file=source_file,
                    printed_page=printed_page,
                    metadata=metadata if isinstance(metadata, dict) else None,
                )
            )

        return results


__all__ = [
    "UnifiedRetriever",
    "determine_rrf_k",
    "adaptive_similarity_threshold",
    "filter_by_threshold",
]
