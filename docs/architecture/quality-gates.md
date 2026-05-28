# Quality Gates and Security Guardrails (M0-H)

## 1. Gate definition

A **quality gate** is a measurable pass/fail, skip, retry, fallback, or block decision that controls whether a request can proceed to the next stage. A **security guardrail** is a gate whose primary purpose is abuse prevention, policy compliance, unsafe-output prevention, or system integrity.

M0-H documents existing gates and desired measurement semantics only. It does not add new gates or change current behavior.

## 2. Runtime gate table

| Gate ID | Stage | Current mechanism | Pass condition | Fail/block/retry outcome | Required metrics |
| --- | --- | --- | --- | --- | --- |
| `G-cache-l1-precheck` | before guardrail | `cache_check` + `SupervisorResponseCache` | no cache hit or valid cache hit | hit routes to `cache_response -> END`; miss continues | hit/miss rate, lookup latency, cache errors, cached mode |
| `G-input-moderation` | input security | `input_guardrail_node()` and `check_input()` | input not blocked or moderation disabled | blocked input returns fallback final answer and ends | blocked rate, categories, moderation latency, fail-open/fail-closed count |
| `G-supervisor-iteration` | routing safety | supervisor iteration/max-retry controls | next agent is valid and loop budget remains | rule fallback, response, or safe termination | iteration count, next agent, loop-stop count, model/rule mode |
| `G-query-analysis-valid` | planning | `query_analysis_node_v2` | query mode, intent, retriever types, keywords/expansions are usable for route | no-retrieval, restricted/meta route, fallback classifier result, missing-field handling | intent distribution, retriever selection rate, missing-field rate, classifier fallback/cache hit |
| `G-retrieval-agent-result` | RAG retrieval | `BaseRetrievalAgent.process()` and specialized retrievers | selected retrieval agent returns documents or explicit empty result without unhandled error | result with `error` flag or zero docs continues to merge with low evidence | docs count, max/avg similarity, search_time_ms, error rate by agent |
| `G-retrieval-merge-quality` | RAG evidence synthesis | `retrieval_merge_node()` | merged retrieval has structured sections and confidence/sources usable by generation | low-similarity or insufficient evidence flags guide generation/follow-up | total docs, section counts, filtered counts, confidence, overflow count |
| `G-cached-retrieval-valid` | follow-up RAG | `inject_cached_retrieval` + L4 cache | session cached retrieval exists and is structurally usable | fallback to normal route or generation with no cached context depending route | hit/miss, injected doc counts, stale/malformed count |
| `G-generation-sufficiency` | answer generation | retrieval sufficiency and generation fallback logic | enough evidence or safe clarification/fallback answer produced | follow-up/clarification or fallback answer | sufficiency flag, model used, fallback reason, answer length, claim-evidence map count |
| `G-legal-review` | answer quality/security | `review_node_v2` | no blocking violation or filtered answer acceptable | retry generation once or return filtered answer/failure context | pass/fail rate, violation count/type, retry rate, confidence score |
| `G-output-moderation` | output security | `output_guardrail_node()` and `check_output()` | final/draft answer not blocked | blocked output returns safe fallback message | blocked rate, categories, fail-closed errors, final answer length |
| `G-memory-save` | post-response state | `memory_save_node()` | eligible RAG/follow-up turn saved or intentionally skipped | warning on L4 cache save failure; graph still ends | saved/skipped count, turn count, cache save error |
| `G-rag-json-log` | observability | `RAGLogger` in `/chat` and `/chat/stream` | request finalized and saved when logging enabled | logging error should not corrupt response path | log save count/error, total_time_ms, node trace completeness |
| `G-prometheus-agent-metrics` | observability | `AgentMetrics` and Prometheus counters/histograms | metrics record emitted for measured agent operation | missing metric reduces comparability, not request success | count, success rate, avg/p95/p99 latency, token/cost/cache counters |
| `G-sse-complete` | streaming API | SSE event generator | complete event or explicit error event emitted after status/token events | client receives error event/heartbeat until termination | event sequence, heartbeat count, stream duration, completion/error rate |

## 3. Current security guardrail structure

