# Case Agent 변경사항 통합 요약

## 범위
- case 전용 흐름만 정리
- merge/law/criteria/counsel는 범위 밖


## 문제였던 사항
1) **category 반환 누락**
- DB에는 `vector_chunks.category`가 존재하지만
- 기존 DB 함수 결과 스키마/매핑에 category가 없어 앱 레벨에서 트랙 추적이 불안정했음

2) **DB 함수 스키마 변경 불가 (42P13)**
- `search_hybrid_rrf_s2`는 RETURNS TABLE 고정 스키마라 컬럼 추가가 불가
- 해결: `search_hybrid_rrf_s2_v2` 신규 함수로 category 포함 스키마 제공

3) **트랙 운영 디버깅 부족**
- 조정=0 split 원인 추적 로그 부족
- winner_track이 top1에서 밀리는 경우를 제어할 옵션 부재


## 적용된 변경 (case 관련)
### 1) rds_retriever.py (DB 함수 선택)
- `search_hybrid_rrf_s2_v2()` 추가: category 포함 스키마 매핑
- `search_hybrid_rrf_best()` 분기 확장
  - 기본: s2
  - 옵션: `RETRIEVAL_HYBRID_FN=s2_v2` → s2_v2
  - 옵션: `RETRIEVAL_HYBRID_FN=s3` → s3
- 선택 로그: `hybrid_rrf_best: selected=... filter_dataset=... filter_category=...`

### 2) case_agent.py (로그/옵션 보강)
- quota 정책 로그 확장
  - `category_scores`, `dispute_split_reason`, `min_split_guard`
- 조정/해결 split 원인 로그
  - `case_dispute_split` (요청당 1회)
- winner_track 보너스 옵션
  - env `CASE_WINNER_TRACK_BONUS_ENABLED=true` 일 때만 `rrf_score`에 eps 가산
  - `CASE_WINNER_TRACK_BONUS_EPS`로 크기 조절(기본 1e-6)
  - `case_winner_track_bonus` 로그 추가


## 변경된 파일 목록
- `backend/app/agents/retrieval/tools/rds_retriever.py`
- `backend/app/agents/retrieval/case_agent.py`
- `docs/CASE_AGENT_DEBUG_LOGGING.md`
- `docs/CASE_HYBRID_RRF_S2_V2.md`
- `docs/CASE_RETRIEVAL_PIPELINE_CASE_AGENT_ONLY.md`
- `docs/CASE_AGENT_ONLY_NO_MERGE.md`


## 확인 방법 (간단)
```bash
export RETRIEVAL_HYBRID_FN=s2_v2
export CASE_WINNER_TRACK_BONUS_ENABLED=true
python backend/scripts/testing/retrieval/smoke_case_counsel.py --query "환불 절차 문의"
python backend/scripts/testing/retrieval/smoke_case_counsel.py --query "손해배상 청구 가능한가"
```

확인 포인트
- `hybrid_rrf_best: selected=s2_v2` 로그 확인
- `case_dispute_split`에서 조정=0 원인 확인
- `case_winner_track_bonus` enabled/eps 확인
- `case_return_state.sample_category`가 null이 아닌지 확인
