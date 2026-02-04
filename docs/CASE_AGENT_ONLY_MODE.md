# Case Agent Only Mode

## 전제
- **MAS Supervisor 정식 운영 그래프에는 retrieval_merge가 존재**한다.
- 이 문서는 **case_agent 단독 고도화/검증 스코프**를 다룬다.
- smoke_case_counsel.py 같은 단독 경로로 검증하며, merge 영향은 범위 밖이다.


## case_agent 내부 정렬 기준
- 정렬 위치: `_finalize_candidates()`
- 정렬 키: `self._rank_key`
  - 기본: `(rrf_score, vector_similarity, bm25_score)`
  - 단, `rrf_score <= 0.01`이면 `(vector_similarity, rrf_score, bm25_score)`

> **soft_score는 case_agent 내부 정렬에 사용되지 않는다.**
> `_format_results()`에서 계산되어 내려갈 뿐이다.


## 단독 고도화 체크리스트
1) **카테고리 분포 확인**
- topK 결과가 상담/조정/해결 중 한쪽으로 과도하게 쏠리지 않는지

2) **조정=0 원인 로그 확인**
- `case_dispute_split`에서 reason 확인
  - 예: `quota_too_small`, `adjust_score_zero`, `ratio_rounding`

3) **quota_policy 로그 해석**
- `case_quota_policy`의 `category_scores`, `dispute_split_reason`, `min_split_guard` 확인


## smoke 확인 방법
```bash
export RETRIEVAL_HYBRID_FN=s2_v2
export SMOKE_CASE_AGENT_ONLY_NOTE=true
python backend/scripts/testing/retrieval/smoke_case_counsel.py --query "환불 절차 문의"
python backend/scripts/testing/retrieval/smoke_case_counsel.py --query "손해배상 청구 가능한가"
```

확인 포인트
- `[SMOKE] This script calls case_agent directly; retrieval_merge is NOT involved.`
- `hybrid_rrf_best: selected=s2_v2` 로그
- `case_return_state.sample_category`가 null이 아닌지