| Guardrail | Current behavior | Source | Harness concern |
| --- | --- | --- | --- |
| Input moderation | Uses `MODERATION_ENABLED`, `MODERATION_MODEL`, blocked categories, and fallback input message. Missing API key is fail-open; API runtime exception is fail-closed. | `backend/app/guardrail/moderation.py:18-146` | M4 should measure both policy blocks and moderation infrastructure failures separately. |
| Output moderation | Checks final/draft answer after review/generation and can replace it with fallback. | `backend/app/guardrail/nodes.py:47-121` | M4 should measure unsafe-output rate and false positive/negative behavior on golden sets. |
| Policy category helpers | Defines blocked/warn categories and fallback messages. | `backend/app/guardrail/policies.py:17-58` | Future policy versions should be logged to compare security behavior over time. |
| Supervisor input sanitization | Supervisor node masks dangerous prompt-like patterns and enforces length constraints before decision prompts. | `backend/app/supervisor/nodes/supervisor.py:523-568` | Treat as prompt-injection/system-integrity guardrail; add explicit metric later. |
| Legal review | Checks prohibited expressions, citation/evidence sufficiency, citation accuracy, and can request regeneration. | `backend/app/agents/legal_review/agent.py:577-748` | Bridges quality and safety: hallucination/evidence failures should be tracked as security-adjacent failures. |

## 4. Current observability coverage

| Coverage area | Current implementation | Gap |
| --- | --- | --- |
| Per-node timing | `_create_timed_node()` records start/end/duration, snapshots, state changes, and protocol summaries. | Not yet persisted as queryable DB rows by default. |
| Pipeline summary | `build_pipeline_summary()` produces total duration, node sequence, and per-node summaries. | Routing reasons and capability IDs are not first-class fields. |
| RAG JSON log | `RAGLogger` supports input, retrieval, structured retrieval, LLM, response, node timings, and pipeline trace logs. | Log completeness depends on endpoint path and enabled file logging. |
| Prometheus/in-memory metrics | Agent latency/request counters, LLM token/cost counters, cache counters, and stats API exist. | Not all nodes/providers currently emit normalized records. |
| API debug timing | `/chat` can return node timings when debug is enabled. | SSE path needs comparable final diagnostics for automated smoke. |

## 5. Gate-to-roadmap mapping

| Roadmap area | Relevant gates | Measurement objective |
| --- | --- | --- |
| M1 RAG/DB/cache/frontend smoke | `G-cache-l1-precheck`, `G-retrieval-agent-result`, `G-retrieval-merge-quality`, `G-sse-complete` | Establish baseline result counts, cache behavior, latency, and endpoint pass/fail. |
| M2 provider/local LLM | `G-query-analysis-valid`, `G-generation-sufficiency`, `G-supervisor-iteration` | Compare provider availability, fallback rate, latency, token usage, and classification/generation behavior. |
| M3 observability DB | all gates, especially `G-rag-json-log` and `G-prometheus-agent-metrics` | Persist gate outcomes and capability metrics for before/after regression comparison. |
| M4 chatbot/code security | `G-input-moderation`, `G-output-moderation`, `G-legal-review`, supervisor sanitization | Measure blocked/warned/refused/unsafe rates under golden-set tests and PR security review automation. |

## 6. Target gate event schema for future modules

Future M3/M4 implementation can persist each gate as an event with this logical shape:

| Field | Meaning |
| --- | --- |
| `request_id`, `session_id` | Join key for request/session. |
| `gate_id` | Stable gate ID from this document. |
| `node_name` | LangGraph node that emitted the gate. |
| `capability_id` | Capability used by the gate. |
| `status` | `pass`, `fail`, `block`, `skip`, `retry`, or `fallback`. |
| `reason_code` | Stable machine-readable reason. |
| `duration_ms` | Gate evaluation latency. |
| `metrics` | Gate-specific counts/scores, such as doc count, similarity, category score, violation count. |
| `provider` / `model` | Provider/model when LLM or moderation is involved. |
| `created_at` | Event timestamp. |

## 7. Non-scope

- No new moderation policy.
- No new refusal behavior.
- No legal review rule change.
- No migration for gate events.
- No enforcement of target schema in runtime code.
- No golden-set execution in M0-H.
