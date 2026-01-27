"""
똑소리 프로젝트 - Hybrid Retriever with RRF Fusion
작성일: 2026-01-11
Sprint 1 - PR S1-D4: Hybrid Retrieval MVP
Updated: 2026-01-17 - S2-9: BGE-M3 Sparse + 3-way RRF

Combines dense (pgvector), lexical (PostgreSQL FTS), and sparse (BGE-M3) retrieval
using Reciprocal Rank Fusion (RRF) algorithm.
"""

import os
import json
import time
import requests
from typing import List, Dict, Optional, Any, cast, Union
import psycopg2
from .retriever import (
    RAGRetriever,
    SearchResult,
    _map_doc_type_filter_to_vector_chunks,
    _map_vector_chunks_doc_type,
    _to_category_path,
)
from .base import BaseRetriever, Document, to_documents

# Import embedding configuration
from utils.embedding_connection import (
    EMBEDDING_MODEL,
    ENABLE_SPARSE_SEARCH,
    RRF_WEIGHT_DENSE,
    RRF_WEIGHT_LEXICAL,
    RRF_WEIGHT_SPARSE,
    get_bge_m3_api_url
)


class HybridRetriever:
    """
    Advanced hybrid retrieval using RRF (Reciprocal Rank Fusion)
    Combines dense vector search + lexical FTS search + sparse vector search (BGE-M3)

    Architecture:
    - Dense search: Delegates to RAGRetriever.vector_search() (pgvector)
    - Lexical search: PostgreSQL FTS using mv_searchable_chunks
    - Sparse search: BGE-M3 sparse vectors with dot product (optional)
    - Fusion: RRF algorithm with configurable weights
    - Graceful degradation: Works with FTS-only when embeddings are NULL
    """

    def __init__(
        self,
        db_config: Dict[str, str],
        embed_api_url: str = "http://localhost:8001/embed",
        bge_api_url: Optional[str] = None,
        embedding_model: Optional[str] = None,
        enable_sparse: Optional[bool] = None
    ):
        """
        Initialize hybrid retriever

        Args:
            db_config: Database connection config
            embed_api_url: KURE-v1 embedding API endpoint URL
            bge_api_url: BGE-M3 embedding API endpoint URL (optional)
            embedding_model: Active embedding model ('kure-v1' or 'bge-m3')
            enable_sparse: Enable sparse search (BGE-M3 required)
        """
        self.db_config = db_config
        self.embed_api_url = embed_api_url
        self.conn: Any = None

        # BGE-M3 configuration
        self.bge_api_url = bge_api_url or get_bge_m3_api_url()
        self.embedding_model = embedding_model or EMBEDDING_MODEL
        self.enable_sparse = enable_sparse if enable_sparse is not None else ENABLE_SPARSE_SEARCH

        # RRF weights (from environment or defaults)
        self.rrf_weight_dense = RRF_WEIGHT_DENSE
        self.rrf_weight_lexical = RRF_WEIGHT_LEXICAL
        self.rrf_weight_sparse = RRF_WEIGHT_SPARSE

        # Create RAGRetriever instance for dense search
        self.rag_retriever = RAGRetriever(db_config, embed_api_url)

    def connect(self):
        """Connect to database"""
        self.conn = psycopg2.connect(**cast(Any, self.db_config))  # type: ignore[call-overload]
        self.rag_retriever.connect()
        self._has_vector_chunks = getattr(self.rag_retriever, '_has_vector_chunks', False)

    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
        self.rag_retriever.close()

    def search(
        self,
        query: str,
        top_k: int = 10,
        doc_type_filter: Optional[str] = None,
        dataset_type_filter: Optional[str] = None,
        chunk_type_filter: Optional[Union[str, List[str]]] = None,
        category_filter: Optional[Union[str, List[str]]] = None
    ) -> List[SearchResult]:
        """
        Main hybrid search with RRF fusion

        Supports 2-way (Dense + Lexical) or 3-way (Dense + Lexical + Sparse) fusion
        based on configuration.

        Args:
            query: Search query
            top_k: Number of results to return
            doc_type_filter: Filter by document type (e.g., 'law', 'mediation_case')
            chunk_type_filter: Filter by chunk type (e.g., 'article', 'paragraph')

        Returns:
            List of SearchResult objects sorted by RRF score
        """
        # Fetch more candidates for RRF fusion (3x top_k)
        candidate_count = top_k * 3

        # 1. Dense retrieval (vector search)
        # NOTE: Will return empty if embeddings are NULL
        dense_results = self._dense_search(
            query,
            candidate_count,
            doc_type_filter,
            dataset_type_filter,
            chunk_type_filter,
            category_filter
        )

        # 2. Lexical retrieval (FTS)
        lexical_results = self._lexical_search(
            query,
            candidate_count,
            doc_type_filter,
            dataset_type_filter,
            chunk_type_filter,
            category_filter
        )

        # 3. Sparse retrieval (BGE-M3) - optional
        sparse_results = []
        if self.enable_sparse and self.bge_api_url:
            sparse_results = self._sparse_search(
                query,
                candidate_count,
                doc_type_filter,
                dataset_type_filter,
                chunk_type_filter,
                category_filter
            )

        # 4. RRF fusion (2-way or 3-way)
        if sparse_results:
            fused_results = self._reciprocal_rank_fusion_3way(
                dense_results,
                lexical_results,
                sparse_results,
                k=60
            )
        else:
            fused_results = self._reciprocal_rank_fusion(
                dense_results,
                lexical_results,
                k=60
            )

        return fused_results[:top_k]

    def vector_search(
        self,
        query: str,
        top_k: int = 10,
        doc_type_filter: Optional[str] = None,
        chunk_type_filter: Optional[str] = None
    ) -> List[SearchResult]:
        return self.search(query, top_k, doc_type_filter, chunk_type_filter)

    def invoke(
        self,
        query: str,
        top_k: int = 10,
        doc_type_filter: Optional[str] = None,
        chunk_type_filter: Optional[str] = None,
        **kwargs
    ) -> List[Document]:
        results = self.search(query, top_k, doc_type_filter, chunk_type_filter)
        return to_documents(results)

    def search_instrumented(
        self,
        query: str,
        top_k: int = 10,
        doc_type_filter: Optional[str] = None,
        chunk_type_filter: Optional[str] = None
    ) -> Dict:
        """
        Instrumented hybrid search with timing and candidate counts.

        Returns:
            {
                'results': List[SearchResult],
                'embedding_time_ms': float,
                'search_time_ms': float,
                'dense_candidates': int,
                'lexical_candidates': int
            }
        """
        candidate_count = top_k * 3

        # Dense retrieval with timing (includes embedding time)
        dense_start = time.time()
        dense_results = self._dense_search(
            query, candidate_count, doc_type_filter, chunk_type_filter
        )
        dense_time = (time.time() - dense_start) * 1000

        # Lexical retrieval with timing
        lex_start = time.time()
        lexical_results = self._lexical_search(
            query, candidate_count, doc_type_filter, chunk_type_filter
        )
        lex_time = (time.time() - lex_start) * 1000

        # RRF fusion
        fused_results = self._reciprocal_rank_fusion(
            dense_results, lexical_results, k=60
        )

        return {
            'results': fused_results[:top_k],
            'embedding_time_ms': dense_time,  # Dense includes embedding
            'search_time_ms': lex_time,       # Lexical search time
            'dense_candidates': len(dense_results),
            'lexical_candidates': len(lexical_results)
        }

    def _dense_search(
        self,
        query: str,
        top_k: int,
        doc_type_filter: Optional[str] = None,
        dataset_type_filter: Optional[str] = None,
        chunk_type_filter: Optional[Union[str, List[str]]] = None,
        category_filter: Optional[Union[str, List[str]]] = None
    ) -> List[SearchResult]:
        """
        Dense retrieval using pgvector
        Reuses RAGRetriever.vector_search() method

        NOTE: Will return empty list if embeddings are NULL
        """
        try:
            return self.rag_retriever.vector_search(
                query=query,
                top_k=top_k,
                doc_type_filter=doc_type_filter,
                dataset_type_filter=dataset_type_filter,
                chunk_type_filter=chunk_type_filter,
                category_filter=category_filter
            )
        except Exception as e:
            # Handle embedding API errors gracefully
            print(f"Dense search failed: {e}")
            return []

    def _lexical_search(
        self,
        query: str,
        top_k: int,
        doc_type_filter: Optional[str] = None,
        dataset_type_filter: Optional[str] = None,
        chunk_type_filter: Optional[Union[str, List[str]]] = None,
        category_filter: Optional[Union[str, List[str]]] = None
    ) -> List[SearchResult]:
        """
        Lexical retrieval using PostgreSQL FTS
        Uses mv_searchable_chunks materialized view with ts_rank
        """
        with self.conn.cursor() as cur:
            if getattr(self, '_has_vector_chunks', False):
                # === PR-3: dataset_type_filter 우선 사용 ===
                if dataset_type_filter is not None:
                    final_dataset_type = dataset_type_filter
                    mapped_category_filter = None
                else:
                    final_dataset_type, mapped_category_filter = _map_doc_type_filter_to_vector_chunks(doc_type_filter)

                # === PR-4: category 필터 우선순위 ===
                # category_filter 파라미터가 명시적으로 제공된 경우 우선 사용
                if category_filter is not None:
                    final_category_filter = category_filter
                else:
                    final_category_filter = mapped_category_filter

                # === PR-3: chunk_type 리스트 지원 ===
                if isinstance(chunk_type_filter, list):
                    chunk_type_condition = "AND vc.chunk_type = ANY(%s)"
                elif chunk_type_filter:
                    chunk_type_condition = "AND vc.chunk_type = %s"
                else:
                    chunk_type_condition = ""

                # === PR-4: category 리스트 지원 ===
                if isinstance(final_category_filter, list):
                    category_condition = "AND vc.category = ANY(%s)"
                elif final_category_filter:
                    category_condition = "AND vc.category = %s"
                else:
                    category_condition = ""

                query_sql = f"""
                    SELECT
                        vc.chunk_id,
                        vc.dataset_type,
                        vc.text,
                        vc.law_name,
                        vc.chunk_type,
                        vc.category,
                        vc.source_url,
                        vc.source_year,
                        vc.metadata,
                        vc.created_at,
                        ts_rank(vc.text_tsv, plainto_tsquery('simple', %s)) AS rank_score
                    FROM vector_chunks vc
                    WHERE
                        vc.text_tsv @@ plainto_tsquery('simple', %s)
                        AND (%s IS NULL OR vc.dataset_type = %s)
                        {category_condition}
                        {chunk_type_condition}
                    ORDER BY rank_score DESC
                    LIMIT %s
                """

                params = [
                    query,
                    query,
                    final_dataset_type, final_dataset_type,
                ]
                if final_category_filter:
                    params.append(final_category_filter)
                if chunk_type_filter:
                    params.append(chunk_type_filter)
                params.append(top_k)

                cur.execute(query_sql, tuple(params))

                rows = cur.fetchall()
                if not rows:
                    # FTS can return 0 for Korean depending on how text_tsv was built.
                    # Fall back to ILIKE to keep retrieval functional.
                    search_pattern = f"%{query}%"

                    fallback_sql = f"""
                        SELECT
                            vc.chunk_id,
                            vc.dataset_type,
                            vc.text,
                            vc.law_name,
                            vc.chunk_type,
                            vc.category,
                            vc.source_url,
                            vc.source_year,
                            vc.metadata,
                            vc.created_at,
                            0.5 AS rank_score
                        FROM vector_chunks vc
                        WHERE
                            vc.text ILIKE %s
                            AND (%s IS NULL OR vc.dataset_type = %s)
                            {category_condition}
                            {chunk_type_condition}
                        LIMIT %s
                    """

                    fallback_params = [
                        search_pattern,
                        final_dataset_type, final_dataset_type,
                    ]
                    if final_category_filter:
                        fallback_params.append(final_category_filter)
                    if chunk_type_filter:
                        fallback_params.append(chunk_type_filter)
                    fallback_params.append(top_k)

                    cur.execute(fallback_sql, tuple(fallback_params))
                    rows = cur.fetchall()

                results = []
                for row in rows:
                    metadata_json = row[8] if row[8] else {}
                    dataset_type = row[1]
                    category = row[5]
                    doc_type = _map_vector_chunks_doc_type(dataset_type, category)

                    title = None
                    if isinstance(metadata_json, dict):
                        title = metadata_json.get('title')
                    if not title and dataset_type == 'law_guide':
                        if isinstance(metadata_json, dict):
                            article_no = metadata_json.get('조문번호')
                            article_title = metadata_json.get('조문제목')
                        else:
                            article_no, article_title = None, None
                        parts = [p for p in [row[3], article_no, article_title] if p]
                        title = ' '.join(parts) if parts else (row[3] or row[0])

                    doc_id = row[0]
                    if isinstance(metadata_json, dict) and metadata_json.get('number'):
                        doc_id = str(metadata_json.get('number'))
                    url = row[6] or (metadata_json.get('url') if isinstance(metadata_json, dict) else None)
                    source_org = None
                    if dataset_type == 'law_guide':
                        source_org = 'statute'
                    elif isinstance(metadata_json, dict):
                        source_org = metadata_json.get('source')
                    decision_date = metadata_json.get('decision_date') if isinstance(metadata_json, dict) else None

                    results.append(SearchResult(
                        chunk_id=row[0],
                        doc_id=doc_id,
                        chunk_type=row[4] or '',
                        content=row[2] or '',
                        doc_title=title or '',
                        doc_type=doc_type,
                        category_path=_to_category_path(category),
                        similarity=float(row[10]) if row[10] is not None else 0.0,
                        source_org=source_org,
                        url=url,
                        collected_at=row[9].isoformat() if row[9] else None,
                        decision_date=decision_date,
                        metadata=metadata_json if isinstance(metadata_json, dict) else None,
                    ))

                return results

            # Build tsquery from query string (using 'simple' parser for Korean)
            # Split query into tokens and join with '&' for AND search
            tokens = query.split()
            tsquery = ' & '.join(tokens)

            # === PR-3: chunk_type 리스트 지원 (mv_searchable_chunks) ===
            if isinstance(chunk_type_filter, list):
                chunk_type_condition = "AND chunk_type = ANY(%s)"
            elif chunk_type_filter:
                chunk_type_condition = "AND chunk_type = %s"
            else:
                chunk_type_condition = ""

            query_sql = f"""
                SELECT
                    chunk_id,
                    doc_id,
                    chunk_type,
                    content,
                    doc_type,
                    source_org,
                    category_path,
                    title,
                    url,
                    collected_at,
                    metadata,
                    ts_rank(content_vector, to_tsquery('simple', %s)) AS rank_score
                FROM mv_searchable_chunks
                WHERE
                    content_vector @@ to_tsquery('simple', %s)
                    AND (%s IS NULL OR doc_type = %s)
                    {chunk_type_condition}
                ORDER BY rank_score DESC
                LIMIT %s
            """

            params = [
                tsquery, tsquery,
                doc_type_filter, doc_type_filter,
            ]
            if chunk_type_filter:
                params.append(chunk_type_filter)
            params.append(top_k)

            cur.execute(query_sql, tuple(params))

            results = []
            for row in cur.fetchall():
                # Parse decision_date from metadata if exists
                metadata_json = row[10] if len(row) > 10 and row[10] else {}
                decision_date = metadata_json.get('decision_date') if isinstance(metadata_json, dict) else None

                results.append(SearchResult(
                    chunk_id=row[0],
                    doc_id=row[1],
                    chunk_type=row[2],
                    content=row[3],
                    doc_title=row[7],         # From title column
                    doc_type=row[4],
                    category_path=row[6] or [],
                    similarity=float(row[11]),  # ts_rank score
                    source_org=row[5],
                    url=row[8],
                    collected_at=row[9].isoformat() if row[9] else None,
                    decision_date=decision_date,
                    metadata=metadata_json
                ))

            return results

    def _reciprocal_rank_fusion(
        self,
        results_a: List[SearchResult],
        results_b: List[SearchResult],
        k: int = 60
    ) -> List[SearchResult]:
        """
        Reciprocal Rank Fusion (RRF) algorithm

        Formula: score(d) = sum(1 / (k + rank_i(d)))
        where:
        - k is a constant (typically 60)
        - rank_i(d) is the rank of document d in result list i (1-indexed)

        Args:
            results_a: First ranked list (dense results)
            results_b: Second ranked list (lexical results)
            k: RRF constant (default 60)

        Returns:
            Merged and re-ranked list of SearchResult objects
        """
        # Calculate RRF scores
        rrf_scores = {}  # {chunk_id: rrf_score}
        chunk_data = {}  # {chunk_id: SearchResult}

        # Score from first result list (dense)
        for rank, result in enumerate(results_a, start=1):
            chunk_id = result.chunk_id
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + (1.0 / (k + rank))
            chunk_data[chunk_id] = result

        # Score from second result list (lexical)
        for rank, result in enumerate(results_b, start=1):
            chunk_id = result.chunk_id
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + (1.0 / (k + rank))
            # Store result data if not already stored (from dense search)
            if chunk_id not in chunk_data:
                chunk_data[chunk_id] = result

        # Sort by RRF score (descending)
        sorted_chunk_ids = sorted(
            rrf_scores.keys(),
            key=lambda cid: rrf_scores[cid],
            reverse=True
        )

        # Create final result list with updated similarity scores
        final_results = []
        for chunk_id in sorted_chunk_ids:
            result = chunk_data[chunk_id]
            # Update similarity to RRF score for consistency
            result.similarity = rrf_scores[chunk_id]
            final_results.append(result)

        return final_results

    def _sparse_search(
        self,
        query: str,
        top_k: int,
        doc_type_filter: Optional[str] = None,
        dataset_type_filter: Optional[str] = None,
        chunk_type_filter: Optional[Union[str, List[str]]] = None,
        category_filter: Optional[Union[str, List[str]]] = None
    ) -> List[SearchResult]:
        """
        Sparse retrieval using BGE-M3 sparse vectors

        Uses dot product calculation with bge_sparse_dot_product() function.
        Requires BGE-M3 embeddings to be generated for chunks.

        Args:
            query: Search query
            top_k: Number of results to return
            doc_type_filter: Filter by document type
            chunk_type_filter: Filter by chunk type
            category_filter: Filter by category (single string or list)

        Returns:
            List of SearchResult objects sorted by sparse similarity
        """
        if not self.bge_api_url:
            return []

        try:
            # 1. Get sparse embedding for query
            response = requests.post(
                self.bge_api_url,
                json={'text': query, 'return_dense': False, 'return_sparse': True},
                timeout=30
            )

            if response.status_code != 200:
                print(f"BGE-M3 API error: {response.status_code}")
                return []

            query_sparse = response.json().get('sparse_embedding', {})

            if not query_sparse:
                return []

            # 2. Search using sparse dot product
            with self.conn.cursor() as cur:
                # === PR-3: chunk_type 리스트 지원 ===
                if isinstance(chunk_type_filter, list):
                    chunk_type_condition = "AND c.chunk_type = ANY(%s)"
                elif chunk_type_filter:
                    chunk_type_condition = "AND c.chunk_type = %s"
                else:
                    chunk_type_condition = ""

                # === PR-4: category 리스트 지원 (documents.category_path는 배열) ===
                if isinstance(category_filter, list):
                    # 여러 카테고리 중 하나라도 포함되면 매칭 (overlap 연산자)
                    category_condition = "AND d.category_path && %s::text[]"
                elif category_filter:
                    # 단일 카테고리 포함 확인 (contains 연산자)
                    category_condition = "AND d.category_path @> ARRAY[%s]::text[]"
                else:
                    category_condition = ""

                query_sql = f"""
                    SELECT
                        c.chunk_id,
                        c.doc_id,
                        c.chunk_type,
                        c.content,
                        d.title AS doc_title,
                        d.doc_type,
                        d.category_path,
                        bge_sparse_dot_product(c.bge_sparse_vector, %s::jsonb) AS similarity,
                        d.source_org,
                        d.url,
                        d.collected_at,
                        d.metadata
                    FROM chunks c
                    JOIN documents d ON c.doc_id = d.doc_id
                    WHERE
                        c.bge_sparse_vector IS NOT NULL
                        AND c.bge_m3_encoded = TRUE
                        AND c.drop = FALSE
                        AND (%s IS NULL OR d.doc_type = %s)
                        {chunk_type_condition}
                        {category_condition}
                    ORDER BY bge_sparse_dot_product(c.bge_sparse_vector, %s::jsonb) DESC
                    LIMIT %s
                """

                params = [
                    json.dumps(query_sparse),
                    doc_type_filter, doc_type_filter,
                ]
                if chunk_type_filter:
                    params.append(chunk_type_filter)
                if category_filter:
                    params.append(category_filter)
                params.extend([json.dumps(query_sparse), top_k])

                cur.execute(query_sql, tuple(params))

                results = []
                for row in cur.fetchall():
                    metadata_json = row[11] if len(row) > 11 and row[11] else {}
                    decision_date = metadata_json.get('decision_date') if isinstance(metadata_json, dict) else None

                    results.append(SearchResult(
                        chunk_id=row[0],
                        doc_id=row[1],
                        chunk_type=row[2],
                        content=row[3],
                        doc_title=row[4],
                        doc_type=row[5],
                        category_path=row[6] or [],
                        similarity=float(row[7]) if row[7] else 0.0,
                        source_org=row[8],
                        url=row[9],
                        collected_at=row[10].isoformat() if row[10] else None,
                        decision_date=decision_date,
                        metadata=metadata_json
                    ))

                return results

        except requests.exceptions.RequestException as e:
            print(f"Sparse search API error: {e}")
            return []
        except Exception as e:
            print(f"Sparse search failed: {e}")
            return []

    def _reciprocal_rank_fusion_3way(
        self,
        results_a: List[SearchResult],
        results_b: List[SearchResult],
        results_c: List[SearchResult],
        k: int = 60
    ) -> List[SearchResult]:
        """
        3-way Reciprocal Rank Fusion (RRF) algorithm

        Combines Dense + Lexical + Sparse search results with configurable weights.

        Formula: score(d) = w_dense * 1/(k + rank_dense(d))
                          + w_lexical * 1/(k + rank_lexical(d))
                          + w_sparse * 1/(k + rank_sparse(d))

        Args:
            results_a: First ranked list (dense results)
            results_b: Second ranked list (lexical results)
            results_c: Third ranked list (sparse results)
            k: RRF constant (default 60)

        Returns:
            Merged and re-ranked list of SearchResult objects
        """
        # Calculate RRF scores with weights
        rrf_scores = {}  # {chunk_id: rrf_score}
        chunk_data = {}  # {chunk_id: SearchResult}

        # Score from dense results (with weight)
        for rank, result in enumerate(results_a, start=1):
            chunk_id = result.chunk_id
            rrf_scores[chunk_id] = self.rrf_weight_dense * (1.0 / (k + rank))
            chunk_data[chunk_id] = result

        # Score from lexical results (with weight)
        for rank, result in enumerate(results_b, start=1):
            chunk_id = result.chunk_id
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + self.rrf_weight_lexical * (1.0 / (k + rank))
            if chunk_id not in chunk_data:
                chunk_data[chunk_id] = result

        # Score from sparse results (with weight)
        for rank, result in enumerate(results_c, start=1):
            chunk_id = result.chunk_id
            rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + self.rrf_weight_sparse * (1.0 / (k + rank))
            if chunk_id not in chunk_data:
                chunk_data[chunk_id] = result

        # Sort by RRF score (descending)
        sorted_chunk_ids = sorted(
            rrf_scores.keys(),
            key=lambda cid: rrf_scores[cid],
            reverse=True
        )

        # Create final result list with updated similarity scores
        final_results = []
        for chunk_id in sorted_chunk_ids:
            result = chunk_data[chunk_id]
            # Update similarity to RRF score for consistency
            result.similarity = rrf_scores[chunk_id]
            final_results.append(result)

        return final_results

    def search_prioritized(
        self,
        query: str,
        top_k: int = 5,
        primary_doc_type: str = 'mediation_case',
        secondary_doc_type: str = 'counsel_case'
    ) -> List[SearchResult]:
        """
        2단계 검색: primary doc_type 우선, 부족분은 secondary에서 채움

        Args:
            query: 검색 쿼리
            top_k: 반환할 결과 수
            primary_doc_type: 우선 검색할 문서 유형 (기본: mediation_case)
            secondary_doc_type: 보조 검색할 문서 유형 (기본: counsel_case)

        Returns:
            List of SearchResult (primary 결과 우선, 부족분은 secondary로 채움)
        """
        # 1단계: primary doc_type (분쟁조정사례) 우선 검색
        primary_results = self.search(
            query=query,
            top_k=top_k,
            doc_type_filter=primary_doc_type
        )

        # 결과가 충분하면 반환
        if len(primary_results) >= top_k:
            return primary_results[:top_k]

        # 2단계: 부족분만큼 secondary doc_type (상담사례) 추가
        remaining = top_k - len(primary_results)
        secondary_results = self.search(
            query=query,
            top_k=remaining,
            doc_type_filter=secondary_doc_type
        )

        return primary_results + secondary_results

    def get_case_chunks(self, case_uid: str) -> List[Dict]:
        """
        특정 사례의 모든 청크 조회
        RAGRetriever.get_case_chunks()로 위임

        Args:
            case_uid: 문서 ID (doc_id)

        Returns:
            해당 사례의 모든 청크 정보 리스트
        """
        return self.rag_retriever.get_case_chunks(case_uid)

    def search_by_doc_type(
        self,
        query: str,
        doc_type: str,
        top_k: int = 5
    ) -> List[SearchResult]:
        """
        특정 doc_type만 검색

        Args:
            query: 검색 쿼리
            doc_type: 문서 유형 (law, mediation_case, counsel_case, criteria_* 등)
            top_k: 반환할 결과 수

        Returns:
            List[SearchResult]: 해당 doc_type의 검색 결과
        """
        return self.search(
            query=query,
            top_k=top_k,
            doc_type_filter=doc_type
        )

    def search_all_sections(
        self,
        query: str,
        dispute_k: int = 3,
        counsel_k: int = 3,
        law_k: int = 3,
        criteria_k: int = 3
    ) -> Dict[str, List[SearchResult]]:
        """
        4개 섹션 데이터 일괄 검색 (간소화 버전)

        StructuredRetriever를 사용하지 않고 HybridRetriever만으로 검색.
        법령/기준의 2단계 검색은 지원하지 않음 (StructuredRetriever 사용 권장)

        Args:
            query: 검색 쿼리
            dispute_k: 분쟁조정사례 검색 수
            counsel_k: 상담사례 검색 수
            law_k: 법령 검색 수
            criteria_k: 기준 검색 수

        Returns:
            {
                'disputes': List[SearchResult],
                'counsels': List[SearchResult],
                'laws': List[SearchResult],
                'criteria': List[SearchResult]
            }
        """
        return {
            'disputes': self.search_by_doc_type(query, 'mediation_case', dispute_k),
            'counsels': self.search_by_doc_type(query, 'counsel_case', counsel_k),
            'laws': self.search_by_doc_type(query, 'law', law_k),
            'criteria': self._search_criteria(query, criteria_k)
        }

    def _search_criteria(self, query: str, top_k: int = 3) -> List[SearchResult]:
        """
        기준(criteria) 검색

        criteria_* doc_type들을 모두 검색
        """
        candidate_count = top_k * 3

        # Dense search
        dense_results = []
        try:
            query_embedding = self.rag_retriever.embed_query(query)

            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        c.chunk_id,
                        c.doc_id,
                        c.chunk_type,
                        c.content,
                        d.title AS doc_title,
                        d.doc_type,
                        d.category_path,
                        1 - (c.embedding <=> %s::vector) AS similarity,
                        d.source_org,
                        d.url,
                        d.collected_at,
                        d.metadata
                    FROM chunks c
                    JOIN documents d ON c.doc_id = d.doc_id
                    WHERE
                        c.embedding IS NOT NULL
                        AND c.drop = FALSE
                        AND d.doc_type LIKE 'criteria_%%'
                    ORDER BY c.embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (query_embedding, query_embedding, candidate_count)
                )

                for row in cur.fetchall():
                    metadata_json = row[11] if len(row) > 11 and row[11] else {}
                    decision_date = metadata_json.get('decision_date') if isinstance(metadata_json, dict) else None

                    dense_results.append(SearchResult(
                        chunk_id=row[0],
                        doc_id=row[1],
                        chunk_type=row[2],
                        content=row[3],
                        doc_title=row[4],
                        doc_type=row[5],
                        category_path=row[6] or [],
                        similarity=float(row[7]),
                        source_org=row[8],
                        url=row[9],
                        collected_at=row[10].isoformat() if row[10] else None,
                        decision_date=decision_date,
                        metadata=metadata_json
                    ))
        except Exception as e:
            print(f"Criteria dense search failed: {e}")

        return dense_results[:top_k]
