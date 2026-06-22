# M2 Provider Transition Detailed Plan

- 작성일: 2026-06-22
- 모듈: `M2` OpenAI API 중심 호출을 RunPod/local LLM 중심으로 전환
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`
- 선행 완료: M1 local RAG reproducibility, M0-H architecture baseline
- 목표: OpenAI 중심 추론 경로를 RunPod/local vLLM 우선 구조로 전환하되, 임베딩과 보안 moderation은 분리해 비용/안정성/측정 가능성을 개선한다.
- 이번 문서에서 하지 않는 일: provider 구현, endpoint 수정, RunPod 연결 실행, Agent 코드 변경, DB migration.

## 1. Portfolio objective

M2는 단순히 “OpenAI 대신 local model을 쓴다”가 아니다. 사용자의 포트폴리오 기준상 M2의 목표는 다음을 증명하는 것이다.

1. AI backend 시스템에서 provider abstraction과 fallback policy를 설계할 수 있다.
2. 외부 API 남용을 줄이고 비용/장애 의존성을 관리할 수 있다.
3. provider/model/fallback/latency/token 사용량을 후속 M3에서 측정 가능한 형태로 만든다.
4. AI Security 관심 기업을 위해 LLM provider, moderation, embedding, guardrail 의존성을 분리해서 설명할 수 있다.

## 2. M0-H integration

M2는 M0-H의 capability/gate vocabulary를 기준으로 진행한다.

| M0-H 항목 | M2 의미 |
| --- | --- |
| `llm.provider_factory` | provider client 생성과 fallback 정책의 중심 후보 |
| `llm.exaone_vllm` | RunPod/local vLLM OpenAI-compatible endpoint 후보 |
| `generation.answer` | answer generation provider 전환의 주요 대상 |
| `analysis.query_classifier` | query classification provider 전환 또는 rule fallback 측정 대상 |
| `supervisor.routing` | supervisor LLM/rule fallback 전환 대상 |
| `G-query-analysis-valid` | classifier가 provider 변경 후에도 유효한 route를 내는지 확인 |
| `G-generation-sufficiency` | answer generation이 충분한 근거/안전 fallback을 반환하는지 확인 |
| `G-supervisor-iteration` | provider 장애 시 supervisor loop/fallback이 안전하게 끝나는지 확인 |
| `G-sse-complete` | frontend smoke에서 `/chat/stream` complete/error event를 비교 가능하게 유지 |

## 3. Current evidence snapshot

현재 repo에는 provider 관련 코드가 이미 존재하지만, 실제 호출 경로는 일관된 factory/policy로 묶여 있지 않다.

| 영역 | 현재 증거 | 계획상 해석 |
| --- | --- | --- |
| Provider factory | `backend/app/llm/providers/factory.py:32-198` | OpenAI/EXAONE/Anthropic client factory가 있으나 모든 Agent가 이를 쓰지는 않는다. |
| RunPod/vLLM client | `backend/app/llm/exaone_client.py:27-201` | OpenAI-compatible EXAONE client와 `/health` check가 있음. |
| Tool calling candidate | `backend/app/llm/tool_calling_client.py:25-147` | M2 핵심 전환 범위가 아니라 future/candidate로 유지. |
| Supervisor LLM | `backend/app/supervisor/nodes/supervisor.py:58-86`, `203-227` | OpenAI primary + Anthropic fallback + rule fallback 구조. RunPod 우선은 아직 아님. |
| Query classifier/expander | `backend/app/agents/query_analysis/llm_classifier.py:143-222`, `llm_expander.py:60-136` | OpenAI Async client 직접 생성. |
| Answer generation | `backend/app/agents/answer_generation/tools/generator.py:125-143`, `210-249`, `1173-1175` | OpenAI sync/async client 직접 사용, streaming도 OpenAI 의존. |
| Legal review | `backend/app/agents/legal_review/llm_reviewer.py:195-209`, `394-421` | LLM review가 활성화될 때 OpenAI client 직접 사용. |
| Moderation guardrail | `backend/app/guardrail/moderation.py:24-80` | OpenAI Moderation API 사용. M2 추론 provider 전환과 분리해야 함. |
| Embedding | `backend/app/common/embedding/openai_provider.py:24-138`, `backend/app/agents/retrieval/tools/unified_retriever.py:352-356` | restored DB가 OpenAI 1536d embedding 기반이므로 M2에서는 유지하고 M2-6에서 분리 정책을 명확히 함. |
| Health endpoints | `backend/app/api/health.py:78-139` | `/health/llm/supervisor`, `/health/llm/exaone`, `/health/embedding`은 있으나 provider policy/status 통합은 부족. |

## 4. M2 execution principles

- 한 번에 전체 Agent를 바꾸지 않는다.
- `embedding`과 `moderation`은 추론 LLM provider 전환과 분리한다.
- OpenAI는 즉시 제거하지 않고 fallback 또는 embedding/moderation provider로 남긴다.
- RunPod/local endpoint가 꺼져 있어도 실패 원인이 명확해야 한다.
- provider 변경은 항상 숫자를 남긴다: status, latency, fallback count, selected provider/model, error reason.
- M2 구현은 후속 M3 `llm_calls` 저장으로 이어질 수 있게 event field를 미리 정의한다.

## 5. Module breakdown

| 순서 | 모듈 | 목표 | 주요 산출물 | 완료 기준 |
| --- | --- | --- | --- | --- |
| M2-1 | LLM call path inventory | Agent별 OpenAI/Anthropic/EXAONE/embedding/moderation 호출 경로 확정 | `M2-1-llm-call-path-inventory.md` | active/candidate/deprecated 호출 경로와 전환 후보가 표로 정리됨 |
| M2-2 | RunPod vLLM health check 정리 | vLLM endpoint 상태를 재현 가능하게 확인 | health check script 또는 API 정리 문서/작은 코드 | `/health` 또는 `/v1/models` 성공/실패가 provider/model/url/latency와 함께 표시 |
| M2-3 | Provider policy 결정 | 기본 provider와 fallback 순서 확정 | provider policy doc | `runpod_vllm -> openai -> rule_based` 등 node별 정책 확정 |
| M2-4 | 단일 Agent 전환 | 가장 작은 runtime 호출 하나를 RunPod 우선으로 변경 | 1개 Agent 코드 변경 + smoke | selected provider가 RunPod로 기록되고 fallback도 검증됨 |
| M2-5 | Agent별 순차 전환 | 나머지 Agent를 하나씩 provider policy에 맞춤 | 작은 PR/commit 여러 개 | 각 Agent smoke 통과, fallback rate/latency 기록 |
| M2-6 | Embedding provider 분리 | 추론 LLM과 embedding 의존성 명시 분리 | embedding policy/config doc/code | OpenAI embedding 유지/대체 여부와 1536d DB compatibility가 명확함 |

## 6. Recommended target sequence

M2-4의 첫 전환 후보는 **answer generation**보다 작고 위험이 낮은 **query classifier 또는 query expander**를 우선 검토한다.

다만 최종 선택은 M2-1 inventory에서 아래 기준으로 결정한다.

| 기준 | 우선순위 |
| --- | --- |
| fallback이 이미 존재하는가 | 높음 |
| output schema가 작고 테스트하기 쉬운가 | 높음 |
| frontend `/chat/stream` 전체 completion에 미치는 위험이 낮은가 | 높음 |
| RunPod/local vLLM이 JSON output을 안정적으로 만들 수 있는가 | 확인 필요 |
| portfolio demo에서 provider 전환 효과가 잘 보이는가 | 중간 |

## 7. Acceptance metrics for M2

M2 완료 시 최소 다음 숫자를 제시할 수 있어야 한다.

| Metric | 의미 |
| --- | --- |
| provider availability | RunPod/OpenAI/Anthropic/embedding/moderation status |
| selected provider/model | node별 실제 선택된 provider와 model |
| fallback count/rate | RunPod 실패 시 OpenAI/rule fallback 발생률 |
| latency | provider health와 generation/classification latency |
| token usage | 가능한 경우 prompt/completion token 수 |
| endpoint pass/fail | `/health/llm/*`, `/chat/stream`, targeted Agent smoke pass/fail |
| cost-risk reduction evidence | OpenAI 추론 호출 경로 감소 또는 fallback-only 전환 증거 |

## 8. Non-scope until later phases

- M3의 `llm_calls` DB table 구현은 M2에서 하지 않는다. 단, field 설계는 M2 문서에 남긴다.
- M4 Goldenset security runner는 M2에서 하지 않는다.
- local embedding 모델 전환은 M2-6 이전에 하지 않는다.
- Tool calling 활성화는 M2 범위가 아니다.
- LangGraph topology 재작성은 M2 범위가 아니다.

## 9. Next gate

M2-1에서 실제 LLM 호출 경로 inventory를 작성한다. M2-1 완료 전에는 M2-2 health check 구현이나 M2-4 provider 전환을 시작하지 않는다.
