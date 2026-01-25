# 똑소리 (ddoksori_demo)

**한국 소비자 분쟁 조정을 위한 멀티 에이전트 챗봇 시스템**

## 1. 프로젝트 개요

본 프로젝트는 복잡하고 전문적인 한국의 소비자 분쟁 관련 문의에 대해 정확하고 신뢰도 높은 답변을 제공하는 MAS(Multi-Agent System) 챗봇입니다. React, FastAPI, LangGraph, PostgreSQL 등 현대적인 기술 스택을 활용하여 분쟁조정사례, 상담사례, 법령 데이터를 기반으로 최적의 해결 방안을 제시합니다.

### 핵심 기능
- **멀티 에이전트 워크플로우**: 질의 분석, 정보 검색, 답변 생성, 법률 검토 단계별 전문 에이전트 배치
- **하이브리드 검색**: pgvector 기반 벡터 검색과 전문(Full-text) 검색을 결합한 고정밀 RAG
- **실시간 스트리밍**: SSE(Server-Sent Events)를 통한 실시간 답변 생성 및 출처 제공
- **신뢰성 보장**: 법률 검토 에이전트를 통한 환각 방지 및 면책 문구 자동 포함

---

## 2. Quickstart (Local)

### Backend
```bash
# 1. 가상환경 활성화 (Conda 필수)
conda activate dsr

# 2. 의존성 설치
cd backend
pip install -r requirements.txt

# 3. 서버 실행
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
# 1. 의존성 설치
cd frontend
npm install

# 2. 개발 서버 실행
npm run dev
```

---

## 3. Quickstart (Docker)

Docker Compose를 사용하여 전체 스택(DB, Redis, Backend, Frontend, Monitoring)을 한 번에 실행할 수 있습니다.

```bash
# 전체 서비스 실행
docker compose up --build -d

# BGE-M3 임베딩 서버 포함 실행 (선택)
docker compose --profile bge-m3 up -d
```

### 서비스 포트 정보
| 서비스 | 포트 | 설명 |
|--------|------|------|
| Frontend | 5173 | React Web UI |
| Backend | 8000 | FastAPI API Server |
| Database | 5432 | PostgreSQL + pgvector |
| Redis | 6379 | Answer Caching |
| Embedding API | 8003 | BGE-M3 Embedding Server |
| CloudBeaver | 8978 | Web-based DB Manager |
| Prometheus | 9090 | Monitoring Metrics |
| Grafana | 3000 | Monitoring Dashboard |

---

## 4. Key URLs & Endpoints

상세 API 명세는 [backend/app/api/README.md](backend/app/api/README.md)를 참고하세요.

- **Web UI**: `http://localhost:5173`
- **API Docs**: `http://localhost:8000/docs`
- **주요 API**:
  - `POST /chat`: 챗봇 응답 생성
  - `POST /chat/stream`: SSE 스트리밍 응답
  - `POST /search`: 벡터 검색 (LLM 미사용)
  - `GET /health`: 서버 상태 확인

---

## 5. Configuration

`.env` 파일 설정을 통해 시스템 동작을 제어합니다. `backend/.env.example`을 복사하여 사용하세요.

| 변수명 | 설명 | 기본값/예시 |
|--------|------|------------|
| `OPENAI_API_KEY` | OpenAI API 키 | `sk-...` |
| `ANTHROPIC_API_KEY` | Anthropic API 키 | `sk-ant-...` |
| `EMBEDDING_MODEL` | 사용할 임베딩 모델 | `nlpai-lab/KURE-v1` |
| `RETRIEVAL_MODE` | 검색 모드 | `hybrid` |
| `ENABLE_ANSWER_CACHE` | Redis 캐싱 활성화 | `false` |
| `EXAONE_RUNPOD_URL` | EXAONE LLM API URL | `http://localhost:19080/v1` |

---

## 6. Architecture

### 전체 시스템 구조
```mermaid
graph TB
    subgraph "Frontend Layer"
        A[사용자] -->|질문 입력| B[Chat Interface]
        B -->|HTTP/SSE| C[API Client]
    end
    
    subgraph "Backend Layer (FastAPI)"
        C -->|/chat, /chat/stream| D[API Gateway]
        D --> E[Session Manager]
        D --> F[SSE Handler]
        E --> G[LangGraph Orchestrator]
        
        subgraph "Multi-Agent System"
            G --> H[Query Analysis]
            H --> I[Information Retrieval]
            I --> J[Answer Generation]
            J --> K[Legal Review]
        end
    end
    
    subgraph "Data & Infrastructure"
        I --> L[(PostgreSQL/pgvector)]
        I --> M[(Redis Cache)]
        I --> N[Embedding API:8003]
        G --> O[Prometheus/Grafana]
    end
    
    subgraph "External LLM"
        J -.-> P[OpenAI/Anthropic]
        K -.-> P
    end
```

### 에이전트 데이터 흐름
```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as API Gateway
    participant Orch as Orchestrator
    participant QA as Query Analysis
    participant IR as Retrieval
    participant AG as Generation
    participant LR as Legal Review
    
    FE->>API: POST /chat/stream
    API->>Orch: 워크플로우 시작
    Orch->>QA: 질의 분석 (의도/키워드)
    Orch->>IR: 하이브리드 검색 (DB/Embedding)
    Orch->>AG: 답변 초안 생성 (LLM)
    Orch->>LR: 법률 검토 및 가드레일
    LR-->>Orch: 최종 승인
    Orch->>API: 최종 답변 + 출처
    API->>FE: SSE 스트리밍 응답
```

---

## 7. Documentation Hub

| 대상 | 문서 링크 | 설명 |
|------|-----------|------|
| **시작하기** | [EASY_START_GUIDE_KR.md](docs/guides/EASY_START_GUIDE_KR.md) | 상세 설치 및 실행 가이드 |
| **API** | [backend/app/api/README.md](backend/app/api/README.md) | 엔드포인트 및 데이터 모델 명세 |
| **아키텍처** | [backend/app/orchestrator/README.md](backend/app/orchestrator/README.md) | 에이전트 상세 설계 및 구현 가이드 |
| **로드맵** | [docs/plans/sprint-roadmap.md](docs/plans/sprint-roadmap.md) | 스프린트별 개발 계획 및 PR 목록 |
| **평가** | [docs/guides/evaluation-strategy.md](docs/guides/evaluation-strategy.md) | 에이전트별 평가 지표 및 전략 |
| **테스트** | [backend/scripts/testing/README.md](backend/scripts/testing/README.md) | 테스트 전략 및 데이터 파이프라인 |
