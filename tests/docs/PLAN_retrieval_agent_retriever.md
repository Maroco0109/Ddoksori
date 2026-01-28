# Retrieval Agent ↔ DB Function 연동 계획서 (search_* + vector_chunks)

## 1) 전체 구조 요약 (한눈에 흐름)
- 입력: user_query → (optional) LLM 쿼리 재작성 → Retrieval Agent 4개 병렬 실행 → DB 함수(search_similar_chunks/search_hybrid_rrf) 호출 → 결과 포맷 통일 → retrieval_merge에서 섹션별 병합 → supervisor로 반환.
- 핵심 원칙: **vector_chunks + 기존 plpgsql 함수(search_*)를 그대로 호출**해서 검색을 통일하고, 에이전트별 결과 스키마만 맞춘다.

## 2) 실제 파일/경로 기준 (어느 파일을 왜 보는지)
- `backend/app/agents/retrieval/base_retrieval_agent.py` : 공통 process 흐름(쿼리 재작성, top_k, 결과 포맷, sources) 확인.
- `backend/app/agents/retrieval/law_agent.py` / `criteria_agent.py` / `case_agent.py` / `counsel_agent.py` : 각 에이전트가 어떤 retriever를 호출하는지 파악.
- `backend/app/agents/retrieval/tools/specialized_retrievers.py` : Law/Criteria/Case retriever가 직접 SQL(chunks/documents) 쓰는 부분 확인.
- `backend/app/agents/retrieval/tools/rds_retriever.py` : vector_chunks 직접 SQL 기반 + hybrid_rrf 구현. **DB 함수 기반으로 전환 시 핵심 변경 포인트**.
- `backend/app/agents/retrieval/cli_search_similar_chunks_existing_fn.py` : 이미 plpgsql 함수(search_similar_chunks/search_hybrid_rrf) 호출 예시 존재. **정답 레퍼런스**.
- `backend/app/agents/retrieval/tools/retriever.py` / `tools/hybrid_retriever.py` : 기존 chunks/documents 기반 검색 로직(우회 경로) 확인.
- `backend/app/orchestrator/nodes/retrieval_merge.py` : merge 시 기대 섹션 키(`laws/criteria/disputes/counsels`)와 필드명 확인.
- `backend/app/orchestrator/graph_mas.py` : Fan-out/Fan-in 연결 구조 확인(변경 시 영향도 파악).

## 3) 데이터/요청 흐름 (쿼리 재생성 → 검색(DB 함수 호출) → 포맷 → merge → 다음 단계)
1. **쿼리 재작성**
   - `BaseRetrievalAgent.process()` → `_build_search_query()`
   - Law/Criteria는 OPENAI_API_KEY가 있으면 재작성(gpt-4o-mini), 그 외는 원문 사용.
2. **검색 (DB 함수 호출)**
   - 현재: Law/Criteria/Case/Counsel이 chunks/documents 직접 SQL 사용.
   - 목표: `search_similar_chunks()` / `search_hybrid_rrf()`를 호출해 vector_chunks에서 검색.
   - 호출 파라미터는 `cli_search_similar_chunks_existing_fn.py` 시그니처에 맞춤:
     - dense: `search_similar_chunks(query_embedding, dataset, category, law_name, year, limit)`
     - hybrid: `search_hybrid_rrf(query_text, query_embedding, dataset, category, document_type, year, limit, rrf_k)`
3. **포맷팅**
   - DB 함수 결과 필드 → Agent 표준 포맷 매핑
     - vector_chunks: `chunk_id, dataset_type, text, similarity, law_name, chunk_type, category, source_url, source_file, printed_page, source_year, metadata`
     - agent output: `chunk_id, doc_id, chunk_type, content, doc_title, source_org, url, decision_date, similarity, doc_similarity...`
4. **merge**
   - `retrieval_merge_node`는 섹션 키: `laws/criteria/disputes/counsels`.
   - 각 Agent 결과의 `documents`를 섹션에 합침 → sources 리스트 생성.
5. **다음 단계**
   - `supervisor`가 retrieval 완료 상태를 반영하고 generation 단계로 진행.

## 4) 이번 작업 범위에서 “우리가 손대야 할 파일 리스트”와 확인/수정 포인트
- `backend/app/agents/retrieval/tools/rds_retriever.py`
  - **수정 포인트**: direct SQL (vector_chunks) → DB 함수 호출 방식으로 전환.
  - `dense_search()`는 `search_similar_chunks()`를 호출하도록 변경.
  - `hybrid_rrf_search()`는 `search_hybrid_rrf()`를 호출하도록 변경.
  - 반환 스키마를 Agent 표준 포맷으로 쉽게 매핑할 수 있도록 정리.
- `backend/app/agents/retrieval/tools/specialized_retrievers.py`
  - **수정 포인트**: Case/Counsel/Law/Criteria에서 `RDSRetriever`(혹은 신규 함수형 client)를 사용하도록 전환.
  - doc_type 기반 필터 → vector_chunks의 `dataset_type`/`document_type`로 매핑 규칙 정의.
  - 필요 시 Law/Criteria 전용 필터 파라미터(law_name/category 등) 매핑.
