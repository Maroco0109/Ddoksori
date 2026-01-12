# RunPod GPU를 SSH로 터널링해서 로컬(무GPU)에서 개발/임베딩 진행하기

이 문서는 `README.md`, `AI_MEMO.md`, `AI_MEMO_S1.md` 기준으로, **GPU가 없는 로컬 환경**에서 프로젝트를 진행하는 현실적인 운영 플로우(계획)를 정리합니다. 핵심은 **임베딩 서버(Embedding API)** 만 RunPod GPU에서 띄우고, 로컬에서는 DB/백엔드/프론트엔드를 계속 개발·실행하는 방식입니다.

## 0) 결론 요약 (추천 플로우)

- 로컬은 `docker-compose`로 `PostgreSQL(pgvector)` + (선택) 백엔드/프론트엔드를 띄운다.
- 검색 모드는 **`RETRIEVAL_MODE=hybrid`** 로 둔다. (임베딩이 없거나 임베딩 API가 잠시 죽어도 FTS로 graceful fallback)
- RunPod GPU에는 `backend/embedding_server.py` (FastAPI, `:8001`)만 실행한다.
- 로컬에서는 **SSH Local Port Forwarding** 으로 RunPod의 `:8001`을 로컬 포트로 당겨서 사용한다.
- 로컬에서 `REMOTE_EMBED_URL=http://127.0.0.1:<LOCAL_PORT>` 를 설정하면 `backend/utils/embedding_connection.py`의 adaptive 로직이 원격 임베딩 서버를 사용한다.

---

## 1) 왜 이렇게 하나요? (GPU 없는 로컬에서의 제약)

- 프로젝트는 **KURE-v1(1024d) 임베딩**을 전제로 `pgvector` 기반 dense/hybrid 검색을 지원합니다.
- 로컬에 GPU가 없으면 KURE-v1을 CPU로 돌릴 수는 있지만, 다음 문제가 생길 수 있습니다.
  - 성능 저하(지연 증가)
  - 모델 다운로드/캐시가 필요해서 환경에 따라 시작이 느리거나 실패할 수 있음
- 따라서 “로컬 개발 환경”과 “GPU 리소스(임베딩 생성)”를 분리하는 것이 가장 안정적입니다.

---

## 2) 진행 계획 (GPU 없는 로컬 기준)

### Phase A — 로컬에서 기능 개발/검증(임베딩 없이도 가능)

1. 로컬 DB 준비 (Docker 권장)
   - `docker-compose up -d db`
2. 로컬 백엔드 실행
   - `.env`에서 `RETRIEVAL_MODE=hybrid` 설정
   - 백엔드 실행: `cd backend && uvicorn app.main:app --reload`
3. 임베딩이 아직 없어도(또는 임베딩 API가 없어도) 검색/챗 API가 동작하는지 확인
   - 하이브리드 검색은 내부적으로 dense가 실패하면 FTS 결과만으로 동작하도록 설계되어 있습니다.

### Phase B — RunPod GPU 준비(임베딩 서버만)

1. RunPod에 GPU Pod 생성 (예: CUDA/PyTorch 템플릿)
2. SSH 접속 가능 상태로 설정 (RunPod에서 제공하는 SSH 커맨드/키 사용)
3. Pod 내부에서 임베딩 서버 실행
   - 이 서버는 `GET /health`, `POST /embed`를 제공합니다.

### Phase C — SSH 터널로 로컬에서 GPU 임베딩 사용

1. 로컬에서 SSH 터널 생성 (RunPod `:8001` → 로컬 포트로 포워딩)
2. 로컬에서 `REMOTE_EMBED_URL` 환경변수 설정 후 백엔드/스크립트 실행
3. (선택) 로컬 DB에 대해 `backend/scripts/data_loading/embed_law_units_v2.py`로 임베딩을 채운 뒤
   - `REFRESH MATERIALIZED VIEW mv_searchable_chunks;`가 자동 수행됨(스크립트 내)
4. hybrid 검색에서 dense+lexical이 함께 쓰이는지 확인

---

## 3) RunPod에서 임베딩 서버 띄우기

아래는 “임베딩 서버만” 띄우는 최소 절차입니다. (Pod의 기본 이미지에 따라 패키지 설치 방식은 달라질 수 있습니다.)

### 3.1 Pod에서 코드 준비

옵션 1) 저장소를 Pod에 클론해서 실행(가장 단순)

```bash
git clone <YOUR_REPO_URL>
cd LLM
pip install -r backend/requirements.txt
```

옵션 2) 임베딩 서버만 따로 준비

- 파일은 `backend/embedding_server.py` 하나로도 동작합니다.
- 단, `fastapi`, `uvicorn`, `sentence-transformers`, `torch`가 필요합니다.

### 3.2 (권장) 외부 노출 없이 127.0.0.1로만 바인딩

SSH 터널로만 접근할 것이면 RunPod에서 임베딩 API를 공인망에 열 필요가 없습니다.

```bash
cd backend
export EMBEDDING_MODEL_NAME="nlpai-lab/KURE-v1"
uvicorn embedding_server:app --host 127.0.0.1 --port 8001
```

정상 확인:

```bash
curl -s http://127.0.0.1:8001/health
```

---

## 4) 로컬에서 SSH 터널 만들기 (핵심)

아래는 로컬 포트 `18001`로 RunPod의 `127.0.0.1:8001`을 가져오는 예시입니다.

```bash
ssh -N \
  -L 18001:127.0.0.1:8001 \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  <RUNPOD_SSH_COMMAND_OR_USER_HOST>
```

터널 정상 확인(로컬에서):

```bash
curl -s http://127.0.0.1:18001/health
```

`device: "cuda"`로 나오면 RunPod GPU로 모델이 올라간 상태입니다.

---

## 5) 로컬 백엔드/스크립트에서 RunPod 임베딩 쓰기

### 5.1 로컬 백엔드 실행 시 (검색/챗에서 사용)

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

### 5.2 로컬 DB에 임베딩 채우기(배치)

임베딩 생성 스크립트는 `REMOTE_EMBED_URL`을 우선 사용하도록 되어 있습니다.

```bash
export REMOTE_EMBED_URL="http://127.0.0.1:18001"
python backend/scripts/data_loading/embed_law_units_v2.py
```

---

## 6) 운영 팁 / 트러블슈팅

- `curl /health`가 `503 Model not initialized`이면
  - RunPod에서 모델 다운로드/로드에 실패한 상태입니다. Pod에서 로그를 확인하세요.
  - `EMBEDDING_MODEL_NAME`를 바꿔(예: 더 작은 한국어 임베딩) 재시도할 수 있습니다.
- 로컬 백엔드가 뜨는데 시간이 오래 걸리면
  - 백엔드 실행 전에 SSH 터널과 `REMOTE_EMBED_URL`을 먼저 준비하세요.
  - (현재 로직상) 원격 임베딩 서버가 확인되면 로컬 임베딩 서버를 띄우지 않습니다.
- 포트 충돌 시
  - 로컬 포트를 `18001`처럼 다른 값으로 바꾸고 `REMOTE_EMBED_URL`만 그에 맞게 변경하세요.

