# M3-5 retrieval event 저장 (결과 문서)

- 작성일: 2026-06-24
- 모듈: `M3-5` retrieval event 저장 (RAG 결과 품질)
- 계획서: `docs/plans/modules/M3-5-retrieval-events-plan.md`
- 상위 계획: §M3 (L117)
- 성격: 코드 구현 + 라이브 검증. A 동작 무변경(B는 per-search 계측만 추가).

## 0. 한 줄 결론

`007_retrieval_events.sql`을 적용하고 동기 `/chat`의 A·B 경로가 **검색 호출별 retrieval_event**(`source`/`top_k`/`result_count`/`max·avg_similarity` + `top_chunks` JSONB)를 best-effort 저장하게 했다. **실제 `/chat`으로 A 3섹션·B gate+tool** 저장을 라이브 검증했고, `top_chunks`에 chunk별 `(chunk_id, similarity, rank)`가 들어가 **retrieval 품질을 SQL로 A/B 비교**함을 확인했다.

## 1. 구현 내용

| 파일 | 변경 |
| --- | --- |
| `backend/app/database/migrations/007_retrieval_events.sql` | 신규 (FK→workflow_runs CASCADE, UNIQUE(run_id,seq), source CHECK, top_chunks JSONB) |
| `backend/app/observability/retrieval_events.py` | 신규 (`RetrievalEventDB` batch + best-effort + `build_a_retrieval_events`/`build_b_retrieval_events`) |
| `backend/app/variant_b/tools.py` | per-search 이벤트 recorder 추가 (`_record_search_event`/`get_recorded_search_events`) — 검색 결과 무변경, 계측만 |
| `backend/app/variant_b/agent.py` | gate + tool 검색을 `retrieval_records`로 수집해 반환 |
| `backend/app/api/chat.py` | A: `final_state["retrieval"]` 4섹션. B: `run_b` retrieval_records. |

## 2. 라이브 검증 결과 (5432 DB, RunPod EXAONE up)

### A run — 섹션별 retrieval_events
```
seq | source   | top_k | result_count | max_sim | avg_sim | n_chunks
 0  | law      |   5   |      1       |  0.046  |  0.046  |   1
 1  | criteria |   5   |      2       |  0.016  |  0.016  |   2
 2  | case     |   5   |      3       |  0.678  |  0.676  |   3
```

### B run — gate + tool retrieval_events (per-search 계측)
```
seq | source | domain | top_k | result_count | max_sim | avg_sim | n_chunks
 0  | gate   |        |   5   |      5       |  0.695  |  0.695  |   5
 1  | tool   | law    |   5   |      5       |  0.412  |  0.402  |   5
 2  | tool   | case   |   5   |      5       |  0.682  |  0.668  |   5
```
→ B 모델이 law·case 도메인으로 재검색한 게 기록됨(agentic retrieval).

### top_chunks JSONB (검증)
```
gate: {"rank":0,"chunk_id":"crawl_semantic_상담_1239_full_1","similarity":0.695}
tool: {"rank":0,"chunk_id":"민법_제604조","similarity":0.412}
```

### A/B retrieval 품질 비교 (모듈 목적)
```
variant | source   | n_events | avg_results | avg_max_sim
 A      | case     |    1     |    3.0      |   0.678
 A      | criteria |    1     |    2.0      |   0.016
 A      | law      |    1     |    1.0      |   0.046
 B      | gate     |    1     |    5.0      |   0.695
 B      | tool     |    2     |    5.0      |   0.547
```

| 검증 항목 | 결과 |
| --- | --- |
| migration 007 (FK CASCADE/UNIQUE/CHECK/JSONB) | ✅ `\d retrieval_events` |
| A run → 섹션별 top_k/result_count/similarity (완료기준 L117) | ✅ law/criteria/case |
| B run → gate + tool, similarity·top_chunks 채워짐 (per-search 계측) | ✅ |
| `top_chunks` JSONB chunk별 similarity·rank 조회 | ✅ `jsonb_array_length`/`->` |
| A/B retrieval 품질 비교 집계 | ✅ |
| best-effort 비차단 (테이블 제거 후 `/chat`) | ✅ HTTP 200, warning만 |
| A 로직 diff 0 (B는 계측만) | ✅ |

## 3. 해석 주의점 / 발견 (backlog)

- **A/B similarity 척도 차이**: A의 `law`(0.046)·`criteria`(0.016) 섹션 similarity가 A `case`(0.678)·B cosine(0.4~0.7)과 스케일이 달라 보인다. A 일부 섹션의 `similarity`가 raw cosine이 아닌 다른 척도(RRF 점수/정규화 등)일 가능성. **M3-5는 A가 산출한 값을 충실히 기록**하며, A/B를 max_similarity로 직접 비교할 때는 **척도 정규화 확인이 필요**(해석 caveat). → 후속: A 섹션 similarity 출처/척도 확인.
- B `tool` source는 `domain` 컬럼으로 검색 대상(law/case 등) 구분 → A의 source(law/criteria/case)와 교차 비교는 `domain`/`source` 조합으로.

## 4. Next gate → M3-6

`llm_calls` 저장(provider/model/fallback/error/token). 정적 라벨(`"variant-b"`/`"gpt-4o-mini"`)을 실제 호출 단위 provider/model로 대체. A=S3 LLMLog+토큰, B=react 모델 호출.
