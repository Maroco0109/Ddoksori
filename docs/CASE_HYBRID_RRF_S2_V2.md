# CASE Hybrid RRF s2_v2 안내

## 배경
- 기존 DB 함수 `search_hybrid_rrf_s2`는 `RETURNS TABLE`로 고정 스키마를 사용한다.
- `CREATE OR REPLACE`로 반환 컬럼을 늘리면 **SQL Error 42P13**(cannot change return type of existing function) 발생.
- 그래서 **새 함수명**으로 스키마가 다른 함수를 만들어야 한다.

## 왜 s2_v2를 만들었나
- case_agent 운영을 위해 `category` 컬럼을 반환해야 한다.
- 기존 s2는 category를 반환하지 않으므로, **category 포함 스키마**를 가진 함수가 필요했다.
- 사용자 DB에 `public.search_hybrid_rrf_s2_v2`가 이미 생성되어 있음.

## 호출 위치
- `backend/app/agents/retrieval/tools/rds_retriever.py`
  - `search_hybrid_rrf_best()`에서 s2 / s2_v2 / s3 선택
  - `search_hybrid_rrf_s2_v2()`에서 SQL 호출 및 row 매핑
- `backend/app/agents/retrieval/case_agent.py`
  - `search_hybrid_rrf_best()`를 호출 (직접 함수명 고정 X)

## 사용법 (환경변수)
- 기본: `RETRIEVAL_HYBRID_FN` 미설정 또는 기타 값 → **s2 사용**
- 옵션: `export RETRIEVAL_HYBRID_FN=s2_v2` → **s2_v2 사용**
- 옵션: `export RETRIEVAL_HYBRID_FN=s3` → **s3 사용**

## s2_v2 반환 스키마 (중요)
- `chunk_id, dataset_type, category, text, rrf_score, bm25_score, vector_similarity,
  source_url, source_file, printed_page, source_year, metadata`

## 실행 확인 (간단)
1) `python backend/scripts/testing/retrieval/smoke_case_counsel.py`
2) 로그 확인
   - `hybrid_rrf_best: selected=s2|s2_v2|s3 filter_dataset=... filter_category=...`
   - `case_return_state.sample_category`가 **null이 아닌지** 확인

## 참고
- `search_hybrid_rrf_s2` / `search_hybrid_rrf_s3`는 변경하지 않는다.
- s2_v2는 **category 반환이 필요할 때만** 선택적으로 사용한다.
