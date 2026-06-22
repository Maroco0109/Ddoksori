# Ddoksori Agent Harness Architecture (M0-H)

## 1. Purpose

This document defines **Ddoksori Agent Harness** as the measurement-oriented control layer around the current LangGraph/MAS chatbot. The goal is not to rewrite the existing agent graph in M0-H. The goal is to name the runtime contracts, capabilities, routing policies, state, observability, quality gates, and security guardrails that future M1-M4 modules can measure and improve.

M0-H is documentation-only. It does not change LangGraph nodes, LLM providers, retrieval code, tool calling, database schema, or existing agent implementations.

## 2. Evidence sources

The current architecture was inspected from these repo-local files:

- MAS graph topology and node registration: `backend/app/supervisor/graph_mas.py:379-497`
- Graph selection and timing/trace wrapper: `backend/app/supervisor/graph.py:35-72`, `backend/app/supervisor/graph.py:116-238`, `backend/app/supervisor/graph.py:241-352`, `backend/app/supervisor/graph.py:360-378`
- Chat and SSE entrypoints: `backend/app/api/chat.py:67-313`, `backend/app/api/chat.py:354-620`
- Shared `ChatState`: `backend/app/supervisor/state/__init__.py:109-245`
- Agent result schemas: `backend/app/supervisor/state/agent_results.py:13-157`, `backend/app/supervisor/state/agent_results.py:214-262`
- Routing mode and trace state: `backend/app/supervisor/state/control.py:11-103`
- Agent metadata and registry: `backend/app/agents/base.py:43-77`, `backend/app/agents/base.py:113-155`, `backend/app/agents/registry/agent_registry.py:41-72`, `backend/app/agents/registry/agent_registry.py:273-353`
- Guardrails: `backend/app/guardrail/nodes.py:13-121`, `backend/app/guardrail/moderation.py:18-146`, `backend/app/guardrail/policies.py:17-58`
- Metrics/logging: `backend/app/common/metrics.py:17-40`, `backend/app/common/metrics.py:53-179`, `backend/app/common/logging/rag_logger.py:270-291`, `backend/app/common/logging/rag_logger.py:588-620`
- Caches and checkpointer: `backend/app/supervisor/cache.py:33-180`, `backend/app/supervisor/checkpointer.py:27-132`
- Provider factory and local LLM clients: `backend/app/llm/providers/factory.py:32-198`, `backend/app/llm/exaone_client.py:27-201`, `backend/app/llm/tool_calling_client.py:25-147`
- Roadmap context: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`

## 3. Definition: Ddoksori Agent Harness

**Ddoksori Agent Harness** is the explicit specification layer that treats every LangGraph node, retrieval agent, LLM provider, cache, guardrail, and persistence boundary as a measurable runtime capability.

The harness answers these questions for every request:

1. **Contract**: what state fields does the node consume and produce?
2. **Capability**: what external or internal capability does it depend on?
3. **Routing policy**: why was this node selected, skipped, retried, or short-circuited?
4. **State**: what `ChatState` fields are authoritative before and after the node?
5. **Observability**: what timings, counts, scores, pass/fail outcomes, provider IDs, and errors are emitted?
6. **Quality gate**: what condition must pass before the request can move to the next stage?
7. **Security guardrail**: what unsafe input/output or unsafe system behavior is blocked, warned, or logged?

The current code already has parts of this harness: typed `ChatState`, timed wrappers, JSON RAG logs, Prometheus metrics, Redis caches, moderation guardrails, and legal review. The missing part is a stable harness vocabulary that connects these pieces into one architecture contract.

## 4. Current runtime shape

### 4.1 Entrypoints

- `POST /chat` creates a `ChatState`, optionally persists conversation memory, checks L1 response cache, invokes the MAS graph, logs retrieval/trace/timing, and returns a `ChatResponse` (`backend/app/api/chat.py:67-313`).
- `POST /chat/stream` runs the same graph through `astream_events`, emits SSE status/token/fallback/error/complete events, and keeps a heartbeat during long blocking calls (`backend/app/api/chat.py:354-620`).
- `GET /chat/stream` is not a supported entrypoint; the stream route is POST-only.

### 4.2 Active LangGraph topology

`get_graph_for_chat_type()` always returns the compiled MAS Supervisor graph; `chat_type` affects initial state and review/iteration semantics rather than selecting a different graph (`backend/app/supervisor/graph.py:360-378`). The graph is built in `create_mas_supervisor_graph()` with these nodes (`backend/app/supervisor/graph_mas.py:379-497`):

```text
cache_check
  ├─ cache_response -> END
  └─ input_guardrail -> supervisor
       ├─ query_analysis -> supervisor
       ├─ retrieval_law ─┐
       ├─ retrieval_criteria ─> retrieval_merge -> supervisor
       ├─ retrieval_case ─┘
       ├─ inject_cached_retrieval -> generation -> supervisor
       ├─ generation -> supervisor
       ├─ review -> supervisor
       └─ output_guardrail -> memory_save -> END
