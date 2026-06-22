# RunPod vLLM Setup Guide — EXAONE 4.5-33B

DDOKSORI의 M2 canonical RunPod 추론 모델인 **EXAONE 4.5-33B**(`LGAI-EXAONE/EXAONE-4.5-33B`)를
RunPod GPU Pod에서 vLLM(OpenAI-compatible)으로 서빙하고, 로컬 백엔드와 연결해 health/추론을
확인하는 절차를 설명한다.

> **최종 업데이트**: 2026-06-22 (EXAONE 4.5-33B 기준 재작성)
>
> 이전 1.2B(EXAONE 4.0-1.2B, :19010) 절차는 deprecated다. canonical env는 `EXAONE_RUNPOD_URL`,
> 대상 모델은 EXAONE 4.5-33B로 통일한다(M2-2 결정). 과거 문서가 참조하던
> `scripts/runpod/*.sh`는 repo에 존재하지 않으므로, 본 문서는 인라인 명령을 사용한다.

---

## 0. 요약 (한눈에)

| 단계 | 위치 | 핵심 |
| --- | --- | --- |
| 1. 모델 구동 | RunPod Pod | 커스텀 vLLM 포크 설치 → `vllm serve ... --tensor-parallel-size 2` (Pod 내부 :8000) |
| 2. 로컬 연결 | 로컬 | SSH 터널 `19080→8000` → `EXAONE_RUNPOD_URL=http://localhost:19080/v1` |
| 3. 연결 확인 | 로컬 | `python backend/scripts/testing/llm/check_vllm_health.py` (exit 0 = healthy) |

> ⚠️ **비용 주의**: EXAONE 4.5-33B는 H200×1 또는 A100-40GB×4가 필요하다. RunPod balance가
> 테스트용($180 수준)이므로 **상시 가동하지 말고** 측정/테스트가 끝나면 Pod를 정지한다.

---

## 1. RunPod 환경에서 모델 다운로드 + 구동

### 1.1 Pod 배포

