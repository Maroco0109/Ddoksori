# Counsel 서브에이전트 구현 계획서 v2 (Case 보류, 기존 파일 유지)

## 1) 전체 구조 요약
현재 단계에서는 **상담사례(Counsel)만** 계획대로 진행하고, Case 쪽은 보류한다. `query_analysis`가 쿼리 재작성(Rewrite)을 수행하고 `BaseRetrievalAgent._build_search_query()`는 이를 선택/전달한다. Retrieve는 **DB 함수 기반**(hybrid/vector/bm25) 호출을 사용하는 방향을 유지하며, Rerank는 필요 시에만 적용한다. Context Building은 Counsel 결과를 LLM 입력용 근거로 구성하는 단계이며, Answer Generation으로 이어진다. 기존 파일은 변경하지 않고, **이 문서(v2)만 새로 작성**해 진행한다.

## 2) 파일/경로별 변경 포인트

### A) `backend/app/agents/retrieval/counsel_agent.py`
- 수정 위치(함수/메서드)
  - `_execute_search()`
  - `_format_results()`
  - (선택) `_build_sources()`
- 수정 내용(계획)
  - tools를 건드리지 않는 조건이므로, `RDSRetriever`의 **기존 공개 메서드 범위** 내에서 DB 함수 기반 호출을 적용
  - 기본 필터: `filter_dataset='counsel_case'`
  - 결과 매핑:
    - `content <- text`
    - `url <- source_url`
    - `doc_title <- metadata.doc_title OR source_file`
    - `doc_id <- metadata.doc_id OR chunk_id`
    - `decision_date <- metadata.decision_date (없으면 None)`
    - `similarity <- vector_similarity(하이브리드) 또는 similarity(밀집)`
    - 필요 시 `rrf_score`, `bm25_score`, `vector_similarity` 보존
  - `title` alias 추가: `title <- doc_title` (merge 호환용)
- 주의점/호환성
  - dataset_type 값이 실제 DB 값과 일치하는지 검증 필요
  - 결과 스키마는 `results/sources/max_similarity/avg_similarity` 유지

### B) `backend/app/agents/retrieval/case_agent.py`
- 수정 위치
  - **변경 없음 (Case 보류)**
- 주의점
  - Case 관련 변경은 v3 이후로 이관

### C) `backend/app/orchestrator/graph_mas.py`
- 수정 위치
  - 변경 없음
- 주의점
  - `results → documents` 매핑은 그대로 유지

### D) `backend/app/orchestrator/nodes/retrieval_merge.py`
- 수정 위치
  - 변경 없음 (Counsel에서 `title` alias 보강 예정)

### E) `backend/app/agents/query_analysis/agent.py`
- 수정 위치
  - 변경 없음 (재작성은 query_analysis 담당)

## 3) 런타임 데이터 흐름
1. 사용자 입력 → `query_analysis_node`
2. Rewrite → `query_analysis.rewritten_query`
3. `BaseRetrievalAgent._build_search_query()`가 재작성 쿼리 선택/전달
4. Retrieve → Counsel `_execute_search()`에서 DB 함수 기반 검색 호출
5. (선택) Rerank → 필요 시에만 적용
6. Context Building → `_format_results()`로 근거 묶음 구성 + `title` alias 추가
7. `graph_mas.py`가 `results`를 `documents`로 포장
8. `retrieval_merge.py`가 4섹션 병합 + `sources` 생성
9. Answer Generation → `retrieval.counsels` 근거로 답변 생성

## 4) 설계 이유/트레이드오프
- Counsel만 우선 적용해 리스크를 낮추고 변경 범위를 최소화한다.
- tools 수정 금지 조건에 맞춰 기존 인터페이스만 사용한다.
- `title` alias 추가로 orchestrator 변경을 피한다.

## 5) 체크리스트
- dataset_type 검증: DB의 `vector_chunks.dataset_type` 값이 `counsel_case`인지 확인
- metadata 키 확인: `doc_title`, `doc_id`, `decision_date` 존재 여부 확인
- similarity 계산 확인: hybrid에서 `vector_similarity`가 있는지 확인
- merge 호환성 확인: `title` alias가 `retrieval_merge`에서 정상 인용되는지 확인