- `backend/app/agents/retrieval/law_agent.py`
  - **확인 포인트**: `_execute_search()`에서 retriever 교체; 기존 2-stage 법령 검색 사용 여부 결정.
  - 현업 기준: law는 `search_hybrid_rrf` + `law_name`/`category` 필터 또는 dataset_type='law' 고정.
- `backend/app/agents/retrieval/criteria_agent.py`
  - **확인 포인트**: criteria 관련 필터(`category`, `item_group`, `dispute_type`)를 vector_chunks metadata로 매핑할지 결정.
- `backend/app/agents/retrieval/case_agent.py` / `counsel_agent.py`
  - **수정 포인트**: `CaseRetriever.search_disputes/search_counsels`를 DB 함수 기반으로 변경.
  - 문서 수준 유사도(Phase 3) 기능은 `search_hybrid_rrf` 결과에서 doc_id 정보 유무에 따라 유지/축소 판단.
- `backend/app/orchestrator/nodes/retrieval_merge.py`
  - **확인 포인트**: sources 생성 시 사용되는 `doc.get('title')` 등 키 불일치 여부(현 결과 키는 `doc_title`/`content`).
  - vector_chunks 기반 결과에 맞춰 sources 필드명 정리 필요.

## 5) 리스크/헷갈리는 포인트
- **키/스키마 mismatch**
  - vector_chunks에는 `doc_id`가 없고 `dataset_type`/`document_type` 구조가 다름 → Agent 포맷 필드 매핑 규칙 필요.
  - `retrieval_merge`는 `doc.get('title')`를 참조하지만 agent 결과는 `doc_title` 사용 중.
- **법령/기준의 계층 구조 손실**
  - 기존 Law/Criteria는 law_units/criteria_units 기반(조항/항/목)인데, vector_chunks로 전환 시 계층 정보가 metadata로만 남을 수 있음.
- **graph merge 기대값**
  - `retrieval_merge`는 `source` 값을 `law/criteria/case/counsel`로 기대. Agent 결과 key 누락 시 병합 실패 위험.
- **환경 변수/임베딩 경로**
  - `USE_OPENAI_EMBEDDING`, `OPENAI_API_KEY`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`, `EMBED_API_URL` 조합에 따라 임베딩 경로가 다름.
  - LLM 쿼리 재작성(OpenAI) 미설치 환경에서 실패 로그 가능.
- **RRF 파라미터/검색 함수 차이**
  - 기존 `rds_retriever.hybrid_rrf_search`는 내부 SQL; DB 함수는 파라미터 및 결과 스키마가 약간 다를 수 있음.

## 6) 작업 순서 (체크리스트) + 각 단계별 검증 방법
1. **DB 함수 호출 경로 정리**
   - 작업: `rds_retriever.py`에서 `search_similar_chunks`/`search_hybrid_rrf` 함수 호출로 변경.
   - 검증:
     - `rg "search_similar_chunks" backend/app/agents/retrieval/tools -n`
     - SQL: `SELECT proname FROM pg_proc WHERE proname IN ('search_similar_chunks','search_hybrid_rrf');`
2. **Agent별 retriever 교체**
   - 작업: `specialized_retrievers.py`에서 Law/Criteria/Case/Counsel 검색을 DB 함수 기반으로 전환.
   - 검증:
     - `rg "RDSRetriever|search_hybrid_rrf|search_similar_chunks" backend/app/agents/retrieval -n`
     - 간단 호출 스크립트: `python backend/app/agents/retrieval/cli_search_similar_chunks_existing_fn.py "테스트" --mode hybrid_rrf`
3. **포맷 매핑 및 sources 키 정리**
   - 작업: vector_chunks 결과 → `BaseRetrievalAgent` 표준 결과 필드로 매핑, `retrieval_merge`에서 sources 키 맞춤.
   - 검증:
     - `rg "doc_title|title" backend/app/orchestrator/nodes/retrieval_merge.py -n`
     - 샘플 결과 로그 확인(로깅 추가 시): `rg "RetrievalMerge" backend/app/orchestrator/nodes/retrieval_merge.py -n`
4. **스키마/필터 규칙 확정**
   - 작업: dataset_type/document_type/category/law_name/metadata 키 매핑 문서화 및 코드 반영.
   - 검증:
     - SQL: `SELECT DISTINCT dataset_type, document_type FROM vector_chunks LIMIT 50;`
     - SQL: `SELECT DISTINCT category FROM vector_chunks LIMIT 50;`
5. **기능 회귀 확인**
   - 작업: 기존 Law/Criteria 2-stage 로직을 유지할지 결정 후, 대체 경로에 대한 영향 점검.
   - 검증:
     - `python backend/app/agents/retrieval/cli_search_similar_chunks_existing_fn.py "법령 테스트" --mode dense_fn --limit 3`
     - (선택) 기존 로직 비교 스모크 테스트용 스크립트 실행.

---

### 부록: 스키마 매핑 가이드 (초안)
- `vector_chunks.text` → `content`
- `vector_chunks.source_url` → `url`
- `vector_chunks.law_name` → `doc_title` (law 전용)
- `vector_chunks.dataset_type` → agent 섹션 선택 근거 (`law/criteria/mediation_case/counsel_case` 등)
- `vector_chunks.metadata` → `decision_date`, `doc_id` 유사 필드(있다면) 추출

