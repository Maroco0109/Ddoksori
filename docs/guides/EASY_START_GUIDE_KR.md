# 똑소리 프로젝트 실행 및 테스트 가이드 📘

이 문서는 '똑소리' 프로젝트의 **단계별 실행 가이드**입니다. 데이터 흐름 순서(DB → Text 적재 → Model 연결 → Embedding)에 맞춰 진행해주세요.

---

## 1. Docker 실행 및 DB 스키마 설정

가장 먼저 데이터베이스를 실행하고 스키마를 초기화해야 합니다.

### 1-1. DB 컨테이너 실행
PostgreSQL(pgvector) 데이터베이스를 Docker로 실행합니다.

```bash
# DB 컨테이너만 실행 (권장)
docker-compose up -d db

# (참고) 전체 시스템 실행 시: docker-compose up --build
```

### 1-2. DB 스키마 적용
DB가 실행된 후, 테이블 스키마를 생성합니다.

```bash
# pgvector 확장 설치 및 테이블 생성
docker exec -i ddoksori_db psql -U postgres -d ddoksori < backend/database/schema_v2_final.sql
```

---

## 2. 기초 데이터 적재 (RDB Text)

임베딩 생성 전, **텍스트 데이터(Case, Criteria 등)**를 먼저 DB에 적재합니다.
(이 단계는 GPU가 필요 없으며, 로컬 CPU로 수행됩니다.)

```bash
# 가상환경 활성화
conda activate dsr

# backend 디렉토리로 이동
cd backend

# 전체 테스트 데이터(상담사례, 분쟁조정사례, 해결기준) 적재
python scripts/data_loading/load_all_test_data.py --all
```
> **확인**: 터미널에 `✅ Data Loading Complete!` 메시지가 뜨면 성공입니다.

---

## 3. LLM/임베딩 환경 설정 (RunPod)

데이터 텍스트가 DB에 준비되었습니다. 이제 이를 벡터화(Embedding)하고 챗봇을 구동하기 위해 **고성능 GPU(RunPod)**를 준비합니다.

### 3-1. RunPod 서버 세팅 (RunPod 터미널)

RunPod에 접속하여 환경을 구성합니다.

```bash
# 1. 필수 패키지 설치
pip install torch==2.1.0+cu121 --index-url https://download.pytorch.org/whl/cu121
pip install fastapi uvicorn pydantic
pip install huggingface_hub hf_transfer
pip install sentence-transformers>=3.0.0    # 3.0 이상 필수 (huggingface_hub 호환)
pip install FlagEmbedding>=1.2.11 peft      # peft는 FlagEmbedding 의존성
pip install vllm

# 2. HuggingFace 로그인 (gated 모델 접근용)
huggingface-cli login
export HF_HUB_ENABLE_HF_TRANSFER=1
```

### 3-2. 서버 스크립트 업로드

로컬 프로젝트의 서버 스크립트를 RunPod에 업로드합니다.

| 모델 | 로컬 파일 경로 | RunPod 업로드 위치 |
|------|---------------|-------------------|
| KURE-v1 | `backend/app/agents/retrieval/services/embedding_server.py` | `/workspace/embedding_server.py` |
| BGE-M3 | `backend/app/agents/retrieval/services/bge_m3_server.py` | `/workspace/bge_m3_server.py` |

```bash
# SCP로 업로드 예시 (로컬 PC에서 실행)
scp -P [RunPod_Port] -i [Key_Path] \
    backend/app/agents/retrieval/services/embedding_server.py \
    backend/app/agents/retrieval/services/bge_m3_server.py \
    root@[RunPod_IP]:/workspace/
```

### 3-3. 모델 서버 실행 (RunPod 터미널)

각 모델을 **tmux**로 백그라운드 실행합니다.

| 모델 | 포트 | 용도 | VRAM 요구량 |
|------|------|------|------------|
| **KURE-v1** | 9001 | Dense 임베딩 (1024D) | ~2GB |
| **BGE-M3** | 9003 | Dense + Sparse 임베딩 | ~4GB |
| **EXAONE** | 9080 | 답변 생성 LLM | ~6GB |

> **Note**: RunPod에서 8000-8080 포트는 Jupyter, 웹 서비스 등에서 자주 사용되므로 9000번대를 사용합니다.

#### KURE-v1 실행 (포트 9001)

```bash
# tmux 세션 생성 및 실행
tmux new -s kure
cd /workspace
PORT=9001 python embedding_server.py
# Ctrl+B, D 로 detach (백그라운드 전환)
```

