# Capability Registry (M0-H)

## 1. Definition

A **capability** is a measurable runtime dependency or service used by one or more agents/nodes. Capabilities are broader than agents: a capability can be retrieval, LLM generation, caching, moderation, checkpointing, memory, logging, metrics, or streaming.

The registry below is a design baseline. It does not enable, disable, or rewire any implementation.

## 2. Current capability registry

| Capability ID | Type | Current implementation | Used by | Inputs / outputs | Observability required | Roadmap link |
| --- | --- | --- | --- | --- | --- | --- |
| `graph.mas_supervisor_v2` | orchestration | `create_mas_supervisor_graph()` in `backend/app/supervisor/graph_mas.py:379-497` | `/chat`, `/chat/stream` | `ChatState` -> final graph state | node sequence, total duration, recursion/iteration count, graph error | M3 observability baseline |
| `state.chat_state` | state contract | `ChatState` in `backend/app/supervisor/state/__init__.py:109-245` | all nodes | shared request/session/retrieval/output/control state | state deltas per node, invalid/missing fields | M0-H contract baseline |
| `state.checkpointer.memory` | graph state persistence | `MemorySaver` in `backend/app/supervisor/checkpointer.py:27-101` | compiled MAS graph | thread ID -> checkpointed state | mode, persistence backend, restore failures | M3 durable observability; later DB persistence |
| `cache.l1_supervisor_response` | Redis cache | `SupervisorResponseCache` in `backend/app/supervisor/cache.py:33-57` | `cache_check`, `/chat`, `output_guardrail` | query/session -> final answer summary | hit/miss, save/delete errors, TTL, bypass reason | M1-9/M1-10 cache smoke, M3 metrics |
| `cache.l2_query_analysis` | Redis cache | `QueryAnalysisCache` in `backend/app/supervisor/cache.py:63-89` | query analysis | normalized query -> analysis fields | hit/miss, TTL, stale/malformed entry | M3 cache metrics |
| `cache.l3_intent_classification` | Redis cache | `IntentClassificationCache` in `backend/app/supervisor/cache.py:96-121` | LLM intent classifier | query -> intent/model/confidence | hit/miss, model used, confidence | M2 provider comparison, M3 metrics |
| `cache.l4_retrieval_result` | Redis cache | `RetrievalResultCache` in `backend/app/supervisor/cache.py:128-180` | `memory_save`, cached retrieval injection | session -> merged retrieval result | hit/miss, section counts, TTL | M1-9 cache smoke, M3/M4 follow-up evaluation |
| `cache.l5_retrieval_overflow` | Redis cache | `RetrievalOverflowCache` in `backend/app/supervisor/cache.py:186-242` | retrieval merge follow-up flows | session -> overflow retrieval sections | overflow counts, retrieval section counts | M3/M4 progressive disclosure metrics |
| `guardrail.input_moderation` | security guardrail | `input_guardrail_node()` and `check_input()` | `input_guardrail` | user text -> blocked/category/fallback | blocked rate, category scores, fail-open/fail-closed reason | M4 chatbot security |
| `guardrail.output_moderation` | security guardrail | `output_guardrail_node()` and `check_output()` | `output_guardrail` | answer text -> safe answer or fallback | blocked rate, category scores, cache-save status | M4 chatbot security |
| `guardrail.policy_categories` | policy config | `backend/app/guardrail/policies.py:17-58` | moderation wrappers/future policy gates | category flags -> block/warn/fallback | category distribution, policy version | M4 security regression |
| `supervisor.routing` | routing policy | `SupervisorNode` in `backend/app/supervisor/nodes/supervisor.py:163-232` and MAS route function | `supervisor` | current state -> next agent/action | next agent, policy reason, rule/LLM mode, fallback model | M3 routing metrics, M4 policy audit |
| `analysis.query_classifier` | semantic analysis | `query_analysis_node_v2` in `backend/app/agents/query_analysis/agent.py` | `query_analysis` | query/onboarding/history -> query analysis | intent, retriever types, missing fields, expanded query count, classifier fallback | M2 provider, M4 golden-set classification |
| `retrieval.law` | RAG retrieval | `LawRetrievalAgent` | `retrieval_law` | query/filter -> law docs | docs count, max/avg similarity, search time, errors | M1 retrieval baseline, M3 metrics |
| `retrieval.criteria` | RAG retrieval | `CriteriaRetrievalAgent` in `backend/app/agents/retrieval/criteria_agent.py:27-139` | `retrieval_criteria` | query/filter -> criteria docs | docs count, RRF/fusion strategy, similarity, search time | M1 retrieval baseline, M3 metrics |
| `retrieval.case` | RAG retrieval | `CaseRetrievalAgent` in `backend/app/agents/retrieval/case_agent.py:16-83` | `retrieval_case` | query/filter -> mediation case docs | docs count, similarity, dataset filter, search time | M1 retrieval baseline, M3/M4 evidence quality |
| `retrieval.base_executor` | retrieval execution wrapper | `BaseRetrievalAgent.process()` in `backend/app/agents/retrieval/base_retrieval_agent.py:39-129` | retrieval agents | supervisor request -> standardized report | per-agent status, errors, search_time_ms | M1/M3 baseline |
| `retrieval.merge` | evidence synthesis | `retrieval_merge_node()` in `backend/app/supervisor/nodes/retrieval_merge.py` | `retrieval_merge` | individual results -> merged retrieval/sources | section counts, filtered counts, confidence | M1 retrieval quality, M4 evidence gates |
| `generation.answer` | answer generation | `generation_node_v2` in `backend/app/agents/answer_generation/agent.py:904-1015` | `generation` | query/retrieval/analysis -> answer/claim map | model used, answer length, sufficiency, fallback, cited cases | M2 provider comparison, M4 golden set |
| `review.legal` | quality/security review | `review_node_v2` in `backend/app/agents/legal_review/agent.py:577-748` | `review` | draft/sources/retrieval -> pass/fail/final/retry | pass rate, violation count/type, retry count, confidence | M4 security and hallucination evaluation |
| `memory.conversation` | conversation persistence | `ConversationMemory` usage in `backend/app/api/chat.py:115-169`, `backend/app/api/chat.py:401-450` | `/chat`, `/chat/stream` | session/user turns -> context summary/history | backend type, turn count, DB save failures | M3 memory metrics |
| `memory.rag_turn` | RAG turn memory | `memory_save_node()` in `backend/app/supervisor/nodes/memory_save.py:18-99` | `memory_save` | mode/query/answer/retrieval -> memory/context | saved/skipped, turn count, L4 save outcome | M3/M4 multi-turn evaluation |
| `llm.provider_factory` | provider abstraction | `LLMProviderFactory` in `backend/app/llm/providers/factory.py:32-198` | supervisor, future agents | env/config -> OpenAI/Anthropic/EXAONE clients | provider availability, timeout, model name, init errors | M2 provider inventory |
| `llm.exaone_vllm` | local/RunPod LLM | `ExaoneLLMClient` in `backend/app/llm/exaone_client.py:27-201` | future/legacy LLM paths | prompts -> generated text | health, model size, tokens, timeout/fallback | M2 local LLM comparison |
| `llm.tool_calling_client` | tool-calling client candidate | `ToolCallingClient` in `backend/app/llm/tool_calling_client.py:25-147` | not enabled by M0-H | tools + prompt -> tool-bound LLM | health, bind errors, latency | Future module only; no M0-H implementation |
| `observability.node_timing` | trace/timing | `_create_timed_node()` in `backend/app/supervisor/graph.py:241-352` | all graph nodes | node state -> timings/trace entries | duration, input/output snapshot, state changes | M3 observability DB |
| `observability.rag_json_log` | structured file logging | `RAGLogger` in `backend/app/common/logging/rag_logger.py:270-291`, `backend/app/common/logging/rag_logger.py:588-620` | `/chat`, `/chat/stream` | request pipeline -> JSON log | total time, retrieval, LLM, response, pipeline trace | M3 durable metrics |
| `observability.prometheus` | metrics | `PROM_*` and `AgentMetrics` in `backend/app/common/metrics.py:17-179` | agents/admin metrics | records -> counters/histograms/stats | request count, success rate, p95/p99, tokens/cost/cache | M3 metrics dashboard |
| `api.chat_sync` | API entrypoint | `POST /chat` in `backend/app/api/chat.py:67-313` | frontend/backend smoke | `ChatRequest` -> `ChatResponse` | status, total time, node timings in debug, error rate | M1-10 smoke, M3 SLIs |
| `api.chat_sse` | API entrypoint | `POST /chat/stream` in `backend/app/api/chat.py:354-620` | frontend/backend smoke | `ChatRequest` -> SSE events | event sequence, heartbeat, token count, completion/error | M1-10 smoke, M3 SLIs |
| `api.search` | retrieval-only API | `POST /search` in `backend/app/api/search.py:44-97` | DB/RAG smoke | query/top_k -> results_count/results | results count, latency, error rate | M1 retrieval smoke |

