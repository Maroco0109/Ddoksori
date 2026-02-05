# Case Agent Debug Logging

## 왜 "조정=0" split이 생기나
- dispute_quota 자체가 작으면(예: 1) 한쪽이 0이 되는 게 정상이다.
- 점수 기반 가중치가 한쪽에 몰리면 ratio 계산 과정에서 0이 될 수 있다.
- 조정/해결 점수가 모두 0이면 임시 가중치(1,1)로 분배되지만, quota가 작으면 0이 여전히 발생할 수 있다.
- strong hit 최소 보장(min guard)이 들어오면 0을 막아주지만, 조건에 따라 적용되지 않을 수 있다.

## 추가된 로그 설명
### case_quota_policy
- 목적: quota 및 split 정책의 전체 맥락 기록
- 추가 필드:
  - category_scores: {"상담": x, "조정": y, "해결": z}
  - dispute_split_reason: ratio_based / min_guard_applied / score_zero / no_dispute_quota
  - min_split_guard: {"조정": 1, "해결": 1} 형태(적용 시) 또는 null

### case_dispute_split
- 목적: 조정 또는 해결이 0이 되는 원인 추적 (요청당 1회)
- 필드:
  - dispute_quota
  - scores: {"조정":..., "해결":...}
  - split: {"조정":..., "해결":...}
  - reason: adjust_score_zero / relief_score_zero / quota_too_small / ratio_rounding

### case_winner_track_bonus
- 목적: winner_track bonus 적용 여부/값 추적
- 필드:
  - enabled
  - eps
  - winner_track


## 스모크 테스트 확인 방법
```bash
export RETRIEVAL_HYBRID_FN=s2_v2
export CASE_WINNER_TRACK_BONUS_ENABLED=true
python backend/scripts/testing/retrieval/smoke_case_counsel.py --query "환불 절차 문의"
python backend/scripts/testing/retrieval/smoke_case_counsel.py --query "손해배상 청구 가능한가"
```

### 로그에서 확인할 포인트
- `case_quota_policy`에 category_scores / dispute_split_reason / min_split_guard 존재
- `case_dispute_split`에서 reason 확인 (조정=0 원인)
- `case_winner_track_bonus`에서 enabled/eps/winner_track 확인
- (옵션) `case_return_state.sample_category`가 null이 아닌지 확인
