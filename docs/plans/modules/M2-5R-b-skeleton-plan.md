# M2-5R B 최소 골격 (계획서)

- 작성일: 2026-06-23
- 모듈: `M2-5R` B(Agentic RAG) 최소 골격 — LangGraph ReAct + retrieval tool 1개 + 게이트형 단발 clarification
- 상위 계획: `docs/plans/2026-05-18-...roadmap.md` §1.2, `docs/plans/modules/M2-3R-b-architecture-ab-harness.md`
- 성격: **계획서**(코드 없음). **pod는 EXAONE smoke 단계에서만 필요**(frontier 단계는 pod 불필요).
- 원칙: **A(MAS) 무변경.** B는 격리된 신규 모듈.

## 0. 한 줄 요약

`langgraph.create_react_agent`로 B 골격을 만든다: retrieval tool 1개(`search_consumer_disputes`, A의 `search_hybrid_rrf` 래핑) + 결정형 cosine 게이트 단발 clarification + trace 기록. **frontier 모델로 먼저 배선·검증(pod X)** 후 **EXAONE tool-calling smoke 1회(pod O)**. 엔드포인트 배선은 M2-6R.

## 1. 목표 / 비목표

### 목표
- B의 최소 동작 골격(모델 + tool 1개 + clarification 게이트 + trace)을 importable 모듈로 구현하고 CLI smoke로 검증.

### 비목표(이번 모듈 아님)
- 추가 tool(criteria/case/verify_citation/get_*/calculate_deadline) → M2-6R
- `/chat?variant=B` 엔드포인트 배선, 서버 e2e → M2-6R
- A(MAS) 변경, DB 저장(M3), A/B 정량 비교 런(M2-7R)

## 2. 결정사항 (토론 확정, 2026-06-23)

| 항목 | 결정 |
| --- | --- |
| 모델 순서 | **frontier 먼저**(`ChatOpenAI`, pod 불필요) 배선·검증 → **EXAONE smoke 1회**(pod, vLLM tool-calling). base_url만 바꿔 전환(model-agnostic) |
| 하니스 | `langgraph.prebuilt.create_react_agent` (deps에 langgraph 1.0.1 존재, 현재 미사용=greenfield) |
| 첫 tool | `search_consumer_disputes(query, top_k)` — A core retriever와 **동일** `search_hybrid_rrf`(필터없음) 래핑 → A/B parity. 반환: 청크 리스트 + `max_cosine` |
| clarification | **결정형 cosine 게이트**: 첫 retrieval `max_cosine < τ`면 `request_clarification` **1회**, 루프 없음. τ 초기값 데이터 기반(관측 relevant cosine ≈ 0.58~0.76 → τ≈0.45~0.50 후보, smoke로 조정) |
| 통합 깊이 | **B 모듈 + CLI smoke**. 엔드포인트는 M2-6R |
| 측정 | tool 호출(name/args/result)·clarification 발동·최종답변을 trace로 기록 → trace 완전성/clarification_rate 근거 |

## 3. 파일 범위 (예상)

### In scope
- `backend/app/variant_b/__init__.py`
- `backend/app/variant_b/tools.py` — `search_consumer_disputes`(psycopg2로 `search_hybrid_rrf` 호출, max_cosine 반환)
- `backend/app/variant_b/model.py` — model factory(`ChatOpenAI` frontier 기본 / base_url=EXAONE vLLM 전환)
- `backend/app/variant_b/agent.py` — `create_react_agent` + 결정형 cosine clarification 게이트 + trace 수집
- `backend/scripts/testing/variant_b/smoke_b.py` — CLI smoke(명확질의/모호질의 2케이스)
- (선택) `docs/plans/modules/M2-5R-b-skeleton-results.md` — 결과 문서

### Out of scope
A 변경, 엔드포인트 배선, 추가 tool, DB 저장.

## 4. 환경

- B는 eval용 최소 venv보다 무겁다: **langgraph + langchain-openai** 필요. 시스템 python 3.14에서 핀고정 충돌 위험 → **py3.11/3.12 별도 venv** 권장(예: `~/.venvs/ddoksori-b`).
- DB: 로컬 pgvector(localhost:5432/ddoksori) — tool이 검색에 사용.
- **EXAONE smoke 시 pod 필요**: H100 Resume + tool-calling 플래그로 재기동 `vllm serve ... --enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser deepseek_r1` (그 외 M2-2 검증 config 동일). smoke 후 **Stop**.

## 5. 작업 순서

1. py3.11/3.12 venv + langgraph·langchain-openai·psycopg2-binary 설치.
2. `search_consumer_disputes` tool 구현(검색 + max_cosine).
3. model factory(frontier 기본, EXAONE base_url 옵션).
4. ReAct agent + 결정형 cosine 게이트(단발) + trace 수집.
5. **frontier CLI smoke**(pod 불필요): (a) 명확 질의 → tool 호출 → 근거기반 답변, (b) 모호 질의 → max_cosine<τ → clarification 1회(루프 없음) 확인.
6. **EXAONE smoke 1회**(pod): 사용자에게 H100 Resume 요청 → tool-calling 플래그 재기동 → 동일 smoke로 tool-calling 동작 확인(bounded) → Stop 안내.
7. 결과 문서화.

## 6. 완료 기준 / 검증

- frontier B: 질의 → `search_consumer_disputes` 호출 → 검색 근거 기반 답변 생성, **trace에 tool input/output 기록**.
- 모호 질의에서 **cosine 게이트가 단발 clarification 발동(루프 없음)**.
- **EXAONE smoke 1회 통과**(vLLM tool-calling 동작 확인).
- **A 무변경** 확인(B는 별도 모듈, MAS 코드 diff 0).

## 7. pod 안내

- 1~5단계(frontier 배선·검증)는 **pod 불필요**.
- **6단계(EXAONE smoke)에서만 pod 필요** → 그 시점에 H100 Resume 요청, smoke 후 즉시 Stop(과금 정지).

## 8. 리스크

- py3.14 의존성 충돌 → py3.11/3.12 venv로 회피.
- EXAONE tool-calling 파서(hermes) 안정성 — frontier에서 먼저 검증해 B 로직 버그와 분리.
- τ 튜닝(과잉/과소 clarification) → smoke로 조정, M2-7R에서 clarification_rate로 측정.
- vLLM 재기동 시간/비용 → smoke bounded.

## 9. Next gate

M2-6R: 나머지 retrieval tool(criteria/case) + verify_citation + get_law_article/get_case_detail + guardrail pre/post + `/chat?variant=B` 엔드포인트 배선.
