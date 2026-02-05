소비자 쿼리 → 쿼리 재생성(Rewrite) → 검색(Retrieve: DB 함수 hybrid/vector/bm25) → 컨텍스트 구성(Context Building) → 출력(Answer)

# Case/Counsel Retrieval Pipeline v2 (실무형 스코어링/쿼터/머지 고도화)

## 0) 목적
- 기존 파이프라인을 유지하면서, **실무 운영 가능한 점수화/쿼터/머지 재랭킹/로그 기반 튜닝 루프**를 추가한다.

## 1) 변경한 파일/함수 목록 (계획)
- 문서 중심 업데이트: `docs/CASE_COUNSEL_RETRIEVAL_PIPELINE.v2.md`
- 실행된 가성비 항목:
  - Dedup 정책 적용 (doc_id > case_number > url > chunk_id)
  - soft_score 계산 (query-local minmax 기반)
  - case 단일 트랙(상담 vs 분쟁/구제 quota+2단계 fill)

## 2) 스코어 스택 설계 (검색 점수 표준화 + soft_score)
### 2.0 Score Contract (retriever 결과 표준 필드)
- 필수: `doc_id`, `chunk_id`, `title`, `source`, `vec`, `bm25`, `rrf`
- 기대: 각 트랙 결과가 동일 필드명으로 내려오면 soft_score 계산/merge 재랭킹이 단순화됨
### 2.1 기본 스코어(현재)
- Vector similarity
- BM25 score
- RRF score (hybrid 결과)

### 2.2 문제점
- 점수 스케일이 달라 단순 합산 시 왜곡 발생

### 2.3 표준화 + soft_score (권장)
- 개념:
  - `soft_score = w_vec * norm(vec) + w_bm25 * norm(bm25) + w_rrf * norm(rrf) + bonuses - penalties`
- norm 후보:
  - min-max (0~1)
  - sigmoid
  - rank-based
### 2.4 Norm Default (기본값)
- 기본: **query-local minmax** (또는 rank-based)  
- 이유: 쿼리별 분포 차이를 가장 단순하게 보정하면서 스케일을 0~1로 안정화

## 3) 메타 기반 bonus/penalty (품질 체감 개선)
### 3.1 bonus
- 현재 OFF

### 3.2 penalty
- 중복: 동일 doc_id/사건번호/청크 반복
- 필수 메타 결손(title/url 없음)
- 지나치게 짧은/노이즈 청크 (상담 60 / 조정+해결 100 / 기타 80)
- penalty weight: -0.03

### 3.3 Dedup Key Policy (우선순위)
- dedup 우선순위: **doc_id > case_number > url > chunk_id**
- 동일 키 충돌 시 soft_score가 낮은 항목 제거

## 4) quota 동적화 (의도/확신도 기반)
- 정적 quota → 동적 quota
- 상담 vs 분쟁/구제 2트랙으로 배분
- 확신: winner_track에 0.7 비율 배분(ceil), 나머지 트랙은 K-배분
- 애매: 0.5 비율 배분(ceil)
- Hard routing 금지, **quota 조절만**
- 결과 부족 시 2단계 fill (카테고리 완화 → broaden query)
- 정책 로그: `case_quota_policy`, `case_track_counts`
- 입력 인터페이스: `RetrievalTaskInputV2` (expanded_queries/agent_keywords/metadata_filter/top_k/ignore_threshold)

## 4.2) 1차 룰베이스 분류 (case_agent)
- case_agent가 query/query_analysis 기반으로 상담 vs 분쟁/구제 점수 계산
- 확신: winner_track 0.7 배분(ceil)
- 애매: 0.5 배분(ceil)
- 조정/해결 strong hit이 있으면 통합 quota 내에서 각 3개 최소 보장
- 부족분은 2단계 fill로 채움
- metadata_filter.categories는 ['조정','해결','상담'] 입력 가능, 내부는 2트랙 통합 처리
- 강제 분쟁/구제 입력(조정+해결/통합) 시 상담 트랙은 제외

### 4.1 Quota Policy Table (예시)
| confidence | counsel | 분쟁/구제 | 비고 |
|---|---:|---:|---|
| Confident | ceil(0.7*K) | K-배분 | 1등 우선 |
| Uncertain | ceil(0.5*K) | K-배분 | 균형 |

