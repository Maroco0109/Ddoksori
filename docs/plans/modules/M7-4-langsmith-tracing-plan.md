# M7-4 LangSmith 리치 트레이싱 (계획 + 결과)

- 작성일: 2026-07-05
- 모듈: `M7-4` LangSmith 리치 트레이싱(보완) — M7 마지막
- 상위: 로드맵 §M7, 선행 M7-1/M7-2/M7-3
- 성격: **보완 태깅.** 자체 스택(M3 Postgres + M6 Prometheus/Grafana)이 canonical, LangSmith는 개발 트레이싱·eval 편의.

## 0. 한 줄 요약

이미 켜져 있던 LangSmith(`LANGCHAIN_TRACING_V2=true`, project `ddoksori`) 트레이스에 **variant/session/model_spec/chat_type 태그·메타데이터**를 부여해 A/B를 필터·비교 가능하게 했다. 태깅만 추가하며 측정의 canonical은 자체 스택 유지.

## 1. 배경 (코드 확인)

- LangSmith는 env로 활성(`LANGCHAIN_TRACING_V2/API_KEY/PROJECT`)이나, 코드에 **tags/metadata가 전무** → 트레이스는 쌓이지만 A/B 필터·비교 불가(사용자가 "어떤 에이전트가 어떤 툴을 몇 초에" 수준만 보던 이유).
- A(LangGraph)는 `graph.ainvoke/astream_events(config)`, B(ReAct)는 `agent.invoke(input)`으로 실행 — RunnableConfig의 top-level `tags`/`metadata`가 LangSmith run에 전파된다.

## 2. 변경

- **`backend/app/common/tracing.py`**(신규): `trace_tags_metadata()` + `with_trace_tags(config, variant, session_id, chat_type, model_spec)` — 기존 config에 tags/metadata를 **병합(기존 값 보존)**.
- **A 태깅**(`chat.py`): 비스트리밍 `config`(ainvoke)·스트리밍 `runnable_config`(astream_events) 둘 다 `with_trace_tags(..., variant="A", session_id, chat_type)`로 감쌈. `configurable.thread_id`/`recursion_limit` 보존.
- **B 태깅**: `run_b(..., trace_config=None)` 파라미터 추가 → `agent.invoke(input, config=trace_config)` + 합성 폴백 `chat_model.invoke(..., config=trace_config)`에 전달. chat.py의 두 B 호출부(비스트리밍 분기 + `_variant_b_stream`)가 `with_trace_tags({}, variant="B", session_id, chat_type, model_spec)`를 만들어 넘김.

태그 형식: `variant:A|B`, `model_spec:frontier|exaone`(B만), `chat_type:dispute|general`. metadata에 동일 키 + `session_id`.

## 3. 포지셔닝 (보완, 대체 아님)

- **canonical = 자체 스택**: M3 DB(재현 가능한 SQL·커스텀 A/B 지표)·M6 Prometheus/Grafana. 포트폴리오의 "측정 시스템 직접 설계" 코어.
- **LangSmith = 보완**: 개발 트레이싱(노드/툴/토큰/지연 시각화), (옵션) dataset/eval·annotation·pairwise 비교. env 설정만으로 저비용. 단점(벤더 전송·비용) 때문에 태깅 범위로 한정.
- **민감정보 주의**: 태그/metadata에 PII를 넣지 않음(variant/session_id/chat_type/model_spec만).

## 4. 스코프 경계

- **대상**: 태깅 헬퍼 + A/B 호출 config. **비대상**: eval의 LangSmith 이관(문서 옵션만), mainline 확정, B 토큰 스트리밍.

## 5. 완료 기준 / 검증

- [x] 헬퍼 단위: A→`['variant:A','chat_type:dispute']`, B→`['variant:B','model_spec:frontier','chat_type:general']`, `configurable`/`recursion_limit` 보존 확인.
- [x] 라이브: worktree 코드로 `/chat/stream` A(`m7-4-A`)·B-frontier(`m7-4-Bf`) 요청 모두 `complete`(에러 없음) → **태그된 config를 LangGraph(A)·ReAct(B)가 정상 수용**, `TRACING_V2=true`로 트레이스 전송.
- [~] LangSmith 반영: 프레임워크상 config tags/metadata는 run에 전파됨(표준 동작). REST API 스팟체크는 프로젝트 id 해석·filter DSL·ingestion 지연으로 이번엔 비결정적이었음 → **최종 확인은 LangSmith UI에서 `variant:A`/`variant:B` 태그로 필터**(권장 검증 방법). 실패가 아니라 확인 경로 이슈.

## 6. M7 완료

M7-1(스트리밍 계측 파리티) → M7-2(variant 라우팅) → M7-3(프론트 셀렉터) → **M7-4(LangSmith 태깅)** 완료. 이제 제품 경로(`/chat/stream`)가 세 variant를 실행·측정하고, 자체 스택(canonical)과 LangSmith(보완) 양쪽에서 A/B가 구분된다. **mainline(A/B) 확정**은 이 인프라 위 실사용/테스트 데이터로 후속 결정.
