# Law/Criteria Retrieval Subagents - Runtime Flow (process() 기준)

이 문서는 **law_agent.py / criteria_agent.py**의 실제 실행 흐름을 기준으로, `.process()` 호출 시 어떤 모듈들이 어떤 순서로 동작하는지 정리한다. 기존 내용은 폐기한다.

---

## 공통 진입점
### BaseRetrievalAgent.process()
- 파일: `backend/app/agents/retrieval/base_retrieval_agent.py`
- 역할:
  1) request 검증
  2) `context.user_query`, `context.query_analysis` 추출
  3) `context.retrieval_task_input`가 있으면 사용 (없으면 `query_analysis.retrieval_task_input` fallback)
  4) `retrieval_task_input`이 없으면 실패 처리
  5) `_execute_search()` 호출
     - 시그니처에 `task_input`이 있으면 함께 전달
  6) `_format_results()`로 결과 포맷
  7) `_build_sources()`로 sources 생성
  8) 응답 메시지 구성 ("n건 검색 완료")

### 공통 입력/출력
- 입력(요구됨): `context.retrieval_task_input`
  - `expanded_queries: List[str]` (확장 쿼리)
  - `agent_keywords: List[str]` (현재 미사용)
  - `metadata_filter.document_types: Optional[List[str]]`
  - `top_k: int`
  - `ignore_threshold: bool` (현재 미사용)
- 출력:
  - `results`: LawDocument 또는 CriteriaDocument 리스트
  - `sources`: 검색 출처 리스트
  - `max_similarity`, `avg_similarity`, `search_time_ms`

---

## LawRetrievalAgent 흐름
### 1) Agent
- 파일: `backend/app/agents/retrieval/law_agent.py`
- 클래스: `LawRetrievalAgent`
- `.process()` → BaseRetrievalAgent에서 처리

### 2) _execute_search()
- 입력: `query`, `top_k`, `task_input`
- 동작:
  - `expanded_queries`를 사용 (없으면 `query` 1개로 대체)
  - 각 확장 쿼리마다 `LawRetriever.hybrid_search(q, per_query_k, document_types)` 실행
    - `per_query_k = max(top_k, 12)`
  - 쿼리별 결과를 RRF로 통합하여 최종 top_k 반환
  - 후처리:
    - 삭제 조문 제외: `text`에 `() ... 삭제 <` 패턴이 있으면 제거
    - 같은 조문 최대 2개 제한 (chunk_id를 `_`로 split, 앞 2개를 조문 키로 사용)
  - `task_input.metadata_filter.document_types`를 읽어 `document_types`로 전달
  - `agent_keywords`는 현재 사용하지 않음

- 출력: `List[SimilarChunkResult]` (최종 top_k개)

### 3) LawRetriever.hybrid_search()
- 파일: `backend/app/agents/retrieval/tools/specialized_retrievers.py`
- 동작:
  - `document_types`가 없으면 기본값 `['법률','시행령']`
  - `RDSInternalRetriever.search_hybrid_rrf_2()` 호출
    - `filter_dataset='law_guide'`
    - `filter_document_type=document_types`
    - `result_limit=top_k`

### 4) RDSInternalRetriever.search_hybrid_rrf_2()
- 파일: `backend/app/agents/retrieval/tools/rds_internal_retriever.py`
- 동작:
  - 임베딩 생성 (`embed_query`)
  - DB 함수 호출: `SELECT * FROM search_hybrid_rrf_2(...)`
  - 결과 row 매핑
    - 포함 필드: `law_name`, `chunk_type`, `category`, `document_type`, `source_url`, `source_file`, `printed_page`, `source_year`, `metadata`

### 5) DB 함수
- 문서: `backend/app/agents/retrieval/docs/rds_internal_function.md`
- 함수: `search_hybrid_rrf_2`
- 특성:
  - BM25 + dense → RRF 결합
  - 필터: dataset, category, document_type[], chunk_type[], year_from/to
  - 반환 컬럼: law_name, chunk_type, category, document_type 포함

### 6) _format_results()
- 파일: `backend/app/agents/retrieval/law_agent.py`
- 입력: `List[SimilarChunkResult]`
- 출력: List[LawDocument] (LawDocument 포맷)
- LawDocument:
  - `chunk_id`, `content`, `metadata`, `similarity`
  - `metadata` 안에 포함:
    - `law_name`, `full_path`, `article`, `document_type`, `dataset_type`

