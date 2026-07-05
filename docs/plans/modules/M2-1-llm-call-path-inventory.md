# M2-1 LLM 호출 경로 인벤토리 (결과 문서)

- 작성일: 2026-06-22
- 모듈: `M2-1` 현재 LLM 호출 경로 inventory (산출물)
- 상위 계획: `docs/plans/modules/M2-1-llm-call-path-inventory-plan.md`
- 성격: **read-only 조사 결과**. 런타임 코드 변경 없음. 모든 항목은 현재 `develop` 코드와 file:line 대조 완료.
- 목적: 어떤 코드가 OpenAI/Anthropic/EXAONE/embedding/moderation을 호출하는지 Capability별로 확정하고, M2-2~M2-6 전환 순서를 결정할 call map을 제공한다.

## 0. 활성 진입점 (entry point)

- `/chat`, `/chat/stream`는 `backend/app/api/chat.py:110`에서 `get_graph_for_chat_type()`로 그래프를 얻는다.
- `get_graph_for_chat_type()`(`backend/app/supervisor/graph.py:360`)는 `get_mas_supervisor_graph()`(`graph.py:375` → `backend/app/supervisor/graph_mas.py`)를 반환한다. → **운영 그래프 = MAS Supervisor graph (Phase 7 기본).**
- MAS graph는 input_guardrail → query analysis → supervisor routing → retrieval(fan-out 4종: law/criteria/case) → retrieval_merge → generation → (legal review) → output_guardrail 순으로 구성된다.
- `backend/app/orchestrator/graph_mas.py`는 어떤 활성 코드에서도 import되지 않음 → **legacy 중복본**으로 분류.

## 1. 활성 호출 경로 (active: 정상 `/chat`·`/chat/stream`)

