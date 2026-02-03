"""
똑소리 프로젝트 - 전문 검색기 (Specialized Retrievers)
작성일: 2026-01-13
법령, 기준, 사례의 2단계 계층 검색 지원
Phase 2: 분쟁조정사례 메타데이터 실시간 LLM 추출 추가
Phase 3: 문서 수준 유사도 검색 (Document-Level Similarity)
"""

import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, List, Optional

import psycopg2

from .rds_internal_retriever import RDSInternalRetriever, SimilarChunkResult

if TYPE_CHECKING:
    from .base import Document

logger = logging.getLogger(__name__)

# 메타데이터 추출 활성화 여부
ENABLE_DISPUTE_METADATA_EXTRACTION = (
    os.getenv("ENABLE_DISPUTE_METADATA_EXTRACTION", "true").lower() == "true"
)

# Phase 3: 문서 수준 유사도 검색 활성화 여부
ENABLE_DOCUMENT_LEVEL_SIMILARITY = (
    os.getenv("ENABLE_DOCUMENT_LEVEL_SIMILARITY", "true").lower() == "true"
)
# 문서 수준 유사도 계산을 위한 후보 청크 배수 (top_k * N개 검색)
DOCUMENT_SIMILARITY_CANDIDATE_MULTIPLIER = int(
    os.getenv("DOCUMENT_SIMILARITY_CANDIDATE_MULTIPLIER", "5")
)


@dataclass
class DocumentLevelResult:
    """
    문서 수준 유사도 검색 결과 (Phase 3)

    하나의 문서(doc_id)에 속한 모든 청크의 유사도를 집계하여
    문서 전체의 관련성을 평가
    """

    doc_id: str
    doc_title: str
    source_org: str
    avg_similarity: float  # 모든 청크의 평균 유사도
    max_similarity: float  # 가장 높은 청크 유사도
    min_similarity: float  # 가장 낮은 청크 유사도
    chunk_count: int  # 검색된 청크 수
    total_doc_chunks: int  # 문서 전체 청크 수
    best_chunk: Dict  # 가장 유사한 청크 정보
    all_chunks: List[Dict] = field(default_factory=list)  # 검색된 모든 청크


