# Agent Contracts (M0-H)

## 1. Contract model

An **agent contract** is the minimum measurable interface for a LangGraph node or MAS agent:

- **Inputs**: `ChatState` fields or request fields the node reads.
- **Outputs**: state updates the node writes.
- **Dependencies**: retrieval, LLM, guardrail, DB/cache, memory, or logging capabilities it calls.
- **Routing semantics**: how the supervisor or graph reaches the node and how the node can short-circuit, retry, or end.
- **Observability**: timings, counts, scores, pass/fail flags, provider/model IDs, and errors that must be captured.

Current code already contains partial contracts through `BaseAgent.required_inputs/provided_outputs` (`backend/app/agents/base.py:43-77`), standardized supervisor reports (`backend/app/agents/base.py:113-155`), default registry metadata (`backend/app/agents/registry/agent_registry.py:273-353`), typed state/result definitions (`backend/app/supervisor/state/__init__.py:109-245`, `backend/app/supervisor/state/agent_results.py:13-157`), and graph timing/trace wrappers (`backend/app/supervisor/graph.py:241-352`). This document makes those contracts explicit for future harness work.

## 2. Shared state contract

| State area | Representative fields | Current source | Harness meaning |
| --- | --- | --- | --- |
| Session/request | `user_query`, `session_id`, `chat_type`, `onboarding` | `ChatState`, `SessionState` | Request identity and user-provided context. |
| Query analysis | `query_analysis`, `expanded_queries`, `mode` | `QueryAnalysisResult`, `RoutingMode` | Intent, search plan, and high-level route. |
| Retrieval | `individual_retrieval_results`, `retrieval`, `sources` | `IndividualRetrievalResult`, `RetrievalResult` | Per-agent and merged RAG evidence. |
| Generation/review | `draft_answer`, `final_answer`, `review`, `retry_context`, `retry_count` | `OutputState`, `ReviewResult` | Answer production, validation, and retry loop. |
| Guardrail | `guardrail_blocked`, `guardrail_type` | `ControlState`, guardrail nodes | Input/output safety gate outcome. |
| Supervisor | `supervisor.current_phase`, `next_agent`, `iteration_count` | `SupervisorState` | Routing state and loop guard. |
| Observability | `_node_timings`, `_agent_trace_entries` | graph timed wrapper | Per-node duration, state deltas, protocol summaries. |
| Memory | `conversation_history`, `compact_summary`, `rag_conversation_memory`, `_last_turn_context` | memory state and `memory_save` | Multi-turn context and RAG follow-up reuse. |

## 3. Active node contracts