**테스트**:
```bash
curl -X POST http://localhost:9001/embed \
  -H "Content-Type: application/json" \
  -d '{"text": "헬스장 환불"}'
```

#### BGE-M3 실행 (포트 9003)

```bash
# tmux 세션 생성 및 실행
tmux new -s bge
cd /workspace
BGE_M3_PORT=9003 python bge_m3_server.py
# Ctrl+B, D 로 detach
```

**테스트**:
```bash
curl -X POST http://localhost:9003/embed \
  -H "Content-Type: application/json" \
  -d '{"text": "헬스장 환불", "return_dense": true, "return_sparse": true}'
```

#### EXAONE 3.5 실행 (포트 9080)

vLLM의 OpenAI-compatible API 서버를 사용합니다.

```bash
# tmux 세션 생성 및 실행
tmux new -s exaone
python -m vllm.entrypoints.openai.api_server \
    --model LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct \
    --port 9080 \
    --host 0.0.0.0 \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.7 \
    --trust-remote-code \
    --enforce-eager \
    --dtype float16
# Ctrl+B, D 로 detach
```

> **Note**: vLLM 0.13+에서는 `--enforce-eager`와 `--dtype float16`이 필요합니다. 없으면 v1 엔진 초기화 오류가 발생할 수 있습니다.

**테스트**:
```bash
curl -X POST http://localhost:9080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct",
    "messages": [{"role": "user", "content": "안녕하세요"}],
    "max_tokens": 100
  }'
```

#### (선택) 한 번에 모두 실행 스크립트

`/workspace/start_all.sh` 파일 생성:

```bash
#!/bin/bash
# start_all.sh - 모든 모델 서버 한 번에 실행

cd /workspace

# KURE-v1 (포트 9001)
tmux new-session -d -s kure "PORT=9001 python embedding_server.py"
echo "✅ KURE-v1 started on port 9001"

# BGE-M3 (포트 9003)
tmux new-session -d -s bge "BGE_M3_PORT=9003 python bge_m3_server.py"
echo "✅ BGE-M3 started on port 9003"

# EXAONE (포트 9080)
tmux new-session -d -s exaone "python -m vllm.entrypoints.openai.api_server \
    --model LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct \
    --port 9080 --host 0.0.0.0 \
    --max-model-len 4096 --gpu-memory-utilization 0.7 \
    --trust-remote-code --enforce-eager --dtype float16"
echo "✅ EXAONE started on port 9080"

echo ""
echo "📋 Running sessions:"
tmux ls
```

실행:
```bash
chmod +x start_all.sh
./start_all.sh
```

#### tmux 관리 명령어

```bash
tmux ls                    # 세션 목록 확인
tmux attach -t kure        # 세션 접속 (로그 확인)
tmux kill-session -t kure  # 세션 종료
tmux kill-server           # 모든 세션 종료
```

### 3-4. 로컬 연결 (SSH Tunneling)

로컬 PC에서 RunPod의 모델을 `localhost`로 접근하기 위해 터널을 뚫습니다.

```bash
# [로컬 PC] 새 터미널에서 실행
ssh -L 19001:127.0.0.1:9001 \
    -L 19003:127.0.0.1:9003 \
    -L 19080:127.0.0.1:9080 \
    root@[RunPod_IP] -p [RunPod_Port] -i [Key_Path]
```

> **포트 매핑**: 로컬 19001 → RunPod 9001 (KURE), 로컬 19003 → RunPod 9003 (BGE-M3), 로컬 19080 → RunPod 9080 (EXAONE)

**연결 확인** (로컬 PC에서):
```bash
curl http://localhost:19001/health
curl http://localhost:19003/health
curl http://localhost:19080/v1/models
```

#### SSH 연결 유지 설정 (Keep-alive)

SSH 터널이 일정 시간 후 자동으로 끊기는 것을 방지하려면, 클라이언트 설정을 추가합니다.

**방법 1: SSH 명령어에 직접 옵션 추가**

```bash
ssh -L 19001:127.0.0.1:9001 \
    -L 19003:127.0.0.1:9003 \
    -L 19080:127.0.0.1:9080 \
    -o ServerAliveInterval=60 \
    -o ServerAliveCountMax=3 \
    root@[RunPod_IP] -p [RunPod_Port] -i [Key_Path]
```

**방법 2: SSH 설정 파일에 영구 적용 (권장)**

`~/.ssh/config` 파일에 다음 내용을 추가합니다:

```bash
Host *
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

| 옵션 | 설명 |
|------|------|
| `ServerAliveInterval 60` | 60초마다 keep-alive 패킷 전송 |
| `ServerAliveCountMax 3` | 3번 연속 응답 없으면 연결 종료 |

> **Note**: 위 설정으로 최대 180초(3분) 동안 네트워크 불안정을 견딜 수 있으며, 유휴 상태에서도 연결이 유지됩니다.

### 3-5. .env 설정 (로컬 PC)

`backend/.env` 파일에 RunPod URL을 설정합니다.

#### SSH 터널링 사용 시 (권장)

```bash
# 임베딩 모델
REMOTE_EMBED_URL=http://localhost:19001
BGE_M3_REMOTE_URL=http://localhost:19003

# LLM (vLLM OpenAI-compatible)
EXAONE_RUNPOD_URL=http://localhost:19080/v1
EXAONE_RUNPOD_API_KEY=dummy
EXAONE_MODEL=LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct
```

#### RunPod Proxy URL 직접 사용 시

SSH 터널링 없이 RunPod의 Public URL을 사용하는 경우:

```bash
# 형식: https://{POD_ID}-{PORT}.proxy.runpod.net
# POD_ID는 RunPod 대시보드 → Pod → Connect → HTTP Service URLs에서 확인

REMOTE_EMBED_URL=https://abc123xyz-9001.proxy.runpod.net
BGE_M3_REMOTE_URL=https://abc123xyz-9003.proxy.runpod.net
EXAONE_RUNPOD_URL=https://abc123xyz-9080.proxy.runpod.net/v1
```

---

## 4. 벡터 임베딩 생성 (RunPod 연동)

이제 로컬의 텍스트 데이터를 RunPod 모델(KURE-v1)로 보내 임베딩 벡터를 생성하고, 다시 DB에 저장합니다.

```bash
# [로컬 PC] backend 디렉토리
cd backend

# .env 파일의 REMOTE_EMBED_URL 설정 확인 후 실행
python scripts/data_loading/embed_all_data.py
```
> **Note**: 약 1~2만 건의 청크를 처리하므로 시간이 다소 소요될 수 있습니다. (RunPod 성능에 따라 5~20분)

---

## 5. 서버 실행 및 테스트

모든 데이터 준비가 완료되었습니다. 서비스를 실행합니다.

### 5-1. Backend (FastAPI)
```bash
cd backend
# RunPod 터널링이 연결된 상태여야 합니다.
export REACT_THINK_MODE=llm
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 5-2. Frontend (React)
```bash
cd frontend
npm install
npm run dev
```

### 5-3. 접속 및 최종 확인
- **Web UI**: [http://localhost:5173](http://localhost:5173)
- **API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **테스트 시나리오**:
  1. 채팅창에 "헬스장 환불 규정 알려줘" 입력
  2. 스트리밍 답변 생성 확인
  3. `[1]` 각주 클릭하여 근거 자료(Database Source)가 잘 뜨는지 확인

---

## 6. (부록) 자동화 테스트 스크립트

개발 중 기능 검증을 위해 사용합니다.

```bash
# 1. 오케스트레이터(Thinking Process) 테스트
pytest backend/scripts/testing/orchestrator/test_react_llm.py -v

# 2. 통합 환경(DB+Model) 테스트
PYTHONPATH=. python backend/scripts/testing/integration/test_docker_environment.py

# 3. 전체 테스트 실행
./backend/run_local_rag_tests.sh all
```

---

## 7. (부록) 트러블슈팅

### RunPod 연결 문제

```bash
# SSH 터널이 끊어진 경우 재연결
ssh -L 19001:127.0.0.1:9001 -L 19003:127.0.0.1:9003 -L 19080:127.0.0.1:9080 \
    root@[RunPod_IP] -p [RunPod_Port] -i [Key_Path]

# 포트 사용 중 에러 시 기존 프로세스 종료 (로컬)
lsof -ti:19001 | xargs kill -9

# RunPod에서 포트 사용 중인 프로세스 확인
lsof -i :9001
# 또는 강제 종료
fuser -k 9001/tcp
```

### 모델 서버 상태 확인 (RunPod)

```bash
# tmux 세션 확인
tmux ls

# 특정 세션 로그 확인
tmux attach -t kure

# GPU 사용량 확인
nvidia-smi
```

### 임베딩 오류

```bash
# KURE 서버 헬스체크 (로컬 PC에서)
curl http://localhost:19001/health

# RunPod에서 직접 확인
curl http://localhost:9001/health

# 응답 예시: {"status":"healthy","device":"cuda","model":"nlpai-lab/KURE-v1"}
```