class LawRetriever:
    """
    법령 검색기
    """

    def __init__(
        self,
        db_config: Dict[str, str],
        embed_api_url: Optional[str] = None,  # deprecated, kept for compatibility
    ):
        self.db_config = db_config
        self.conn = None
        self._rds_retriever: Optional[RDSInternalRetriever] = None

    def connect(self):
        """데이터베이스 연결"""
        self.conn = psycopg2.connect(**self.db_config)
        self._rds_retriever = RDSInternalRetriever(self.db_config)
        self._rds_retriever.connect()

    def close(self):
        """연결 종료"""
        if self.conn:
            self.conn.close()
        if self._rds_retriever:
            self._rds_retriever.close()

    def embed_query(self, query: str) -> List[float]:
        """쿼리 임베딩 생성 (OpenAI text-embedding-3-large)"""
        if self._rds_retriever is None:
            raise RuntimeError("connect()를 먼저 호출하세요.")
        return self._rds_retriever.embed_query(query)

    def hybrid_search(
        self,
        query: str,
        top_k: int = 3,
        document_types: Optional[List[str]] = None,
    ) -> List[SimilarChunkResult]:
        """
        법령 검색 (RDS 기반 Hybrid RRF)

        Args:
            query: 검색 쿼리
            top_k: 반환 개수
            document_types: '법률' or '시행령' or ['법률', '시행령']

        Returns:
            List[SimilarChunkResult]
        """
        rds = RDSInternalRetriever(self.db_config, self.embed_api_url)
        rds.connect()
        try:
            doc_types = document_types or ["법률", "시행령"]
            rows, _sql_ms = rds.search_hybrid_rrf_2(
                query_text=query,
                filter_dataset="law_guide",
                filter_document_type=doc_types,
                result_limit=top_k,
            )
        finally:
            rds.close()

        results: List[SimilarChunkResult] = []
        for row in rows:
            if not isinstance(row, dict):
                logger.warning("[LawRetriever] Skipping non-dict row: %s", type(row))
                continue
            metadata = row.get("metadata")
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except Exception:
                    metadata = None
            metadata = metadata if isinstance(metadata, dict) else {}

            results.append(
                SimilarChunkResult(
                    chunk_id=row.get("chunk_id", ""),
                    dataset_type=row.get("dataset_type") or "",
                    text=row.get("text", ""),
                    similarity=float(row.get("rrf_score", 0.0)),
                    law_name=row.get("law_name"),
                    chunk_type=row.get("chunk_type"),
                    category=row.get("category"),
                    document_type=row.get("document_type"),
                    source_url=row.get("source_url"),
                    source_file=row.get("source_file"),
                    printed_page=row.get("printed_page"),
                    source_year=row.get("source_year"),
                    metadata=metadata or None,
                    vector_similarity=float(row.get("vector_similarity", 0.0)),
                    rrf_score=float(row.get("rrf_score", 0.0)),
                )
            )

        return results

    def criteria_search(
        self,
        query: str,
        top_k: int = 3,
        document_types: Optional[List[str]] = None,
        category_set: Optional[Dict[str, str]] = None,
    ) -> List[SimilarChunkResult]:
        """분류 세트 기반 criteria 검색 (DB 필터 포함 hybrid RRF)"""
        if not self.conn:
            raise RuntimeError("Database connection is not initialized. Call connect() first.")

        rds = RDSInternalRetriever(self.db_config, self.embed_api_url)
        query_embedding = rds.embed_query(query)

        filter_dataset = "law_guide"
        filter_document_type = document_types or ["시행규칙", "별표"]
        section = (category_set or {}).get("section_name")
        category = (category_set or {}).get("category_name")
        subcategory = (category_set or {}).get("subcategory_name")

        #중분류는 부분 매칭 허용
        category_like = None
        if category:
            category_like = category if "%" in category else f"%{category}%"

        with self.conn.cursor() as cur:
            cur.execute(
                """
                WITH bm25_results AS (
                    SELECT
                        vc.chunk_id,
                        ts_rank_cd(
                            '{0.1, 0.2, 0.4, 0.6}',
                            vc.text_tsv,
                            websearch_to_tsquery('simple', regexp_replace(%s, '\\s+', ' OR ', 'g'))
                        )::FLOAT as score,
                        ROW_NUMBER() OVER (
                            ORDER BY ts_rank_cd(
                                '{0.1, 0.2, 0.4, 0.6}',
                                vc.text_tsv,
                                websearch_to_tsquery('simple', regexp_replace(%s, '\\s+', ' OR ', 'g'))
                            ) DESC
                        ) as rank
                    FROM vector_chunks vc
                    WHERE
                        vc.text_tsv @@ websearch_to_tsquery('simple', regexp_replace(%s, '\\s+', ' OR ', 'g'))
                        AND ts_rank_cd(
                            '{0.1, 0.2, 0.4, 0.6}',
                            vc.text_tsv,
                            websearch_to_tsquery('simple', regexp_replace(%s, '\\s+', ' OR ', 'g'))
                        ) >= 0.02
                        AND ( %s IS NULL OR vc.dataset_type = %s )
                        AND ( %s IS NULL OR vc.document_type = ANY(%s) )
                        AND ( %s IS NULL OR vc.metadata ->> '대분류' = %s )
                        AND ( %s IS NULL OR vc.metadata ->> '중분류' LIKE %s )
                        AND ( %s IS NULL OR vc.metadata ->> '소분류' = %s )
                    ORDER BY score DESC
                    LIMIT 100
                ),
                vector_results AS (
                    SELECT
                        vc.chunk_id,
                        (1 - (vc.embedding <=> %s::vector))::FLOAT as similarity,
                        ROW_NUMBER() OVER (ORDER BY vc.embedding <=> %s::vector) as rank
                    FROM vector_chunks vc
                    WHERE
                        ( %s IS NULL OR vc.dataset_type = %s )
                        AND ( %s IS NULL OR vc.document_type = ANY(%s) )
                        AND ( %s IS NULL OR vc.metadata ->> '대분류' = %s )
                        AND ( %s IS NULL OR vc.metadata ->> '중분류' LIKE %s )
                        AND ( %s IS NULL OR vc.metadata ->> '소분류' = %s )
                    ORDER BY vc.embedding <=> %s::vector
                    LIMIT 100
                ),
                rrf_combined AS (
                    SELECT
                        COALESCE(b.chunk_id, v.chunk_id) as chunk_id,
                        (COALESCE(1.0 / (60 + b.rank), 0) +
                         COALESCE(1.0 / (60 + v.rank), 0))::FLOAT as rrf_score,
                        COALESCE(b.score, 0)::FLOAT as bm25_score,
                        COALESCE(v.similarity, 0)::FLOAT as vector_similarity
                    FROM bm25_results b
                    FULL OUTER JOIN vector_results v ON b.chunk_id = v.chunk_id
                )
                SELECT
                    vc.chunk_id,
                    vc.dataset_type,
                    vc.text,
                    rc.rrf_score,
                    rc.bm25_score,
                    rc.vector_similarity,
                    vc.law_name,
                    vc.chunk_type,
                    vc.category,
                    vc.document_type,
                    vc.source_url,
                    vc.source_file,
                    vc.printed_page,
                    vc.source_year,
                    vc.metadata
                FROM rrf_combined rc
                JOIN vector_chunks vc ON rc.chunk_id = vc.chunk_id
                ORDER BY rc.rrf_score DESC
                LIMIT %s
                """,
                (
                    query,
                    query,
                    query,
                    query,
                    filter_dataset,
                    filter_dataset,
                    filter_document_type,
                    filter_document_type,
                    section,
                    section,
                    category_like,
                    category_like,
                    subcategory,
                    subcategory,
                    query_embedding,
                    query_embedding,
                    filter_dataset,
                    filter_dataset,
                    filter_document_type,
                    filter_document_type,
                    section,
                    section,
                    category_like,
                    category_like,
                    subcategory,
                    subcategory,
                    query_embedding,
                    top_k,
                ),
            )

            results: List[SimilarChunkResult] = []
            for row in cur.fetchall():
                metadata = row[14]
                if isinstance(metadata, str):
                    try:
                        metadata = json.loads(metadata)
                    except Exception:
                        metadata = None
                metadata = metadata if isinstance(metadata, dict) else {}

                results.append(
                    SimilarChunkResult(
                        chunk_id=row[0],
                        dataset_type=row[1] or "",
                        text=row[2] or "",
                        similarity=float(row[3] or 0.0),
                        law_name=row[6],
                        chunk_type=row[7],
                        category=row[8],
                        document_type=row[9],
                        source_url=row[10],
                        source_file=row[11],
                        printed_page=row[12],
                        source_year=row[13],
                        metadata=metadata or None,
                        vector_similarity=float(row[5] or 0.0),
                        rrf_score=float(row[3] or 0.0),
                    )
                )

        return results

    def search_two_stage(self, query: str, top_k: int = 3) -> List[SimilarChunkResult]:
        """Legacy API wrapper for compatibility."""
        return self.hybrid_search(query, top_k)

    def search_by_article(self, law_id: str, article_no: str) -> List[Dict]:
        """특정 조문의 모든 하위 노드 조회"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    lu.doc_id,
                    lu.level,
                    lu.paragraph_no,
                    lu.item_no,
                    lu.subitem_no,
                    lu.path,
                    lu.text
                FROM law_units lu
                WHERE
                    lu.law_id = %s
                    AND lu.article_no = %s
                ORDER BY
                    CASE lu.level
                        WHEN 'article' THEN 1
                        WHEN 'paragraph' THEN 2
                        WHEN 'item' THEN 3
                        WHEN 'subitem' THEN 4
                    END,
                    lu.paragraph_no, lu.item_no, lu.subitem_no
                """,
                (law_id, article_no),
            )

            return [
                {
                    "doc_id": row[0],
                    "level": row[1],
                    "paragraph_no": row[2],
                    "item_no": row[3],
                    "subitem_no": row[4],
                    "path": row[5],
                    "text": row[6],
                }
                for row in cur.fetchall()
            ]

    def invoke(self, query: str, top_k: int = 10, **kwargs) -> List["Document"]:
        from .base import to_documents

        results = self.hybrid_search(query, top_k)
        return to_documents(results)


