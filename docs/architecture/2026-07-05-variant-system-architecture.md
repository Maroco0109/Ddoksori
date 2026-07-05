# DDOKSORI 변형(Variant) 시스템 아키텍처 — A / A-hub / B-frontier / B-exaone

- 작성일: 2026-07-05
- 성격: **시스템 아키텍처 정리 + 변형 비교의 단일 출처(single source).** 각 변형의 구조·의사결정 메커니즘·모델·측정 결과를 한 문서로 통합한다.
- 관련: [A 결정 기록](2026-07-05-a-orchestration-decision.md), [M8 라우팅 측정](../plans/modules/M8-a-hub-routing-results.md), [M7 mainline 프레임워크](../plans/modules/M7-mainline-decision-framework.md), [LLM 클라이언트 레이어](../../backend/app/llm/README.md)

---

## 0. 이 프로젝트가 측정하는 것

DDOKSORI의 목표는 "답변 잘하는 챗봇" 하나를 만드는 것이 아니라, **서로 다른 아키텍처의 챗봇을 동일 조건에서 측정·비교하는 시스템**을 갖추는 것이다. 그래서 하나의 백엔드가 여러 **변형(variant)** 을 실행할 수 있고, 각 요청은 variant 라벨과 함께 DB(`workflow_runs`/`llm_calls`/`protocol_events`…)와 Prometheus에 적재되어 SQL·대시보드로 A/B 비교가 가능하다.

핵심 대비는 **아키텍처 패러다임**이다 — Anthropic *"Building Effective Agents"* 의 구분과 정확히 일치한다:

- **Workflow (결정론적 조율)**: 코드가 정해진 단계를 실행. → variant **A**
- **Autonomous Agent (LLM 자율 판단)**: LLM이 tool-calling으로 다음 행동을 결정. → variant **B**
- **A-hub**: A의 구조에 "LLM이 라우팅"만 얹은 중간형(측정 전용) — workflow vs agent 경계를 정량화하기 위한 대조군.

---

## 1. 네 변형 한눈에

| 변형 | 한 줄 정의 | 의사결정 | LLM tool-calling | 라우팅 모델 | 답변 모델 | 상태 |
| --- | --- | --- | --- | --- | --- | --- |
| **A** | MAS Hub-Spoke **고정 파이프라인** (결정론적 orchestration) | 규칙 기반 | ❌ 없음 | 없음(규칙) | gpt-4o | **프로덕션 기본(동결)** |
| **A-hub** | A와 동일 그래프 + **LLM 슈퍼바이저 라우팅** | LLM이 다음 에이전트 선택 | ❌ (라우팅만 LLM) | gpt-4o | gpt-4o | 측정 전용(M8) |
| **B-frontier** | **ReAct 자율 에이전트** (프론티어 모델) | LLM 자율 (tool-calling) | ✅ | — | gpt-4o-mini | opt-in 비교 |
| **B-exaone** | ReAct 자율 에이전트 (**자체 호스팅 오픈모델**) | LLM 자율 (tool-calling) | ✅ | — | EXAONE 4.5-33B (RunPod H100) | 연구/비교 전용 |

> A와 A-hub는 **같은 LangGraph 그래프**를 공유한다. 차이는 슈퍼바이저의 라우팅 방식뿐(`routing_mode`). B-frontier와 B-exaone은 **같은 ReAct 에이전트**를 공유한다. 차이는 chat model 객체뿐(`model_spec`). 즉 변형은 두 축(구조 A vs B, 모델/라우팅)으로 구성된다.

라우팅/모델 선택 지점:
- variant/model_spec: 요청 body(`variant`, `model_spec`) 또는 백엔드 env(`VARIANT_B_MODEL_SPEC`, `SUPERVISOR_LLM_ENABLED`).
- 코드: A/A-hub = `backend/app/supervisor/`(`nodes/supervisor.py`의 `decide_next_action` 분기), B = `backend/app/variant_b/`(`agent.py` + `model.py`).

---

## 2. Variant A — 결정론적 MAS (workflow)

**구조**: Hub-Spoke LangGraph. 중앙 Supervisor(hub)가 전문 에이전트(spoke)를 조율한다.

```
Entry → cache_check ─HIT→ cache_response → END
              │MISS
              v
        input_guardrail ─BLOCK→ END
              │PASS
              v
         Supervisor ⇄ query_analysis
              │  (Fan-out)
        ┌─────┼─────┐
        v     v     v
      law  criteria case   → retrieval_merge → Supervisor
              │
              v
         generation → Supervisor
              │
              v
          review → Supervisor ─(retry≤1)→ generation
              │PASS
              v
      output_guardrail → memory_save → END
```

