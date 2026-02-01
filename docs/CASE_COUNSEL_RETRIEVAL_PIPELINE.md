소비자 쿼리 -> 쿼리 재생성(Rewrite) -> 검색(Retrieve: DB 함수 hybrid/vector/bm25) -> 컨텍스트 구성(Context Building) -> 출력(Answer)

# Case/Counsel Retrieval Pipeline (DB 함수 + QueryAnalysis Rewrite)

## 1) 현재 파이프라인 연결식
- 소비자 쿼리 -> 쿼리 재생성(Rewrite) -> 검색(Retrieve: DB 함수 hybrid/vector/bm25) -> 컨텍스트 구성(Context Building) -> 출력(Answer)

## 2) 변경한 파일/함수 목록
- `backend/app/agents/retrieval/base_retrieval_agent.py` : `_build_search_query`, `_should_rerank`, `_rerank_results`
- `backend/app/agents/retrieval/case_agent.py` : `_execute_search`, `_format_results`, `_build_sources`
- `backend/app/agents/retrieval/tools/rds_retriever.py` : `search_similar_chunks`, `search_hybrid_rrf`
- `backend/app/orchestrator/nodes/retrieval_merge.py` : merge 정렬/penalty/로그
- `backend/scripts/testing/retrieval/smoke_case_counsel.py` : `main`, `_run_one`, `_check_required_fields`

## 3) 데이터 흐름 (최소 5줄 연결식)
- user_query -> query_analysis → `QueryAnalysisOutputV2` (expanded_queries/keywords/retriever_types)
- supervisor → `RetrievalTaskInputV2` (expanded_queries/agent_keywords/metadata_filter/top_k/ignore_threshold)
- retrieval(case) -> `RDSRetriever.search_hybrid_rrf` 호출
- 검색 결과 -> `_format_results` -> content/title/url/metadata 유지
- results -> `graph_mas.py` documents 매핑 -> `retrieval_merge.py` 병합
- merged retrieval -> answer_generation -> 답변 생성

## 3.1) Retrieve 모드 결정
- 현재는 Case agent가 `search_hybrid_rrf`를 호출하여 **모드를 고정**한다. dense/bm25 전환은 확장 포인트로만 유지한다.

## 4) 결과 스키마 예시 (필드 이름만, 샘플 1개)
- RetrievalResultV2
  - source
  - documents[]
    - chunk_id
    - doc_id
    - doc_title
    - title
    - content
    - url
    - decision_date
    - similarity
    - category
    - dataset_type
    - rrf_score
    - bm25_score
    - vector_similarity
    - metadata
  - max_similarity
  - avg_similarity
  - search_time_ms
  - error

## 5) 검증 방법 (실행 커맨드 + 기대 결과)
- QueryAnalysis Output 확인
  - `rg -n "QueryAnalysisOutput" -S backend/app/agents/query_analysis`
  - 기대: expanded_queries/keywords/retriever_types 생성
- Case 검색 경로 확인
  - `sed -n '1,360p' backend/app/agents/retrieval/case_agent.py`
  - 기대: `RDSRetriever.search_hybrid_rrf` 호출, title alias 포함
  - 참고: case_agent는 상담 vs 분쟁/구제 1차 룰베이스 분류 후 해당 트랙을 우선 검색
- DB 함수 래퍼 확인
  - `rg -n "search_hybrid_rrf|search_similar_chunks" -S backend/app/agents/retrieval/tools/rds_retriever.py`
  - 기대: 래퍼 메서드 존재
  - 참고: `search_hybrid_rrf` 이슈 해결됨(우회/rollback/fallback 경로 철회)
- merge title 기대 확인
  - `rg -n "get\('title'\)|\['title'\]" -S backend/app/orchestrator`
  - 기대: title 참조 지점 존재, 에이전트 alias로 호환됨
