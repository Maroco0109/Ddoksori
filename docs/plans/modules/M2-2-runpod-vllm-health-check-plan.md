# M2-2 RunPod vLLM Health Check 계획

- 작성일: 2026-06-22
- 모듈: `M2-2` RunPod vLLM health check 정리
- 상위 계획: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`, `docs/plans/modules/M2-0-provider-transition-plan.md`
- 선행 완료: `M2-1` LLM 호출 경로 인벤토리 (`docs/plans/modules/M2-1-llm-call-path-inventory.md`)
- 목표: RunPod/local vLLM endpoint 상태를 **재현 가능하게** 확인하고, 성공/실패를 **provider/model/url/latency와 함께** 표시하는 health 도구를 정의한다.
- 이번 모듈에서 하지 않는 일: agent의 provider 전환(M2-4), RunPod 상시 가동, embedding/moderation 전환, LangGraph topology 변경.

## 1. 포트폴리오 목적

M2-2는 vLLM 가용성을 "켜져 있나/꺼져 있나"의 감이 아니라 **재현 가능한 숫자**(status, latency_ms, model, http_status)로 만든다. 이 기준선은 다음을 가능하게 한다.

- M2-3 provider policy(`runpod_vllm -> openai -> rule_based`) 결정의 근거.
- M2-4 첫 전환 후 "selected provider = runpod" 및 fallback 측정의 비교 기준.
- M3 측정 시스템이 수집할 provider availability/latency 필드의 출처.

## 2. M2-1 handoff 입력 (확정된 전제)

| 항목 | M2-1 확정값 |
| --- | --- |
| canonical env | `EXAONE_RUNPOD_URL` (활성 `ExaoneLLMClient` 경로가 사용) |
| 권위 health | `ExaoneLLMClient.health_check()`(`backend/app/llm/exaone_client.py:78-116`) + `/health/llm/exaone`(`backend/app/api/health.py:105-127`) |
| metrics provider 이름 | `runpod_vllm`, `openai`, `anthropic`, `rule_based` |
| 첫 M2-4 전환 후보 | `analysis.ambiguity_detector`(`detectors.py:70`) |

## 3. 확인된 현재 상태 (근거)

- `/health/llm/exaone`(`backend/app/api/health.py:105-127`): `MODEL_EXAONE_BASE_URL` 우선 → `EXAONE_RUNPOD_URL` fallback, `{base}/models` 호출, **`{status, url}`만 반환** — model/latency/provider 없음.
- `ExaoneLLMClient.health_check()`(`backend/app/llm/exaone_client.py:78-116`): `/health`(vLLM native, `/v1` 제거) 호출, **bool만 반환**.
- 전용 health 스크립트 없음 (`backend/scripts/testing/llm/`엔 `verify_compatibility.py`만 존재).
- `docs/infrastructure/runpod-vllm-setup.md`는 **EXAONE 4.0-1.2B(:19010)** 기준 — 본 모듈에서 통일할 4.5-33B와 불일치.
- env 혼재: `EXAONE_RUNPOD_URL`(:19080, 활성경로) vs `MODEL_EXAONE_BASE_URL`(:19010, MAS/candidate).

## 4. Canonical 대상 결정 — EXAONE 4.5-33B 통일

M2의 RunPod 추론 대상을 **EXAONE 4.5-33B**로 통일한다(기존 3.5-7.8B/4.0-1.2B 혼재 정리).

| 항목 | 값 |
| --- | --- |
| 모델 repo | `LGAI-EXAONE/EXAONE-4.5-33B` |
| 파라미터 | 33B (31.7B LM + 1.29B vision), 컨텍스트 262,144 |
| canonical env | `EXAONE_RUNPOD_URL` 단일화. `MODEL_EXAONE_BASE_URL`(:19010, 4.0-1.2B) 역할은 deprecate 또는 candidate로 문서화 |
| 모델 이름 env | `EXAONE_MODEL` = `LGAI-EXAONE/EXAONE-4.5-33B` |

> **env 정리는 M2-2에서 문서/`.env.example` 수준**으로만 진행한다. 활성 코드의 env 일원화(=`MODEL_EXAONE_BASE_URL` 제거)는 회귀 위험이 있어 M2-3/M2-4에서 다룬다.

## 5. 완료 기준 (M2-0 계승)

M2-2는 다음이 충족되면 완료한다.

1. `/health` 또는 `/v1/models` 성공/실패가 **provider / model / url / latency_ms / status / http_status**와 함께 표시된다.
2. RunPod이 꺼져 있어도 실패 원인(`error_type`)이 명확히 구분된다(미설정 / 연결 거부 / 타임아웃 / 응답 오류).
3. 동일 명령으로 누구나 재현 가능하다(앱 전체 기동 불필요).

## 6. 구현 산출물 명세 (M2-2 실행 세션 대상)

> 본 계획 수락 후 별도 실행 세션에서 구현한다. 경량 원칙(M2-0): 기존 코드 재사용 우선, 신규 프레임워크 금지.

### (a) 독립 health 스크립트 — 주 산출물
- 위치(안): `backend/scripts/testing/llm/check_vllm_health.py`
- 입력: `EXAONE_RUNPOD_URL`(기본), `--url` 인자로 override 가능.
- 동작: `/health`(vLLM native)와 `/v1/models`를 순차 probe, 각 latency 측정.
- 출력(JSON):
  ```json
  {
    "provider": "runpod_vllm",
    "url": "http://localhost:19080/v1",
    "model": "LGAI-EXAONE/EXAONE-4.5-33B",
    "status": "healthy | unhealthy",
    "http_status": 200,
    "latency_ms": 0,
    "error_type": null
  }
  ```
- 재사용: `ExaoneLLMClient.health_check()` 로직을 참고/재사용하되, latency·model 보고를 위해 `/v1/models` 응답 파싱을 추가. 신규 추상화는 만들지 않는다.

### (b) `/health/llm/exaone` 개선
- 대상: `backend/app/api/health.py:105-127`.
- 추가: `model`(`/v1/models` 응답에서), `latency_ms`, `provider`("runpod_vllm").
- canonical env 정렬: `EXAONE_RUNPOD_URL`을 우선하도록 정리(현재는 `MODEL_EXAONE_BASE_URL` 우선) — M2-1 canonical 결정 반영.
- 변경은 in-place 최소 수정. 응답 스키마는 기존 키 유지 + 신규 키 추가(하위 호환).

### (c) 문서 갱신
- `.env.example`: canonical EXAONE 4.5-33B 대상 명시(`EXAONE_MODEL`, `EXAONE_RUNPOD_URL`), :19010 4.0-1.2B 항목에 candidate/deprecate 주석.
- `docs/infrastructure/runpod-vllm-setup.md`: 4.5-33B 반영(커스텀 vLLM 포크, tensor-parallel, GPU 요구) — 분량이 크면 M2-2에서는 **요약 + follow-up 플래그**로 처리하고 전체 재작성은 RunPod 실제 셋업 시점으로 미룬다.

## 7. 측정 필드 (M3 연계)

스크립트·엔드포인트가 emit하는 필드는 M2-1 측정 필드와 정합:

| Field | 의미 |
| --- | --- |
| `provider` | `runpod_vllm` |
| `model` | `/v1/models` 응답의 실제 서빙 모델 |
| `url` | 체크한 endpoint |
| `status` | `healthy` / `unhealthy` |
| `http_status` | probe HTTP 코드 |
| `latency_ms` | probe 왕복 시간 (포트폴리오 성능 숫자) |
| `error_type` | `not_configured` / `connection_error` / `timeout` / `bad_response` |

## 8. RunPod 가동 방침

- **툴링 먼저.** RunPod을 지금 띄우지 않고 down/unhealthy 경로를 먼저 검증한다.
- healthy 숫자는 RunPod 셋업 후 **bounded 런 1회**로 캡처한다($180 balance 보존, 상시 가동 금지).
- EXAONE 4.5-33B는 H200×1 또는 A100-40GB×4가 필요하고 커스텀 vLLM 포크를 써야 하므로, 셋업 절차는 healthy 캡처 직전에 별도로 진행한다.

## 9. 검증 계획

M2-2 구현 시 다음을 수행한다.

```bash
# (i) URL 미설정 → not_configured
unset EXAONE_RUNPOD_URL; python backend/scripts/testing/llm/check_vllm_health.py

