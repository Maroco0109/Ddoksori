Rewrite -> Retrieve(DB 함수) -> (opt) Rerank -> Context Building -> Answer Generation
# Case/Counsel 서브에이전트 최적 구현 계획서 (DB 함수 기반, rds_retriever 기준)

## 1) 전체 구조 요약
Case/Counsel retrieval의 Rewrite는 `BaseRetrievalAgent._build_search_query()`에서 수행하며, 이 단계에서 최종 쿼리를 결정한다. 검색(Retrieve)은 **DB 함수 기반** 호출(hybrid/vector/bm25)을 사용하고, 필요 시에만 Rerank를 적용한다. 이후 컨텍스트 구성(Context Building)으로 LLM 입력용 근거 묶음을 만들고, Answer Generation으로 이어진다. tools 코드는 수정하지 않고 `backend/app/agents/retrieval/tools/rds_retriever.py`가 이미 제공하는 인터페이스 범위 내에서만 동작하도록 구성한다. 결과는 `BaseRetrievalAgent`가 `results/sources/max_similarity/avg_similarity` 스키마로 반환하고, `graph_mas.py`가 `results → documents`로 감싸 `retrieval_merge.py`에서 4섹션으로 병합한다. 기존 orchestrator 파일은 최소 변경 원칙을 유지한다.

## 2) 파일/경로별 변경 포인트

### A) `backend/app/agents/retrieval/tools/rds_retriever.py`
- 수정 위치(함수/메서드)
  - **변경 없음** (tools는 수정하지 않는 조건)
- 수정 내용
  - 없음. 기존 구현(직접 SQL / 내부 메서드)을 그대로 둔다.
- 주의점/호환성
  - tools를 건드리지 않으므로, Case/Counsel은 **현재 rds_retriever가 제공하는 공개 인터페이스 범위 내**에서만 사용해야 한다.
  - DB 함수 호출이 필요한 경우, **기존 tools에서 이미 제공되는 함수/메서드가 있는지 확인**하고 그 범위 내에서 설계한다.

### B) `backend/app/agents/retrieval/case_agent.py`
- 수정 위치
  - `_execute_search()`
  - `_format_results()`
  - (선택) `_build_sources()`
- 수정 내용
  - `CaseRetriever` 의존 제거(팀원 작업중인 `specialized_retrievers.py` 충돌 회피)
  - `RDSRetriever`의 **기존 공개 메서드**만 사용 (tools 수정 금지 조건)
  - DB 함수 기반 호출이 필요하면, 현재 tools에 노출된 함수가 무엇인지 확인 후 그 범위로 제한
  - 기본 필터: `filter_dataset='mediation_case'`
  - 결과 매핑(필수):
    - `content <- text`
    - `url <- source_url`
    - `doc_title <- metadata.doc_title OR source_file`
    - `doc_id <- metadata.doc_id OR chunk_id`
    - `decision_date <- metadata.decision_date (없으면 None)`
    - `similarity <- vector_similarity(하이브리드) 또는 similarity(밀집)`
    - 필요 시 `rrf_score`, `bm25_score`, `vector_similarity`는 메타 필드로 보존
  - **title alias 추가**: `title <- doc_title` (retrieval_merge가 `title`을 기대)
- 주의점/호환성
  - `filter_dataset` 값은 **DB 함수가 실제 사용하는 dataset_type과 일치해야 함** (불일치 시 체크리스트에서 검증)
  - 기존 결과 스키마(`results/sources/max_similarity/avg_similarity`) 유지

### C) `backend/app/agents/retrieval/counsel_agent.py`
- 수정 위치
  - `_execute_search()`
  - `_format_results()`
  - (선택) `_build_sources()`
- 수정 내용
  - Case와 동일 패턴, 단 `filter_dataset='counsel_case'`
  - 결과 매핑/`title` alias 동일 적용
- 주의점/호환성
  - `filter_dataset` 값 검증 필요 (DB 함수 dataset_type 불일치 가능)

### D) `backend/app/orchestrator/graph_mas.py`
- 수정 위치
  - `_create_retrieval_agent_node()`
