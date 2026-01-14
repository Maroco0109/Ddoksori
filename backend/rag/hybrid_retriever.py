"""
똑소리 프로젝트 - Hybrid Retriever with RRF Fusion
작성일: 2026-01-11
Sprint 1 - PR S1-D4: Hybrid Retrieval MVP

Combines dense (pgvector) and lexical (PostgreSQL FTS) retrieval
using Reciprocal Rank Fusion (RRF) algorithm.
"""

import time
from typing import List, Dict, Optional
import psycopg2
from .retriever import RAGRetriever, SearchResult


class HybridRetriever:
    """
    Advanced hybrid retrieval using RRF (Reciprocal Rank Fusion)
    Combines dense vector search + lexical FTS search

    Architecture:
    - Dense search: Delegates to RAGRetriever.vector_search() (pgvector)
    - Lexical search: PostgreSQL FTS using mv_searchable_chunks
    - Fusion: RRF algorithm with k=60
    - Graceful degradation: Works with FTS-only when embeddings are NULL
    """

    def __init__(self, db_config: Dict[str, str], embed_api_url: str = "http://localhost:8001/embed"):
        """
        Initialize hybrid retriever

        Args:
            db_config: Database connection config
            embed_api_url: Embedding API endpoint URL
        """
        self.db_config = db_config
        self.embed_api_url = embed_api_url
        self.conn = None

        # Create RAGRetriever instance for dense search
        self.rag_retriever = RAGRetriever(db_config, embed_api_url)

    def connect(self):
        """Connect to database"""
        self.conn = psycopg2.connect(**self.db_config)
        self.rag_retriever.connect()

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
        chunk_type_filter: Optional[str] = None
    ) -> List[SearchResult]:
        """
        Main hybrid search with RRF fusion

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
            chunk_type_filter
        )

        # 2. Lexical retrieval (FTS)
        lexical_results = self._lexical_search(
            query,
            candidate_count,
            doc_type_filter,
            chunk_type_filter
        )

        # 3. RRF fusion
        fused_results = self._reciprocal_rank_fusion(
            dense_results,
            lexical_results,
            k=60  # RRF constant (standard value)
        )

        return fused_results[:top_k]

    def vector_search(
        self,
        query: str,
        top_k: int = 10,
        doc_type_filter: Optional[str] = None,
        chunk_type_filter: Optional[str] = None
    ) -> List[SearchResult]:
        """
        Backward-compatible alias for .search() method
        Maintains API compatibility with RAGRetriever

        Delegates to .search() which performs hybrid retrieval with RRF fusion
        """
        return self.search(query, top_k, doc_type_filter, chunk_type_filter)

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
        chunk_type_filter: Optional[str] = None
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
                chunk_type_filter=chunk_type_filter
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
        chunk_type_filter: Optional[str] = None
    ) -> List[SearchResult]:
        """
        Lexical retrieval using PostgreSQL FTS
        Uses mv_searchable_chunks materialized view with ts_rank
        """
        with self.conn.cursor() as cur:
            # Build tsquery from query string (using 'simple' parser for Korean)
            # Split query into tokens and join with '&' for AND search
            tokens = query.split()
            tsquery = ' & '.join(tokens)

            cur.execute(
                """
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
                    AND (%s IS NULL OR chunk_type = %s)
                ORDER BY rank_score DESC
                LIMIT %s
                """,
                (
                    tsquery, tsquery,
                    doc_type_filter, doc_type_filter,
                    chunk_type_filter, chunk_type_filter,
                    top_k
                )
            )

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