class CriteriaRetriever:
    """
    분쟁조정기준 검색기
    """

    def __init__(
        self,
        db_config: Dict[str, str],
        embed_api_url: Optional[str] = None,  # deprecated, kept for compatibility
    ):
        self.db_config = db_config
        self.conn = None
        self._rds_retriever: Optional[RDSInternalRetriever] = None

    def connect(self):
        """데이터베이스 연결"""
        self.conn = psycopg2.connect(**self.db_config)
        self._rds_retriever = RDSInternalRetriever(self.db_config)
        self._rds_retriever.connect()

    def close(self):
        """연결 종료"""
        if self.conn:
            self.conn.close()
        if self._rds_retriever:
            self._rds_retriever.close()

    def embed_query(self, query: str) -> List[float]:
        """쿼리 임베딩 생성 (OpenAI text-embedding-3-large)"""
        if self._rds_retriever is None:
            raise RuntimeError("connect()를 먼저 호출하세요.")
        return self._rds_retriever.embed_query(query)

    def hybrid_search(
        self,
        query: str,
        top_k: int = 3,
        document_types: Optional[List[str]] = None,
    ) -> List[SimilarChunkResult]:
        """
        기준 검색 (RDS 기반 Hybrid RRF)

        Returns:
            List[SimilarChunkResult]
        """
        rds = RDSInternalRetriever(self.db_config, self.embed_api_url)
        rds.connect()
        try:
            doc_types = document_types or ["시행규칙", "별표"]
            rows, _sql_ms = rds.search_hybrid_rrf_2(
                query_text=query,
                filter_dataset="law_guide",
                filter_document_type=doc_types,
                result_limit=top_k,
            )
        finally:
            rds.close()

        results: List[SimilarChunkResult] = []
        for row in rows:
            metadata = row.get("metadata")
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except Exception:
                    metadata = None
            metadata = metadata if isinstance(metadata, dict) else {}

            metadata.update(
                {
                    "source_id": metadata.get("source_id") or metadata.get("sourceId"),
                    "source_label": metadata.get("source_label")
                    or metadata.get("sourceLabel"),
                    "category": metadata.get("category"),
                    "industry": metadata.get("industry"),
                    "item_group": metadata.get("item_group")
                    or metadata.get("itemGroup"),
                    "item": metadata.get("item"),
                    "dispute_type": metadata.get("dispute_type")
                    or metadata.get("disputeType"),
                }
            )

            results.append(
                SimilarChunkResult(
                    chunk_id=row.get("chunk_id", ""),
                    dataset_type=row.get("dataset_type") or "",
                    text=row.get("text", ""),
                    similarity=float(row.get("rrf_score", 0.0)),
                    law_name=None,
                    chunk_type=row.get("chunk_type") or metadata.get("chunk_type"),
                    category=row.get("category") or metadata.get("category"),
                    document_type=row.get("document_type")
                    or (metadata.get("document_type") if metadata else None),
                    source_url=row.get("source_url"),
                    source_file=row.get("source_file"),
                    printed_page=row.get("printed_page"),
                    source_year=row.get("source_year"),
                    metadata=metadata or None,
                    vector_similarity=float(row.get("vector_similarity", 0.0)),
                    rrf_score=float(row.get("rrf_score", 0.0)),
                )
            )

        return results

    def fetch_chunk_texts(self, chunk_ids: List[str]) -> Dict[str, str]:
        """Fetch chunk text by chunk_id from vector_chunks."""
        if not chunk_ids:
            return {}
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    chunk_id,
                    text
                FROM vector_chunks
                WHERE chunk_id = ANY(%s)
                """,
                (chunk_ids,),
            )
            return {row[0]: row[1] for row in cur.fetchall()}

    def search_two_stage(self, query: str, top_k: int = 3) -> List[SimilarChunkResult]:
        """Legacy API wrapper for compatibility."""
        return self.hybrid_search(query, top_k)

    def _get_source_label(self, doc_type: str) -> str:
        """doc_type에서 사람이 읽기 좋은 source_label 생성"""
        labels = {
            "criteria_table1": "소비자분쟁해결기준 별표1 (품목별 분류)",
            "criteria_table2": "소비자분쟁해결기준 별표2 (일반적 기준)",
            "criteria_table3": "소비자분쟁해결기준 별표3 (품목별 기준)",
            "criteria_table4": "소비자분쟁해결기준 별표4 (특수거래)",
            "criteria_content_guideline": "콘텐츠이용자보호지침",
            "criteria_ecommerce_guideline": "전자상거래 소비자보호지침",
        }
        return labels.get(doc_type, doc_type)

    def search_by_category(
        self,
        category: Optional[str] = None,
        industry: Optional[str] = None,
        item_group: Optional[str] = None,
        top_k: int = 10,
    ) -> List[SimilarChunkResult]:
        """카테고리/산업/품목그룹으로 기준 검색"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    cu.unit_id,
                    cu.source_id,
                    c.source_label,
                    cu.category,
                    cu.industry,
                    cu.item_group,
                    cu.item,
                    cu.dispute_type,
                    cu.unit_text,
                    1.0 AS similarity
                FROM criteria_units cu
                JOIN criteria c ON cu.source_id = c.source_id
                WHERE
                    (%s IS NULL OR cu.category = %s)
                    AND (%s IS NULL OR cu.industry = %s)
                    AND (%s IS NULL OR cu.item_group = %s)
                LIMIT %s
                """,
                (category, category, industry, industry, item_group, item_group, top_k),
            )

            return [
                SimilarChunkResult(
                    chunk_id=row[0],
                    dataset_type="criteria",
                    text=row[8],
                    similarity=float(row[9]),
                    law_name=None,
                    chunk_type=None,
                    category=row[3],
                    document_type=None,
                    source_url=None,
                    source_file=None,
                    printed_page=None,
                    source_year=None,
                    metadata={
                        "source_id": row[1],
                        "source_label": row[2],
                        "industry": row[4],
                        "item_group": row[5],
                        "item": row[6],
                        "dispute_type": row[7],
                    },
                )
                for row in cur.fetchall()
            ]

    def invoke(self, query: str, top_k: int = 10, **kwargs) -> List["Document"]:
        from .base import to_documents

        results = self.search_two_stage(query, top_k)
        return to_documents(results)


class CaseRetriever:
    def __init__(
        self,
        db_config: Dict[str, str],
        embed_api_url: Optional[str] = None,  # deprecated, kept for compatibility
    ):
        self.db_config = db_config
        self.conn = None
        self._rds_retriever: Optional[RDSInternalRetriever] = None

    def connect(self):
        self.conn = psycopg2.connect(**self.db_config)
        self._rds_retriever = RDSInternalRetriever(self.db_config)
        self._rds_retriever.connect()

    def close(self):
        """연결 종료"""
        if self.conn:
            self.conn.close()
        if self._rds_retriever:
            self._rds_retriever.close()

    def embed_query(self, query: str) -> List[float]:
        """쿼리 임베딩 생성 (OpenAI text-embedding-3-large)"""
        if self._rds_retriever is None:
            raise RuntimeError("connect()를 먼저 호출하세요.")
        return self._rds_retriever.embed_query(query)

    def _search_by_doc_type(
        self, query: str, doc_type: str, top_k: int = 3
    ) -> List[Dict]:
        """특정 doc_type으로 검색"""
        query_embedding = self.embed_query(query)

        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    c.chunk_id,
                    c.doc_id,
                    c.chunk_type,
                    c.content,
                    d.title,
                    d.source_org,
                    d.url,
                    d.metadata,
                    1 - (c.embedding <=> %s::vector) AS similarity
                FROM chunks c
                JOIN documents d ON c.doc_id = d.doc_id
                WHERE
                    d.doc_type = %s
                    AND c.embedding IS NOT NULL
                    AND c.drop = FALSE
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                (query_embedding, doc_type, query_embedding, top_k),
            )

            results = []
            for row in cur.fetchall():
                metadata = row[7] if row[7] else {}
                results.append(
                    {
                        "chunk_id": row[0],
                        "doc_id": row[1],
                        "chunk_type": row[2],
                        "content": row[3],
                        "doc_title": row[4],
                        "source_org": row[5],
                        "url": row[6],
                        "decision_date": metadata.get("decision_date"),
                        "similarity": float(row[8]),
                    }
                )

            return results

    def _search_with_candidate_pool(
        self, query: str, doc_type: str, candidate_count: int
    ) -> List[Dict]:
        """
        문서 수준 유사도 계산을 위한 후보 청크 검색 (확대된 후보군)

        Args:
            query: 검색 쿼리
            doc_type: 문서 유형
            candidate_count: 검색할 후보 청크 수

        Returns:
            청크 목록 (더 많은 후보)
        """
        query_embedding = self.embed_query(query)

        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    c.chunk_id,
                    c.doc_id,
                    c.chunk_type,
                    c.chunk_index,
                    c.content,
                    d.title,
                    d.source_org,
                    d.url,
                    d.metadata,
                    1 - (c.embedding <=> %s::vector) AS similarity,
                    (SELECT COUNT(*) FROM chunks c2 WHERE c2.doc_id = c.doc_id AND c2.drop = FALSE) AS total_chunks
                FROM chunks c
                JOIN documents d ON c.doc_id = d.doc_id
                WHERE
                    d.doc_type = %s
                    AND c.embedding IS NOT NULL
                    AND c.drop = FALSE
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                (query_embedding, doc_type, query_embedding, candidate_count),
            )

            results = []
            for row in cur.fetchall():
                metadata = row[8] if row[8] else {}
                results.append(
                    {
                        "chunk_id": row[0],
                        "doc_id": row[1],
                        "chunk_type": row[2],
                        "chunk_index": row[3],
                        "content": row[4],
                        "doc_title": row[5],
                        "source_org": row[6],
                        "url": row[7],
                        "decision_date": metadata.get("decision_date"),
                        "similarity": float(row[9]),
                        "total_doc_chunks": row[10],
                    }
                )

            return results

    def _aggregate_by_document(
        self, chunks: List[Dict], top_k: int
    ) -> List[DocumentLevelResult]:
        """
        청크들을 문서별로 그룹화하고 평균 유사도 계산

        Args:
            chunks: 검색된 청크 목록
            top_k: 반환할 문서 수

        Returns:
            평균 유사도 기준 상위 문서 목록
        """
        # doc_id별 청크 그룹화
        doc_chunks = defaultdict(list)
        doc_metadata = {}

        for chunk in chunks:
            doc_id = chunk["doc_id"]
            doc_chunks[doc_id].append(chunk)

            # 문서 메타데이터 저장 (첫 번째 청크 기준)
            if doc_id not in doc_metadata:
                doc_metadata[doc_id] = {
                    "doc_title": chunk["doc_title"],
                    "source_org": chunk["source_org"],
                    "url": chunk.get("url"),
                    "decision_date": chunk.get("decision_date"),
                    "total_doc_chunks": chunk.get("total_doc_chunks", 1),
                }

        # 문서별 유사도 통계 계산
        doc_results = []
        for doc_id, chunks_list in doc_chunks.items():
            similarities = [c["similarity"] for c in chunks_list]
            avg_similarity = sum(similarities) / len(similarities)
            max_similarity = max(similarities)
            min_similarity = min(similarities)

            # 가장 유사한 청크 선택
            best_chunk = max(chunks_list, key=lambda c: c["similarity"])

            meta = doc_metadata[doc_id]
            doc_results.append(
                DocumentLevelResult(
                    doc_id=doc_id,
                    doc_title=meta["doc_title"],
                    source_org=meta["source_org"],
                    avg_similarity=avg_similarity,
                    max_similarity=max_similarity,
                    min_similarity=min_similarity,
                    chunk_count=len(chunks_list),
                    total_doc_chunks=meta["total_doc_chunks"],
                    best_chunk=best_chunk,
                    all_chunks=chunks_list,
                )
            )

        # 평균 유사도로 정렬
        doc_results.sort(key=lambda d: d.avg_similarity, reverse=True)

        return doc_results[:top_k]

    def _document_results_to_chunks(
        self, doc_results: List[DocumentLevelResult]
    ) -> List[Dict]:
        """
        DocumentLevelResult를 기존 chunk dict 형식으로 변환

        각 문서의 best_chunk를 반환하며, 문서 수준 유사도 정보 추가

        Args:
            doc_results: 문서 수준 검색 결과

        Returns:
            청크 목록 (기존 형식 호환)
        """
        results = []
        for doc_result in doc_results:
            chunk = doc_result.best_chunk.copy()

            # 문서 수준 유사도 정보 추가
            chunk["doc_similarity"] = doc_result.avg_similarity
            chunk["doc_chunk_count"] = doc_result.chunk_count
            chunk["doc_total_chunks"] = doc_result.total_doc_chunks

            # 원래 similarity는 청크 수준, doc_similarity가 문서 수준
            # 정렬/표시를 위해 similarity도 문서 평균으로 대체 가능
            # chunk['original_chunk_similarity'] = chunk['similarity']
            # chunk['similarity'] = doc_result.avg_similarity

            results.append(chunk)

        return results

    def search_disputes(self, query: str, top_k: int = 3) -> List[Dict]:
        """
        분쟁조정사례 검색 (doc_type='mediation_case')

        법적 효력이 있는 분쟁조정 결과

        Phase 3: 문서 수준 유사도 검색이 활성화된 경우:
        - 더 많은 후보 청크를 검색하고
        - doc_id별로 그룹화하여 평균 유사도 계산
        - 평균 유사도가 높은 문서의 best chunk 반환
        """
        if ENABLE_DOCUMENT_LEVEL_SIMILARITY:
            # 더 많은 후보 검색
            candidate_count = top_k * DOCUMENT_SIMILARITY_CANDIDATE_MULTIPLIER
            candidates = self._search_with_candidate_pool(
                query, "mediation_case", candidate_count
            )

            if not candidates:
                return []

            # 문서별 집계
            doc_results = self._aggregate_by_document(candidates, top_k)

            # 기존 형식으로 변환
            return self._document_results_to_chunks(doc_results)
        else:
            # 기존 방식: 개별 청크 유사도
            return self._search_by_doc_type(query, "mediation_case", top_k)

    def search_counsels(self, query: str, top_k: int = 3) -> List[Dict]:
        """
        상담사례 검색 (doc_type='counsel_case')

        참고용 상담 사례
        """
        return self._search_by_doc_type(query, "counsel_case", top_k)

    def search_both(
        self, query: str, dispute_k: int = 3, counsel_k: int = 3
    ) -> Dict[str, List[Dict]]:
        """
        분쟁조정사례와 상담사례 동시 검색

        Returns:
            {
                'disputes': [...],
                'counsels': [...]
            }
        """
        disputes = self.search_disputes(query, dispute_k)

        # Phase 2: 분쟁조정사례 메타데이터 추출
        if ENABLE_DISPUTE_METADATA_EXTRACTION and disputes:
            disputes = self.extract_dispute_metadata(disputes)

        return {
            "disputes": disputes,
            "counsels": self.search_counsels(query, counsel_k),
        }

    def extract_dispute_metadata(self, disputes: List[Dict]) -> List[Dict]:
        """
        분쟁조정사례에서 품목, 금액, 일시, 조정결과 메타데이터 추출 (실시간 LLM)

        Args:
            disputes: 검색된 분쟁조정사례 목록

        Returns:
            메타데이터가 추가된 분쟁조정사례 목록
        """
        try:
            from ...llm.exaone_client import ExaoneLLMClient, LLMUnavailableError

            client = ExaoneLLMClient()
            if not client.is_available():
                logger.warning(
                    "[CaseRetriever] LLM unavailable, skipping metadata extraction"
                )
                return disputes

            system_prompt = """당신은 분쟁조정사례에서 핵심 정보를 추출하는 전문가입니다.