**의사결정 = 규칙 기반(결정론).** Supervisor는 LLM으로 라우팅하지 **않는다**. `decide_next_action`이 `mode`(query_analysis가 도출)와 완료 태스크에 따라 다음 노드를 고정 규칙으로 정한다. LLM은 오직 두 곳 — query_analysis(조건부 의도분류/쿼리확장)와 generation(답변 작성) — 에서 tool 없는 prompt→text로만 쓰인다. review는 전부 정규식/규칙. 검색은 `UnifiedRetriever`(SQL 하이브리드 RRF)를 코드가 무조건 호출한다.

**"MAS인데 왜 결정론인가":** 원래 LLM 슈퍼바이저로 설계됐으나(2026-01-26) 지연 최적화(2026-01-27) 과정에서 결정론 라우팅으로 동결됐고, LLM 라우팅 코드는 dead code로 남았다. 이 결정의 정당성은 §5(M8)로 실측 검증됐다. 상세: [A 결정 기록](2026-07-05-a-orchestration-decision.md).

**모델**: `MODEL_SUPERVISOR`/`MODEL_DRAFT_AGENT`/`MODEL_REVIEW_AGENT` = gpt-4o(기본), fallback 체인(gpt-4o → gpt-4o-mini → claude → rule_based → safe_fallback).

---

## 3. Variant A-hub — LLM 슈퍼바이저 라우팅 (측정 전용)

**구조**: A와 **완전히 동일한 그래프**. 차이는 Supervisor가 다음 에이전트를 **LLM으로 선택**한다는 것(`routing_mode="llm"`). dead code였던 `_try_llm_decision`/`_build_decision_prompt`를 부활시켜 만든 측정 변형이다.

- 매 라우팅마다: 결정론 결정을 함께 계산해 (1) LLM 결정과의 **일치율**을 측정하고 (2) LLM 실패 시 폴백에 사용.
- 계측(`_routing_meta`)은 supervisor 노드의 `protocol_summary`→`protocol_events`로 적재.
- 활성 조건: `SUPERVISOR_LLM_ENABLED=true` + `SUPERVISOR_LLM_MODEL`(기본 gpt-4o). A는 `routing_mode` 미지정이므로 이 플래그가 켜져도 영향 없음(동결 유지).

**목적**: "선형 파이프라인에서 LLM 라우팅이 이득이 있는가"를 격리 측정. 결과는 §5.

---

## 4. Variant B — ReAct 자율 에이전트 (agent)

**구조**: 단일 LLM + 도구. `backend/app/variant_b/agent.py`의 `run_b`:

```
input_guardrail ─BLOCK→ fallback
      │PASS
      v
gate_retrieval (결정론 cosine 게이트, A와 동일 primitive)
      │ max_cosine < τ(0.45) → 단발성 clarification 질문, 종료
      │ else
      v
ReAct agent = create_react_agent(chat_model, B_TOOLS)
      │  LLM이 tool 호출을 자율 결정
      v
output_guardrail ─BLOCK→ fallback → 최종 답변
```

**의사결정 = LLM 자율(진짜 agentic).** `create_react_agent`가 LLM에게 도구를 바인딩하고, LLM이 어떤 도구를 언제 호출할지 스스로 정한다.

**B_TOOLS** (`variant_b/tools.py`):
- `search_consumer_disputes(query, domain, top_k)` — 하이브리드 검색(law/criteria/case/all)
- `get_law_article(law_name, article_number)` — 조문 원문
- `get_case_detail(identifier)` — 사례 상세
- `verify_citation(reference)` — 인용의 실제 존재 검증(환각 방지)

**입출력 가드레일·게이트 검색은 A와 동일 primitive를 재사용**해 "구조 차이"만 순수 비교되도록 했다.

### 4.1 B-frontier vs B-exaone — 모델만 다르다

동일한 ReAct 에이전트가 chat model 객체만 바꿔 돈다(`variant_b/model.py`, `model_spec`):

