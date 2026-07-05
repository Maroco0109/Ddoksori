# `app/llm/` — LLM 클라이언트 레이어

DDOKSORI의 모든 변형(variant)이 공유하는 **LLM 클라이언트/프로바이더 레이어**. 모델 호출을 프로바이더별 클라이언트로 캡슐화하고 싱글톤으로 재사용한다. 변형별 아키텍처/측정 비교는 [변형 시스템 아키텍처](../../../docs/architecture/2026-07-05-variant-system-architecture.md) 참조.

> 참고: 이 디렉터리는 **모델 호출 프리미티브**만 제공한다. "어느 변형이 언제 무엇을 호출하는가"의 오케스트레이션은 `app/supervisor/`(A/A-hub)와 `app/variant_b/`(B)에 있다.

---

## 구성 파일

| 파일 | 역할 |
| --- | --- |
| `providers/factory.py` | **`LLMProviderFactory`** — OpenAI / EXAONE(vLLM) / Anthropic 클라이언트를 싱글톤으로 생성·관리. 편의 함수 `get_openai_client()`, `get_exaone_client(domain=...)`, `get_anthropic_client()`, `reset_all_clients()`. |
| `exaone_client.py` | **`ExaoneLLMClient`** — RunPod 상의 vLLM(OpenAI 호환)으로 EXAONE 모델 호출. 서버 장애 시 `LLMUnavailableError`를 던져 상위의 규칙 기반 폴백을 유도. |
| `tool_calling_client.py` | **`ToolCallingClient`** — LangChain `ChatOpenAI` + `bind_tools()`로 vLLM tool-calling 지원. `ToolCallingUnavailableError`. |
| `query_cache.py` | **`QueryCache`**, `COMMON_REWRITES` — 쿼리 재작성 캐시(초기 단일-RAG 유산, MAS 전환 후 대부분 미사용/보관). |
| `__init__.py` | 위 심볼 export. |

---

## 프로바이더별 클라이언트

### OpenAI (`get_openai_client`)
- env: `OPENAI_API_KEY`
- 용도: A/A-hub의 supervisor·generation·review(gpt-4o 계열), B-frontier의 ReAct 모델(gpt-4o-mini). 미설정 시 `None` 반환 → 상위에서 폴백/규칙 처리.

### EXAONE via vLLM (`get_exaone_client`)
- env: `EXAONE_RUNPOD_URL`(공유), `RETRIEVAL_LLM_{DOMAIN}_URL`(도메인별: law/criteria/case/counsel), `EXAONE_RUNPOD_API_KEY`
- 자체 호스팅 오픈모델(EXAONE 4.5-33B)을 RunPod H100 + vLLM(OpenAI 호환)으로 서빙. 도메인별 독립 인스턴스 또는 공유 인스턴스.
- 용도: B-exaone의 ReAct 모델(연구/비교 전용). 파드가 떠 있어야 함.

### Anthropic (`get_anthropic_client`)
- env: `ANTHROPIC_API_KEY`. 패키지/키 미설치 시 `None`.
- 용도: 폴백 체인(예: supervisor 폴백 Claude). 선택적.

---

## 변형 ↔ 클라이언트 매핑

| 변형 | 라우팅 | 답변 생성 | 사용 클라이언트 |
| --- | --- | --- | --- |
| **A** (결정론 MAS) | 규칙(LLM 미사용) | gpt-4o | OpenAI (generation/review) |
| **A-hub** (LLM 라우팅) | gpt-4o (`SUPERVISOR_LLM_*`) | gpt-4o | OpenAI (라우팅 + generation/review) |
| **B-frontier** (ReAct) | LLM tool-calling | gpt-4o-mini | OpenAI (`ChatOpenAI`) |
| **B-exaone** (ReAct) | LLM tool-calling | EXAONE 4.5-33B | vLLM(OpenAI 호환) via `EXAONE_RUNPOD_URL` |

> B는 `app/variant_b/model.py`의 `get_chat_model(spec)`으로 `ChatOpenAI` 객체를 직접 만든다(base_url 스왑). A/A-hub의 supervisor LLM은 `app/supervisor/graph_mas.py`의 `_create_supervisor_llm()`가 생성한다. 즉 이 팩토리(`providers/factory.py`)는 주로 검색/보조 경로에서 쓰이고, 변형별 주 모델 객체는 각 오케스트레이션 모듈이 관리한다.

---

## 주요 환경변수

| 변수 | 용도 |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI 호출(A/A-hub/B-frontier) |
| `ANTHROPIC_API_KEY` | Anthropic 폴백(선택) |
| `EXAONE_RUNPOD_URL` / `EXAONE_RUNPOD_API_KEY` | EXAONE vLLM 엔드포인트(B-exaone) |
| `EXAONE_MODEL` | EXAONE 모델 ID (기본 `LGAI-EXAONE/EXAONE-4.5-33B`) |
| `RETRIEVAL_LLM_{LAW,CRITERIA,CASE,COUNSEL}_URL` | 도메인별 EXAONE 인스턴스 |
| `SUPERVISOR_LLM_ENABLED` / `SUPERVISOR_LLM_MODEL` | A-hub의 LLM 슈퍼바이저 라우팅 활성/모델(기본 gpt-4o) |
| `VARIANT_B_FRONTIER_MODEL` | B-frontier 모델(기본 `gpt-4o-mini`) |

---

## 주의 / 유지보수 노트

- `exaone_client.py`의 헤더 주석은 초기 도입 당시의 "EXAONE 3.5 2.4B"를 언급하지만, **현재 서빙 대상 모델은 EXAONE 4.5-33B**(`EXAONE_MODEL` 기본값)이다. 클라이언트 코드는 모델-불문(OpenAI 호환)이라 동작에는 영향 없음.
- 모든 클라이언트는 싱글톤. 테스트에서 프로바이더를 갈아끼울 때는 `reset_all_clients()` 사용.
- 키/URL 미설정 시 예외 또는 `None`으로 degrade → 상위 오케스트레이션이 규칙 기반/폴백으로 처리(하드 실패 회피).
