# RunPod vLLM Scripts

DDOKSORI Retrieval Agent용 EXAONE vLLM 서버 배포 스크립트입니다.

## Quick Start

### 권장: 단일 Pod에서 4개 인스턴스 (A40 등 대용량 GPU)

EXAONE 1.2B는 인스턴스당 ~4GB VRAM → A40(48GB)에서 4개 충분히 실행 가능

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
scp scripts/runpod/start_vllm.sh root@<pod-ip>:~/
ssh root@<pod-ip> "bash start_vllm.sh"
./scripts/runpod/connect_local.sh --pod-ip <pod-ip>
```

### 대안 B: 4개 Pod 각각 (소용량 GPU)

```bash
# 각 Pod에서 도메인별 실행
bash start_vllm.sh --domain law       # Pod 1
bash start_vllm.sh --domain criteria  # Pod 2
bash start_vllm.sh --domain case      # Pod 3
bash start_vllm.sh --domain counsel   # Pod 4

# 로컬에서 4개 연결
./scripts/runpod/connect_local.sh --multi --pod-ips "IP1,IP2,IP3,IP4"
```

## Scripts

| 파일 | 실행 위치 | 용도 |
|-----|----------|------|
| `start_vllm_multi.sh` | RunPod | 4개 vLLM 인스턴스 동시 시작 (권장) |
| `start_vllm.sh` | RunPod | 단일 vLLM 서버 시작 |
| `connect_local.sh` | 로컬 | SSH 터널링 설정 |

## Port Mapping

| Domain | Local Port | Remote Port | 환경변수 |
|--------|------------|-------------|---------|
| law | 19010 | 9010 | `RETRIEVAL_LLM_LAW_URL` |
| criteria | 19011 | 9011 | `RETRIEVAL_LLM_CRITERIA_URL` |
| case | 19012 | 9012 | `RETRIEVAL_LLM_CASE_URL` |
| counsel | 19013 | 9013 | `RETRIEVAL_LLM_COUNSEL_URL` |

## VRAM Requirements

| 구성 | 모델 | VRAM | GPU 권장 |
|-----|------|------|---------|
| 단일 인스턴스 | EXAONE 1.2B | ~4GB | RTX 4090 (24GB) |
| 4개 인스턴스 | EXAONE 1.2B × 4 | ~16GB | A40 (48GB), A100 |

## Commands

```bash
# 연결 상태 확인
./connect_local.sh --status

# 모든 연결 종료
./connect_local.sh --kill

# 도움말
./start_vllm.sh --help
./start_vllm_multi.sh --help
./connect_local.sh --help
```

자세한 내용은 [docs/infrastructure/runpod-vllm-setup.md](../../docs/infrastructure/runpod-vllm-setup.md) 참조.