주어진 텍스트에서 다음 정보를 추출하여 JSON 형식으로 반환하세요:
- product_item: 분쟁 대상 품목 (예: "키보드", "헬스회원권", "냄비세트")
- dispute_amount: 분쟁 금액 (예: "120,000원", "587,450원")
- transaction_date: 거래/구매 일자 (예: "2024.01.15", "2024년 1월")
- mediation_result: 조정 결과 (예: "인용", "기각", "조정성립", "환불 결정")

정보가 없으면 null로 표시하세요. 반드시 유효한 JSON만 반환하세요."""

            for dispute in disputes:
                content = dispute.get("content", "")[:1500]  # 1500자 제한
                if not content:
                    continue

                try:
                    user_prompt = f"""다음 분쟁조정사례에서 정보를 추출하세요:

{content}

JSON 형식으로 반환:"""

                    response = client.generate(system_prompt, user_prompt)

                    # JSON 파싱 시도
                    metadata = self._parse_metadata_json(response)
                    if metadata:
                        dispute["product_item"] = metadata.get("product_item")
                        dispute["dispute_amount"] = metadata.get("dispute_amount")
                        dispute["transaction_date"] = metadata.get("transaction_date")
                        dispute["mediation_result"] = metadata.get("mediation_result")

                except LLMUnavailableError:
                    logger.warning(
                        "[CaseRetriever] LLM became unavailable during extraction"
                    )
                    break
                except Exception as e:
                    logger.debug(
                        f"[CaseRetriever] Metadata extraction failed for {dispute.get('doc_id')}: {e}"
                    )
                    continue

            return disputes

        except ImportError:
            logger.warning("[CaseRetriever] ExaoneLLMClient not available")
            return disputes
        except Exception as e:
            logger.warning(f"[CaseRetriever] Metadata extraction error: {e}")
            return disputes

    def _parse_metadata_json(self, response: str) -> Optional[Dict]:
        """LLM 응답에서 JSON 추출 및 파싱"""
        try:
            # JSON 블록 찾기
            response = response.strip()

            # ```json ... ``` 형식 처리
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                if end > start:
                    response = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                if end > start:
                    response = response[start:end].strip()

            # { ... } 찾기
            if "{" in response and "}" in response:
                start = response.find("{")
                end = response.rfind("}") + 1
                json_str = response[start:end]
                return json.loads(json_str)

            return None
        except json.JSONDecodeError:
            return None

    def invoke(
        self, query: str, top_k: int = 10, doc_type: str = "mediation_case", **kwargs
    ) -> List["Document"]:
        from .base import to_documents

        results = self._search_by_doc_type(query, doc_type, top_k)
        return to_documents(results)


class AgencyClassifier:
    """
    추천 기관 분류기

    분쟁 유형에 따라 적절한 기관 추천:
    - KCA (한국소비자원): 1:N 일반 소비자 분쟁
    - ECMC (전자거래분쟁조정위원회): 1:1 개인간 거래
    - KCDRC (콘텐츠분쟁조정위원회): 콘텐츠 관련 분쟁
    """

    # 콘텐츠 관련 키워드 (KCDRC)
    CONTENT_KEYWORDS = [
        "게임",
        "영화",
        "콘텐츠",
        "앱",
        "어플",
        "애플리케이션",
        "음악",
        "웹툰",
        "만화",
        "동영상",
        "영상",
        "스트리밍",
        "OTT",
        "넷플릭스",
        "왓챠",
        "디즈니",
        "유튜브",
        "인앱",
        "결제",
        "아이템",
        "캐시",
        "다이아",
        "루비",
        "디지털",
        "다운로드",
        "구독",
        "VOD",
        "e북",
        "전자책",
    ]

    # 개인간 거래 키워드 (ECMC)
    INDIVIDUAL_KEYWORDS = [
        "중고",
        "직거래",
        "당근",
        "당근마켓",
        "번개장터",
        "중고나라",
        "개인간",
        "개인거래",
        "개인 판매",
        "개인판매자",
        "직접 거래",
        "직접거래",
        "만나서",
        "택배거래",
        "중고거래",
        "중고 거래",
        "세컨핸드",
        "second hand",
    ]

    # 기관 정보
    AGENCIES = {
        "KCA": {
            "name": "한국소비자원",
            "full_name": "한국소비자원 소비자분쟁조정위원회",
            "description": "일반 소비자 분쟁 조정 (사업자 대 소비자)",
            "url": "https://www.kca.go.kr",
        },
        "ECMC": {
            "name": "전자거래분쟁조정위원회",
            "full_name": "전자거래분쟁조정위원회",
            "description": "전자거래 및 개인간 거래 분쟁 조정",
            "url": "https://www.ecmc.or.kr",
        },
        "KCDRC": {
            "name": "콘텐츠분쟁조정위원회",
            "full_name": "콘텐츠분쟁조정위원회",
            "description": "콘텐츠(게임, 영화, 음악 등) 관련 분쟁 조정",
            "url": "https://www.kcdrc.kr",
        },
    }

    def classify(self, query: str) -> Dict:
        """
        질문을 분석하여 적절한 기관 추천

        Args:
            query: 사용자 질문

        Returns:
            {
                'agency': 'KCA' | 'ECMC' | 'KCDRC',
                'agency_info': {...},
                'dispute_type': '1:N' | '1:1' | 'contents',
                'reason': '추천 이유',
                'confidence': 0.0 ~ 1.0,
                'matched_keywords': [...]  # 매칭된 키워드 목록
            }
        """
        query_lower = query.lower()

        # 콘텐츠 관련 키워드 체크
        content_matches = [kw for kw in self.CONTENT_KEYWORDS if kw in query_lower]
        if content_matches:
            return {
                "agency": "KCDRC",
                "agency_info": self.AGENCIES["KCDRC"],
                "dispute_type": "contents",
                "reason": f"콘텐츠 관련 분쟁으로 판단됩니다 (키워드: {', '.join(content_matches[:3])})",
                "confidence": min(0.6 + len(content_matches) * 0.1, 1.0),
                "matched_keywords": content_matches,
            }

        # 개인간 거래 키워드 체크
        individual_matches = [
            kw for kw in self.INDIVIDUAL_KEYWORDS if kw in query_lower
        ]
        if individual_matches:
            return {
                "agency": "ECMC",
                "agency_info": self.AGENCIES["ECMC"],
                "dispute_type": "1:1",
                "reason": f"개인간 거래 분쟁으로 판단됩니다 (키워드: {', '.join(individual_matches[:3])})",
                "confidence": min(0.6 + len(individual_matches) * 0.1, 1.0),
                "matched_keywords": individual_matches,
            }

        # 기본값: KCA (일반 소비자 분쟁)
        return {
            "agency": "KCA",
            "agency_info": self.AGENCIES["KCA"],
            "dispute_type": "1:N",
            "reason": "일반 소비자 분쟁으로 판단됩니다 (사업자 대 소비자)",
            "confidence": 0.7,
            "matched_keywords": [],
        }


class StructuredRetriever:
    """
    4개 섹션 통합 검색기

    1. 추천 기관 (AgencyClassifier)
    2. 유사 사례 (CaseRetriever)
    3. 관련 법령 (LawRetriever)
    4. 관련 기준 (CriteriaRetriever)
    """

    def __init__(
        self,
        db_config: Dict[str, str],
        embed_api_url: Optional[str] = None,  # deprecated, kept for compatibility
    ):
        self.db_config = db_config

        self.agency_classifier = AgencyClassifier()
        self.case_retriever = CaseRetriever(db_config)
        self.law_retriever = LawRetriever(db_config)
        self.criteria_retriever = CriteriaRetriever(db_config)

    def connect(self):
        """모든 retriever 연결"""
        self.case_retriever.connect()
        self.law_retriever.connect()
        self.criteria_retriever.connect()

    def close(self):
        """모든 retriever 연결 종료"""
        self.case_retriever.close()
        self.law_retriever.close()
        self.criteria_retriever.close()

    def search_all_sections(
        self,
        query: str,
        dispute_k: int = 3,
        counsel_k: int = 3,
        law_k: int = 3,
        criteria_k: int = 3,
    ) -> Dict:
        """
        4개 섹션 데이터 일괄 검색

        Returns:
            {
                'agency': {...},          # 추천 기관
                'disputes': [...],        # 분쟁조정사례
                'counsels': [...],        # 상담사례
                'laws': [...],            # 관련 법령
                'criteria': [...]         # 관련 기준
            }
        """
        # 1. 기관 분류
        agency_result = self.agency_classifier.classify(query)

        # 2. 사례 검색
        cases = self.case_retriever.search_both(query, dispute_k, counsel_k)

        # 3. 법령 검색
        law_results = self.law_retriever.search_two_stage(query, law_k)

        # 4. 기준 검색
        criteria_results = self.criteria_retriever.search_two_stage(query, criteria_k)

        return {
            "agency": agency_result,
            "disputes": cases["disputes"],
            "counsels": cases["counsels"],
            "laws": [
                {
                    "chunk_id": r.chunk_id,
                    "dataset_type": r.dataset_type,
                    "text": r.text,
                    "similarity": r.similarity,
                    "law_name": r.law_name,
                    "chunk_type": r.chunk_type,
                    "category": r.category,
                    "source_url": r.source_url,
                    "source_file": r.source_file,
                    "printed_page": r.printed_page,
                    "source_year": r.source_year,
                    "hierarchy_path": (r.metadata or {}).get("hierarchy_path"),
                    "metadata": r.metadata,
                }
                for r in law_results
            ],
            "criteria": [
                {
                    "chunk_id": r.chunk_id,
                    "dataset_type": r.dataset_type,
                    "text": r.text,
                    "similarity": r.similarity,
                    "law_name": r.law_name,
                    "chunk_type": r.chunk_type,
                    "category": r.category,
                    "source_url": r.source_url,
                    "source_file": r.source_file,
                    "printed_page": r.printed_page,
                    "source_year": r.source_year,
                    "hierarchy_path": (r.metadata or {}).get("hierarchy_path"),
                    "metadata": r.metadata,
                }
                for r in criteria_results
            ],
        }
