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
import time
from typing import List, Dict, Optional, Any, cast

import psycopg2
from psycopg2.extras import RealDictCursor

from .retriever import SearchResult, _to_category_path

logger = logging.getLogger(__name__)


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
        """DB 연결"""
        self.conn = psycopg2.connect(
            **cast(Any, self.db_config),
            cursor_factory=RealDictCursor,
            connect_timeout=10,
        )

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

        Returns:
            List[SearchResult]: RRF 점수 기준 정렬된 검색 결과
        """
        start_time = time.time()

        # 1. 쿼리 임베딩 생성 (HyDE: 가상 답변 임베딩 사용)
        embed_text = hyde_query if hyde_query else query
        query_embedding = self._create_embedding(embed_text)
        if hyde_query:
            logger.info(f"[UnifiedRetriever] HyDE embedding used (length={len(hyde_query)})")

        # rrf_k: config에서 가져오거나 인자로 전달된 값 사용
        from ....common.config import get_config
        effective_rrf_k = rrf_k if rrf_k is not None else get_config().retrieval.rrf_k

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

        elapsed_ms = (time.time() - start_time) * 1000
        logger.info(
            f"[UnifiedRetriever] query={query[:50]!r} "
            f"dataset={dataset_filter} category={category_filter} "
            f"doc_type={document_type_filter} "
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
        effective_rrf_k = rrf_k if rrf_k is not None else get_config().retrieval.rrf_k_python

        per_query_k = max(top_k, 12)

        all_results = [self.search(q, top_k=per_query_k, **filters) for q in queries]

        # RRF Fusion
        fused_scores: Dict[str, float] = {}
        fused_results: Dict[str, SearchResult] = {}
        for results in all_results:
            for rank, result in enumerate(results, start=1):
                key = result.chunk_id
                fused_scores[key] = fused_scores.get(key, 0.0) + 1.0 / (effective_rrf_k + rank)
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
        for row in rows:
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
                article_no = metadata.get("조문번호", "") if isinstance(metadata, dict) else ""
                article_title = metadata.get("조문제목", "") if isinstance(metadata, dict) else ""
                parts = [p for p in [law_name, article_no, article_title] if p]
                title = " ".join(parts) if parts else (law_name or row.get("chunk_id", ""))

            # doc_id 결정
            doc_id = row.get("chunk_id", "")
            if isinstance(metadata, dict) and metadata.get("number"):
                doc_id = str(metadata["number"])

            # source 정보
            url = row.get("source_url") or (metadata.get("url") if isinstance(metadata, dict) else None)
            if dataset_type == "law_guide":
                source_org = "statute"
            elif isinstance(metadata, dict):
                source_org = metadata.get("source")
            else:
                source_org = None

            decision_date = metadata.get("decision_date") if isinstance(metadata, dict) else None

            results.append(
                SearchResult(
                    chunk_id=row.get("chunk_id", ""),
                    doc_id=doc_id,
                    chunk_type=metadata.get("chunk_type", "") if isinstance(metadata, dict) else "",
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
                    metadata=metadata if isinstance(metadata, dict) else None,
                )
            )

        return results


__all__ = ["UnifiedRetriever"]
