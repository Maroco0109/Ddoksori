# Case Agent ↔ Retrieval Merge 호환 정리

## 목적
- **팀 파일(Protocol/merge)은 수정하지 않고**, case_agent만 조정해 merge와 100% 호환 유지
- RetrievalResult(4섹션) 구조는 팀 스펙 그대로 유지


## merge가 읽는 키 (중요)
- `title`
- `url`
- `content` (없으면 `text`)
- `soft_score` (없으면 `similarity`)

추가 패널티 조건
- title/url 누락 시 패널티
- content 길이 짧으면 패널티


## case_agent 반환 구조 (IndividualRetrievalResult)
- `source`: 항상 `case`
- `documents`: case_agent 문서 리스트
- `max_similarity`, `avg_similarity`: documents 기준 계산


## case_agent 문서 매핑 (row → document)
- `text` → `content`
- `source_url` → `url`
- `vector_similarity` → `similarity`
- `doc_title`/`title`/`source_file` → `title`
- `soft_score`: case_agent 내부 계산값

### 메타데이터 보관 정책
아래 키는 **metadata에 함께 보관**한다 (merge 기준에는 영향을 주지 않음):
- `category`, `dataset_type`, `chunk_id`, `source_year`
- `rrf_score`, `bm25_score`, `vector_similarity`


## smoke 확인 포인트
1) `case_agent` 결과에 `title/url/content/similarity`가 빠지지 않는지
2) `case_return_state.sample_category`가 null이 아닌지
3) `hybrid_rrf_best: selected=...` 로그로 DB 함수 선택 확인


## 참고
- merge는 `source_to_section`에서 `case → disputes`로 매핑한다.
- soft_score가 있으면 merge는 soft_score 우선 정렬한다.
