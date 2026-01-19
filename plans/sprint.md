# Sprint Plan (ReAct MAS, Generator 단일 출력, NO_RETRIEVAL Fast Path)

> 핵심 근거(설계 전제):
>
> * ReAct 에이전트는 툴 호출/관찰을 반복하다가 최종 답을 내는 루프 구조 ([LangChain Docs][1])
> * LangGraph는 workflow(고정 경로) vs agent(동적/자율 툴 사용) 패턴을 구분 ([LangChain Docs][2])
> * Retriever는 “string query → Document list” 인터페이스 ([LangChain Docs][3])
> * AgentExecutor는 실행 루프 제한(max_iterations 등)을 제공(무한 루프 방지) ([LangChain Docs][4])
> * OpenAI Moderation endpoint는 유해성 분류(무료) + omni-moderation-latest 모델 ([OpenAI 플랫폼][5])
> * OpenAI Moderation endpoint는 유해성 분류(무료) + omni-moderation-latest 모델 ([OpenAI 플랫폼][5])
> * LLM: `GPT-4o-mini` (최종 답변 생성 및 구조화)
> * Embeddings: `nlpai-lab/KURE-v1` (Dense, 1024d) + `BAAI/bge-m3` (Sparse)

---

## Sprint 0 (1주) — 계약(Contract) 고정 + 루프/정책 설계

### 목표

* “행복 경로(선형)” + “ReAct 루프(예외/되돌림)”를 **스키마/정책**으로 고정

### 작업

* **Agent I/O 스키마 확정(JSON)**

  * `QueryAnalysisResult{ mode, draft, uncertainties[], need_evidence, required_slots[], filters_candidate, sql_params_candidate }`
  * `SearchPlan{ retrievers[], top_k, rerank, rounds_budget, time_budget }`
  * `RetrievalReport{ relevance, coverage(required_slots->status), diversity, marginal_gain }`
  * `GenerationOutput{ final_answer, claim_evidence_map, assumptions, citations }`
  * `ReviewReport{ pass/fail, issues[], required_more_evidence?, requested_slots? }`
* **Orchestrator 라우팅 정책 확정**

  * `NO_RETRIEVAL → Generator(최종) → (출력 Guardrail) → User`
  * `NEED_RAG → Retriever → Sufficiency → Generator → Reviewer → (필요 시 루프)`
  * `NEED_USER_CLARIFICATION → Generator가 질문 생성 → User → QueryAnalysis 재진입`
* **에이전트 루프 제한/예산**

  * Orchestrator와 각 에이전트에 `max_iterations`, `max_execution_time` 적용 ([LangChain Docs][4])
* **Fast Path 승격 규칙(강제 NEED_RAG)**

  * 법/분쟁 고위험 키워드/행동 권유/기간·권리 판단 요청 시 `NO_RETRIEVAL`이라도 승격

### 산출물

* `/docs/contracts/*.md` (스키마 + 예시 payload)
* `/docs/policies/routing.md` (승격 규칙 포함)
* `/docs/policies/loop_limits.md` (max_iterations/time budget)

### DoD

* 모든 에이전트 출력이 스키마로 검증됨(JSON schema validation)

---

## Sprint 1 (1주) — Guardrail + Query Analysis v1 (구조화만)

### 목표

* Query Analysis가 **답변 생성 금지**(draft/불확실/근거 필요 여부만)로 안정 동작

### 작업

* **입력/출력 Guardrail**

  * OpenAI Moderation endpoint 연결(입력/출력 모두) ([OpenAI 플랫폼][5])
  * 모델: `omni-moderation-latest` 적용 ([OpenAI 플랫폼][7])
* **Query Analysis v1**

  * `mode` 분류: `NO_RETRIEVAL / NEED_RAG / NEED_USER_CLARIFICATION`
  * `draft`, `uncertainties[]`, `need_evidence`, `required_slots[]` 생성
  * JSON schema 강제(모델 프롬프트/출력 파서)

### 산출물

* `/agents/query_analysis/*`
* `/guardrail/*` (moderation wrapper + 정책 룰셋)
* 단위 테스트(모드 분류/스키마 준수)

### DoD

* 샘플 50건에서 QueryAnalysis 스키마 준수율 99%+
* moderation 실패/차단 시 fallback 메시지 정책 확정 ([OpenAI 플랫폼][5])

---

## Sprint 2 (2주) — Orchestrator v1 (Control Plane) + LangGraph 상태/루프

### 목표

* ReAct MAS의 “실제 루프”를 Orchestrator가 통제(단일 제어 평면)

### 작업

* **LangGraph 상태 모델**

  * 세션 상태: `mode`, `required_slots`, `search_round`, `budget_remaining`, `retrieval_report_history`
  * workflow(행복 경로) + agent loop(예외/되돌림) 구조화 ([LangChain Docs][2])
* **Orchestrator 라우팅 구현**

  * `NO_RETRIEVAL`이면 Retriever/Reviewer 스킵 후 Generator 호출
  * `NEED_RAG`이면 SearchPlan 컴파일 후 Retriever 호출
  * `NEED_USER_CLARIFICATION`이면 Generator로 “추가 질문” 생성 후 종료
* **채팅 모드 이원화 (Dual Chat Modes)**

  * `ChatRequest.chat_type == 'general'` (비회원): `Simple Graph` (Retrieval → Generation → END) 실행
  * `ChatRequest.chat_type == 'dispute'` (회원/상담): 기존 `ReAct Graph` (QueryAnalysis → ... → Review) 실행
* **루프 제한 적용**

  * Orchestrator/에이전트 max_iterations/time budget 적용 ([LangChain Docs][4])

### 산출물

