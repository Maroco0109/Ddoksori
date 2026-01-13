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