## 5) merge 재랭킹 (트랙 간 최종 우선순위)
- 섹션별 top-k 유지 + 전체 우선순위 추가
- QueryAnalysis의 **답변 전략(strategy)**에 따라 트랙 가중치 변경
- 예시:
  - 법령 질의 → laws 비중↑, cases 비중↓
  - \"환불 가능?\" → criteria + cases 비중↑


## 6) 평가/로그 기반 튜닝 루프
### 6.1 로그(최소)
- query 원문 / rewrite / subtype_confidence
- 각 트랙 상위 20 후보
- doc_id, chunk_id, soft_score 구성요소(vec/bm25/rrf/bonus/penalty)
- 최종 선택된 contexts
- (가능 시) 사용자 피드백/정답 라벨

### 6.2 지표(가볍게 시작)
- Coverage@k
- DupRate
- SourceDiversity
- SubtypeBalance
- Latency/Cost

### 6.3 Logging Leveling (저장 범위)
- INFO: query/rewrite, 최종 선택된 contexts, top-k 요약(점수 합계/대표값)
- DEBUG: 후보 상위 20의 vec/bm25/rrf/norm/bonus/penalty 구성요소, dedup 제거 내역

## 7) 적용 순서 (가성비 순)
1) 중복 제거 + 필수 메타/길이 penalty
2) 스코어 표준화 + soft_score
3) 동적 quota
4) 2단계 fill 정책 정교화

## 8) 체크리스트 (운영 점검)
- 점수 표준화 함수 선택 및 스케일 검증
- bonus/penalty 기준 확정(출처/최신성/중복/메타결손)
- subtype confidence 산출 품질 검증
- merge 재랭킹 전략(답변 전략) 정의
- 로그/지표 수집 파이프라인 구축

## 9) Implementation Record (Before/After)
### 9.1 case_agent._format_results (요약)
Before
```python
for r in results:
    ...
    formatted.append({
        "chunk_id": ...,
        "doc_id": ...,
        "doc_title": ...,
        "title": doc_title,
        "similarity": similarity,
        "rrf_score": ...,
        "bm25_score": ...,
        "vector_similarity": ...,
        "metadata": metadata,
    })
```
After
```python
score_list = [_scores(r) for r in results]
norm_vec = _minmax([s["vec"] for s in score_list])
norm_bm25 = _minmax([s["bm25"] for s in score_list])
norm_rrf = _minmax([s["rrf"] for s in score_list])
seen_keys = set()
for idx, r in enumerate(results):
    dedup_key = doc_id or case_number or source_url or chunk_id
    if dedup_key in seen_keys:
        continue
    soft_score = 0.6 * norm_vec[idx] + 0.2 * norm_bm25[idx] + 0.2 * norm_rrf[idx]
    formatted.append({..., "soft_score": soft_score, ...})
```

### 9.2 counsel_agent._format_results (요약)
Before
```python
for r in results:
    ...
    formatted.append({..., "title": doc_title, "similarity": similarity, ...})
```
After
```python
score_list = [_scores(r) for r in results]
... (minmax normalize)
dedup_key = doc_id or case_number or source_url or chunk_id
soft_score = 0.6 * norm_vec[idx] + 0.2 * norm_bm25[idx] + 0.2 * norm_rrf[idx]
formatted.append({..., "soft_score": soft_score, ...})
```

### 9.3 rds_retriever.search_hybrid_rrf (오류 처리, 현재 이슈 해결됨)
Before
```python
cur.execute(\"\"\"SELECT * FROM search_hybrid_rrf(...)\"\"\", params)
```
After
```python
try:
    cur.execute(\"\"\"SELECT * FROM search_hybrid_rrf(...)\"\"\", params)
except psycopg2.errors.AmbiguousColumn:
    raise RuntimeError(\"search_hybrid_rrf() ... recreate function with qualified columns\")
```

### 9.4 DB 함수 패치 (참고용 SQL)
- 파일: `backend/scripts/db/patch_search_hybrid_rrf.sql`
- 목적: DB 함수 내 `chunk_id` 모호성 제거(별칭 명시, 현재 적용 완료)

## CHANGELOG
- 2026-02-01: 상담 vs 분쟁/구제 2트랙, 비율 기반 quota/2단계 fill, penalty 로그 반영
