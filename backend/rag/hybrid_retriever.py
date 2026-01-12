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
