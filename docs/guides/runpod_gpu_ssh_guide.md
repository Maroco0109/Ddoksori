# RunPod GPU를 SSH로 터널링해서 로컬(무GPU)에서 개발/임베딩 진행하기

이 문서는 `README.md`, `AI_MEMO.md`, `AI_MEMO_S1.md` 기준으로, **GPU가 없는 로컬 환경**에서 프로젝트를 진행하는 현실적인 운영 플로우(계획)를 정리합니다. 핵심은 **임베딩 서버(Embedding API)** 만 RunPod GPU에서 띄우고, 로컬에서는 DB/백엔드/프론트엔드를 계속 개발·실행하는 방식입니다.

---

## 빠른 시작 (Quick Reference)

### RunPod에서 실행할 명령어:
```bash
# 1. 의존성 설치 (hf_transfer 필수!)
pip install sentence-transformers fastapi uvicorn torch huggingface_hub hf_transfer

# 2. Hugging Face 로그인
huggingface-cli login

# 3. 임베딩 서버 실행 (hf_transfer 활성화 필수)
HF_HUB_ENABLE_HF_TRANSFER=1 python embedding_server.py

# 또는 다른 포트로 실행
HF_HUB_ENABLE_HF_TRANSFER=1 PORT=8002 python embedding_server.py
```

### 로컬에서 파일 전송 (SCP):
```bash
# embdding_server.py 붙여넣기
nano embedding_server.py
```

### 로컬에서 SSH 터널 생성:
```bash
ssh -L 18001:127.0.0.1:8001 root@[IP] -p [PORT] -i ~/.ssh/runpod_key
```

### 로컬 환경변수 설정:
```bash
export REMOTE_EMBED_URL=http://127.0.0.1:18001
```

---

### 포트 충돌 해결

RunPod에서 8001 포트가 이미 사용 중일 수 있습니다 (Jupyter 등).

```bash
# 8001 포트 사용 중인 프로세스 확인
lsof -i :8001

# 강제 종료
fuser -k 8001/tcp

# 또는 다른 포트 사용 (8002 등)
```

### 임베딩 서버 실행

정상 실행 시 출력:
```
📦 Loading model: nlpai-lab/KURE-v1
✅ Model nlpai-lab/KURE-v1 loaded successfully!
   Load time: 5.68s
   Device: cuda
   Embedding dimension: 1024
============================================================
✅ Embedding Server Ready
============================================================
INFO:     Uvicorn running on http://0.0.0.0:8001
```

정상 확인:

```bash
curl -s http://127.0.0.1:8001/health
# 또는 다른 포트 사용 시:
curl -s http://127.0.0.1:8002/health
```

---

## 로컬에서 SSH 터널 만들기 (핵심)

아래는 로컬 포트 `18001`로 RunPod의 `127.0.0.1:8001`을 가져오는 예시입니다.

```bash
ssh -L 18001:127.0.0.1:8002 root@[IP] -p [PORT] -i ~/.ssh/runpod_key
```
터널 정상 확인(로컬에서):

```bash
curl -s http://127.0.0.1:18001/health
```

`device: "cuda"`로 나오면 RunPod GPU로 모델이 올라간 상태입니다.

---

## 로컬 백엔드/스크립트에서 RunPod 임베딩 쓰기

### 로컬 백엔드 실행 시 (검색/챗에서 사용)

`.env` 또는 셸에서 다음을 설정합니다.

```bash
export RETRIEVAL_MODE=hybrid
export REMOTE_EMBED_URL="http://127.0.0.1:18001"
```

그 다음 백엔드 실행:

```bash
cd backend
uvicorn app.main:app --reload
```

### 로컬 DB에 임베딩 채우기(배치)

임베딩 생성 스크립트는 `REMOTE_EMBED_URL`을 우선 사용하도록 되어 있습니다.

```bash
export REMOTE_EMBED_URL="http://127.0.0.1:18001"
python backend/scripts/data_loading/embed_law_units_v2.py
```

---

## Sprint 2 추가 모델 (다중 GPU 서비스)

Sprint 2에서 추가된 GPU 모델들을 각각 다른 포트에서 실행할 수 있습니다.

### 포트 할당 정리