```

### 4.3 Current agent/node inventory

| Runtime node / agent | Current role | Primary implementation |
| --- | --- | --- |
| `cache_check` | L1 response cache precheck | `backend/app/supervisor/graph_mas.py` internal node |
| `cache_response` | Return cached final answer | `backend/app/supervisor/graph_mas.py` internal node |
| `input_guardrail` | Moderate user input before graph work | `backend/app/guardrail/nodes.py` |
| `supervisor` | Decide next node/action | `backend/app/supervisor/nodes/supervisor.py` |
| `query_analysis` | Classify intent, expand queries, choose retrievers | `backend/app/agents/query_analysis/agent.py` |
| `retrieval_law` | Search law articles | `backend/app/agents/retrieval/law_agent.py` |
| `retrieval_criteria` | Search dispute resolution criteria | `backend/app/agents/retrieval/criteria_agent.py` |
| `retrieval_case` | Search mediation/dispute cases | `backend/app/agents/retrieval/case_agent.py` |
| `retrieval_merge` | Merge, filter, and structure retrieval outputs | `backend/app/supervisor/nodes/retrieval_merge.py` |
| `inject_cached_retrieval` | Load cached retrieval for follow-up contexts | `backend/app/supervisor/graph_mas.py` internal node |
| `generation` | Generate draft/final answer from retrieval context | `backend/app/agents/answer_generation/agent.py` |
| `review` | Legal/citation/evidence review and retry signal | `backend/app/agents/legal_review/agent.py` |
| `output_guardrail` | Moderate final output and save L1 cache | `backend/app/guardrail/nodes.py` |
| `memory_save` | Persist RAG turn and cached retrieval context | `backend/app/supervisor/nodes/memory_save.py` |

The Agent Registry additionally declares `retrieval_team`, `retrieval_counsel`, `answer_drafter`, and `legal_reviewer` metadata (`backend/app/agents/registry/agent_registry.py:273-353`). The active MAS graph currently registers three retrieval nodes (`law`, `criteria`, `case`) and does not register a `retrieval_counsel` node in `create_mas_supervisor_graph()` (`backend/app/supervisor/graph_mas.py:417-423`).

## 5. Current structure limitations

The current architecture is functional, but it is still closer to an **agent/node listing** than a harness specification.

1. **Contracts are implicit in `ChatState` mutations.** `BaseAgent` exposes `required_inputs` and `provided_outputs`, but graph nodes mostly communicate by reading/writing shared state fields (`backend/app/agents/base.py:43-77`, `backend/app/supervisor/state/__init__.py:109-245`).
2. **Registry metadata and graph topology are not the same source of truth.** The registry lists `retrieval_counsel` and `retrieval_team`, while the active MAS graph fans out to `law`, `criteria`, and `case` only.
3. **Capability dependencies are distributed.** Retrieval uses PostgreSQL/vector retrievers, generation uses templates and LLM fallback, guardrails use moderation, cache uses Redis, and state uses checkpointer/memory; these dependencies are not currently expressed as one registry.
4. **Routing policy is code-driven rather than policy-named.** Supervisor/routing code handles modes such as `NO_RETRIEVAL`, `NEED_RAG`, `CACHED_RAG`, `META_CONVERSATIONAL`, and retry, but those decisions are not yet captured as measurable policy outcomes.
5. **Observability exists but is split.** Node timing and protocol summaries are added to state, RAG logs are saved as JSON, Prometheus counters/histograms exist, and admin metrics expose in-memory stats. A harness should define which metrics are required per node and per gate.
6. **Quality gates are present but not uniformly named.** Input moderation, retrieval sufficiency, legal review, output moderation, and cache short-circuiting act as gates, but they do not yet share one gate table with pass/fail semantics.

## 6. Target harness structure

| Harness layer | Target meaning | Current anchor | M0-H status |
| --- | --- | --- | --- |
| Contract | Node consumes/produces named state fields with failure semantics | `ChatState`, result TypedDicts, `BaseAgent` | Documented in `agent-contracts.md` |
| Capability | Reusable service dependency: retrieval, LLM, cache, DB, moderation, memory | retrievers, providers, caches, guardrails | Documented in `capability-registry.md` |
| Routing policy | Named policy for node selection/skip/retry/fallback | supervisor routing modes and retry context | Described here; future implementation can emit policy IDs |
| State | Authoritative request/session/runtime state | `ChatState`, checkpointer, conversation memory | Mapped in contracts |
| Observability | Required timings, counts, scores, provider IDs, pass/fail rates | timed wrapper, RAG logs, Prometheus metrics | Mapped to gates and capabilities |
| Quality gate | Pass/fail condition before progressing | moderation, retrieval sufficiency, legal review | Documented in `quality-gates.md` |
| Security guardrail | Unsafe input/output/system behavior controls | moderation nodes, legal review, sanitization | Documented in `quality-gates.md` |

## 7. Roadmap connection

| Roadmap phase | Harness connection |
| --- | --- |
| M1: RAG/DB smoke and baseline | Provides retrieval counts, similarities, cache hit/miss, latency, and frontend/backend smoke evidence that the harness should preserve as baseline numbers. |
| M2: Provider/local LLM inventory and comparison | Uses capability registry to compare OpenAI, Anthropic, EXAONE/vLLM, RunPod, and fallback behavior by provider capability instead of scattered environment variables. |
| M3: Observability DB and metrics | Turns the documented trace, timing, metric, and gate outcomes into durable records and dashboards. |
| M4: Security and golden-set evaluation | Uses quality gate and guardrail definitions to measure chatbot security behavior, refusal/blocked rates, review pass/fail, and code/PR security automation outcomes. |

## 8. Non-scope for M0-H

- No LangGraph node or edge changes.
- No provider factory, EXAONE, Anthropic, OpenAI, or RunPod implementation changes.
- No tool calling implementation or enablement.
- No database migration or checkpointer migration.
- No existing agent refactor.
- No answer-quality tuning or prompt rewrite.
- No new runtime metrics emission; this document only defines what future modules should measure.

## 9. Design rule for future modules

Future modules should avoid adding another untracked node or provider path without updating the harness docs first. A new runtime element should be added with:

1. an agent/node contract,
2. a capability registry row,
3. a quality/security gate row when it can block, retry, fallback, or degrade,
4. an observability claim with concrete metrics.
