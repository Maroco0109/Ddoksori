# RDSRetriever 간단 사용 가이드

## 위치
- `backend/app/agents/retrieval/tools/rds_retriever.py`

## 주요 클래스
- `RDSRetriever`: vector_chunks 기반 직접 SQL 검색기

## 생성/연결
- `RDSRetriever(db_config=None, embed_api_url=None)`
- `connect()` / `close()`

## 주요 메서드 (모든 인자)
- `embed_query(query: str) -> List[float]`

- `dense_search(
    query: str,
    filter_dataset: Optional[str] = None,
    filter_category: Optional[str] = None,
    filter_law_name: Optional[str] = None,
    filter_document_type: Optional[List[str]] = None,
    filter_year: Optional[int] = None,
    result_limit: int = 10,
    exclude_deleted: bool = True,
  ) -> (List[SimilarChunkResult], embed_ms, sql_ms)`

- `keyword_search(
    query_text: str,
    filter_dataset: Optional[str] = None,
    filter_category: Optional[str] = None,
    filter_document_type: Optional[List[str]] = None,
    result_limit: int = 100,
    exclude_deleted: bool = True,
  ) -> (List[Dict], sql_ms)`

- `keyword_search_split(
    query_text: str,
    filter_dataset: Optional[str] = None,
    filter_category: Optional[str] = None,
    filter_document_type: Optional[List[str]] = None,
    result_limit: int = 100,
    exclude_deleted: bool = True,
  ) -> (List[Dict], sql_ms)`
  - 조문 토큰(예: "제110조") 분리 후 BM25 결과 합산

- `hybrid_rrf_search(
    query_text: str,
    filter_dataset: Optional[str] = None,
    filter_category: Optional[str] = None,
    filter_document_type: Optional[List[str]] = None,
    filter_year: Optional[int] = None,
    result_limit: int = 10,
    rrf_k: int = 60,
    exclude_deleted: bool = True,
  ) -> (List[Dict], sql_ms)`

## 편의 함수
- `hybrid_rrf_search(...)` (모듈 레벨 함수)
  - 내부에서 `RDSRetriever` 생성/연결/종료까지 처리

## 데이터 필드 (대표)
- dense/hybrid 결과에는 `chunk_id`, `dataset_type`, `text`, `source_year`, `metadata` 등이 포함됨

## 인자 값 예시/범위
- `filter_document_type`:  vector_chunks.document_type. [NULL, '별표', '시행령', '행정규칙', '법률']
- `filter_dataset`: vector_chunks.dataset_type. ['law_guide', 'case']
- `filter_category`: vector_chunks.category. [NULL, '상담', '해결', '조정']
- `filter_law_name`: vector_chunks.law_name. [NULL, '관의 규제에 관한 법률', '콘텐츠이용자 보호지침'] 등 NULL 포함 25개
- `filter_year`: vector_chunks.source_year. [NULL, 2010~2026]


## 사용 예시
```python
from backend.app.agents.retrieval.tools.rds_retriever import RDSRetriever

retriever = RDSRetriever()
retriever.connect()

try:
    query = "민법 제110조 알려줘"

    dense_results, embed_ms, sql_ms = retriever.dense_search(
        query=query,
        result_limit=3,
    )

    keyword_results, keyword_sql_ms = retriever.keyword_search(
        query_text=query,
        result_limit=3,
    )

    keyword_results, keyword_sql_ms = retriever.keyword_search_split(
        query_text=query,
        result_limit=3,
    )

    hybrid_results, hybrid_sql_ms = retriever.hybrid_rrf_search(
        query_text=query,
        filter_document_type=["법률", "시행령"],
        result_limit=3,
    )
finally:
    retriever.close()
```
