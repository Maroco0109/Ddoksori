# M3-4 workflow step 저장 (결과 문서)

- 작성일: 2026-06-24
- 모듈: `M3-4` workflow step 저장 (node sequence + latency)
- 계획서: `docs/plans/modules/M3-4-workflow-steps-plan.md`
- 상위 계획: §M3 (L116)
- 성격: 코드 구현 + 라이브 검증. A 동작 무변경(B는 단계 타이머만 추가).

## 0. 한 줄 결론

`006_workflow_steps.sql`을 적용하고 동기 `/chat`의 A·B 경로가 run 1건의 실행 경로를 **step N행**(`seq`/`step_name`/`category`/`duration_ms`)으로 best-effort 저장하게 했다. **실제 `/chat`으로 A 16-step(node별 latency)·B 4-step(신규 타이머)** 저장을 라이브 검증했고, `category`로 **A/B를 SQL 한 번에 비교**(retrieval/generation/guardrail 평균 latency)함을 확인했다.

## 1. 구현 내용

| 파일 | 변경 |
| --- | --- |
| `backend/app/database/migrations/006_workflow_steps.sql` | 신규 (FK→workflow_runs CASCADE, UNIQUE(run_id,seq), category CHECK) |
| `backend/app/observability/workflow_steps.py` | 신규 (`WorkflowStepDB` batch + best-effort `save_workflow_steps` + `build_a_steps`/`build_b_steps` + category 매핑) |
| `backend/app/variant_b/agent.py` | B 4단계에 `perf_counter` 타이머 → trace `duration_ms` (B만, 동작 무변경) |
| `backend/app/api/chat.py` | A: `pipeline_summary.per_node`+`node_timings`로 step 저장. B: `run_b` trace로 step 저장. |

- 저장: `execute_values` batch `INSERT ... ON CONFLICT (run_id, seq) DO NOTHING`, 실패 시 예외 삼킴(best-effort).
- category 매핑은 `workflow_steps.py` 한 곳에서 관리(A node→category, B step→category).

## 2. 라이브 검증 결과 (5432 DB, RunPod EXAONE up)

### A run — 16 step (node sequence + per-node latency)
```
seq | step_name        | category   | ms
 0  | cache_check      | other      |   0
 1  | input_guardrail  | guardrail  | 797
 2  | supervisor       | analysis   |   0
 3  | query_analysis   | analysis   | 4005
 5  | retrieval_law    | retrieval  | 4626
 6  | retrieval_criteria| retrieval | 1266
 7  | retrieval_case   | retrieval  | 1428
 8  | retrieval_merge  | retrieval  |   1
10  | generation       | generation | 5613
12  | review           | review     |   3
14  | output_guardrail | guardrail  | 443
15  | memory_save      | other      |   0
```

### B run — 4 step (신규 단계 타이머)
```
seq | step_name        | category   | ms
 0  | guardrail_input  | guardrail  | 742
 1  | gate_retrieval   | retrieval  | 442
 2  | react            | generation | 8452
 3  | guardrail_output | guardrail  | 692
```

### A/B category별 평균 step latency (모듈 목적 — SQL A/B 비교)
```
variant | category   | n_steps | avg_ms | sum_ms
 A      | retrieval  |    8    | 1645   | 13157
 A      | generation |    2    | 3882   |  7764
 A      | guardrail  |    2    |  620   |  1239
 A      | analysis   |   12    |  851   | 10218
 B      | generation |    1    | 8452   |  8452   (ReAct, tool+생성 통합)
 B      | retrieval  |    1    |  442   |   442   (gate만; tool 검색은 M3-5)
 B      | guardrail  |    2    |  717   |  1433
```

| 검증 항목 | 결과 |
| --- | --- |
| migration 006 (FK CASCADE/UNIQUE/CHECK/인덱스) | ✅ `\d workflow_steps` 확인 |
| A run → node별 duration 조회 (완료기준 L116) | ✅ 16 step, seq 순 duration |
| B run → step별 duration 채워짐 (신규 타이머) | ✅ 4 step 실측 latency |
| `category`로 A/B 비교 집계 | ✅ retrieval/generation/guardrail 등 |
| best-effort 비차단 (steps 테이블 제거 후 `/chat`) | ✅ HTTP 200 유지, warning만 |
| A 파이프라인 로직 diff 0 (B는 타이머만) | ✅ |

## 3. 구현 중 발견 / 수정

- **A 노드 집합이 M3-1 인벤토리(`REGISTERED_NODES`)보다 풍부**: 실제 그래프에 `cache_check`, `input_guardrail`, `output_guardrail`, `memory_save` 노드가 존재. 초기 매핑이 guardrail 노드를 `other`로 분류 → **`input_guardrail`/`output_guardrail`→`guardrail` 매핑 + `"guardrail" in node` 폴백 추가**로 수정(라이브 재검증). 이로써 A guardrail과 B guardrail이 같은 범주로 비교됨.

## 4. 후속 / 인계 (backlog)

- B `react` step은 tool 검색 + 모델 생성이 한 블록 → **retrieval/generation 분해는 M3-5**(`retrieval_events`)에서 tool 검색 단위로.
- A `supervisor` 반복 호출(라우팅)이 `analysis`로 다수 집계됨 — 의미 분석 시 참고.
- 스트리밍 `/chat/stream` step 저장은 M3-3-follow와 함께.

## 5. Next gate → M3-5

`retrieval_events` 저장(top-k/result count/similarity). step의 `retrieval` 범주를 검색 단위로 분해. A=S3 Retrieval/Structured 로그, B=`gate_retrieval` + `react` tool 검색.