- 수정 내용
  - 원칙적으로 **변경 없음** (이미 `results → documents` 매핑 수행)
- 주의점/호환성
  - Case/Counsel에서 `title` alias를 추가하면 `retrieval_merge` 수정 없이 호환 가능

### E) `backend/app/orchestrator/nodes/retrieval_merge.py`
- 수정 위치
  - `sources` 생성부
- 수정 내용
  - **최소 변경 기준**: Case/Counsel에서 `title` alias를 추가하는 방식 선택
  - (대안) merge에서 `doc_title` fallback 허용도 가능하나, orchestrator 변경을 최소화하기 위해 **에이전트쪽 보완**을 기본 선택
- 주의점/호환성
  - 기존 4섹션 병합 로직 유지

### F) `backend/app/agents/query_analysis/agent.py`
- 수정 위치
  - 변경 없음
- 수정 내용
  - Rewrite는 BaseRetrievalAgent가 담당하므로, query_analysis는 기존 로직 유지
- 주의점/호환성
  - query_analysis의 `rewritten_query`는 사용하지 않으며, 최종 쿼리는 BaseRetrievalAgent에서 결정됨

## 3) 런타임 데이터 흐름
1. 사용자 입력 → `query_analysis_node` (`backend/app/agents/query_analysis/agent.py`)
2. Rewrite → `BaseRetrievalAgent._build_search_query()`에서 최종 쿼리 생성
3. `BaseRetrievalAgent`가 `final_query/rewritten_query`를 결과에 저장
4. Retrieve → Case/Counsel `_execute_search()`에서 **DB 함수 기반 검색**(hybrid/vector/bm25 중 선택)
5. (선택) Rerank → 필요 시에만 적용 (기본 경로는 생략)
6. Context Building → `_format_results()`에서 필드 매핑 + `title` alias 보강
7. `graph_mas.py`가 `results`를 `documents`로 담아 `individual_retrieval_results` 생성
8. `retrieval_merge.py`가 4섹션 병합 + `sources` 생성
9. Answer Generation → `answer_generation`에서 `retrieval.disputes/counsels` 근거로 답변 생성

## 4) 설계 이유/트레이드오프
- DB 함수 기반 통일은 SQL/플랜을 DB로 집중시켜 운영 안정성과 재현성을 높인다.
- `specialized_retrievers.py` 의존 제거로 팀원 작업 충돌 위험을 최소화한다.
- `title` alias를 에이전트에서 보완하면 orchestrator 변경 없이 호환이 가능하다.
- hybrid RRF는 recall 향상(키워드+벡터), dense-only는 단순/빠름 → 필요 시 정책 스위치 가능하도록 유지.
- Rerank는 비용/지연을 늘릴 수 있으므로 “필요할 때만” 적용하는 구조로 설계한다.

## 5) 체크리스트 (검증 항목 + 빠른 확인 방법)
- DB 함수 존재/스키마 확인
  - 확인: `backend/app/agents/retrieval/cli_search_similar_chunks_existing_fn.py`의 호출 시그니처가 **tools 수정 없이 사용 가능한지** 확인 (불가 시 설계 재조정 필요)
- dataset_type 값 검증
  - 확인: 실제 DB에서 `vector_chunks.dataset_type` 값이 `mediation_case` / `counsel_case`인지 점검 (불일치 시 필터 수정 필요)
- metadata 키 검증
  - 확인: DB 함수 반환 `metadata`에 `doc_title`, `doc_id`, `decision_date`가 들어오는지 샘플로 확인
- title 필드 호환
  - 확인: Case/Counsel `_format_results()`에 `title` alias가 포함되어 `retrieval_merge.py`의 `doc.get('title')`이 비지 않는지 확인
- similarity 계산 기준 확인
  - 확인: hybrid 시 `vector_similarity`가 있는지 확인하고, `BaseRetrievalAgent`의 max/avg 계산이 정상 동작하는지 점검
- Rewrite 경로 확인
  - 확인: `BaseRetrievalAgent`에서 `rewritten_query`가 생성되고 결과에 저장되는지 점검