## 3. Capability states

For future implementation, each capability should declare one of these states:

| State | Meaning |
| --- | --- |
| `active` | Used in the active `/chat` or `/chat/stream` request path. |
| `available` | Implemented and callable, but not necessarily active in the current graph. |
| `candidate` | Present as a client/helper for a future module, not wired by M0-H. |
| `planned` | Only mentioned in docs or TODOs. |
| `deprecated` | Kept for compatibility but not a target for new harness work. |

Examples: `api.chat_sync`, `graph.mas_supervisor_v2`, and `retrieval.case` are active; `llm.tool_calling_client` is candidate; PostgreSQL checkpointer is planned because `CHECKPOINTER_MODE=postgres` raises `NotImplementedError` in the current code path.

## 4. Registry gaps

| Gap | Why it matters | Future module hook |
| --- | --- | --- |
| No canonical capability ID in runtime logs | Hard to group metrics by capability across providers/nodes. | M3: add durable event schema with `capability_id`. |
| Provider availability is not normalized | OpenAI/Anthropic/EXAONE health and fallback are not comparable by one schema. | M2: provider inventory and comparison. |
| Tool-calling client exists but is not a harness capability in the graph | Tool use could bypass current gates if enabled ad hoc. | Future tool module must add contracts and gates first. |
| Cache tiers have separate semantics | Hit/miss rates need to be compared by cache tier and route. | M3: cache metrics table/dashboard. |
| Retrieval quality has multiple score shapes | Law/criteria/case search expose counts and similarities differently. | M1/M3: normalize retrieval metrics. |

## 5. Non-scope

This registry does not add new dependencies, providers, caches, health checks, or logging code. It is a documentation baseline for future implementation modules.