| | B-frontier | B-exaone |
| --- | --- | --- |
| 모델 | gpt-4o-mini (`VARIANT_B_FRONTIER_MODEL`) | EXAONE 4.5-33B (`EXAONE_MODEL`) |
| 호스팅 | OpenAI API | 자체 RunPod H100 + vLLM (OpenAI 호환) |
| 활성 조건 | 기본 | `EXAONE_RUNPOD_URL` 필요(파드 기동) |
| 특성 | 저비용·빠름·견고 | 자체호스팅·느림(≈84s)·불안정 |
| 특이사항 | — | ReAct 누적 컨텍스트가 `max_model_len`(8192) 초과 시 답변이 빈 채로 옴 → gate 근거로 1회 재합성 폴백(#68) |
| 위치 | opt-in 비교 variant | 연구/비교 전용(프로덕션 mainline 제외) |

LLM 클라이언트 레이어 상세: [backend/app/llm/README.md](../../backend/app/llm/README.md).

---

## 5. 측정 결과 (핵심 비교)

동일 백엔드·동일 goldenset에서 variant 라벨로 적재해 비교한 실측치. 출처: M5-5(품질), M4-A5(보안), M8(라우팅).

### 5.1 답변 품질 · 지연 · 보안

| 지표 | A (결정론 MAS) | B-frontier (ReAct) | B-exaone (ReAct) | 출처 |
| --- | --- | --- | --- | --- |
| faithfulness | **2.00** | 1.92 | — | M5-5 |
| coverage | 0.575 | 0.551 | — | M5-5 |
| safety pass | **1.00** | 0.83 | — | M5-5 |
| 보안 decided | **100%** | 96% | 96.2% | M4-A5 |
| leak_rate | 0% | 0% | 0% | M4-A5 |
| latency median | 10.2s | **6.4s** | ≈84s | M5-5 / 운영 |
| 자율성/유연성 | 낮음(고정) | **높음** | **높음** | 구조 |

**해석**: A(workflow)는 도메인 핵심 축(충실성·안전·보안)에서 최고, B-frontier(agent)는 속도·유연성 우위·품질 근접·안전 소폭 열위. B-exaone은 자체호스팅 실험(지연·불안정)으로 프로덕션 mainline에서 제외. 보안 격차는 **모델이 아니라 아키텍처**(고정 파이프라인 vs 자율 에이전트) 차이임이 3-way 측정으로 규명됐다.

### 5.2 A vs A-hub — "LLM 라우팅은 이득이 있는가" (M8)

quality goldenset 12문항, A-hub 라우팅 모델 = gpt-4o(A-hub에 유리한 강모델):

| 지표 | A (결정론) | A-hub (LLM 라우팅) |
| --- | --- | --- |
| latency avg | **10.8s** | 18.9s (**+74%**) |
| 라우팅 결정 = 결정론과 일치 | — | **60/60 (100%)** |
| 요청당 추가 LLM 호출 | 0 | +5 (총 60) |
| 답변 길이(품질 프록시) | 745자 | 737자 (동등) |
| 실패 모드 | 없음 | 약모델(gpt-4o-mini) **루프→에러** |

**해석**: 선형 파이프라인에서 LLM 슈퍼바이저는 결정론 라우터를 **100% 재현**하며 지연·비용만 더한다. → A의 결정론 동결은 정당(측정으로 뒷받침). 상세/공정성 caveat: [M8 결과](../plans/modules/M8-a-hub-routing-results.md).

---

## 6. 관측(Observability) — 어떻게 variant별로 비교되나

모든 변형은 동일한 측정 백본에 적재된다:

- **DB(M3)**: `workflow_runs`(variant·latency·status·answer), `llm_calls`(모델·토큰), `retrieval_events`, `guardrail_events`, `protocol_events`(A=노드 궤적/라우팅 계측, B=ReAct 메시지 궤적). `variant` 컬럼으로 SQL 그룹 비교. (`workflow_runs.variant` ∈ {A, A-hub, B})
- **Prometheus/Grafana(M6)**: `chat_request_duration_seconds{variant}`, `chat_requests_total{status,variant}`, `llm_tokens_total{variant}` + ops/A-B/drilldown 대시보드.
- **LangSmith(M7-4)**: `variant:*` 태그로 트레이스 필터·pairwise 비교.
- **평가 러너**: `scripts/evaluation/run_answer_eval.py --variant {A|A-hub|B}`로 goldenset을 `/chat`에 흘려 적재, `judge_answer_quality.py`(품질)·`score_security_eval.py`(보안)·`m8_routing_report.py`(라우팅)로 집계.

---

## 7. 요약

- **A = workflow**(결정론 MAS), **B = agent**(ReAct tool-calling). A-hub는 그 경계를 정량화하는 대조군.
- 측정 결론: 도메인 핵심(안전·보안·충실성)은 A, 속도·유연성은 B-frontier. LLM 라우팅(A-hub)은 이 파이프라인에서 순수 오버헤드.
- 이 프로젝트의 가치는 "어느 하나가 최고"가 아니라 **아키텍처 선택을 숫자로 비교·설명할 수 있다**는 것.
- 운영 기본값은 A(동결), B-frontier는 opt-in, B-exaone·A-hub는 연구/측정용. mainline 확정은 [운영 중 결정 프레임워크](../plans/modules/M7-mainline-decision-framework.md)를 따른다.
