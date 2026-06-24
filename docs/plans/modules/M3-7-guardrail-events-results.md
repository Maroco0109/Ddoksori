# M3-7 guardrail event 저장 (결과 문서)

- 작성일: 2026-06-24
- 모듈: `M3-7` guardrail event 저장 (입력/출력 보안 판단)
- 계획서: `docs/plans/modules/M3-7-guardrail-events-plan.md`
- 상위 계획: §M3 (L119)
- 성격: 코드 구현 + 라이브 검증. A 무변경(read-only), B는 guardrail reason 계측만 추가.
- 비고: **M3 저장 계층(M3-3~M3-7) 마지막 테이블 완료.** 다음은 M3-8 조회 API.

## 0. 한 줄 결론

`009_guardrail_events.sql`을 적용하고 동기 `/chat`이 보안 판단을 `guardrail_events`로 best-effort 저장하게 했다. **A는 input/output(moderation)+review(legal) 3행**을 `_node_timings.output_snapshot`에서 read-only로, **B는 input/output 2행**(`run_b` categories 계측)으로 기록. 정상 쿼리의 `pass`와 **유해입력의 `block`(reason=violence)** 을 라이브로 검증했다.

## 1. 구현 내용

| 파일 | 변경 |
| --- | --- |
| `backend/app/database/migrations/009_guardrail_events.sql` | 신규 (FK→workflow_runs CASCADE, UNIQUE(run_id,seq), stage/decision CHECK) |
| `backend/app/observability/guardrail_events.py` | 신규 (`GuardrailEventDB` batch + best-effort + `build_a_guardrail_events`/`build_b_guardrail_events`) |
| `backend/app/variant_b/agent.py` | guardrail trace에 flagged categories 추가 (B만, 동작 무변경) |
| `backend/app/api/chat.py` | A: `node_timings` snapshot으로 events. B: `run_b` trace로 events. |

## 2. 라이브 검증 결과 (5432 DB, RunPod EXAONE up)

### A run — input/output/review 3행 (read-only)
```
seq | stage  | source       | decision | reason
 0  | input  | moderation   | pass     |
 1  | output | moderation   | pass     |
 2  | review | legal_review | flag     | forbidden_header
```
→ review 노드가 규칙 위반(forbidden_header) 탐지 시 `flag` 기록.

### B normal run — input/output 2행
```
seq | stage  | decision | reason
 0  | input  | pass     |
 1  | output | pass     |
```

### B harmful input — input block (reason 계측)
```
seq | stage | decision | reason   | detail
 0  | input | block    | violence | {"categories": ["violence"]}
```
→ 유해입력이 input_guardrail에서 차단되고 **실제 moderation category(violence)** 가 reason/detail로 기록(B reason 계측 성공). pod 불필요 경로.

### A/B guardrail decision 집계 (모듈 목적)
```
variant | stage  | decision | n
 A      | input  | pass     | 1
 A      | output | pass     | 1
 A      | review | flag     | 1
 B      | input  | block    | 1
 B      | input  | pass     | 1
 B      | output | pass     | 1
```

| 검증 항목 | 결과 |
| --- | --- |
| migration 009 (FK CASCADE/UNIQUE/CHECK/인덱스) | ✅ `\d guardrail_events` |
| A run → input/output/review decision·reason (완료기준 L119) | ✅ 3행 |
| B run → input/output, **block 시 reason 채움** | ✅ violence |
| decision별 A/B 집계 | ✅ |
| best-effort 비차단 (테이블 제거 후 `/chat`) | ✅ HTTP 200, warning만 |
| A 로직 diff 0 (read-only; B는 reason 계측만) | ✅ |

## 3. caveat / 발견 (backlog)

- **A output reason NULL(설계대로)**: `output_guardrail` snapshot에 `guardrail_type` 미포함 → output 차단 사유 NULL. 입력/리뷰는 reason 보유.
- **review decision = flag**: review 위반은 정책상 차단이 아닌 플래그(`passed=false`)로 기록. 실제 차단(block)은 moderation에서.
- **정상 쿼리는 대부분 pass**: block/flag는 유해입력·위반표현 샘플로 별도 확인(본 검증에서 violence/forbidden_header로 확인).

## 4. Next gate → M3-8 (M3 마무리)

조회 API 최소 구현(read-only): 최근 run 목록 + run detail(steps/retrieval/llm/guardrail join). M3 저장 계층(M3-3~M3-7)을 소비해 모니터링 백본을 마무리. 이후 A/B 측정·회귀비교의 조회 기반 완성.
