# M7-1 스트리밍 계측 파리티 (계획 + 결과)

- 작성일: 2026-07-05
- 모듈: `M7-1` 스트리밍 계측 파리티
- 상위: 로드맵 §M7, 개요 `docs/plans/modules/M7-streaming-integration-plan.md`
- 성격: **기존 계측 재사용.** 새 빌더/계측 정의 없음. variant 라우팅은 M7-2.

## 0. 한 줄 요약

프론트 실사용 경로 `/chat/stream`에 비스트리밍 `/chat`의 A-path 계측(M3 적재 + M6 메트릭 + guardrail_events)을 **동일하게** 부여한다. 스트리밍 `final_state`가 `_node_timings`·`retrieval`을 이미 담고 있어 **기존 A 빌더를 그대로 재사용**하며, 계측 실패가 이미 전송된 스트림을 깨지 않도록 **best-effort(try/except)** 로 감싼다.

## 1. 배경 / 근거 (코드 확인)

- 비스트리밍 `/chat` A-path(`chat.py` ~394–486)는 성공 시 `save_workflow_run`(M3-3), `save_workflow_steps`(M3-4), `save_retrieval_events`(M3-5), `save_llm_calls`(M3-6), `save_guardrail_events`(M3-7), `save_protocol_events`(M3-9) + M6 `record_chat_request`/`record_guardrail_blocks`/`record_llm_tokens`를 호출한다.
- 이 빌더들의 입력:
  - `node_timings = final_state.get("_node_timings", {})` (chat.py:365) — **final_state 안**에 있음.
  - `retrieval = final_state.get("retrieval") or {}` — **final_state 안**.
  - `build_a_*`는 `node_timings`/`final_state`만으로 구성(read-only).
- `/chat/stream`(`chat.py` 555–939)은 `graph.astream_events`로 `final_state`를 누적하지만 **위 저장/메트릭을 하나도 호출하지 않음**. 즉 동일 `final_state`를 갖고도 계측만 빠져 있다.

→ **결론**: 스트리밍 완료 지점(`final_state` 확정 후, `rag_logger.finalize` 이후)에 동일 블록을 붙이면 파리티가 된다. 신규 로직 최소.

## 2. 설계

- **성공 경로**(`if final_state:` 블록, `rag_logger.save(log_entry)` 다음): `node_timings = final_state.get("_node_timings", {})` 추출 → 기존 6개 `save_*` + 3개 `record_*` 호출. 인자는 비스트리밍과 동일(`run_id=log_entry.request_id`, `variant="A"`, `answer`, `blocked=final_state.get("guardrail_blocked")`, `clarified=not has_sufficient_evidence` 등).
- **에러 경로**(`except Exception`): `save_workflow_run(status="error")` + `record_chat_request("A","error")`.
- **best-effort 필수**: 스트리밍은 이미 `complete`/`error` 이벤트를 클라이언트에 보낸 뒤라, 계측 예외가 스트림을 깨면 안 된다. 전체 계측 블록을 **`try/except`로 감싸 로그만 남기고 무시**한다(비스트리밍은 메인 try에 있어 500으로 전파되지만, 스트리밍은 비파괴적이어야 함 — 유일한 구조적 차이).
- **variant는 여전히 "A"**: 스트리밍은 아직 MAS 전용(M7-2에서 라우팅). 본 모듈은 라벨 A로 적재.

## 3. 스코프 경계

- **대상**: `chat_stream_sse` 성공/에러 경로만. 그래프/노드/빌더/DB 스키마 변경 없음.
- **비대상**: variant 분기(M7-2), 프론트(M7-3), LangSmith(M7-4). cancelled 경로는 기존대로(부분답 메모리 저장만) 두되, 필요 시 후속.

## 4. 완료 기준 / 검증

- [x] 스트리밍 요청 1건 → `workflow_runs`에 `variant='A'` 성공 row 적재.
- [x] 같은 run에 `guardrail_events` 적재(input/output/review 중 실행된 것).
- [x] `/metrics`에 `chat_requests_total{variant="A",...}` 증가.
- [x] 계측 예외가 스트림 응답을 깨지 않음(best-effort).
- 검증 = 라이브: 스택 기동 → `POST /chat/stream` → DB(`workflow_runs`/`guardrail_events`) + `/metrics` 확인.

## 5. 결과 (라이브 검증, 2026-07-05)

worktree 코드를 backend 컨테이너에 마운트해 기동 → `POST /chat/stream`(`session_id=m7-1-verify-1`, dispute) 1건 실행.

- **workflow_runs**: 1 row — `variant='A'`, `status='success'`, `blocked=f`, answer 854자.
- **M3 child parity (같은 run_id)**: `workflow_steps=1`, `retrieval_events=3`, `llm_calls=3`, **`guardrail_events=3`**, `protocol_events=1` → 비스트리밍 A-path와 동일하게 6개 테이블 전부 적재.
- **M6 metric**: `/metrics`에 `chat_requests_total{status="success",variant="A"} 1.0` 노출.
- **비파괴**: `complete` 이벤트 정상 수신, 계측은 성공 이후 best-effort로 실행되어 스트림 무영향.

→ 완료 기준 전부 충족. 이제 프론트 실사용 경로(`/chat/stream`)가 M3/M6에 잡힌다. (variant는 아직 A 고정 — M7-2에서 라우팅.)

## 6. Next gate → M7-2

`/chat/stream`을 per-request variant 3택(A / B-frontier / B-exaone) 라우팅으로. 본 M7-1 계측 블록은 variant 라벨만 요청값으로 바꾸면 B에도 재사용 가능하도록 설계됨.
