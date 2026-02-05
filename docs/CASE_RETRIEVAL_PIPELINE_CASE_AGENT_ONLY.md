# Case Retrieval Pipeline (Case Agent Only)

## 1) 전체 구조 요약
- 소비자 쿼리
- (Rewrite는 query_analysis에서 수행됨)
- Retrieve: DB hybrid RRF 호출 (기본 s2, 옵션 s3)
- case_agent 내부에서 **quota → fill → dedup** 처리
- 결과 반환

> 이 문서는 **case_agent 전용** 범위만 다룬다. merge/law/criteria는 범위 밖이다.


## 2) 현실적인 수정 포인트 (파일/경로)
- `backend/app/agents/retrieval/case_agent.py`
  - retriever 호출을 `search_hybrid_rrf_best()`로 교체
  - quota/fill/dedup/로그 로직은 그대로 유지

- `backend/app/agents/retrieval/tools/rds_retriever.py`
  - `search_hybrid_rrf_s2()` / `search_hybrid_rrf_s3()` 추가
  - `search_hybrid_rrf_best()`에서 기본 s2, 옵션 s3 선택
  - **기존 `search_hybrid_rrf()`는 그대로 유지**

- DB 함수
  - `public.search_hybrid_rrf_s2`
  - `public.search_hybrid_rrf_s3`


## 3) DB 함수 선택 정책 (중요)
- 기본값: **s2**
- 옵션: 환경변수 `RETRIEVAL_HYBRID_FN=s3` → s3 호출
- 그 외 값이면 s2 호출

> s3는 **호출을 바꿔야** 효과가 난다. DB에 함수가 있어도 호출이 s2면 의미 없다.


## 4) 데이터/요청 흐름 (case_agent._execute_search 기준)
### 4.1 공통 전제
- dataset_type 기본값: `case`
- category 매핑: `상담` / `조정` / `해결`
- 내부 `_search_rrf` 래퍼에서만 DB 함수 선택
  - `search_hybrid_rrf_best()`를 통해 s2/s3 선택
  - 그 외 로직은 DB 함수명을 직접 건드리지 않음

### 4.2 top_k <= 5
1) **룰베이스 점수화**
   - 상담 vs 분쟁/구제 승자 트랙 결정
   - 확신도에 따라 quota 비율 결정

2) **트랙별 최소 호출**
   - 승자 트랙 위주로 우선 검색
   - 필요 시 반대 트랙 최소 확보

3) **quality gate (필요 시)**
   - 상담/분쟁 top1 비교
   - 상담 쪽이 의미 있게 우수하면 추가 상담 1~2건 탐색

4) **dedup 1회 확정**
   - doc_id > case_number > url > chunk_id 우선순위

5) **fill (2단계)**
   - 1) 카테고리 완화: category=None
   - 2) broaden query 후 재검색


### 4.3 top_k > 5
1) **룰베이스 점수화 + quota 분배**
   - 상담 vs 분쟁/구제 2트랙 quota 산정
   - 분쟁/구제 내부는 조정/해결로 추가 분배

2) **카테고리별 검색**
   - 상담/조정/해결 각각 quota만큼 호출

3) **quality gate (필요 시)**
   - 상담 top1이 분쟁 top1보다 의미 있게 높은 경우 상담 추가

4) **dedup 1회 확정**
   - 문서 단위 1건만 유지

5) **fill (2단계)**
   - 1) 카테고리 완화: category=None
   - 2) broaden query


## 5) 헷갈리는 포인트 정리
- **soft_score/bonus/penalty/merge 계약은 이 문서 범위 밖**
- dedup은 **execute_search에서 1회만 확정**하고
  format 단계에서는 건드리지 않는 방향 권장
- s3는 **호출을 바꿔야** 효과가 난다


## 6) 로그 항목 (운영 추적용)
### 6.1 search_hybrid_rrf_best (선택 로그)
- selected (s2/s3)
- filter_dataset
- filter_category

### 6.2 case_quota_policy
- K
- confident / confidence
- winner_track
- ratio
- counsel_score / combined_score / score_gap
- p_dispute
- quotas (counsel/dispute)
- dispute_split (조정/해결)

### 6.3 case_quality_gate
- winner_track / winner_track_after_gate
- best_counsel / best_dispute
- delta
- extra_counsel

### 6.4 case_dedup_state
- stage
- raw / deduped / removed
- group_max

### 6.5 case_fill
- stage
- added
- remaining

### 6.6 case_return_state
- len
- type
- keys
- has_metadata
- sample_category
- sample_dataset_type
- sample_source
- sample_doc_id


## 7) 실행 확인 (간단)
- `python backend/scripts/testing/retrieval/smoke_case_counsel.py`
- 로그에서 `hybrid_rrf_best: selected=s2|s3` 확인
  - filter_dataset / filter_category도 함께 출력됨
