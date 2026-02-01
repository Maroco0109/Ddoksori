# Case Schema ↔ Retrieval Flow (Contract)

## 1) 전체 구조 요약
본 문서는 **vector_chunks 스키마**와 **Retrieval 파이프라인**의 연결을 한눈에 이해하도록 정리한 계약 문서다. Retrieval은 하나의 테이블(vector_chunks)을 공통으로 사용하며, `dataset_type`과(case일 때) `category`를 통해 트랙을 분리한다.

## 2) 스키마(테이블/컬럼) 기반 설명
### 2.1 vector_chunks 핵심 컬럼 (검색 흐름 기준)
- **chunk_id**: 청크 고유 식별자
- **dataset_type**: `('law_guide','case')` 제약
- **text**: 검색 텍스트 본문
- **embedding**: 벡터 유사도 계산용
- **category**: case 내부 분기(상담/조정/해결)
- **law_name/article_number/article_number_normalized/document_type**: law_guide 전용
- **source_url/source_file/printed_page/source_year**: 출처/인용/필터링
- **metadata**: 추가 메타 (title/doc_id/decision_date 등)
- **text_tsv**: BM25 키워드 검색

### 2.2 case 분기 규칙
- `dataset_type='case'`인 경우 **category로 내부 트랙 분기**
  - 상담: `category='상담'`
  - 조정: `category='조정'`
  - 해결: `category='해결'`

## 3) 파라미터 → DB 필터 매핑 표
| 앱 파라미터 | DB 컬럼 | 의미 |
|---|---|---|
| filter_dataset | vector_chunks.dataset_type | law_guide / case 분기 |
| filter_category | vector_chunks.category | case 내부 분기(상담/조정/해결) |
| filter_document_type | vector_chunks.document_type | 법령 문서 유형 필터 |
| filter_year | vector_chunks.source_year | 연도 필터 |
| top_k | LIMIT | 반환 개수 |
| rrf_k | RRF 파라미터 | 하이브리드 결합 상수 |

### 3.1 반환 필드 (search_hybrid_rrf 기준)
- `chunk_id`, `dataset_type`, `text`
- `rrf_score`, `bm25_score`, `vector_similarity`
- `source_url`, `source_file`, `printed_page`, `source_year`
- `metadata`

## 4) 요청/데이터 흐름 (Rewrite→Retrieve→Merge)
1) **입력**: `user_query`
2) **Rewrite**: `query_analysis`에서 rewrite 수행 (retrieval base는 pass-through)
3) **Retrieve**:
   - hybrid RRF = `text_tsv(BM25)` + `embedding(vector)` + RRF 결합
   - case 트랙은 `dataset_type='case'` + `category`로 분리
4) **결과 포맷**:
   - `title` = `metadata.title` 또는 `metadata.doc_title` 또는 `source_file`
   - `url` = `source_url` (없으면 metadata.url fallback)
   - `similarity` = `vector_similarity` 대표값
   - `category`, `dataset_type`는 결과에 포함되어 하위 라우팅/분석에 사용
   - `soft_score`는 추가 계산(고도화 항목)
5) **Merge**:
   - law/criteria/case 3트랙 병합
   - case 내부는 상담 vs 분쟁/구제 quota + 2단계 fill

## 5) 설계 이유 (짧게)
- 한 테이블(vector_chunks)에 law_guide + case를 통합해도
  `dataset_type` + `category`로 분리하면 **검색 API를 공통화**할 수 있다.
- category를 지정하지 않으면 case 내부가 섞여 품질이 떨어지므로
  **quota+fallback(0건 방지)** 설계가 운영에 필수다.

## 6) 헷갈리는 포인트
- `dataset_type`는 **law_guide / case만 허용**됨
- case의 3트랙 분리는 **category(상담/조정/해결)**
- `chunk_type='case'`는 저장 형태 참고용이며 필터 기준은 아님
- `title/url`은 metadata/source 컬럼에 분산됨 (fallback 필요)

## 7) 검증 SQL (재현 가능)
### 7.1 case 카테고리 분포
```sql
SELECT category, COUNT(*)
FROM vector_chunks
WHERE dataset_type='case'
GROUP BY category;
```

### 7.2 category='상담' + dataset_type='case' hybrid_rrf 예시
```sql
SELECT * FROM search_hybrid_rrf(
  '상담 사례 환불 거부',
  (SELECT embedding FROM vector_chunks WHERE dataset_type='case' LIMIT 1),
  'case',
  '상담',
  NULL,
  NULL,
  5,
  60
);
```

### 7.3 vector-only sanity
```sql
SELECT chunk_id,
       1 - (embedding <=> (SELECT embedding FROM vector_chunks LIMIT 1)) AS sim
FROM vector_chunks
WHERE dataset_type='case'
ORDER BY embedding <=> (SELECT embedding FROM vector_chunks LIMIT 1)
LIMIT 5;
```

### 7.4 BM25 sanity
```sql
SELECT COUNT(*)
FROM vector_chunks
WHERE dataset_type='case'
  AND text_tsv @@ plainto_tsquery('simple', '환불');
```

## Handoff Summary (Context 20% 대비)
- Retrieval은 **case 단일 트랙**으로 운영 중: 상담 vs 분쟁/구제 2트랙, quota+2단계 fill은 `case_agent`에 구현됨.
- `counsel_agent`는 제거/미사용 방향으로 정리됨(그래프 fan-out도 3개로 축소됨).
- Rewrite는 query_analysis에서 수행, retrieval base는 pass-through.
- DB 함수 `search_hybrid_rrf` 이슈는 해결됨(우회/rollback/fallback 경로는 철회).
- 스모크 테스트는 **에이전트 통합 경로**로 변경됨: case_combined(rule_based) 호출.
- 스모크에서 0건 발생 시: 쿼리-카테고리 부적합 가능성 큼. DB target 로그로 실제 접속 DB 확인 필요.
- merge 정렬은 bonus OFF, penalty ON(메타 결손/짧은 청크)로 운영됨.
- 최신 수정 파일 요약:
  - `backend/app/agents/retrieval/case_agent.py` (quota 정책, 2단계 fill, soft_score/dedup 포함)
  - `backend/app/orchestrator/nodes/retrieval_merge.py` (penalty/로그)
  - `backend/scripts/testing/retrieval/smoke_case_counsel.py` (통합 스모크)
  - `docs/CASE_COUNSEL_RETRIEVAL_PIPELINE.md` / `.v2.md`