| 서비스 | RunPod 포트 | 로컬 터널 포트 | 환경변수 | 용도 |
|:-------|:-----------:|:-------------:|:---------|:-----|
| FastAPI Backend | - | 8000 | - | 로컬 전용 (충돌 주의) |
| KURE-v1 Embedding | 8001 | 18001 | `REMOTE_EMBED_URL` | Dense 임베딩 |
| BGE-M3 Embedding | 8003 | 18003 | `BGE_M3_REMOTE_URL` | Dense + Sparse 임베딩 |
| EXAONE vLLM | 8080 | 18080 | `EXAONE_RUNPOD_URL` | LLM 추론 |

> **주의**: 로컬 FastAPI 백엔드가 8000 포트를 사용하므로, RunPod 서비스는 8000을 피해야 합니다.

---

### BGE-M3 서버 (S2-9)

BGE-M3는 Dense와 Sparse 임베딩을 동시에 생성합니다.

#### RunPod에서 실행:

```bash
# 1. 의존성 설치
pip install FlagEmbedding==1.2.11 fastapi uvicorn torch

# 2. bge_m3_server.py 파일 생성 (nano 또는 scp)
nano bge_m3_server.py

# 3. 서버 실행 (포트 8003)
python bge_m3_server.py
```

정상 실행 시 출력:
```
Loading BGE-M3 model...
BGE-M3 model loaded successfully!
INFO:     Uvicorn running on http://0.0.0.0:8003
```

헬스체크:
```bash
curl -s http://127.0.0.1:8003/health
# {"status":"healthy","model":"BAAI/bge-m3","dense_dim":1024,"capabilities":["dense","sparse"]}
```

#### 로컬 SSH 터널:

```bash
ssh -L 18003:127.0.0.1:8003 root@[IP] -p [PORT] -i ~/.ssh/runpod_key
```

#### 로컬 환경변수:

```bash
export BGE_M3_REMOTE_URL="http://127.0.0.1:18003"
export ENABLE_SPARSE_SEARCH=true
```

#### BGE-M3 배치 임베딩:

```bash
export BGE_M3_REMOTE_URL="http://127.0.0.1:18003"
python backend/scripts/data_loading/embed_bge_m3_all_data.py --batch-size 32
```

---

### EXAONE 3.5 vLLM 서버 (S2-8)

EXAONE 3.5 2.4B 모델을 vLLM으로 서빙합니다.

#### RunPod에서 실행:

```bash
# 1. vLLM 설치
pip install vllm

# 2. vLLM 서버 실행 (포트 8080, 8000과 충돌 방지)
python -m vllm.entrypoints.openai.api_server \
    --model LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct \
    --port 8080 \
    --host 0.0.0.0 \
    --max-model-len 4096
```

정상 실행 시 출력:
```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8080
```

헬스체크:
```bash
curl -s http://127.0.0.1:8080/health
```

#### 방법 1: SSH 터널 (낮은 지연시간)

```bash
ssh -L 18080:127.0.0.1:8080 root@[IP] -p [PORT] -i ~/.ssh/runpod_key
```

로컬 환경변수:
```bash
export EXAONE_RUNPOD_URL="http://127.0.0.1:18080/v1"
export REACT_THINK_MODE=llm
```

#### 방법 2: RunPod Proxy URL (SSH 불필요)

RunPod 대시보드에서 "Connect" → "HTTP Service"로 포트 8080을 노출하면:
```bash
export EXAONE_RUNPOD_URL="https://<pod-id>-8080.proxy.runpod.net/v1"
export REACT_THINK_MODE=llm
```

---

### 다중 터널 동시 생성

여러 서비스를 한 번에 터널링:

```bash
# 단일 SSH 세션으로 모든 터널 생성
ssh -L 18001:127.0.0.1:8001 \
    -L 18003:127.0.0.1:8003 \
    -L 18080:127.0.0.1:8080 \
    root@[IP] -p [PORT] -i ~/.ssh/runpod_key
```

또는 백그라운드로 실행:
```bash
ssh -fN \
    -L 18001:127.0.0.1:8001 \
    -L 18003:127.0.0.1:8003 \
    -L 18080:127.0.0.1:8080 \
    root@[IP] -p [PORT] -i ~/.ssh/runpod_key
```

모든 터널 확인:
```bash
# KURE-v1
curl -s http://127.0.0.1:18001/health

# BGE-M3
curl -s http://127.0.0.1:18003/health

# EXAONE vLLM
curl -s http://127.0.0.1:18080/health
```