- 스모크 테스트 (실행)
  - `python backend/scripts/testing/retrieval/smoke_case_counsel.py`
  - 기대: case_combined 경로에서 1건 이상 반환, title/doc_title/url/similarity가 출력됨
  - 주의: DB 미기동 시 `[FAIL] DB connection failed` 메시지와 함께 종료 코드 2로 실패함
  - 에이전트 통합 경로 사용(정책 우회 방지)
  - 스모크는 상담 vs 분쟁/구제 2개 트랙 + case 통합(룰베이스 quota+2단계 fill) 호출
  - 정책 로그 확인: `case_quota_policy`, `case_track_counts` (final은 fill 반영)
  - DB 대상 로그 확인: `[INFO] DB target: user@host:port db=...`
  - 필터 로그 확인: `search_hybrid_rrf filters: dataset_type=case category=...`
- soft_score/중복 제거 로그
  - 기대: `[INFO] ... raw=..., formatted=..., dedup_removed=...`
  - 기대: `[INFO] ... soft_score min/max/avg` 출력
- rewrite 출력 형태 검증
  - 기대: 한 줄만 출력, 따옴표/설명/리스트 없는 단일 문장

## 6) 체크리스트
- QueryAnalysis 출력
  - `QueryAnalysisOutputV2`의 expanded_queries/keywords/retriever_types 사용
  - RetrievalTaskInputV2.metadata_filter.categories는 ['조정','해결','상담'] 입력 가능
- Retrieve 모드 결정 주체
  - case_agent가 `search_hybrid_rrf`를 호출하여 모드를 고정
- case 1차 분류 (룰베이스 점수표)
  - case_agent가 query/query_analysis 기반으로 상담 vs 분쟁/구제 점수 계산
  - 확신: winner_track에 0.7 비율 배분(ceil), 애매: 0.5 비율 배분(ceil)
  - 분쟁/구제 트랙 내부는 조정/해결로 분배 (strong hit 최소 보장)
  - 부족분은 2단계 fill로 채움 (카테고리 완화 → broaden query)
- dataset_type 검증
  - DB `vector_chunks.dataset_type`는 `case` / `law_guide`만 사용
  - case 서브타입은 `category`(상담/조정/해결)로 구분 (운영상 조정+해결은 통합 트랙)
- chunk_type 참고
  - B_case는 `chunk_type='case'`로 저장됨(필터 기준은 dataset_type/category)
- metadata 키 검증
  - `metadata.doc_title`, `metadata.doc_id`, `metadata.decision_date` 존재 여부 확인
- 유사도 기준
  - `formatted_results[].similarity`가 대표값이며, hybrid는 `vector_similarity`를 대표로 사용(권장)
- title alias
  - `title = doc_title`로 merge 호환성 보장
- sources 확장 필드 (optional)
  - `url`, `printed_page`, `source_year`는 optional로 확장 가능
- fallback 정책
  - 1차: 동일 dataset + category 완화
  - 2차: broaden query로 재검색
- case 통합 quota
  - 상담 vs 분쟁/구제 비율 기반 자동 산정
  - categories 입력은 3개지만 내부 로직은 2트랙으로 통합 처리
  - 강제 분쟁/구제 입력(조정+해결/통합) 시 상담 트랙은 제외
- merge 정렬
  - soft_score 우선, similarity tie-break
- bonus/penalty(merge)
  - bonus OFF
  - penalty ON: 필수 메타 결손(title/url), 짧은 청크(상담 60 / 조정+해결 100 / 기타 80)
  - penalty weight: -0.03

## CHANGELOG
- 2026-01-28: counsel_agent 제거 및 case 단일 트랙 정리. Touched files: `backend/app/orchestrator/graph_mas.py`, `backend/app/agents/retrieval/__init__.py`, `backend/scripts/testing/retrieval/smoke_case_counsel.py`, `docs/CASE_COUNSEL_RETRIEVAL_PIPELINE.md`
