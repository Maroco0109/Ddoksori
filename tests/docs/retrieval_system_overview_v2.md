# Retrieval 시스템 흐름 중심 개요 (v2)

## 1) 전체 구조 요약(한눈에 흐름)
- **Supervisor → Retrieval Agents(4개) → 결과 병합** 흐름이다.
- 공통 처리: `BaseRetrievalAgent.process()`가 요청 검증 → 쿼리 재작성 → 검색 실행 → 결과/출처 포맷 → Supervisor에 보고까지 담당한다.
- 검색 실행은 각 도메인 전용 Agent가 담당하며, 내부에서 **Specialized Retriever**(DB + 임베딩 API 사용)로 위임한다.
- README 기준으로 **4개 Agent 결과를 `retrieval_merge_node`에서 통합**하는 팬아웃/팬인 구조가 존재한다.

## 2) 실제 파일/경로 기준 설명(어느 파일이 어떤 책임인지)
- `backend/app/agents/retrieval/base_retrieval_agent.py`  
  - 4개 Retrieval Agent 공통 베이스.  
  - `required_inputs=["user_query"]`, `provided_outputs=["results","sources","max_similarity","avg_similarity"]`, `default_top_k=3`.  
  - `_build_search_query()`에서 `query_analysis.rewritten_query`가 있으면 재작성 쿼리 사용.  
  - `_execute_search`, `_format_results`, `_build_sources`는 서브클래스가 구현.
- `backend/app/agents/retrieval/law_agent.py`  
  - `LawRetrievalAgent` 정의. `LawRetriever.search_two_stage()` 호출.  
  - 결과 포맷에 법령 경로/조항 정보(`law_name`, `full_path`, `text`, `similarity`) 포함.
- `backend/app/agents/retrieval/criteria_agent.py`  
  - `CriteriaRetrievalAgent` 정의. `CriteriaRetriever.search_two_stage()` 호출.  
  - 결과 포맷에 기준 카테고리/품목 정보 포함.
- `backend/app/agents/retrieval/case_agent.py`  
  - `CaseRetrievalAgent` 정의. `CaseRetriever.search_disputes()` 호출.  
  - 분쟁조정사례(`mediation_case`) 전용 결과 포맷.
- `backend/app/agents/retrieval/counsel_agent.py`  
  - `CounselRetrievalAgent` 정의. `CaseRetriever.search_counsels()` 호출.  
  - 상담사례(`counsel_case`) 전용 결과 포맷.
- `backend/app/agents/retrieval/tools/specialized_retrievers.py`  
  - **전문 검색기** 구현.  
  - `LawRetriever`, `CriteriaRetriever`의 2단계 검색 로직 정의.  
  - `LawSearchResult`, `CriteriaSearchResult`, `DocumentLevelResult` 데이터 구조 제공.  
  - `ENABLE_DISPUTE_METADATA_EXTRACTION`, `ENABLE_DOCUMENT_LEVEL_SIMILARITY` 등 **환경변수 플래그** 존재.
- `backend/app/agents/retrieval/README.md`  
  - `retrieval_merge_node`에서 **4개 Agent 결과 통합** 명시.  
  - `retrieval_node`, `retrieval_node_v2` 역할 차이(병합만 담당 등) 설명됨.
- `backend/app/agents/base.py`  
  - Supervisor가 Agent의 `process()`를 호출한다는 계약이 존재.

## 3) 데이터/요청이 이동하는 순서(런타임 플로우)
1. **Supervisor → Agent.process() 호출**
2. **BaseRetrievalAgent.process() 공통 처리** (`base_retrieval_agent.py`)
   - 요청 검증 → `user_query`/`query_analysis` 추출  
   - `_build_search_query()`로 쿼리 재작성 적용  
   - `top_k`는 `params.top_k` 또는 `default_top_k(=3)` 사용
3. **도메인별 검색 실행**
   - Law: `LawRetriever.search_two_stage()`  
   - Criteria: `CriteriaRetriever.search_two_stage()`  
   - Case: `CaseRetriever.search_disputes()`  
   - Counsel: `CaseRetriever.search_counsels()`
4. **검색 결과 포맷/출처 생성**
   - 각 Agent의 `_format_results()` / `_build_sources()` 실행
5. **Supervisor 보고**
6. **결과 병합**
   - `retrieval_merge_node`에서 4개 Agent 결과를 통합

## 4) 왜 이 구조가 필요한지(설계 이유)
- **도메인 분리**: 법령/기준/사례/상담은 데이터 구조와 검색 전략이 다르므로 Agent 분리.
- **공통 처리 일원화**: 쿼리 재작성, 오류 처리, similarity 통계 등은 Base에서 공통화.
- **검색 책임 분리**: 실제 검색(임베딩 + DB)은 retriever로 분리되어 Agent는 흐름 제어/포맷에 집중.
- **확장성**: 도메인 추가 시 Base 상속 + retriever 추가로 확장 가능.

## 5) 헷갈리기 쉬운 포인트(실수 방지 체크리스트)
- **쿼리 재작성 적용 여부**: `query_analysis.rewritten_query`가 있으면 그걸 사용.
- **top_k 기본값**: 기본 3건. params로 넘기지 않으면 3.
- **Case vs Counsel**: 둘 다 CaseRetriever지만 메서드가 다름.
- **병합 위치**: Agent 내부가 아니라 `retrieval_merge_node`에서 병합.
- **환경변수 플래그**: `specialized_retrievers.py`의 ENABLE 플래그가 동작을 바꿈.