# (ii) 잘못된 URL → connection_error/timeout
EXAONE_RUNPOD_URL=http://localhost:9/v1 python backend/scripts/testing/llm/check_vllm_health.py

# (iii) compile sanity
python -m compileall -q backend/app/api backend/app/llm backend/scripts/testing/llm
```

- 엔드포인트: 로컬 기동 후 `curl /health/llm/exaone`로 신규 필드(model/latency_ms/provider) 확인.
- healthy 경로(iv)는 RunPod 셋업 후 bounded 런으로 별도 캡처.

## 10. Non-scope

- agent의 실제 provider 전환(M2-4).
- RunPod 상시 가동 / production 배포.
- embedding·moderation provider 전환.
- 활성 코드의 env 완전 일원화(`MODEL_EXAONE_BASE_URL` 제거) — M2-3/M2-4.
- LangGraph topology 변경.

## 11. 리스크

| 리스크 | 완화 |
| --- | --- |
| EXAONE 4.5-33B 비용/VRAM(H200/4×A100-40GB) | bounded 런만, healthy 캡처는 1회 |
| 커스텀 vLLM 포크 의존(`add-exaone4_5`) | 셋업 절차를 healthy 캡처 직전 별도 검증, M2-2는 도구/문서까지만 |
| env 혼재 정리 중 회귀 | M2-2는 문서/`.env.example`·health endpoint만, 활성 코드 env 일원화는 후속 모듈 |
| 33B JSON 출력 안정성(후속 M2-4 영향) | M2-2 범위 아님, M2-4에서 확인 |

## 12. M2-3 handoff

M2-2 완료 후 M2-3는 다음을 받는다.
- 재현 가능한 vLLM health 도구 + 측정 필드.
- canonical 대상(EXAONE 4.5-33B / `EXAONE_RUNPOD_URL`) 확정.
- 이를 근거로 provider policy(`runpod_vllm -> openai -> rule_based`)와 node별 fallback 순서를 결정.

## 13. 중단 조건

본 계획 문서로 M2-2 **계획**을 확정한다. 실제 health 스크립트·엔드포인트 구현은 계획 수락 후 별도 실행 세션에서 진행하며, 모듈 단위 1개씩 원칙을 따른다.
