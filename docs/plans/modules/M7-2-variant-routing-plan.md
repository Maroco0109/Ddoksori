# M7-2 스트리밍 variant 라우팅 (계획 + 결과)

- 작성일: 2026-07-05
- 모듈: `M7-2` variant 라우팅 통합 (streaming)
- 상위: 로드맵 §M7, 개요 `M7-streaming-integration-plan.md`, 선행 `M7-1`(계측 파리티)
- 성격: **라우팅 + B 스트리밍.** 프론트=M7-3, LangSmith=M7-4.

## 0. 한 줄 요약

`/chat/stream`을 요청 단위로 **A / B-frontier / B-exaone** 3택 라우팅하고, B(ReAct)에 status SSE를 부여했다. B 모델은 `VARIANT_B_MODEL_SPEC` env → **요청 파라미터 `model_spec`**로 승격. B 스트리밍 경로는 비스트리밍 `/chat` B 분기와 동일한 M3 적재+M6 메트릭(build_b_*)을 best-effort로 수행(M7-1과 동일 원칙).

## 1. 변경

- **`ChatRequest.model_spec`**(`models.py`) 추가: `Optional[Literal["frontier","exaone"]]`, 기본 None. variant=B일 때 모델 선택, 미지정 시 env 폴백.
- **`_variant_b_stream(body, session_id, start_time)`**(`chat.py`, 신규 async generator): status 이벤트 → `run_b`(sync → `asyncio.to_thread`) → complete 이벤트. 이어서 `save_workflow_run`+`workflow_steps`/`retrieval_events`/`llm_calls`/`guardrail_events`/`protocol_events`(build_b_*) + M6 `record_*`(variant="B"), best-effort try/except. 에러 시 error run 적재 + error 이벤트.
- **`chat_stream_sse` 분기**: `if body.variant == "B": _variant_b_stream(...) → return`, 아니면 기존 A astream.
- **비스트리밍 B 분기**도 `body.model_spec or env`로 일치(per-request 모델 양 엔드포인트 지원).

## 2. 설계 노트

- **B는 토큰 스트리밍 없음**: `run_b`가 동기 `agent.invoke`라 토큰 단위 스트림 불가 → status/complete 이벤트로 진행 표시(완료 기준=status SSE). 토큰 스트리밍은 후속(옵션).
- **model_spec 승격**: 프론트가 per-request로 B 모델을 고르려면 env 토글(서버 재시작 필요)로는 불가 → 요청 파라미터화. M7-3 셀렉터가 이 필드를 채운다.
- **B-exaone**: 동일 코드 경로(model_spec=exaone) + RunPod 파드 필요. 파드는 비용이라 상시 미가동.

## 3. 스코프 경계

- **대상**: `/chat/stream` variant 분기 + B 스트리밍/계측, `ChatRequest.model_spec`.
- **비대상**: 프론트 UI(M7-3), LangSmith(M7-4), B 토큰 스트리밍. A astream 경로/그래프/빌더 변경 없음.

## 4. 완료 기준 / 검증

- [x] 요청 `variant`로 A/B 라우팅, B에 status SSE.
- [x] `model_spec` per-request 반영(frontier→gpt-4o-mini).
- [x] A/B가 `workflow_runs`에 라벨 분리 적재 + `/metrics` variant별 집계.
- [x] B 계측 best-effort(스트림 비파괴).

## 5. 결과 (라이브 검증, 2026-07-05)

worktree 코드 마운트 후 `/chat/stream` 2건:

- **A**(`session=m7-2-A`, variant 기본): status×6 + complete → `workflow_runs` variant='A' success(844자).
- **B-frontier**(`session=m7-2-Bf`, variant=B, model_spec=frontier): status×2(연결됨+B 실행중) + complete(`model=variant-b-frontier`) → `workflow_runs` variant='B' success(216자), child steps 4 / retrieval 2 / llm 1 / guardrail 2, **llm_calls.model=gpt-4o-mini**(model_spec 반영 확인).
- **/metrics**: `chat_requests_total{variant="A"}=1`, `{variant="B"}=1` 분리 집계.
- **B-exaone**: 동일 경로(model_spec=exaone) — 라우팅 검증됨, 성공 실행은 RunPod 파드 필요(A5에서 실증). 이번엔 파드 미가동으로 라이브 성공 run 생략.

→ 완료 기준 충족. 이제 스트리밍에서 A/B가 요청값으로 갈리고 라벨 분리 측정된다.

## 6. Next gate → M7-3

프론트 `ChatAPIRequest`에 `variant`/`model_spec` 추가 + 테스트 모드 셀렉터 UI(A/B-frontier/B-exaone), B-exaone 지연·파드 경고 표기.
