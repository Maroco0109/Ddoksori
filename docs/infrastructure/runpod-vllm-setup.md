# RunPod vLLM Setup Guide

This guide describes how to set up and run the EXAONE-4.0-1.2B model using vLLM on RunPod for the DDOKSORI project.

> **최종 업데이트**: 2026-01-27 (스크립트 기반 배포 추가)

## Prerequisites

- RunPod account with credits.
- GPU Pod:
  - **단일 인스턴스**: 24GB+ VRAM (RTX 4090)
  - **4개 인스턴스 (권장)**: 48GB VRAM (A40, A100)
- SSH key configured in RunPod.

## VRAM Requirements

| 구성 | 모델 | VRAM 사용 | GPU 권장 |
|-----|------|----------|---------|
| 단일 인스턴스 | EXAONE 1.2B | ~4GB | RTX 4090 (24GB) |
| **4개 인스턴스** | EXAONE 1.2B × 4 | ~16GB | **A40 (48GB)** |

> EXAONE 1.2B는 가벼운 모델이므로 A40 하나에 4개 인스턴스 운영이 비용 효율적입니다.

## Quick Start (스크립트 사용)

### 권장: 단일 Pod에서 4개 인스턴스 (A40 등 대용량 GPU)

EXAONE 1.2B는 인스턴스당 ~4GB VRAM → **A40(48GB)에서 4개 충분히 실행 가능**

```bash
# 1. RunPod에 스크립트 복사
scp scripts/runpod/start_vllm_multi.sh root@<pod-ip>:~/

# 2. RunPod 터미널에서 실행 (4개 인스턴스 자동 시작)
ssh root@<pod-ip>
bash start_vllm_multi.sh

# 3. 로컬에서 4개 포트 연결 (새 터미널)
./scripts/runpod/connect_local.sh --pod-ip <pod-ip> --multi-port
```

### 대안 A: 단일 인스턴스 (공유)

```bash
# 1. RunPod에 스크립트 복사
scp scripts/runpod/start_vllm.sh root@<pod-ip>:~/

# 2. RunPod 터미널에서 실행
ssh root@<pod-ip>
bash start_vllm.sh

# 3. 로컬에서 SSH 터널링 (새 터미널)
./scripts/runpod/connect_local.sh --pod-ip <pod-ip>
```

### 대안 B: 4개 Pod 각각 (소용량 GPU)

```bash
# 1. 각 Pod에 스크립트 복사 후 도메인별로 실행
scp scripts/runpod/start_vllm.sh root@<pod-ip-1>:~/
ssh root@<pod-ip-1> "bash start_vllm.sh --domain law"

scp scripts/runpod/start_vllm.sh root@<pod-ip-2>:~/
ssh root@<pod-ip-2> "bash start_vllm.sh --domain criteria"

# ... (case, counsel도 동일)

# 2. 로컬에서 4개 연결
./scripts/runpod/connect_local.sh --multi --pod-ips "IP1,IP2,IP3,IP4"
```

---

## Manual Setup (수동 설정)

### 1. Deploying the Pod

1. Log in to [RunPod](https://www.runpod.io/).
2. Navigate to **Pods** and click **+ Deploy**.
3. Select a GPU (e.g., RTX 4090).
4. Choose the **RunPod PyTorch** template or a dedicated **vLLM** template if available.
5. Ensure you have enough disk space (at least 50GB for model weights and cache).
6. Click **Deploy**.

### 2. Installing vLLM

Once the Pod is running, connect via SSH and install vLLM:

```bash
pip install vllm
```

### 3. Running the vLLM Server

Run the following command to start the OpenAI-compatible API server for EXAONE-4.0-1.2B:

```bash
python -m vllm.entrypoints.openai.api_server \
    --model LG-AI-EXAONE/EXAONE-4.0-1.2B-Instruct \
    --port 9010 \
    --trust-remote-code \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.9
```

*Note: The first run will download the model weights from Hugging Face.*

### 4. SSH Tunneling for Local Development

To access the vLLM server from your local machine (or the backend server), use SSH tunneling:

```bash
ssh -L 19010:localhost:9010 -i ~/.ssh/id_rsa root@<RUNPOD_POD_IP> -N
```

Now, the EXAONE API will be available at `http://localhost:19010/v1`.

### 5. Configuration

Update your `backend/.env` file with the following variables:

**단일 인스턴스 (공유):**
```env
MODEL_EXAONE_BASE_URL=http://localhost:19010/v1
MODEL_EXAONE_API_KEY=empty
MODEL_EXAONE_NAME=LG-AI-EXAONE/EXAONE-4.0-1.2B-Instruct
```

**4개 인스턴스 (병렬 처리):**
```env
RETRIEVAL_LLM_LAW_URL=http://localhost:19010/v1
RETRIEVAL_LLM_CRITERIA_URL=http://localhost:19011/v1
RETRIEVAL_LLM_CASE_URL=http://localhost:19012/v1
RETRIEVAL_LLM_COUNSEL_URL=http://localhost:19013/v1
RETRIEVAL_LLM_TIMEOUT=3.0
```

### 6. Health Check Verification

You can verify the connection using the health check endpoint:

```bash
# vLLM 서버 직접 확인
curl http://localhost:19010/health

# Backend API 통해 확인
curl http://localhost:8000/health/llm/exaone
```

---

## Port Mapping

| Domain    | Local Port | RunPod Port | 용도 |
|-----------|------------|-------------|------|
| (shared)  | 19010      | 9010        | 단일 인스턴스 공유 |
| law       | 19010      | 9010        | 법령 검색 Agent |
| criteria  | 19011      | 9010        | 분쟁해결기준 검색 Agent |
| case      | 19012      | 9010        | 분쟁조정사례 검색 Agent |
| counsel   | 19013      | 9010        | 상담사례 검색 Agent |

---

## Scripts Reference

| 스크립트 | 위치 | 용도 |
|---------|------|------|
| `start_vllm.sh` | `scripts/runpod/` | RunPod 내부에서 vLLM 서버 시작 |
| `connect_local.sh` | `scripts/runpod/` | 로컬에서 SSH 터널링 설정 |

**start_vllm.sh 옵션:**
```bash
--port PORT        # vLLM 서버 포트 (기본: 9010)
--domain DOMAIN    # Retrieval Agent 도메인 (law, criteria, case, counsel)
--max-model-len N  # 최대 컨텍스트 길이 (기본: 4096)
--gpu-util RATIO   # GPU 메모리 사용률 (기본: 0.9)
```

**connect_local.sh 옵션:**
```bash
--pod-ip IP        # 단일 Pod IP
--pod-ips IPs      # 다중 Pod IPs (쉼표 구분)
--multi            # 병렬 처리 모드
--status           # 현재 연결 상태 확인
--kill             # 모든 연결 종료
```

---

## Troubleshooting

- **Out of Memory (OOM):** If you encounter OOM errors, try reducing `--max-model-len` or using a GPU with more VRAM.
- **Connection Refused:** Ensure the SSH tunnel is active and the vLLM server is running on the correct port.
- **Model Download Issues:** Check your internet connection within the Pod and ensure you have enough disk space.
- **Fallback 동작:** EXAONE 연결 실패 시 `gpt-4.1-nano`로 자동 폴백됩니다.

**터널 상태 확인:**
```bash
./scripts/runpod/connect_local.sh --status
```

**터널 재연결:**
```bash
./scripts/runpod/connect_local.sh --kill
./scripts/runpod/connect_local.sh --pod-ip <pod-ip>
```