---

### 전체 환경변수 설정 예시

`.env` 파일 또는 셸에서:

```bash
# 로컬 백엔드
export RETRIEVAL_MODE=hybrid

# KURE-v1 (Dense 임베딩)
export REMOTE_EMBED_URL="http://127.0.0.1:18001"

# BGE-M3 (Dense + Sparse 임베딩)
export BGE_M3_REMOTE_URL="http://127.0.0.1:18003"
export ENABLE_SPARSE_SEARCH=true

# EXAONE LLM
export EXAONE_RUNPOD_URL="http://127.0.0.1:18080/v1"
export REACT_THINK_MODE=llm

# RRF 가중치 (선택)
export RRF_WEIGHT_DENSE=1.0
export RRF_WEIGHT_LEXICAL=1.0
export RRF_WEIGHT_SPARSE=1.0
```

---

### 트러블슈팅

#### GPU 메모리 부족
여러 모델을 동시에 실행 시 GPU 메모리가 부족할 수 있습니다.

```bash
# GPU 메모리 확인
nvidia-smi

# 권장 사양
# - KURE-v1: ~2GB
# - BGE-M3: ~4GB
# - EXAONE 2.4B: ~6GB
# - 총합: 최소 16GB GPU 권장
```

#### 포트 충돌 확인
```bash
# RunPod에서 사용 중인 포트 확인
netstat -tlnp | grep -E '8001|8003|8080'

# 특정 포트 프로세스 종료
fuser -k 8003/tcp
```

---

## RunPod 모델 실행 가이드 (통합)

모든 GPU 모델을 RunPod에서 실행하기 위한 통합 가이드입니다.

### 모델별 요약

| 모델 | 복사할 파일 | 소스 위치 | 포트 | VRAM |
|:-----|:-----------|:----------|:----:|:----:|
| KURE-v1 | `embedding_server.py` | `backend/embedding_server.py` | 8001 | ~2GB |
| BGE-M3 | `bge_m3_server.py` | `backend/bge_m3_server.py` | 8003 | ~4GB |
| EXAONE | (vLLM 직접 실행) | - | 8080 | ~6GB |

**총 VRAM 요구량**: ~12GB (RTX 3090/4090 24GB 권장)

---

### 공통 사전 준비 (RunPod)

#### 1. PyTorch CUDA 버전 설치

```bash
# CUDA 12.1 (권장)
pip install torch==2.1.0+cu121 --index-url https://download.pytorch.org/whl/cu121

# 또는 CUDA 11.8
pip install torch==2.1.0+cu118 --index-url https://download.pytorch.org/whl/cu118
```

#### 2. Hugging Face 로그인 (모델 다운로드용)

```bash
pip install huggingface_hub hf_transfer
huggingface-cli login
```

#### 3. 빠른 모델 다운로드 활성화

```bash
export HF_HUB_ENABLE_HF_TRANSFER=1
```

---

### 모델 1: KURE-v1 Embedding (포트 8001)

Dense 임베딩 생성용 (1024차원)

#### 패키지 설치

```bash
pip install sentence-transformers==2.2.2 fastapi uvicorn
```

#### 파일 복사 (nano)

```bash
# RunPod 터미널에서
nano embedding_server.py
```

로컬 파일 위치: `backend/embedding_server.py`

복사 방법:
1. 로컬에서 파일 내용 전체 복사 (Ctrl+A → Ctrl+C)
2. RunPod nano 에디터에 붙여넣기 (Ctrl+Shift+V)
3. 저장 (Ctrl+O → Enter) 후 종료 (Ctrl+X)

#### 서버 실행

```bash
HF_HUB_ENABLE_HF_TRANSFER=1 python embedding_server.py
```

#### 정상 실행 확인

```
📦 Loading model: nlpai-lab/KURE-v1
✅ Model nlpai-lab/KURE-v1 loaded successfully!
   Device: cuda
   Embedding dimension: 1024
INFO:     Uvicorn running on http://0.0.0.0:8001
```

#### 헬스체크

```bash
curl -s http://127.0.0.1:8001/health
# {"status":"healthy","device":"cuda","model":"nlpai-lab/KURE-v1"}
```

---

### 모델 2: BGE-M3 Embedding (포트 8003)

Dense + Sparse 임베딩 동시 생성용 (3-way RRF)