| Node | Inputs | Outputs | Dependencies | Routing / gate semantics | Required observability |
| --- | --- | --- | --- | --- | --- |
| `cache_check` | `user_query`, `session_id` | `_cache_hit`, cached response fields when hit | Redis L1 `SupervisorResponseCache` | Entry node. Routes to `cache_response` on hit or `input_guardrail` on miss. | hit/miss, cache lookup latency, error count. |
| `cache_response` | cached response state | `final_answer`, `mode`, cache marker | Redis L1 | Short-circuits graph to `END`. | hit answer length, cached mode, total skipped nodes. |
| `input_guardrail` | `user_query` | `guardrail_blocked`, `guardrail_type`, optional `final_answer` | OpenAI moderation if enabled | Blocks to `END` when unsafe; otherwise routes to `supervisor`. | blocked flag, category/type, fail-open/fail-closed reason, latency. |
| `supervisor` | `query_analysis`, `retrieval`, `draft_answer`, `review`, `mode`, `retry_count`, `supervisor` | updated `supervisor.next_agent`, `current_phase`, `iteration_count`, possible final routing intent | Agent registry, optional supervisor LLM, rule fallback | Decides next graph node; enforces iteration/retry control. | next agent, phase, model/rule mode, reasoning preview, iteration count. |
| `query_analysis` | `user_query`, `chat_type`, `onboarding`, conversation context | `query_analysis`, `expanded_queries`, `mode`, missing fields | Rule classifier, optional LLM classifier/cache, query expansion | First semantic routing gate after supervisor; can choose no-retrieval, RAG, cached/follow-up modes, retriever types. | intent/query type, retriever type count, keyword count, expanded query count, classifier source, cache hit. |
| `retrieval_law` | `user_query`, `query_analysis`, `expanded_queries`, metadata filter | one `IndividualRetrievalResult` for law | Law retriever, PostgreSQL/vector/hybrid search, DB config | Runs in retrieval fan-out when `law` is selected. | document count, max/avg similarity, search time, error flag. |
| `retrieval_criteria` | `user_query`, `query_analysis`, `expanded_queries`, metadata filter | one `IndividualRetrievalResult` for criteria | Criteria retriever, PostgreSQL/vector/hybrid search | Runs in retrieval fan-out when `criteria` is selected. | document count, max/avg similarity, search time, query strategy, error flag. |
| `retrieval_case` | `user_query`, `query_analysis`, metadata filter | one `IndividualRetrievalResult` for case | Case retriever, PostgreSQL/vector/hybrid search | Runs in retrieval fan-out when `case` is selected. | document count, max/avg similarity, search time, dataset filter, error flag. |
| `retrieval_merge` | `individual_retrieval_results`, `query_analysis`, `onboarding` | `retrieval`, `sources`, confidence/sufficiency fields, overflow cache candidates | Merge/filter logic, Redis overflow/result cache | Fan-in point after retrieval agents; returns to supervisor. | section counts, total docs, max/avg similarity, filtered/overflow counts. |
| `inject_cached_retrieval` | `session_id`, cached retrieval context | `retrieval`, source/context fields | Redis L4 `RetrievalResultCache` | Used for `CACHED_RAG`/follow-up reuse before generation. | cache hit/miss, injected section counts. |
| `generation` | `user_query`, `retrieval`, `query_analysis`, `onboarding`, `retry_context`, `mode` | `draft_answer`, `final_answer`, `has_sufficient_evidence`, `claim_evidence_map`, `cited_cases`, follow-up fields | Template router/loader, context builder, LLM fallback, answer cache | Generates answer or fallback/clarifying response; returns to supervisor. | model used, latency, answer length, cited case count, sufficiency flag, fallback reason. |
| `review` | `draft_answer`, `query_analysis`, `sources`, `retrieval`, `retry_count`, conversation phase | `review`, possible `final_answer`, `retry_context`, `retry_count`, `supervisor.next_agent=retry_generation` | Terminology/prohibited expression/citation/evidence checkers | Passes answer, filters answer, or requests one regeneration attempt. | passed flag, violation count/types, retry decision, confidence score. |
| `output_guardrail` | `draft_answer` or `final_answer` | safe `final_answer`, `guardrail_blocked`, `guardrail_type`, L1 cache save side effect | OpenAI moderation if enabled, Redis L1 cache | Final safety gate before memory save; blocked output returns fallback message. | blocked flag, category/type, fail-closed errors, cache-save outcome. |
| `memory_save` | `mode`, `user_query`, `final_answer`, `retrieval`, follow-up fields, `session_id` | `rag_conversation_memory`, `_last_turn_context`; L4 cache side effect | in-state memory, Redis L4 retrieval cache | Persists RAG turn/context then ends graph. | saved/skipped flag, turn count, retrieval cache save outcome. |

## 4. Contract gaps to resolve in future modules

| Gap | Impact | Suggested future treatment |
| --- | --- | --- |
| Registry vs active graph mismatch | Metadata can list capabilities that are not active nodes. | Add active/inactive status and graph binding field to the registry/harness. |
| Shared-state writes are not schema-validated per node | A node can add or omit fields without a contract failure. | Add typed per-node contract tests before changing nodes. |
| Routing decisions lack stable policy IDs | Metrics can show node sequence but not why each decision happened. | Emit `routing_policy_id` and decision reason in supervisor trace. |
| Provider and cache dependencies are implicit | Provider/cost/fallback comparisons require log reconstruction. | Connect each node to capability IDs from `capability-registry.md`. |
| Gate outcomes are distributed | Pass/fail rates are hard to compare across golden sets. | Persist quality gate events as first-class records in M3/M4. |

## 5. Non-scope

This contract file does not introduce new runtime validators, decorators, migrations, providers, tools, or graph edges. It is the documentation baseline that future modules can implement against.