| Runtime path | Node/Agent | Capability ID | Provider (today) | Client 생성 | Env vars | Model | Fallback | Active status | M2 action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| supervisor 라우팅 | SupervisorNode | `supervisor.routing` | OpenAI → Anthropic → rule | `AsyncOpenAI` 직접 (`supervisor/nodes/supervisor.py:68`), `AsyncAnthropic` 직접 (`:85`), 호출 `:115`; MAS LLM `ChatOpenAI` (`supervisor/graph_mas.py:72`) | `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `MODEL_SUPERVISOR`, `MODEL_SUPERVISOR_FALLBACK` | gpt-4o (+ anthropic fallback) | rule_based (`_rule_based_fallback`) | active | M2-5 (factory 경유 + 폴백 헬퍼) |
| query 분류 (LLM) | query_analysis | `analysis.query_classifier` | OpenAI | `openai.AsyncOpenAI` 직접 (`query_analysis/llm_classifier.py:166`, 호출 `:185`); 동기 `OpenAI` (`classifier.py:205`, 호출 `:237`) | `OPENAI_API_KEY`, `MODEL_QUERY_CLASSIFIER` | gpt-4o-mini | 규칙 기반(실패 시 `ambiguous` 반환, **provider 폴백 없음**) | active | M2-4 후보 (단, 폴백 보강 필요) |
| query 확장 | query_analysis | `analysis.query_expander` | OpenAI | `AsyncOpenAI` 직접 (`query_analysis/llm_expander.py:81`, 호출 `:89`; 재시도 `:297`, `:308`) | `OPENAI_API_KEY`, `MODEL_QUERY_EXPANDER` | gpt-4o-mini | 규칙 기반(법령 검색 경로에 rule fallback 존재) | active | M2-5 |
| 모호성 감지 | query_analysis | `analysis.ambiguity_detector` | EXAONE → gpt-4o-mini | `ExaoneLLMClient()` 직접 (`query_analysis/detectors.py:68-70`) | `EXAONE_RUNPOD_URL` 등, `ENABLE_AMBIGUOUS_DETECTION` | EXAONE(미가동 시 gpt-4o-mini) | EXAONE 불가 시 gpt-4o-mini, 그마저 실패 시 `False`(모호 아님) | active(조건부 트리거) | **M2-4 첫 전환 후보** (EXAONE 폴백 이미 배선) |
| 답변 생성 | answer_generation | `generation.answer` | OpenAI (sync + async stream) | `OpenAI` (`answer_generation/tools/generator.py:139`), `AsyncOpenAI` (`:141`); 호출 `:210`, `:248`, `:543`, `:1023`, 스트리밍 `:1174` | `OPENAI_API_KEY`, `MODEL_DRAFT_AGENT` | gpt-4o | stub 모드(키 없을 시 `use_llm=False`) | active (메인 추론) | M2-5 (마지막, 위험 최고) |
| 임베딩(검색) | retrieval | `embedding.openai` | OpenAI embeddings | `OpenAI` 직접 (`retrieval/tools/unified_retriever.py:354`, 호출 `:356`) | `OPENAI_API_KEY`, `EMBEDDING_MODEL` | text-embedding-3-large | 없음 | active | **M2-6에서 분리(즉시 교체 금지)** — restored DB 호환 유지 |
| moderation guardrail | guardrail | `guardrail.input/output_moderation` | OpenAI Moderation | 모듈 싱글톤 `OpenAI` (`guardrail/moderation.py:30`, 호출 `:79`); 노드 `guardrail/nodes.py:13`(input), `:47`(output) | `OPENAI_API_KEY`, `MODERATION_ENABLED`, `MODERATION_MODEL` | omni-moderation-latest | `MODERATION_ENABLED=false` 시 통과 | active | **추론 전환과 분리 유지** (M2 비대상) |

## 2. 조건부 경로 (conditional: env flag/조건부)

| Runtime path | Node/Agent | Capability ID | Provider | Client 생성 | Env/조건 | Model | Fallback | Active status | M2 action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 법률 검토(LLM) | legal_review | `review.legal` | OpenAI | `HybridLegalReviewer`(`llm_reviewer.py:182`), LLM 분기에서 `OpenAI()` 직접 (`:395`, 호출 `:420`) | `ENABLE_LLM_REVIEW`(기본 false), `MODEL_REVIEW_AGENT` | gpt-4o | 기본 rule-based 검토(`_rule_based_review:312`) | conditional (기본 OFF) | M2-5(활성화 시) |
| 분쟁 메타데이터 추출 | retrieval(case) | `retrieval.case_metadata` | EXAONE | `ExaoneLLMClient` 직접 (`retrieval/tools/specialized_retrievers.py:827-829`) | `ENABLE_DISPUTE_METADATA_EXTRACTION`(기본 true), EXAONE 가동 | EXAONE | 불가 시 추출 skip(원본 반환) | conditional (EXAONE dormant라 사실상 skip) | M2-5 |
| HyDE 생성 | retrieval | `retrieval.hyde` | OpenAI(async) | `AsyncOpenAI` 직접 (`retrieval/tools/hyde.py:94`, 호출 `:118`) | HyDE 활성 플래그 | — | 조건부 | conditional | M2-5 |

## 3. Candidate / Legacy / Test 경로

| 항목 | Capability ID | 위치 | 분류 | 비고 |
| --- | --- | --- | --- | --- |
| Provider factory | `llm.provider_factory` | `llm/providers/factory.py:63`(OpenAI), `:102`/`:116`(EXAONE), `:152`(Anthropic) | **candidate** | 정의만 존재, 활성 Agent 호출처 0건. **M2가 실제로 배선할 중심 대상** |
| EXAONE vLLM client | `llm.exaone_vllm` | `llm/exaone_client.py:149`(OpenAI 호환 client), 호출 `:173`, health `:88-115` | candidate/dormant | `EXAONE_RUNPOD_URL` 기본 None → 정상 `/chat`에서 미호출. health_check/generate 제공 |
| Tool calling client | `llm.tool_calling` | `llm/tool_calling_client.py:111`(ChatOpenAI→vLLM) | candidate | 활성 경로 미배선. M2 범위 아님 |
| 대체 임베딩 client | `embedding.openai`(alt) | `rds_retriever.py:43`, `rds_internal_retriever.py:69`, `embedding_client.py:36`, `cli_search_similar_chunks_existing_fn.py:82` | legacy/CLI | 활성 검색은 `unified_retriever` 경유. 나머지는 CLI/구버전 |
| Orchestrator supervisor LLM | — | `orchestrator/graph_mas.py:75`(ChatOpenAI) | legacy | 활성 import 없음(=§0 확인). 중복본 |

## 4. 측정 필드 권고 (M2-2/M3로 이관)

M2-4/M2-5 전환 코드가 호출마다 emit할 구조화 로그 필드(저장은 M3):

| Field | 의미 |
| --- | --- |
| `request_id` / `session_id` | LLM 호출을 chat run과 조인 |
| `node_name` | LangGraph 노드 매핑 |
| `capability_id` | M0-H vocabulary 재사용 |
| `provider` | `runpod_vllm` / `openai` / `anthropic` / `rule_based` / `moderation_openai` / `embedding_openai` |
| `model` | 모델 선택·출력 변화 비교 |
| `status` | `success` / `fallback` / `error` / `skipped` |
| `fallback_from` / `fallback_to` | API 의존성 감소·복원력 증거 |
| `duration_ms` | 포트폴리오 성능 숫자 |
| `prompt_tokens` / `completion_tokens` | 비용·사용량 분석(가능 시) |
| `error_type` / `reason_code` | 디버깅·보안 검토 |

> M2-0 합의: RunPod은 테스트 등급(간헐 가동)이므로 `provider`(selected)와 `fallback_*`를 **반드시** 기록해야 fallback rate/latency 같은 의미 있는 숫자가 남는다.

## 5. M2-2 handoff 답변

계획서 §8의 5개 질문에 대한 확정 답변:

1. **권위 있는 RunPod/vLLM health**: `ExaoneLLMClient.health_check()`(`llm/exaone_client.py:88-115`) + 노출 엔드포인트 `/health/llm/exaone`. M2-2는 이를 정리/재현 가능화한다.
2. **canonical env var**: **`EXAONE_RUNPOD_URL`** (실제 호출되는 `ExaoneLLMClient` 경로가 이 변수를 사용). `MODEL_EXAONE_BASE_URL`(=:19010)은 MAS/tool_calling candidate용으로, M2-2에서 둘을 통일하거나 역할을 문서화한다.
3. **metrics provider 이름**: `runpod_vllm`, `openai`, `anthropic`, `rule_based` (+ 분리 항목 `embedding_openai`, `moderation_openai`).
4. **active vs candidate/legacy**: §1 active / §2 conditional / §3 candidate·legacy 표 참조.
5. **첫 M2-4 전환 후보**: `analysis.ambiguity_detector`(`query_analysis/detectors.py:70`). EXAONE→gpt-4o-mini 폴백이 이미 배선되어 위험이 가장 낮음. (query classifier는 provider 폴백이 없어 보강 필요 → 후순위.)

## 6. M0-H capability/gate 연결

| Capability/Gate | 본 인벤토리 경로 | M2 검증 의미 |
| --- | --- | --- |
| `G-query-analysis-valid` | `analysis.query_classifier`, `analysis.ambiguity_detector` | provider 변경 후에도 유효한 route 생성 확인 |
| `G-generation-sufficiency` | `generation.answer` | 충분한 근거/안전 fallback 반환 확인 |
| `G-supervisor-iteration` | `supervisor.routing` | provider 장애 시 supervisor loop/fallback 안전 종료 |
| `G-sse-complete` | `/chat/stream` (generation 스트리밍 `generator.py:1174`) | frontend smoke에서 complete/error event 비교 가능 유지 |

## 7. Stop condition

본 문서로 M2-1 완료. provider 전환·health endpoint 변경·Agent refactor는 M2-1에서 하지 않는다. 다음 게이트는 **M2-2 RunPod vLLM health check 정리**.