#### 패키지 설치

```bash
pip install FlagEmbedding==1.2.11 fastapi uvicorn
```

#### 파일 복사 (nano)

```bash
# RunPod 터미널에서
nano bge_m3_server.py
```

로컬 파일 위치: `backend/bge_m3_server.py`

#### 서버 실행

```bash
python bge_m3_server.py
```

#### 정상 실행 확인

```
BGE-M3 Embedding Server Initializing
Device: CUDA
Loading model: BAAI/bge-m3
Model BAAI/bge-m3 loaded successfully!
   Dense dimension: 1024
BGE-M3 Server Ready
INFO:     Uvicorn running on http://0.0.0.0:8003
```

#### 헬스체크

```bash
curl -s http://127.0.0.1:8003/health
# {"status":"healthy","model":"BAAI/bge-m3","dense_dim":1024,"capabilities":["dense","sparse"]}
```

---

### 모델 3: EXAONE vLLM (포트 8080)

LLM 추론용 (ReAct 에이전트)

#### 패키지 설치

```bash
pip install vllm
```

> 별도 .py 파일 불필요 - vLLM 내장 서버 사용

#### 서버 실행

```bash
python -m vllm.entrypoints.openai.api_server \
    --model LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct \
    --port 8080 \
    --host 0.0.0.0 \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.9
```

#### 정상 실행 확인

```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8080
```

#### 헬스체크

```bash
curl -s http://127.0.0.1:8080/health
# {}
```

---

### tmux로 다중 모델 동시 실행

RunPod에서 여러 모델을 동시에 실행하려면 tmux 사용:

#### tmux 설치 (필요 시)

```bash
apt-get update && apt-get install -y tmux
```

#### 세션 생성 및 실행

```bash
# 새 세션 시작
tmux new -s models

# KURE-v1 실행 (창 0)
HF_HUB_ENABLE_HF_TRANSFER=1 python embedding_server.py

# 새 창 생성 (Ctrl+B, C) 후 BGE-M3 실행
python bge_m3_server.py

# 새 창 생성 (Ctrl+B, C) 후 EXAONE 실행
python -m vllm.entrypoints.openai.api_server \
    --model LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct \
    --port 8080 --host 0.0.0.0 --max-model-len 4096
```

#### tmux 단축키

| 키 | 동작 |
|:---|:-----|
| `Ctrl+B, C` | 새 창 생성 |
| `Ctrl+B, N` | 다음 창 |
| `Ctrl+B, P` | 이전 창 |
| `Ctrl+B, D` | 세션 분리 (백그라운드) |
| `tmux attach -t models` | 세션 재접속 |

---

### 전체 설치 스크립트 (한번에 실행)

RunPod에서 복사 후 실행:

```bash
#!/bin/bash
# setup_all_models.sh

echo "=== PyTorch CUDA 설치 ==="
pip install torch==2.1.0+cu121 --index-url https://download.pytorch.org/whl/cu121

echo "=== 공통 패키지 설치 ==="
pip install huggingface_hub hf_transfer fastapi uvicorn

echo "=== KURE-v1 패키지 설치 ==="
pip install sentence-transformers==2.2.2

echo "=== BGE-M3 패키지 설치 ==="
pip install FlagEmbedding==1.2.11

echo "=== vLLM 설치 ==="
pip install vllm

echo "=== Hugging Face 로그인 ==="
huggingface-cli login

echo "=== 완료! ==="
echo "embedding_server.py, bge_m3_server.py 파일을 복사하세요."
```

---

### 로컬 SSH 터널 (모든 서비스)

```bash
# 모든 서비스 동시 터널링
ssh -L 18001:127.0.0.1:8001 \
    -L 18003:127.0.0.1:8003 \
    -L 18080:127.0.0.1:8080 \
    root@[IP] -p [PORT] -i ~/.ssh/runpod_key
```

### 로컬 환경변수 (모든 서비스)

```bash
# backend/.env 또는 셸에서
export REMOTE_EMBED_URL="http://127.0.0.1:18001"
export BGE_M3_REMOTE_URL="http://127.0.0.1:18003"
export EXAONE_RUNPOD_URL="http://127.0.0.1:18080/v1"
export ENABLE_SPARSE_SEARCH=true
export REACT_THINK_MODE=llm
```

---
