소비자 쿼리 -> 쿼리 재생성(Rewrite) -> 검색(Retrieve: DB 함수 hybrid/vector/bm25) -> (선택)리랭크(Rerank) -> 컨텍스트 구성(Context Building) -> 출력(Answer)

# Case/Counsel Retrieval Pipeline (DB 함수 + Base Rewrite)

## 1) 현재 파이프라인 연결식
- 소비자 쿼리 -> 쿼리 재생성(Rewrite) -> 검색(Retrieve: DB 함수 hybrid/vector/bm25) -> (선택)리랭크(Rerank) -> 컨텍스트 구성(Context Building) -> 출력(Answer)

## 2) 변경한 파일/함수 목록
- `backend/app/agents/retrieval/base_retrieval_agent.py` : `_build_search_query`, `_rewrite_query`, `_should_rerank`, `_rerank_results`
- `backend/app/agents/retrieval/case_agent.py` : `_execute_search`, `_format_results`, `_build_sources`
- `backend/app/agents/retrieval/counsel_agent.py` : `_execute_search`, `_format_results`, `_build_sources`
- `backend/app/agents/retrieval/tools/rds_retriever.py` : `search_similar_chunks`, `search_hybrid_rrf`
- `backend/scripts/testing/retrieval/smoke_case_counsel.py` : `main`, `_run_one`, `_check_required_fields`

## 3) 데이터 흐름 (최소 5줄 연결식)
- user_query -> `BaseRetrievalAgent._build_search_query` -> final_query/rewritten_query 결정 (Base에서 rewrite 수행)
- final_query -> `CaseRetrievalAgent._execute_search` -> `RDSRetriever.search_hybrid_rrf` 호출
- final_query -> `CounselRetrievalAgent._execute_search` -> `RDSRetriever.search_hybrid_rrf` 호출
- 검색 결과 -> `_format_results` -> content/title/url/metadata 유지
- results -> `graph_mas.py` documents 매핑 -> `retrieval_merge.py` 병합
- merged retrieval -> answer_generation -> 답변 생성

## 3.1) Retrieve 모드 결정
- 현재는 Case/Counsel agent가 `search_hybrid_rrf`를 호출하여 **모드를 고정**한다. dense/bm25 전환은 확장 포인트로만 유지한다.

## 4) 결과 스키마 예시 (필드 이름만, 샘플 1개)
- result
  - results[]
    - chunk_id
    - doc_id
    - doc_title
    - title
    - content
    - url
    - decision_date
    - similarity
    - rrf_score
    - bm25_score
    - vector_similarity
    - metadata
  - sources[]
    - type
    - index
    - chunk_id
    - doc_id
    - doc_title
    - source_org
    - similarity
  - max_similarity
  - avg_similarity
  - final_query
  - rewritten_query

## 5) 검증 방법 (실행 커맨드 + 기대 결과)
- Rewrite 단계 확인
  - `rg -n "def _build_search_query|def _rewrite_query|REWRITE_" -S backend/app/agents/retrieval/base_retrieval_agent.py`
  - 기대: Base에서 rewrite 수행, env 기반 설정 상수 확인 가능
- Case/Counsel 검색 경로 확인
  - `sed -n '1,260p' backend/app/agents/retrieval/case_agent.py`
  - `sed -n '1,260p' backend/app/agents/retrieval/counsel_agent.py`
  - 기대: `RDSRetriever.search_hybrid_rrf` 호출, title alias 포함
- DB 함수 래퍼 확인
  - `rg -n "search_hybrid_rrf|search_similar_chunks" -S backend/app/agents/retrieval/tools/rds_retriever.py`
  - 기대: 래퍼 메서드 존재
- merge title 기대 확인
  - `rg -n "get\('title'\)|\['title'\]" -S backend/app/orchestrator`
  - 기대: title 참조 지점 존재, 에이전트 alias로 호환됨
- 스모크 테스트 (실행)
  - `python backend/scripts/testing/retrieval/smoke_case_counsel.py`
  - 기대: mediation_case / counsel_case 각각 1건 이상 반환, title/doc_title/url/similarity가 출력됨
  - 주의: DB 미기동 시 `[FAIL] DB connection failed` 메시지와 함께 종료 코드 2로 실패함
- rewrite 출력 형태 검증
  - 기대: 한 줄만 출력, 따옴표/설명/리스트 없는 단일 문장

## 6) 체크리스트
- Rewrite 정책
  - `QUERY_REWRITE_ENABLED` (기본: true)
  - `QUERY_REWRITE_MODEL` (기본: gpt-4o-mini)
  - `QUERY_REWRITE_TIMEOUT_SEC` (기본: 4.0)
  - `QUERY_REWRITE_MIN_CHARS` (기본: 5)
  - 프롬프트 규칙: 한 줄 출력, 설명/따옴표/리스트 금지
  - 프롬프트 규칙: 고유명사/기관명/제품명/숫자 원문 보존
  - 프롬프트 규칙: 입력 언어 유지, 이미 명확하면 변경 금지
- Retrieve 모드 결정 주체
  - 현재는 Case/Counsel agent가 `search_hybrid_rrf`를 호출하여 모드를 고정
- dataset_type 검증
  - DB `vector_chunks.dataset_type`가 `mediation_case` / `counsel_case`인지 확인
- metadata 키 검증
  - `metadata.doc_title`, `metadata.doc_id`, `metadata.decision_date` 존재 여부 확인
- 유사도 기준
  - `formatted_results[].similarity`가 대표값이며, hybrid는 `vector_similarity`를 대표로 사용(권장)
- title alias
  - `title = doc_title`로 merge 호환성 보장
- sources 확장 필드 (optional)
  - `url`, `printed_page`, `source_year`는 optional로 확장 가능
- rerank
  - 기본 OFF, 훅만 유지되며 활성화 시에도 스키마 유지

## CHANGELOG
- 2026-01-28: rewrite 프롬프트 강화(검색 최적화 규칙 적용). Touched files: `backend/app/agents/retrieval/base_retrieval_agent.py`, `docs/CASE_COUNSEL_RETRIEVAL_PIPELINE.md`