---

## CriteriaRetrievalAgent 흐름
### 1) Agent
- 파일: `backend/app/agents/retrieval/criteria_agent.py`
- 클래스: `CriteriaRetrievalAgent`

### 2) _execute_search()
- 입력: `query`, `top_k`, `task_input`
- 동작:
  - `expanded_queries`를 사용 (없으면 `query` 1개로 대체)
  - 각 확장 쿼리마다 `CriteriaRetriever.hybrid_search(q, top_k, document_types)` 실행
  - 쿼리별 결과를 RRF로 통합하여 최종 top_k 반환
  - 후처리(부모/조건/하위 content 합성):
    - 자식(`..._조건n`)이면 부모 청크를 조회해 content 앞에 결합
    - 손자(`..._조건n_하위m`)면 부모 + 자식(조건n) 모두 조회해 content 앞에 결합
    - 부모 청크는 새 문서로 추가하지 않고, 원본 top_k 개수 유지
    - 합성 시 길이 제한 1000자, 동적 재분배(하위 → 조건 → 부모, caps: 부모 400 / 조건 300 / 하위 400)
  - `task_input.metadata_filter.document_types`를 읽어 `document_types`로 전달
  - `agent_keywords`는 현재 사용하지 않음

- 출력: `List[SimilarChunkResult]` (최종 top_k개)

### 3) CriteriaRetriever.hybrid_search()
- 파일: `backend/app/agents/retrieval/tools/specialized_retrievers.py`
- 동작:
  - `document_types` 없으면 기본값 `['시행규칙','별표']`
  - `RDSInternalRetriever.search_hybrid_rrf_2()` 호출
    - `filter_dataset='law_guide'`
    - `filter_document_type=document_types`
    - `result_limit=top_k`
  - metadata 보강: source_id / source_label / category / industry / item_group / item / dispute_type

### 3-1) CriteriaRetriever.fetch_chunk_texts()
- 파일: `backend/app/agents/retrieval/tools/specialized_retrievers.py`
- 동작:
  - `vector_chunks` 테이블에서 `chunk_id`, `text` 조회
  - 부모/자식/손자 content 합성용 텍스트 제공

### 4) _format_results()
- 파일: `backend/app/agents/retrieval/criteria_agent.py`
- 입력: `List[SimilarChunkResult]`
- 출력: List[CriteriaDocument] (CriteriaDocument 포맷)
- CriteriaDocument:
  - `chunk_id`, `content`, `metadata`, `similarity`
  - `metadata` 안에 포함:
    - `source_label` (metadata에서)
    - `category` (DB column)
    - `item` (metadata에서)
    - `title` (metadata에서)
    - `document_type` (DB column 우선, 없으면 metadata)
    - `dataset_type` (law_guide)

---

## 테스트 스크립트
- 법령: `scripts/test_law_agent.py`
- 기준: `scripts/test_criteria_agent.py`
- 둘 다 `context.retrieval_task_input`을 포함해 테스트 가능

---

## Law/Criteria 구동에 필요한 파일 목록

### 공통/베이스
- `backend/app/agents/retrieval/base_retrieval_agent.py` (BaseRetrievalAgent, _get_db_config, _get_embed_api_url)
- `backend/app/agents/retrieval/tools/rds_internal_retriever.py` (SimilarChunkResult, search_hybrid_rrf_2)

### LawRetrievalAgent 관련
- `backend/app/agents/retrieval/law_agent.py` (LawRetrievalAgent, 후처리 포함)
- `backend/app/agents/retrieval/tools/specialized_retrievers.py` (LawRetriever, RDSInternalRetriever 호출)
- `backend/app/agents/retrieval/docs/rds_internal_function.md` (DB 함수 문서: search_hybrid_rrf_2)

### CriteriaRetrievalAgent 관련
- `backend/app/agents/retrieval/criteria_agent.py` (CriteriaRetrievalAgent, 부모/조건/하위 합성 포함)
- `backend/app/agents/retrieval/tools/specialized_retrievers.py` (CriteriaRetriever, fetch_chunk_texts)
- `backend/app/agents/retrieval/docs/rds_internal_function.md` (DB 함수 문서: search_hybrid_rrf_2)
