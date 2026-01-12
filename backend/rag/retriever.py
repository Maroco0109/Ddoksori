"""
똑소리 프로젝트 - RAG 검색 시스템
작성일: 2026-01-05
벡터 검색, 하이브리드 검색, 컨텍스트 확장 기능 제공
"""

import psycopg2
import time
from typing import List, Dict, Optional, Tuple
import requests
from dataclasses import dataclass
import re


@dataclass
class SearchResult:
    """검색 결과 데이터 클래스 (S1-1 citation metadata)"""
    # Core fields
    chunk_id: str
    doc_id: str
    chunk_type: str
    content: str
    doc_title: str
    doc_type: str
    category_path: List[str]
    similarity: float

    # S1-1 Citation metadata
    source_org: Optional[str] = None      # KCA/ECMC/KCDRC/statute/consumer.go.kr
    url: Optional[str] = None             # Original document URL
    decision_date: Optional[str] = None   # From metadata['decision_date']
    collected_at: Optional[str] = None    # Document collection timestamp

    metadata: Optional[Dict] = None


class RAGRetriever:
    """RAG 검색 시스템"""
    
    def __init__(self, db_config: Dict[str, str], embed_api_url: str = "http://localhost:8001/embed"):
        self.db_config = db_config
        self.embed_api_url = embed_api_url
        self.conn = None
        
        # 쿼리 유형별 데이터 소스 가중치
        self.QUERY_TYPE_WEIGHTS = {
            'legal_interpretation': {  # 법률 해석 질문
                'law': 0.6,
                'mediation_case': 0.3,
                'counsel_case': 0.1
            },
            'similar_case': {  # 유사 사례 질문
                'mediation_case': 0.5,
                'counsel_case': 0.4,
                'law': 0.1
            },
            'general_inquiry': {  # 일반 문의
                'counsel_case': 0.5,
                'mediation_case': 0.3,
                'law': 0.2
            }
        }
    
    def connect(self):
        """데이터베이스 연결"""
        self.conn = psycopg2.connect(**self.db_config)
    
    def close(self):
        """데이터베이스 연결 종료"""
        if self.conn:
            self.conn.close()
    
    def embed_query(self, query: str) -> List[float]:
        """쿼리 임베딩 생성"""
        try:
            response = requests.post(
                self.embed_api_url,
                json={"texts": [query]},
                timeout=10
            )
            response.raise_for_status()
            embeddings = response.json()['embeddings']
            return embeddings[0]
        except requests.exceptions.RequestException as e:
            raise Exception(f"임베딩 API 오류: {e}")

    def embed_query_timed(self, query: str) -> Tuple[List[float], float]:
        """
        쿼리 임베딩 생성 with timing

        Returns:
            Tuple of (embedding_vector, time_ms)
        """
        start = time.time()
        embedding = self.embed_query(query)
        time_ms = (time.time() - start) * 1000
        return embedding, time_ms

    def vector_search_instrumented(
        self,
        query: str,
        top_k: int = 10,
        doc_type_filter: Optional[str] = None,
        chunk_type_filter: Optional[str] = None
    ) -> Dict:
        """
        벡터 유사도 검색 with timing info

        Returns:
            {
                'results': List[SearchResult],
                'embedding_time_ms': float,
                'search_time_ms': float
            }
        """
        # Embedding with timing
        query_embedding, embed_time = self.embed_query_timed(query)

        # Search with timing
        search_start = time.time()

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
                    AND (%s IS NULL OR d.doc_type = %s)
                    AND (%s IS NULL OR c.chunk_type = %s)
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                (
                    query_embedding,
                    doc_type_filter, doc_type_filter,
                    chunk_type_filter, chunk_type_filter,
                    query_embedding,
                    top_k
                )
            )

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
                    similarity=float(row[7]),
                    source_org=row[8],
                    url=row[9],
                    collected_at=row[10].isoformat() if row[10] else None,
                    decision_date=decision_date,
                    metadata=metadata_json
                ))

        search_time = (time.time() - search_start) * 1000

        return {
            'results': results,
            'embedding_time_ms': embed_time,
            'search_time_ms': search_time
        }

    def vector_search(
        self,
        query: str,
        top_k: int = 10,
        doc_type_filter: Optional[str] = None,
        chunk_type_filter: Optional[str] = None
    ) -> List[SearchResult]:
        """벡터 유사도 검색"""
        # 쿼리 임베딩 생성
        query_embedding = self.embed_query(query)
        
        # 데이터베이스 검색
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
                    AND (%s IS NULL OR d.doc_type = %s)
                    AND (%s IS NULL OR c.chunk_type = %s)
                ORDER BY c.embedding <=> %s::vector
                LIMIT %s
                """,
                (
                    query_embedding,
                    doc_type_filter, doc_type_filter,
                    chunk_type_filter, chunk_type_filter,
                    query_embedding,
                    top_k
                )
            )

            results = []
            for row in cur.fetchall():
                # Parse decision_date from metadata if exists
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
                    similarity=float(row[7]),
                    source_org=row[8],
                    url=row[9],
                    collected_at=row[10].isoformat() if row[10] else None,
                    decision_date=decision_date,
                    metadata=metadata_json
                ))

            return results
    
    def keyword_search(
        self,
        query: str,
        top_k: int = 10,
        doc_type_filter: Optional[str] = None,
        chunk_type_filter: Optional[str] = None,
        use_fts: bool = True
    ) -> List[SearchResult]:
        """
        키워드 기반 검색 (PostgreSQL FTS 또는 LIKE 폴백)

        Args:
            query: 검색 쿼리
            top_k: 반환할 최대 결과 수
            doc_type_filter: 문서 타입 필터
            chunk_type_filter: 청크 타입 필터
            use_fts: True이면 FTS 사용, False이면 LIKE 폴백

        Returns:
            검색 결과 리스트
        """
        if use_fts:
            return self._keyword_search_fts(query, top_k, doc_type_filter, chunk_type_filter)
        else:
            return self._keyword_search_like(query, top_k, doc_type_filter)

    def _keyword_search_fts(
        self,
        query: str,
        top_k: int,
        doc_type_filter: Optional[str] = None,
        chunk_type_filter: Optional[str] = None
    ) -> List[SearchResult]:
        """FTS 기반 키워드 검색 (mv_searchable_chunks 사용)"""
        with self.conn.cursor() as cur:
            # 토큰화: 공백으로 분리하고 '&'로 연결 (AND 검색)
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
                # 문서 제목 조회
                cur.execute(
                    "SELECT title FROM documents WHERE doc_id = %s",
                    (row[1],)
                )
                doc_title_row = cur.fetchone()
                doc_title = doc_title_row[0] if doc_title_row else "Unknown"

                results.append(SearchResult(
                    chunk_id=row[0],
                    doc_id=row[1],
                    chunk_type=row[2],
                    content=row[3],
                    doc_title=doc_title,
                    doc_type=row[4],
                    category_path=row[6] or [],
                    similarity=float(row[7])  # ts_rank score
                ))

            return results

    def _keyword_search_like(
        self,
        query: str,
        top_k: int,
        doc_type_filter: Optional[str] = None
    ) -> List[SearchResult]:
        """LIKE 기반 키워드 검색 (폴백용)"""
        # 한국어 키워드 추출 (간단한 토큰화)
        keywords = self._extract_keywords(query)

        with self.conn.cursor() as cur:
            # LIKE 검색 (간단한 구현)
            search_pattern = f"%{query}%"

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
                    0.5 AS similarity
                FROM chunks c
                JOIN documents d ON c.doc_id = d.doc_id
                WHERE
                    (c.content LIKE %s OR d.title LIKE %s)
                    AND (%s IS NULL OR d.doc_type = %s)
                LIMIT %s
                """,
                (
                    search_pattern, search_pattern,
                    doc_type_filter, doc_type_filter,
                    top_k
                )
            )

            results = []
            for row in cur.fetchall():
                results.append(SearchResult(
                    chunk_id=row[0],
                    doc_id=row[1],
                    chunk_type=row[2],
                    content=row[3],
                    doc_title=row[4],
                    doc_type=row[5],
                    category_path=row[6] or [],
                    similarity=float(row[7])
                ))

            return results
    
    def hybrid_search(
        self,
        query: str,
        top_k: int = 10,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
        doc_type_filter: Optional[str] = None
    ) -> List[SearchResult]:
        """하이브리드 검색 (벡터 + 키워드)"""
        # 벡터 검색
        vector_results = self.vector_search(
            query,
            top_k=top_k * 2,
            doc_type_filter=doc_type_filter
        )
        
        # 키워드 검색
        keyword_results = self.keyword_search(
            query,
            top_k=top_k * 2,
            doc_type_filter=doc_type_filter
        )
        
        # 결과 병합 및 가중치 적용
        merged_results = {}
        
        for result in vector_results:
            merged_results[result.chunk_id] = {
                'result': result,
                'score': result.similarity * vector_weight
            }
        
        for result in keyword_results:
            if result.chunk_id in merged_results:
                merged_results[result.chunk_id]['score'] += result.similarity * keyword_weight
            else:
                merged_results[result.chunk_id] = {
                    'result': result,
                    'score': result.similarity * keyword_weight
                }
        
        # 점수 기준 정렬
        sorted_results = sorted(
            merged_results.values(),
            key=lambda x: x['score'],
            reverse=True
        )
        
        # 점수 업데이트 및 반환
        final_results = []
        for item in sorted_results[:top_k]:
            result = item['result']
            result.similarity = item['score']
            final_results.append(result)
        
        return final_results
    
    def multi_source_search(
        self,
        query: str,
        query_type: str = 'general_inquiry',
        top_k: int = 10
    ) -> List[SearchResult]:
        """멀티 소스 검색 (데이터 유형별 가중치 적용)"""
        weights = self.QUERY_TYPE_WEIGHTS.get(query_type, self.QUERY_TYPE_WEIGHTS['general_inquiry'])
        
        all_results = []
        
        for doc_type, weight in weights.items():
            # 각 데이터 소스별 검색
            results = self.vector_search(
                query,
                top_k=int(top_k * weight * 2),
                doc_type_filter=doc_type
            )
            
            # 가중치 적용
            for result in results:
                result.similarity *= weight
                all_results.append(result)
        
        # 점수 기준 정렬
        all_results.sort(key=lambda x: x.similarity, reverse=True)
        
        return all_results[:top_k]
    
    def get_chunk_with_context(
        self,
        chunk_id: str,
        window_size: int = 1
    ) -> List[SearchResult]:
        """청크와 주변 컨텍스트 조회"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM get_chunk_with_context(%s, %s)
                """,
                (chunk_id, window_size)
            )
            
            results = []
            for row in cur.fetchall():
                # 추가 정보 조회
                cur.execute(
                    """
                    SELECT d.title, d.doc_type, d.category_path
                    FROM documents d
                    WHERE d.doc_id = %s
                    """,
                    (row[1],)
                )
                doc_info = cur.fetchone()
                
                results.append(SearchResult(
                    chunk_id=row[0],
                    doc_id=row[1],
                    chunk_type=row[3],
                    content=row[4],
                    doc_title=doc_info[0] if doc_info else "",
                    doc_type=doc_info[1] if doc_info else "",
                    category_path=doc_info[2] if doc_info else [],
                    similarity=1.0 if row[5] else 0.8,  # is_target
                    metadata={'is_target': row[5]}
                ))
            
            return results
    
    def expand_context_for_results(
        self,
        results: List[SearchResult],
        window_size: int = 1
    ) -> List[SearchResult]:
        """검색 결과에 대한 컨텍스트 확장"""
        expanded_results = []
        seen_chunk_ids = set()
        
        for result in results:
            # 주변 청크 조회
            context_chunks = self.get_chunk_with_context(result.chunk_id, window_size)
            
            for chunk in context_chunks:
                if chunk.chunk_id not in seen_chunk_ids:
                    expanded_results.append(chunk)
                    seen_chunk_ids.add(chunk.chunk_id)
        
        return expanded_results
    
    def _extract_keywords(self, query: str) -> List[str]:
        """쿼리에서 키워드 추출 (간단한 구현)"""
        # 한국어 명사 추출 (간단한 토큰화)
        # 실제로는 KoNLPy 등을 사용하는 것이 좋음
        keywords = re.findall(r'[가-힣]+', query)
        return [kw for kw in keywords if len(kw) >= 2]
    
    def format_results_for_llm(self, results: List[SearchResult]) -> str:
        """검색 결과를 LLM 입력 형식으로 포맷팅"""
        formatted = []
        
        for i, result in enumerate(results, 1):
            formatted.append(f"[검색 결과 {i}]")
            formatted.append(f"문서 유형: {result.doc_type}")
            formatted.append(f"제목: {result.doc_title}")
            formatted.append(f"청크 유형: {result.chunk_type}")
            formatted.append(f"유사도: {result.similarity:.4f}")
            formatted.append(f"\n내용:\n{result.content}")
            formatted.append("\n" + "=" * 60 + "\n")
        
        return "\n".join(formatted)


def main():
    """테스트용 메인 함수"""
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', '5432'),
        'database': os.getenv('DB_NAME', 'ddoksori'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'postgres')
    }
    
    embed_api_url = os.getenv('EMBED_API_URL', 'http://localhost:8001/embed')
    
    retriever = RAGRetriever(db_config, embed_api_url)
    retriever.connect()
    
    try:
        # 테스트 쿼리
        query = "환불 받을 수 있나요?"
        print(f"쿼리: {query}\n")
        
        # 벡터 검색
        print("=== 벡터 검색 ===")
        results = retriever.vector_search(query, top_k=3)
        for i, result in enumerate(results, 1):
            print(f"{i}. {result.doc_title} ({result.doc_type}) - 유사도: {result.similarity:.4f}")
        
        print("\n=== 하이브리드 검색 ===")
        results = retriever.hybrid_search(query, top_k=3)
        for i, result in enumerate(results, 1):
            print(f"{i}. {result.doc_title} ({result.doc_type}) - 점수: {result.similarity:.4f}")
        
    finally:
        retriever.close()


if __name__ == "__main__":
    main()
