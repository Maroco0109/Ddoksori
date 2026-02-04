# Case Agent Only (No Merge)

## 범위
- **case_agent 전용** 운영 가이드
- merge(soft_score 기반 최종정렬), law/criteria/counsel fan-in은 범위 밖


## case_agent 내부 정렬 기준
- `_finalize_candidates()`에서 `self._rank_key`로 정렬
- 기본 정렬 키:
  - `(rrf_score, vector_similarity, bm25_score)`
- 단, `rrf_score <= 0.01`이면:
  - `(vector_similarity, rrf_score, bm25_score)`

> **soft_score는 case_agent 정렬에 사용되지 않는다.**
> soft_score는 `_format_results()`에서 계산될 뿐, final sort 기준이 아니다.


## merge 단계 사용 중단 계획
- 오케스트레이션에서 `retrieval_merge` fan-in을 **비활성화/제거 예정**
- case_agent 결과를 그대로 answer 단계로 넘기는 **case_agent_only 모드** 운영
- 목적: merge(soft_score 기반 정렬) 의존 제거


## smoke 확인 방법
```bash
export RETRIEVAL_HYBRID_FN=s2_v2
python backend/scripts/testing/retrieval/smoke_case_counsel.py --query "환불 절차 문의"
python backend/scripts/testing/retrieval/smoke_case_counsel.py --query "손해배상 청구 가능한가"
```

확인 포인트
- 로그 `hybrid_rrf_best: selected=s2_v2` 출력
- `case_return_state.sample_category`가 null이 아닌지
- topK 결과의 category 분포가 상담/조정/해결 중 한쪽으로 과도하게 쏠리지 않는지
