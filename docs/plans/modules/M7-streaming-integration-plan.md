# M7 제품 경로 통합 — 스트리밍 계측 파리티 + variant 라우팅 (개요 계획)

- 작성일: 2026-07-05 (M4-A 완료·v1.0.0 릴리스 후)
- 상위: 로드맵 §M7 (`docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`)
- 성격: **개요/방향 확정.** 세부 구현 계획은 서브모듈(M7-1 등)에서 한 번에 하나씩.

## 0. 한 줄 요약

측정 스택(M3/M4-A/M5/M6)은 비스트리밍 `/chat`에 있는데 프론트 실사용 경로는 `/chat/stream`이라 **실사용이 측정되지 않는다.** M7은 스트리밍 경로에 계측 파리티를 부여하고(우선), 세 variant(A / B-frontier / B-exaone)를 프론트에서 선택·테스트 가능하게 만든다. mainline 확정은 그 위에서 데이터로 후속 결정한다.

## 1. 배경 (코드 확인 근거)

- `save_workflow_run`/`record_chat_request`/`save_guardrail_events` 호출부는 전부 **비스트리밍 `/chat`**(A: `chat.py` ~395–527, B: ~113–198)에만 존재.
- 프론트가 실제 쓰는 **`/chat/stream`**(`chat.py` 555–946)에는 위 계측이 **하나도 없음**(대화 메모리 저장만). 또한 `get_graph_for_chat_type`로 **A(MAS) 전용** — variant B 분기 없음.
- 프론트 `ChatAPIRequest`(`frontend/src/shared/types/chat.types.ts`)에 `variant` 필드 없음 → 프론트에서 A/B 선택 불가.
- 결론: **실사용 트래픽이 M3/M6에 안 잡히고**, A/B 비교가 제품 경로에서 불가능하다.

## 2. 측정 근거 (variant 선택의 데이터)

| | A (MAS) | B-frontier (gpt-4o-mini) | B-exaone (EXAONE 4.5-33B) |
| --- | --- | --- | --- |
| faithfulness(M5) | 2.00(최고) | 1.92 | 1.89 |
| safety(M5) | 1.00(최고) | 0.83 | 0.78 |
| coverage(M5) | 0.575 | 0.551 | 0.757(최고) |
| error_rate(M5) | 0.167※ | 0.00(최고) | 0.25 |
| latency median(M5) | 10.2s | 6.4s(최고) | 84s(제품 부적합) |
| 보안 decided(M4-A) | 100% | 96% | 96.2% |
| leak_rate(M4-A) | 0% | 0% | 0% |
| 스트리밍 | 있음(현 mainline) | 없음 | 없음 |

※ A error_rate는 #67 픽스 이전 측정. 근거: `docs/plans/modules/M5-5-*`, `M4-A5-*`, `docs/report/2026-07-05-reasoning-vs-nonreasoning-exaone.md`.

→ mainline은 데이터상 A가 유력(안전/보안/충실성·이미 스트리밍)하나, **본 M7의 목표는 mainline 확정이 아니라 "세 variant를 측정되는 제품 경로에서 검증 가능하게" 만드는 것**. 확정은 후속.

## 3. 결정 (2026-07-05 토론)

1. **모듈 분할 M7-1~4 확정**, M7-1(계측 파리티) 최우선.
2. **LangSmith = 보완 포지션** — 자체 스택(M3 Postgres + M6 Prometheus/Grafana)을 canonical로 유지, LangSmith는 개발 트레이싱·eval/annotation 가속기로만. LangChain/LangGraph는 env 설정으로 저비용 리치 트레이싱.
3. 세 variant(A/B-frontier/B-exaone) **모두 프론트 연결해 테스트** — mainline 후속 결정.

## 4. 서브모듈 (로드맵 §M7)

| 서브 | 목표 | 핵심 |
| --- | --- | --- |
| **M7-1** | 스트리밍 계측 파리티 | `/chat/stream`에 `save_workflow_run`+M6 `record_*`+`guardrail_events`를 A 경로와 동일 부여. 기존 계측 **재사용**(신규 최소) |
| **M7-2** | variant 라우팅 통합 | 스트리밍을 per-request 3택 라우팅. `VARIANT_B_MODEL_SPEC` env 토글 → **요청 파라미터**로. B(ReAct)에 status SSE |
| **M7-3** | 프론트 variant 셀렉터 | `ChatAPIRequest.variant` 추가 + 테스트 모드 UI. B-exaone 지연/파드 경고 |
| **M7-4** | LangSmith 리치 트레이싱 | variant/session 태그 표준화, (선택) dataset/eval. canonical=자체 스택 |

## 5. 스코프 경계 / caveat

- **측정 파리티가 핵심**: M7-1이 안 깔리면 이후 무의미(실사용 미측정). 그래서 최우선.
- **B-exaone 프론트 테스트**: 84s median·최대 226s → "느린 테스트 모드"로 명시, RunPod 파드 가동 시에만(비용). SSE heartbeat(15s)로 연결 유지.
- **per-request 모델 선택**: 현재 env(`VARIANT_B_MODEL_SPEC`) 방식은 서버 재시작 필요 → 프론트 선택 위해 요청 파라미터화 필요(M7-2).
- **mainline 미확정**: 본 계획은 mainline을 고르지 않는다. M7 인프라 위 데이터로 후속 결정.
- **LangSmith 데이터 전송**: 외부 벤더 전송·비용 존재 → 보완 범위로 한정, 민감정보 태깅 주의.

## 6. Next gate → M7-1

`/chat/stream` 계측 파리티: 세부 구현 계획을 M7-1 계획서로 작성 후 진행(한 번에 하나씩). 완료 기준 = 스트리밍 요청 1건이 `workflow_runs`/`guardrail_events` 적재 + `/metrics`에 variant 라벨 집계.
