# 똑소리 프로젝트 실행 및 테스트 가이드 📘

이 문서는 '똑소리' 프로젝트의**단계별 실행 가이드**입니다. 데이터 흐름 순서(DB → Text 적재 → Model 연결 → Embedding)에 맞춰 진행해주세요.

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
pip install huggingface_hub hf_transfer fastapi uvicorn sentence-transformers==2.2.2 FlagEmbedding==1.2.11 vllm

# 2. HuggingFace 로그인
huggingface-cli login
export HF_HUB_ENABLE_HF_TRANSFER=1
```

### 3-2. 모델 서버 실행 (RunPod 터미널)
각 모델을 백그라운드(tmux 권장)에서 실행합니다.

| 모델 | 포트 | 용도 | 스크립트 |
|---|---|---|---|
| **KURE-v1** | 8001 | 1차 임베딩 (Dense) | `python embedding_server.py` |
| **BGE-M3** | 8003 | 정밀 검색 (Hybrid) | `python bge_m3_server.py` |
| **EXAONE** | 8080 | 답변 생성 (LLM) | (vLLM 실행 명령어, 아래 참고) |

```bash
# EXAONE vLLM 실행 예시
python -m vllm.entrypoints.openai.api_server \
    --model LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct \
    --port 8080 --host 0.0.0.0 --max-model-len 4096 --gpu-memory-utilization 0.9
```

### 3-3. 로컬 연결 (SSH Tunneling)
로컬 PC에서 RunPod의 모델을 마치 로컬 서버인 것처럼(`localhost`) 사용하기 위해 터널을 뚫습니다.

```bash
# [로컬 PC] 새 터미널에서 실행
ssh -L 18001:127.0.0.1:8001 \
    -L 18003:127.0.0.1:8003 \
    -L 18080:127.0.0.1:8080 \
    root@[RunPod_IP] -p [RunPod_Port] -i [Key_Path]
```

---

## 4. 벡터 임베딩 생성 (RunPod 연동)

이제 로컬의 텍스트 데이터를 RunPod 모델(KURE-v1)로 보내 임베딩 벡터를 생성하고, 다시 DB에 저장합니다.

```bash
# [로컬 PC] backend 디렉토리
# .env 파일에 REMOTE_EMBED_URL=http://localhost:18001 설정 확인 (터널링 포트)

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
```
