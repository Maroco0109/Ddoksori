# M3-9 protocol event 저장 (결과 문서)

- 작성일: 2026-06-24
- 모듈: `M3-9` protocol event 저장 (A inter-agent 소통 + B ReAct 궤적)
- 계획서: `docs/plans/modules/M3-9-protocol-events-plan.md`
- 상위 계획: §M3 (M3-8 이후 확장)
- 성격: 코드 구현 + 라이브 검증. A 무변경(read-only), B는 메시지 궤적 distill만 추가.
- 동기: M3 검토의 **목표 1(에이전트 소통/e2e 디버깅) 미달** 보완.

## 0. 한 줄 결론

`010_protocol_events.sql`을 적용하고 동기 `/chat`이 run의 **내부 의사결정 궤적**을 `protocol_events`로 best-effort 저장하게 했다. **A는 supervisor 라우팅/노드 protocol_summary**(read-only), **B는 ReAct 메시지 궤적**(AIMessage 추론+tool_calls, ToolMessage 관찰)을 distill해 기록. 실제 `/chat`으로 "Query가 어떤 판단을 거쳐 Answer가 됐나"를 A·B 양쪽에서 조회 검증했다.

## 1. 구현 내용

| 파일 | 변경 |
| --- | --- |
| `backend/app/database/migrations/010_protocol_events.sql` | 신규 (FK→workflow_runs CASCADE, UNIQUE(run_id,seq), kind CHECK) |
| `backend/app/observability/protocol_events.py` | 신규 (`ProtocolEventDB` batch + best-effort + `build_a`/`build_b`) |
| `backend/app/variant_b/agent.py` | `result["messages"]` distill → `protocol_messages` 반환 (B만, content 500자 절단) |
| `backend/app/api/chat.py` | A: `_agent_trace_entries`로 events. B: `protocol_messages`로 events. |
| `backend/app/observability/query.py` | `get_run_detail`에 `protocol_events` 포함(계획 §6 "선택" → **포함**으로 격상, 개선#1) |

## 2. 라이브 검증 결과 (5432 DB, RunPod EXAONE up)

### A run — inter-agent 라우팅 궤적 (16 node, read-only)
```
seq | node             | summary(요약)
 2  | supervisor       | next_agent=query_analyst,  phase=analyzing
 3  | query_analysis   | intent=information_search, retriever_types=[law,criteria,case,counsel]
 4  | supervisor       | next_agent=retrieval_team, phase=retrieving
 5  | retrieval_law    | doc_count=10, max_sim=0.064
 7  | retrieval_case   | doc_count=10, max_sim=0.650
 9  | supervisor       | next_agent=answer_drafter, phase=drafting
10  | generation       | answer_length=936, cited_case_count=3
11  | supervisor       | next_agent=legal_reviewer, phase=reviewing
```
→ "**어떤 에이전트가 무슨 판단으로 다음으로 넘겼나**"가 supervisor의 `next_agent`/`phase`/`iteration_count`로 조회됨.

### B run — ReAct 궤적 (ai/tool 교차)
```
seq | kind | name                     | content/summary
 0  | ai   |                          | tool_call: search_consumer_disputes(query="중고 휴대폰 환불", domain=law)
 1  | tool | search_consumer_disputes | 관찰: "제9조(청약철회등의 효과) ..."
 2  | ai   |                          | tool_call: search_consumer_disputes(query="중고 휴대폰 환불 사례", domain=case)
 3  | tool | search_consumer_disputes | 관찰: "중고로 구입한 휴대폰 하자 환급 ..."
 4  | ai   |                          | 최종답변: "중고로 구입한 휴대폰이 일주일 만에 ..."
```
→ "**모델이 무슨 근거로 어떤 도구를 어떤 인자로 불렀고, 도구가 뭘 돌려줬나**"가 보임. 모델이 law→case로 **쿼리를 재작성**한 agentic 행동까지 확인.

### 집계 / 조회 API / best-effort
```
variant | kind | n      detail keys: run, workflow_steps, retrieval_events,
 A      | node | 16             llm_calls, guardrail_events, protocol_events  ← 포함
 B      | ai   |  3      protocol_events rows in detail: 16
 B      | tool |  2
```

| 검증 항목 | 결과 |
| --- | --- |
| migration 010 (FK CASCADE/UNIQUE/CHECK/인덱스) | ✅ `\d protocol_events` |
| A run → inter-agent 라우팅/판단 조회 | ✅ 16 node, supervisor next_agent/phase |
| B run → ReAct 궤적(ai/tool, 도구 인자/관찰) 조회 | ✅ 쿼리 재작성까지 |
| `get_run_detail`에 protocol_events 포함 (개선#1) | ✅ e2e 한 응답 |
| best-effort 비차단 (테이블 제거 후 `/chat`) | ✅ HTTP 200 |
| A 로직 diff 0 (read-only; B는 distill만) | ✅ |

## 3. caveat / 발견

- A `protocol_events`는 `workflow_steps`와 노드 겹침(설계대로) — steps=timing/category, protocol=판단 content로 관심사 분리(seq 정렬 동일, join 가능).
- supervisor `reasoning_preview`가 빈 문자열로 옴(현 구성). next_agent/phase/iteration은 확실. reasoning 본문이 필요하면 A가 노출해야(후속).
- B `ai` 최종답변 행의 content는 답변 **preview(절단)** — 전체 답변 본문 영속화는 M5-1(평가 선결).

## 4. 목표 1 충족 + 다음

M3-9로 **목표 1(에이전트 소통/e2e 디버깅)** 충족: A inter-agent 라우팅 + B ReAct 궤적을 `/observability/runs/{id}` 또는 SQL로 추적 가능. M3 관측 백본은 6개 테이블(run/step/retrieval/llm/guardrail/protocol) + 조회 API로 완성.

다음(우선순위): **M5(품질 평가)** — M5-1 답변 본문 영속화 → human goldenset → LLM-judge. 이후 M6(모니터링).
