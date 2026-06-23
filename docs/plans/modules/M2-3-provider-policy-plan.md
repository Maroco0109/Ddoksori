# M2-3 Provider Policy 결정 (계획서)

- 작성일: 2026-06-23
- 모듈: `M2-3` 기본 provider와 fallback 순서 확정
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`, `docs/plans/modules/M2-0-provider-transition-plan.md`
- 선행 완료: M2-1 LLM 호출 경로 인벤토리(`M2-1-llm-call-path-inventory.md`), M2-2 RunPod vLLM health check(EXAONE 4.5-33B H100 baseline latency 467.8ms 캡처)
- 성격: **결정 문서(provider policy doc)를 작성하기 위한 계획서**. 본 계획서는 런타임 코드를 바꾸지 않는다. 정책 결과 문서 작성은 M2-3 실행에서, 코드 전환은 M2-4/M2-5에서 한다.
- 사용자 확정 방향(2026-06-23): **"원칙 runpod 우선 + 점진 전환"** — 정책상 `runpod_vllm` 우선을 목표 원칙으로 선언하되, 실제 코드 전환은 M2-4(최소 1개)→M2-5(노드별)로 점진 적용.

## 1. 목표 / 비목표

### 목표
- node(capability)별 **기본 primary provider**와 **fallback 순서**를 확정한다.
- canonical provider 이름과 env → provider 매핑을 한 곳에 명문화한다.
- 얇은 `call_with_fallback` 헬퍼의 **계약(책임/입출력)** 초안을 정의한다(구현은 M2-4).
- 호출마다 emit할 측정 필드를 확정한다(저장은 M3).

### 비목표 (이번 모듈에서 하지 않음)
- 런타임 코드 변경(`factory.py`, `detectors.py`, `supervisor.py`, generator 등) — M2-4/M2-5.
- `call_with_fallback` 실제 구현 — M2-4.
- RunPod 연결/측정 런 — M2-4 smoke부터.
- DB 저장(`llm_calls` table) — M3.
- embedding/moderation provider 전환 — M2-6 / 비대상.
- `ProviderPolicy`/`ProviderRegistry`/circuit-breaker 등 신규 추상화 framework 신설 — M2-0 §4.1·§8에 의해 금지. 기존 `LLMProviderFactory` 재사용 + 얇은 폴백 헬퍼 1개로 제한.

## 2. RunPod pod 가동 안내 (중요)

- **M2-3는 RunPod pod 가동이 필요 없다.** 정책 결정/문서 작업이라 LLM 호출이 없다.
- pod는 **M2-4(단일 agent 전환 + smoke 측정) 시점부터 필요**하다. 그 시점에 사용자에게 "이제 pod를 켜 주세요(Stop → Resume)"라고 명시적으로 안내한다.
- 그 전까지 H100 pod은 **Stop 상태로 유지**해야 과금이 멈춘다(M2-2 마무리 권고).

## 3. 정책 결과 문서가 담을 내용 (M2-3 실행 산출물 = `M2-3-provider-policy.md`)

### 3.1 Canonical provider 이름
M2-1 §1·§3과 일치시킨다.

| provider id | 의미 | 분류 |
| --- | --- | --- |
| `runpod_vllm` | RunPod/local vLLM EXAONE (OpenAI 호환) | 추론 primary 목표 |
| `openai` | OpenAI Chat Completions | 추론 fallback |
| `anthropic` | Anthropic (supervisor 전용 fallback) | 추론 fallback |
| `rule_based` | LLM 전무 시 규칙 기반/stub | 최종 안전망 |
| `embedding_openai` | OpenAI embeddings (분리 항목) | 비대상(M2-6) |
| `moderation_openai` | OpenAI Moderation (분리 항목) | 비대상(보안 분리) |

### 3.2 Env → provider 매핑 (`backend/app/llm/providers/factory.py`)

| provider | env var | factory 접근자 |
| --- | --- | --- |
| `runpod_vllm` | `EXAONE_RUNPOD_URL` (+도메인별 `RETRIEVAL_LLM_{DOMAIN}_URL`), `EXAONE_RUNPOD_API_KEY` | `get_exaone_client(domain=...)` |
| `openai` | `OPENAI_API_KEY` | `get_openai_client()` |
| `anthropic` | `ANTHROPIC_API_KEY` | `get_anthropic_client()` |

> 직접 `OpenAI()`/`AsyncOpenAI()`/`ChatOpenAI()` 생성부(25곳+)를 위 접근자 경유로 교체하는 것은 M2-4/M2-5 작업이다. 본 정책은 "어떤 노드가 어떤 접근자를 거쳐야 하는지"만 확정한다.

### 3.3 노드별 정책 표 (원칙 runpod 우선 + 점진 전환)

| 노드(capability) | 원칙 primary | fallback chain | 전환 모듈 | 현행 (file:line) |
| --- | --- | --- | --- | --- |
| `analysis.ambiguity_detector` | `runpod_vllm` | → `openai`(gpt-4o-mini) → `rule_based`(False) | **M2-4 첫 전환** | EXAONE→gpt-4o-mini 폴백 이미 배선 (`agents/query_analysis/detectors.py:67-105`) |
| `analysis.query_classifier` | `runpod_vllm`(목표) | → `openai` → `rule_based`(ambiguous) | M2-5 | OpenAI only, provider 폴백 없음 → **폴백 보강 필요** (`query_analysis/llm_classifier.py:166`, `classifier.py:205`) |
| `analysis.query_expander` | `runpod_vllm`(목표) | → `openai` → `rule_based` | M2-5 | OpenAI (`query_analysis/llm_expander.py:81`) |
| `supervisor.routing` | `runpod_vllm`(목표) | → `openai` → `anthropic` → `rule_based` | M2-5 | openai→anthropic→rule (`supervisor/nodes/supervisor.py:203-232`) |
| `generation.answer` | `runpod_vllm`(목표, **최후 전환**) | → `openai` → `rule_based`(stub) | M2-5 마지막 | OpenAI sync/async+stream, 위험 최고 (`answer_generation/tools/generator.py:139-141`) |
| `review.legal` / `retrieval.case_metadata` / `retrieval.hyde` (조건부) | 조건부 | 각 현행 폴백 유지 | M2-5 | conditional (M2-1 §2) |
| `embedding.openai` | `openai` 유지 | — | **M2-6** | 1536d restored DB 호환, 비대상 (`retrieval/tools/unified_retriever.py:354`) |
| `guardrail.moderation` | `openai` 유지 | — | 비대상 | 보안 분리 (`guardrail/moderation.py:30`) |

### 3.4 `call_with_fallback` 헬퍼 계약 초안 (구현은 M2-4)
기존 supervisor 폴백 패턴(`supervisor/nodes/supervisor.py:203-232`의 primary→fallback 체인, `AsyncLLMWrapper`)을 본떠 설계만 한다.

- **책임**: provider chain을 순서대로 시도 → 첫 성공 결과 반환 → 각 시도의 측정 필드 emit → 전부 실패 시 `rule_based`/stub로 안전 종료.
- **입력(초안)**: 정렬된 provider chain, 각 provider의 호출 콜러블, capability/node 식별자, timeout.
- **출력(초안)**: 결과 텍스트 + 측정 메타(§3.5).
- **위치·시그니처·동기/비동기 변형**: M2-4에서 ambiguity_detector 전환과 함께 확정.

### 3.5 측정 필드 (emit만, 저장은 M3 — M2-1 §4 재사용)
`request_id`/`session_id`, `node_name`, `capability_id`, `provider`(selected), `model`, `status`(success/fallback/error/skipped), `fallback_from`/`fallback_to`, `duration_ms`, `prompt_tokens`/`completion_tokens`(가능 시), `error_type`/`reason_code`.

> M2-0 합의: RunPod은 테스트 등급(간헐 가동)이므로 `provider`(selected)와 `fallback_*`를 **반드시** 기록해야 fallback rate/latency 같은 의미 있는 숫자가 남는다.

## 4. 결정 근거
- 점진 전환은 roadmap M2-4(최소 1개)→M2-5(노드별) 순차전환, RunPod 테스트 등급(간헐 가동) 제약(M2-0 §4.2)과 정합한다.
- `runpod_vllm`을 원칙 primary로 "선언"하면 포트폴리오상 provider abstraction/cost-risk 감소 의도가 문서로 드러나고, 실제 전환은 위험 낮은 순서로 진행해 회귀 위험을 통제한다.
- 신규 추상화 framework 금지(M2-0 §8) — 5개 이상 모듈 회귀 위험 회피.

## 5. 완료 기준 / 검증
- 정책 결과 문서(`M2-3-provider-policy.md`)가 §3의 6개 요소(provider 이름, env 매핑, 노드별 정책 표, `call_with_fallback` 계약, 측정 필드, 비목표)를 모두 포함하고, M2-1 인벤토리·M2-0 제약과 file:line 수준에서 모순이 없으면 M2-3 완료.
- 검증 방법: read-only 대조. 코드/런타임 변경 0건.
- M2-3 완료 후 사용자와 결과를 논의/수용한 뒤에만 M2-4로 진행한다.

## 6. Next gate
M2-3 정책 결과 문서 작성. 그 전에는 M2-4 단일 agent 전환을 시작하지 않는다. M2-4 진입 시 사용자에게 pod 가동을 요청한다(§2).