* `/orchestrator/*` (routing + budgeting + loop control)
* `/graphs/*` (LangGraph 정의)
* 통합 테스트: 3경로(NO_RETRIEVAL/NEED_RAG/NEED_USER_CLARIFICATION)

### DoD

* 무한 루프 없이 종료(max_iterations/time budget 준수) ([LangChain Docs][4])
* 라우팅 로그(결정 근거 포함) 남음

---

## Sprint 3 (2주) — Retriever v1 (RAG + RDB) + RetrievalReport

### 목표

* Retriever는 “실행기”로 유지(LLM 비필수), 대신 Orchestrator가 판단할 리포트 제공

### 작업

* **Retriever 인터페이스 구현**

  * 입력: string query(+필터/파라미터), 출력: `Documents[]` ([LangChain Docs][3])
* **임베딩 구성**

  * Dense: `nlpai-lab/KURE-v1` (1024d) - 한국어 법률/행정 도메인 특화
  * Sparse: `BAAI/bge-m3` - 다국어/한국어 지원 및 Learned Sparse Embeddings
* **RetrievalReport 생성**

  * relevance score 요약
  * coverage(required_slots 상태)
  * diversity(출처/문서군)
  * marginal_gain(라운드 증분)
* **RDB 조회 모듈**

  * QueryAnalysis가 준 `sql_params_candidate`를 바인딩(템플릿/파라미터화)

### 산출물

* `/retriever/*`, `/db/*`
* RetrievalReport 샘플 로그 + 리플레이 테스트

### DoD

* “쿼리→문서 반환” 성능/정확도 기본선 확보 ([LangChain Docs][3])
* RetrievalReport가 Orchestrator의 stop/ask-user 분기를 재현 가능

---

## Sprint 4 (2주) — Generator v1 (최종 출력 단일화) + Fast Path 최적화

### 목표

* 모든 사용자 메시지는 Generator가 생성(일반/근거 답변 통일)

### 작업

* **Generator 출력 2채널**

  * `final_answer`(사용자용)
  * `claim_evidence_map`(Reviewer용)
  * (참고) `Simple Graph`(일반 채팅)에서는 `final_answer`만 즉시 반환 (상태 저장/검토 없음)
* **NO_RETRIEVAL Fast Path**

  * Orchestrator가 Retriever/Reviewer 스킵
  * 출력 Guardrail(Moderation)만 통과 ([OpenAI 플랫폼][5])
* **NEED_RAG 답변**

  * 근거 기반 요약 + 불확실 시 조건부 안내(단정 금지)
  * 모델: `GPT-4o-mini` 사용 (비용 효율성 및 한국어 성능 우수)

### 산출물

* `/generator/*`
* E2E 테스트(“fast path 지연 최소화” 포함)

### DoD

* NO_RETRIEVAL 응답 지연/비용 목표치 달성
* NEED_RAG 답변에 claim→evidence 매핑 포함(Reviewer 비용 절감)

---

## Sprint 5 (2주) — Reviewer v1 (NEED_RAG 전용) + Sufficiency 튜닝/평가

### 목표

* 환각/근거 부족/법적 단정 리스크를 Reviewer가 잡고, Orchestrator가 루프를 통제

### 작업

* **Reviewer v1 (NEED_RAG only)**

  * 근거 누락/불일치/단정 표현/정책 위반 체크
  * 추가 근거 필요 시 “요구 슬롯/근거 타입”만 ReviewReport로 반환(실행은 Orchestrator)
* **Sufficiency(Stopping) 스코어 튜닝**

  * coverage/diversity/marginal_gain 기반 stop/continue/ask-user 규칙 고도화
* **평가/관측**

  * KPI: 추가질문율, 재검색 라운드 평균, 근거 누락 차단율, 평균 지연/비용
  * 리플레이 평가셋 구축(라벨: 충분/불충분/추가질문 필요)

### 산출물

* `/reviewer/*`
* `/eval/*` (리플레이 + 리포트)
* 운영 런북(`/docs/runbook.md`)

### DoD

* NEED_RAG에서 “근거 없는 단정” 차단률 목표 달성
* Reviewer 요구사항이 Orchestrator 루프와 충돌 없이 동작

---

## 모델 배치 (구현 체크리스트에 포함)

* Guardrail: OpenAI Moderation + `omni-moderation-latest` ([OpenAI 플랫폼][5])
* LLM: `GPT-4o-mini`
* Dense Embedding: `nlpai-lab/KURE-v1` (1024d)
* Sparse Embedding: `BAAI/bge-m3`
* ReAct 루프/제어: AgentExecutor의 max_iterations/time budget 적용 ([LangChain Docs][4])
* Retriever 계약: string query → Documents 반환 준수 ([LangChain Docs][3])

[1]: https://docs.langchain.com/oss/javascript/langchain/agents?utm_source=chatgpt.com "Agents - Docs by LangChain"
[2]: https://docs.langchain.com/oss/python/langgraph/workflows-agents?utm_source=chatgpt.com "Workflows and agents - Docs by LangChain"
[3]: https://docs.langchain.com/oss/python/integrations/retrievers?utm_source=chatgpt.com "Retrievers - Docs by LangChain"
[4]: https://reference.langchain.com/v0.3/python/langchain/agents/langchain.agents.agent.AgentExecutor.html?utm_source=chatgpt.com "AgentExecutor — 🦜🔗 LangChain documentation"
[5]: https://platform.openai.com/docs/guides/moderation?utm_source=chatgpt.com "Moderation | OpenAI API"
[6]: https://platform.openai.com/docs/guides/embeddings?utm_source=chatgpt.com "Vector embeddings | OpenAI API"
[7]: https://platform.openai.com/docs/models/omni-moderation-latest?utm_source=chatgpt.com "omni-moderation Model | OpenAI API"
