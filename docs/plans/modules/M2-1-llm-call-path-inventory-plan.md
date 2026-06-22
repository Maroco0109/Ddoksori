# M2-1 LLM Call Path Inventory Plan

- 작성일: 2026-06-22
- 모듈: `M2-1` 현재 LLM 호출 경로 inventory
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`
- 선행 완료: M1-10 frontend local smoke, M0-H architecture baseline
- 목표: 어떤 코드가 OpenAI/Anthropic/EXAONE/embedding/moderation을 호출하는지 Agent/Capability별로 확정하고, M2-2~M2-6 전환 순서를 결정할 수 있는 call map을 만든다.
- 이번 계획 문서에서 하지 않는 일: provider 구현, RunPod 연결 실행, Agent 코드 수정, health endpoint 수정, embedding provider 교체.

## 1. Completion criteria

M2-1은 다음 산출물이 생기면 완료한다.

1. `docs/plans/modules/M2-1-llm-call-path-inventory.md` 작성.
2. active `/chat` 및 `/chat/stream` 경로에서 실제로 호출 가능한 LLM/provider 경로를 표로 정리.
3. candidate/legacy/test-only 호출 경로를 active 경로와 분리.
4. 각 경로에 provider, env var, model setting, fallback, cache/metrics 여부를 기록.
5. M2-2 health check와 M2-4 첫 전환 후보를 제안.
6. M0-H capability/gate ID와 연결.

## 2. Files in scope

Read-only inventory 대상 파일은 다음이다.

| Area | Files |
| --- | --- |
| Provider factory/client | `backend/app/llm/providers/factory.py`, `backend/app/llm/exaone_client.py`, `backend/app/llm/tool_calling_client.py` |
| Supervisor | `backend/app/supervisor/nodes/supervisor.py`, `backend/app/supervisor/graph_mas.py`, `backend/app/supervisor/graph.py` |
| Query analysis | `backend/app/agents/query_analysis/llm_classifier.py`, `backend/app/agents/query_analysis/llm_expander.py`, `backend/app/agents/query_analysis/classifier.py`, `backend/app/agents/query_analysis/detectors.py` |
| Retrieval/embedding | `backend/app/agents/retrieval/tools/*`, `backend/app/common/embedding/*`, `backend/app/common/cache/embedding_cache.py` |
| Answer generation | `backend/app/agents/answer_generation/agent.py`, `backend/app/agents/answer_generation/tools/generator.py` |
| Legal review | `backend/app/agents/legal_review/*` |
| Guardrail | `backend/app/guardrail/moderation.py`, `backend/app/guardrail/nodes.py` |
| Health/API | `backend/app/api/health.py`, `backend/app/api/chat.py`, `backend/app/api/search.py` |
| Config/env/docs | `.env.example`, `backend/app/common/config.py`, `backend/README.md`, `docs/feature/E2E_guide.md`, `docs/infrastructure/runpod-vllm-setup.md` if present |
| Tests/scripts | `backend/scripts/testing/llm/*`, provider/embedding/reliability tests |

## 3. Files out of scope

- Runtime implementation files should not be edited in M2-1.
- `.env` must not be committed or printed.
- DB volumes, Docker compose services, and frontend code are out of scope unless referenced as existing smoke evidence.

## 4. Initial findings to verify in M2-1

These findings are based on the planning scan and must be confirmed in the inventory document with exact file references.

| Capability | Initial finding | Evidence to confirm |
| --- | --- | --- |
| `llm.provider_factory` | Factory supports OpenAI, EXAONE OpenAI-compatible, Anthropic, but callers bypass it in several Agent paths. | `backend/app/llm/providers/factory.py:32-198` |
| `llm.exaone_vllm` | EXAONE RunPod client has health check and generation methods. | `backend/app/llm/exaone_client.py:27-201` |
| `supervisor.routing` | Supervisor uses OpenAI primary, Anthropic fallback, rule fallback. | `backend/app/supervisor/nodes/supervisor.py:58-86`, `203-227` |
| `analysis.query_classifier` | LLM classifier creates OpenAI Async client directly. | `backend/app/agents/query_analysis/llm_classifier.py:143-222` |
| `analysis.query_expander` | Query expansion creates OpenAI Async client directly and has rule fallback paths. | `backend/app/agents/query_analysis/llm_expander.py:60-136`, `297-335` |
| `generation.answer` | RAG generator creates OpenAI sync/async clients directly; streaming uses OpenAI async completions. | `backend/app/agents/answer_generation/tools/generator.py:125-143`, `210-249`, `1173-1175` |
| `review.legal` | Optional LLM review uses OpenAI direct client when `ENABLE_LLM_REVIEW=true`. | `backend/app/agents/legal_review/llm_reviewer.py:195-209`, `394-421` |
| `guardrail.input/output_moderation` | Moderation uses OpenAI Moderation API and should remain separate from inference provider migration. | `backend/app/guardrail/moderation.py:24-80` |
| `embedding.openai` | Embedding remains OpenAI 1536d-compatible with restored `vector_chunks`; M2-6 should separate policy rather than replace early. | `backend/app/common/embedding/openai_provider.py:24-138` |
| `api.health` | Existing health endpoints split supervisor OpenAI, EXAONE, and embedding checks but not unified provider policy. | `backend/app/api/health.py:78-139` |

## 5. Inventory table shape

The M2-1 result document should use this table shape.

| Runtime path | Node/Agent | Capability ID | Provider today | Client construction | Env vars | Model config | Fallback | Active status | M2 action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/chat/stream` | `generation` | `generation.answer` | OpenAI | direct `OpenAI`/`AsyncOpenAI` | `OPENAI_API_KEY` | `MODEL_DRAFT_AGENT` or `LLM_MODEL` | rule/safe fallback | active | candidate for later conversion |

`Active status` values:

- `active`: used by normal `/chat` or `/chat/stream` request path.
- `conditional`: used only when env flag or route enables it.
- `candidate`: implemented but not wired into active path.
- `test/script`: test-only or manual script path.
- `legacy`: retained but not target for new work.

## 6. Measurement fields to carry into M2-2/M3

M2-1 should recommend the common fields that later M2/M3 code can emit.

| Field | Why |
| --- | --- |
| `request_id` / `session_id` | Join LLM call to chat run. |
| `node_name` | Map call to LangGraph node. |
| `capability_id` | Reuse M0-H vocabulary. |
| `provider` | `runpod_vllm`, `openai`, `anthropic`, `rule_based`, `moderation_openai`, `embedding_openai`. |
| `model` | Compare model choice and output changes. |
| `status` | `success`, `fallback`, `error`, `skipped`. |
| `fallback_from` / `fallback_to` | Show API dependency reduction and resilience. |
| `duration_ms` | Portfolio performance number. |
| `prompt_tokens` / `completion_tokens` | Cost/usage analysis where available. |
| `error_type` / `reason_code` | Debuggability and security review. |

## 7. Verification plan for M2-1

M2-1 is docs-only but must be evidence-backed.

Run these read-only checks while writing the inventory.

```bash
rg -n "from openai|OpenAI\(|AsyncOpenAI\(|from anthropic|Anthropic\(|AsyncAnthropic\(|ChatOpenAI\(|chat\.completions\.create|moderations\.create|embeddings\.create|ExaoneLLMClient|ToolCallingClient" backend/app backend/scripts -g '*.py'
```

```bash
rg -n "OPENAI_API_KEY|ANTHROPIC_API_KEY|EXAONE|MODEL_|EMBEDDING|MODERATION|LLM_PROVIDER" .env.example backend/app/common/config.py docker-compose.yml backend/README.md docs -g '!docs/plans/modules/M2-*'
```

```bash
python -m compileall -q backend/app/llm backend/app/agents/query_analysis backend/app/agents/answer_generation backend/app/agents/legal_review backend/app/guardrail backend/app/api
```

The compile step is optional for M2-1 because no runtime code should change, but it is a cheap sanity check if the environment has dependencies available.

## 8. M2-2 handoff criteria

M2-2 may start only after M2-1 answers these questions.

1. Which health endpoint/script should be authoritative for RunPod/local vLLM?
2. Which env vars are canonical: `EXAONE_RUNPOD_URL` vs `MODEL_EXAONE_BASE_URL`?
3. Which provider names will be used in metrics: `runpod_vllm`, `openai`, `anthropic`, `rule_based`?
4. Which provider calls are active vs candidate/legacy?
5. Which node is safest for the first M2-4 provider conversion?

## 9. Stop condition

Stop after the inventory document is written and reviewed. Do not implement provider switching, health endpoint changes, or Agent refactors in M2-1.