1. [RunPod](https://www.runpod.io/) 로그인 → **Pods** → **+ Deploy**.
2. GPU 선택:
   - **권장**: H200 ×1 (단일 GPU로 충분)
   - **대안**: A100-40GB ×4 (tensor-parallel)
3. 템플릿: **RunPod PyTorch**(CUDA 12.x) 또는 vLLM 전용 템플릿.
4. **디스크 ≥ 120GB** 확보 (33B 가중치 ~66GB + 캐시/여유).
5. SSH 접근을 위해 RunPod에 SSH 공개키 등록.
6. **Deploy** 후 Pod의 `Public IP` 또는 `Connect → SSH` 정보를 확인.

### 1.2 의존성 설치 (Pod 내부)

SSH로 접속한다.

```bash
ssh root@<POD_IP> -p <SSH_PORT> -i ~/.ssh/id_rsa
```

EXAONE 4.5-33B는 **표준 vLLM로는 서빙되지 않으며** 커스텀 포크가 필요하다.

```bash
# uv 미설치 시
pip install -U uv

# EXAONE 4.5 전용 vLLM + transformers 포크 설치
uv pip install git+https://github.com/lkm2835/vllm.git@add-exaone4_5
uv pip install git+https://github.com/nuxlear/transformers.git@add-exaone4_5-v5.3.0.dev0
```

> Hugging Face gated 모델일 경우 `huggingface-cli login` 또는 `export HF_TOKEN=...`가 필요할 수 있다.

### 1.3 vLLM 서버 구동 (Pod 내부)

```bash
vllm serve LGAI-EXAONE/EXAONE-4.5-33B \
    --served-model-name LGAI-EXAONE/EXAONE-4.5-33B \
    --port 8000 \
    --tensor-parallel-size 2 \
    --max-model-len 262144 \
    --reasoning-parser qwen3 \
    --enable-auto-tool-choice \
    --tool-call-parser hermes \
    --limit-mm-per-prompt '{"image": 64}' \
    --speculative_config '{"method": "mtp", "num_speculative_tokens": 3}'
```

- 최초 구동 시 Hugging Face에서 가중치를 다운로드한다(수 분~수십 분).
- `Application startup complete` / `Uvicorn running on http://0.0.0.0:8000` 로그가 뜨면 준비 완료.
- 단일 GPU(H200)면 `--tensor-parallel-size 1`로 조정 가능.

> **정합성 규칙**: `--served-model-name` 값은 로컬 `.env`의 `EXAONE_MODEL`과 **반드시 동일**해야
> 추론(`/v1/chat/completions`)이 동작한다. 본 문서는 양쪽 모두 `LGAI-EXAONE/EXAONE-4.5-33B`로 맞춘다.
> (HF 모델 카드 예시는 짧은 별칭 `EXAONE-4.5-33B`를 쓰므로, 별칭을 쓰려면 `.env`도 동일하게 바꾼다.)

### 1.4 Pod 내부 1차 확인

서버가 뜬 같은 Pod에서:

```bash
curl http://localhost:8000/health        # 200 OK 면 liveness 정상
curl http://localhost:8000/v1/models      # data[0].id 에 모델명이 보이면 정상
```

---

## 2. 모델을 로컬 환경과 연결

vLLM은 Pod 내부 `:8000`에서 서빙된다. 로컬 백엔드의 canonical 포트는 `:19080`이다.

### 2.1 SSH 터널링 (로컬, 새 터미널)

```bash
# 로컬 19080  ->  Pod 내부 8000
ssh -N -L 19080:localhost:8000 root@<POD_IP> -p <SSH_PORT> -i ~/.ssh/id_rsa
```

- `-N`: 원격 명령 없이 터널만 유지. 이 터미널은 켜둔 채로 둔다.
- 연결 후 로컬에서 vLLM API가 `http://localhost:19080/v1`로 노출된다.

> **대안 (RunPod Proxy URL)**: SSH 터널 대신 RunPod이 제공하는
> `https://<pod-id>-8000.proxy.runpod.net/v1`를 직접 써도 된다. 이 경우 `EXAONE_RUNPOD_URL`에
> 해당 Proxy URL을 넣고 SSH 터널은 생략한다.

### 2.2 로컬 `.env` 설정

`.env`(템플릿은 `.env.example`)에 canonical 값을 설정한다.

```env
EXAONE_RUNPOD_URL=http://localhost:19080/v1
EXAONE_RUNPOD_API_KEY=dummy
EXAONE_MODEL=LGAI-EXAONE/EXAONE-4.5-33B
EXAONE_MODEL_SIZE=33B
EXAONE_TIMEOUT=10
```

> Proxy URL을 쓰면 `EXAONE_RUNPOD_URL`만 그 값으로 교체한다.

---

## 3. 연결 확인 (헬스 체크 + 테스트)

### 3.1 로컬에서 직접 probe

```bash
# /v1/models — 모델 id 확인
curl http://localhost:19080/v1/models

# /health — vLLM liveness
curl http://localhost:19080/health
```

### 3.2 프로젝트 health 스크립트 (권장, 재현 가능)

`EXAONE_RUNPOD_URL`을 읽어 provider/model/url/latency를 JSON으로 출력한다. 종료코드 0이면 healthy.

```bash
# .env 로딩 환경(예: docker compose 또는 export)에서
python backend/scripts/testing/llm/check_vllm_health.py

# 또는 URL을 직접 지정
python backend/scripts/testing/llm/check_vllm_health.py --url http://localhost:19080/v1
```

정상 출력 예:

```json
{
  "provider": "runpod_vllm",
  "url": "http://localhost:19080/v1",
  "model": "LGAI-EXAONE/EXAONE-4.5-33B",
  "status": "healthy",
  "http_status": 200,
  "latency_ms": 12.3,
  "vllm_health": true,
  "error_type": null
}
```

실패 시 `error_type`로 원인을 구분한다: `not_configured`(URL 미설정) / `connection_error`(터널 끊김·Pod 정지) / `timeout` / `bad_response`.

### 3.3 백엔드 API 경유 확인

백엔드(로컬 compose 등)가 떠 있으면:

```bash
curl http://localhost:8000/health/llm/exaone
# -> {"status":"healthy","provider":"runpod_vllm","url":...,"model":...,"latency_ms":...}
```

### 3.4 추론 스모크 테스트 (OpenAI 호환)

실제 생성이 되는지 확인한다. `model` 값은 `--served-model-name`/`EXAONE_MODEL`과 동일해야 한다.

```bash
curl http://localhost:19080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "LGAI-EXAONE/EXAONE-4.5-33B",
    "messages": [{"role": "user", "content": "안녕하세요, 한 문장으로 자기소개 해주세요."}],
    "max_tokens": 64
  }'
```

`choices[0].message.content`에 한국어 응답이 오면 end-to-end 연결 성공이다.

---

## 4. 측정 캡처 (M2-2 healthy 기준선)

healthy 상태에서 다음을 **bounded(수 회)**로 실행해 측정값을 기록한다(balance 보존).

```bash
python backend/scripts/testing/llm/check_vllm_health.py   # latency_ms, model 기록
```

- 기록 항목: `status`, `model`, `latency_ms`, `http_status`.
- 이 값이 M2-3 provider policy 결정과 M3 측정 시스템의 가용성 기준선이 된다.
- 측정이 끝나면 **RunPod Pod를 Stop**해 과금을 멈춘다.

---

## 5. Troubleshooting

| 증상 | 원인/조치 |
| --- | --- |
| `check_vllm_health.py`가 `connection_error` | SSH 터널이 끊겼거나 Pod/vLLM이 정지. 터널 재연결, vLLM 로그 확인 |
| `/v1/models`는 200인데 추론이 404/400 | `model` 값이 `--served-model-name`과 불일치. `EXAONE_MODEL`을 일치시킬 것 |
| OOM (구동 중 메모리 부족) | `--max-model-len` 축소, `--tensor-parallel-size` 증가, 더 큰 VRAM GPU 사용 |
| 가중치 다운로드 실패 | Pod 디스크 용량 확인(≥120GB), HF 토큰/네트워크 확인 |
| 표준 vLLM로 실행해 모델 로드 실패 | 반드시 `add-exaone4_5` 커스텀 포크 설치(§1.2) |

---

## 6. 참고

- 모델 카드: https://huggingface.co/LGAI-EXAONE/EXAONE-4.5-33B
- canonical env / health 도구 결정: `docs/plans/modules/M2-2-runpod-vllm-health-check-plan.md`
- 호출 경로 인벤토리: `docs/plans/modules/M2-1-llm-call-path-inventory.md`
