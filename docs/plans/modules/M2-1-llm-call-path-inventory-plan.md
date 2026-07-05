# M2-1 LLM 호출 경로 인벤토리 계획

- 작성일: 2026-06-22
- 모듈: `M2-1` 현재 LLM 호출 경로 inventory
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`
- 선행 완료: M1-10 frontend local smoke, M0-H architecture baseline
- 목표: 어떤 코드가 OpenAI/Anthropic/EXAONE/embedding/moderation을 호출하는지 Agent/Capability별로 확정하고, M2-2~M2-6 전환 순서를 결정할 수 있는 call map을 만든다.
- 이번 계획 문서에서 하지 않는 일: provider 구현, RunPod 연결 실행, Agent 코드 수정, health endpoint 수정, embedding provider 교체.

## 1. 완료 기준

M2-1은 다음 산출물이 생기면 완료한다.

1. `docs/plans/modules/M2-1-llm-call-path-inventory.md` 작성.
2. active `/chat` 및 `/chat/stream` 경로에서 실제로 호출 가능한 LLM/provider 경로를 표로 정리.
3. candidate/legacy/test-only 호출 경로를 active 경로와 분리.
4. 각 경로에 provider, env var, model setting, fallback, cache/metrics 여부를 기록.
5. M2-2 health check와 M2-4 첫 전환 후보를 제안.
6. M0-H capability/gate ID와 연결.

## 2. 대상 파일 (in scope)

read-only inventory 대상 파일은 다음이다.

| 영역 | 파일 |
| --- | --- |
| Provider factory/client | `backend/app/llm/providers/factory.py`, `backend/app/llm/exaone_client.py`, `backend/app/llm/tool_calling_client.py` |
| Supervisor | `backend/app/supervisor/nodes/supervisor.py`, `backend/app/supervisor/graph_mas.py`, `backend/app/supervisor/graph.py` |
| Query analysis | `backend/app/agents/query_analysis/llm_classifier.py`, `backend/app/agents/query_analysis/llm_expander.py`, `backend/app/agents/query_analysis/classifier.py`, `backend/app/agents/query_analysis/detectors.py` |
| Retrieval/embedding | `backend/app/agents/retrieval/tools/*`, `backend/app/common/embedding/*`, `backend/app/common/cache/embedding_cache.py` |
| Answer generation | `backend/app/agents/answer_generation/agent.py`, `backend/app/agents/answer_generation/tools/generator.py` |
| Legal review | `backend/app/agents/legal_review/*` |
| Guardrail | `backend/app/guardrail/moderation.py`, `backend/app/guardrail/nodes.py` |
| Health/API | `backend/app/api/health.py`, `backend/app/api/chat.py`, `backend/app/api/search.py` |
| Config/env/docs | `.env.example`, `backend/app/common/config.py`, `backend/README.md`, `docs/feature/E2E_guide.md`, `docs/infrastructure/runpod-vllm-setup.md`(존재 시) |
| Tests/scripts | `backend/scripts/testing/llm/*`, provider/embedding/reliability 테스트 |

## 3. 제외 대상 파일 (out of scope)

- 런타임 구현 파일은 M2-1에서 수정하지 않는다.
- `.env`는 커밋하거나 출력하지 않는다.
- DB 볼륨, Docker compose 서비스, 프론트엔드 코드는 기존 smoke 증거로 참조되는 경우를 제외하면 범위 밖이다.

## 4. M2-1에서 검증할 초기 발견 사항

아래 발견 사항은 사전 스캔 기반이며, 인벤토리 문서에서 정확한 file 참조와 함께 확인되어야 한다.

| Capability | 초기 발견 | 확인할 근거 |
| --- | --- | --- |
| `llm.provider_factory` | factory가 OpenAI, EXAONE(OpenAI 호환), Anthropic을 지원하지만 여러 Agent 경로에서 이를 우회한다. | `backend/app/llm/providers/factory.py:32-198` |
| `llm.exaone_vllm` | EXAONE RunPod client가 health check와 generation 메서드를 갖는다. | `backend/app/llm/exaone_client.py:27-201` |
| `supervisor.routing` | Supervisor가 OpenAI primary, Anthropic fallback, rule fallback을 사용한다. | `backend/app/supervisor/nodes/supervisor.py:58-86`, `203-227` |
| `analysis.query_classifier` | LLM classifier가 OpenAI Async client를 직접 생성한다. | `backend/app/agents/query_analysis/llm_classifier.py:143-222` |
| `analysis.query_expander` | query 확장이 OpenAI Async client를 직접 생성하고 rule fallback 경로를 갖는다. | `backend/app/agents/query_analysis/llm_expander.py:60-136`, `297-335` |
| `generation.answer` | RAG generator가 OpenAI sync/async client를 직접 생성하며 streaming도 OpenAI async completions를 사용한다. | `backend/app/agents/answer_generation/tools/generator.py:125-143`, `210-249`, `1173-1175` |
| `review.legal` | 선택적 LLM 검토가 `ENABLE_LLM_REVIEW=true`일 때 OpenAI direct client를 사용한다. | `backend/app/agents/legal_review/llm_reviewer.py:195-209`, `394-421` |
| `guardrail.input/output_moderation` | moderation이 OpenAI Moderation API를 사용하며 추론 provider 전환과 분리되어야 한다. | `backend/app/guardrail/moderation.py:24-80` |
| `embedding.openai` | embedding이 restored `vector_chunks`와 호환되는 OpenAI 1536d를 유지하며, M2-6에서 조기 교체보다 정책 분리를 한다. | `backend/app/common/embedding/openai_provider.py:24-138` |
| `api.health` | 기존 health endpoint가 supervisor OpenAI, EXAONE, embedding 체크를 분리하지만 통합 provider policy는 없다. | `backend/app/api/health.py:78-139` |

## 5. 인벤토리 표 형식

M2-1 결과 문서는 다음 표 형식을 사용한다.

| Runtime path | Node/Agent | Capability ID | Provider today | Client construction | Env vars | Model config | Fallback | Active status | M2 action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `/chat/stream` | `generation` | `generation.answer` | OpenAI | direct `OpenAI`/`AsyncOpenAI` | `OPENAI_API_KEY` | `MODEL_DRAFT_AGENT` or `LLM_MODEL` | rule/safe fallback | active | candidate for later conversion |

`Active status` 값:

- `active`: 정상 `/chat` 또는 `/chat/stream` 요청 경로에서 사용됨.
- `conditional`: env flag 또는 route가 활성화할 때만 사용됨.
- `candidate`: 구현되어 있으나 active 경로에 배선되지 않음.
- `test/script`: 테스트 전용 또는 수동 스크립트 경로.
- `legacy`: 유지되지만 신규 작업 대상은 아님.

## 6. M2-2/M3로 이관할 측정 필드

M2-1은 이후 M2/M3 코드가 emit할 수 있는 공통 필드를 권고해야 한다.

| Field | 이유 |
| --- | --- |
| `request_id` / `session_id` | LLM 호출을 chat run과 조인. |
| `node_name` | 호출을 LangGraph 노드에 매핑. |
| `capability_id` | M0-H vocabulary 재사용. |
| `provider` | `runpod_vllm`, `openai`, `anthropic`, `rule_based`, `moderation_openai`, `embedding_openai`. |
| `model` | 모델 선택과 출력 변화 비교. |
| `status` | `success`, `fallback`, `error`, `skipped`. |
| `fallback_from` / `fallback_to` | API 의존성 감소와 복원력 표시. |
| `duration_ms` | 포트폴리오 성능 숫자. |
| `prompt_tokens` / `completion_tokens` | 가능한 경우 비용/사용량 분석. |
| `error_type` / `reason_code` | 디버깅 가능성과 보안 검토. |

## 7. M2-1 검증 계획

M2-1은 docs-only이지만 근거 기반이어야 한다.

인벤토리를 작성하는 동안 다음 read-only 점검을 실행한다.

```bash
rg -n "from openai|OpenAI\(|AsyncOpenAI\(|from anthropic|Anthropic\(|AsyncAnthropic\(|ChatOpenAI\(|chat\.completions\.create|moderations\.create|embeddings\.create|ExaoneLLMClient|ToolCallingClient" backend/app backend/scripts -g '*.py'
```

```bash
rg -n "OPENAI_API_KEY|ANTHROPIC_API_KEY|EXAONE|MODEL_|EMBEDDING|MODERATION|LLM_PROVIDER" .env.example backend/app/common/config.py docker-compose.yml backend/README.md docs -g '!docs/plans/modules/M2-*'
```

```bash
python -m compileall -q backend/app/llm backend/app/agents/query_analysis backend/app/agents/answer_generation backend/app/agents/legal_review backend/app/guardrail backend/app/api
```

compile 단계는 런타임 코드가 바뀌지 않으므로 M2-1에서 선택 사항이지만, 환경에 의존성이 갖춰져 있다면 값싼 sanity check가 된다.

## 8. M2-2 handoff 기준

M2-2는 M2-1이 다음 질문에 답한 뒤에만 시작할 수 있다.

1. RunPod/local vLLM에 대해 어떤 health endpoint/script를 권위 있는 것으로 삼을 것인가?
2. 어떤 env var가 canonical인가: `EXAONE_RUNPOD_URL` vs `MODEL_EXAONE_BASE_URL`?
3. metrics에서 사용할 provider 이름은 무엇인가: `runpod_vllm`, `openai`, `anthropic`, `rule_based`?
4. 어떤 provider 호출이 active이고 어떤 것이 candidate/legacy인가?
5. 첫 M2-4 provider 전환에 가장 안전한 노드는 무엇인가?

## 9. 중단 조건

인벤토리 문서가 작성·검토되면 중단한다. provider 전환, health endpoint 변경, Agent refactor는 M2-1에서 구현하지 않는다.
