# 똑소리 (ddoksori_demo)

**한국 소비자 분쟁 조정을 위한 멀티 에이전트 챗봇 시스템**

## 1. 프로젝트 개요

본 프로젝트는 복잡하고 전문적인 한국의 소비자 분쟁 관련 문의에 대해 정확하고 신뢰도 높은 답변을 제공하는 MAS(Multi-Agent System) 챗봇입니다. React, FastAPI, LangGraph, PostgreSQL 등 현대적인 기술 스택을 활용하여 분쟁조정사례, 상담사례, 법령 데이터를 기반으로 최적의 해결 방안을 제시합니다.

### 핵심 기능
- **MAS Supervisor v2 아키텍처**: gpt-4o 기반 Supervisor가 전문 에이전트를 조율하는 Hub-Spoke 구조
- **Selective Retrieval**: 쿼리 분석 결과에 따라 필요한 Retrieval Agent만 선택적 병렬 실행 (법령/기준/사례)
- **Progressive Disclosure**: 적응형 응답 모드 (legacy/minimal/adaptive) + 후속 질문 기반 점진적 상세 안내
- **온보딩 컨텍스트 영속화**: 구매일/품목/금액 등 온보딩 데이터를 세션 간 유지, 경과 일수 자동 계산
- **하이브리드 검색**: pgvector (text-embedding-3-large 1536d) + 전문(Full-text) 검색 결합 + 품목 관련도 필터링
- **실시간 스트리밍**: SSE(Server-Sent Events)를 통한 실시간 답변 생성 및 출처 제공
- **신뢰성 보장**: 법률 검토 에이전트(gpt-4o)를 통한 환각 방지 및 면책 문구 자동 포함
- **Fallback 체인**: LLM 실패 시 자동 전환 (gpt-4o → gpt-4o-mini → rule_based → safe_fallback)

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

Docker Compose를 사용하여 서비스 스택(Backend, Frontend, Redis, CloudBeaver)을 한 번에 실행할 수 있습니다.
데이터베이스는 AWS RDS를 사용하므로 로컬에서 실행되지 않습니다.

```bash
# 전체 서비스 실행
docker compose up -d

```

### 서비스 포트 정보
| 서비스 | 포트 | 설명 |
|--------|------|------|
| Frontend | 5173 | React Web UI |
| Backend | 8000 | FastAPI API Server |
| Redis | 6379 | Answer Caching |
| CloudBeaver | 8978 | Web-based DB Manager |

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

### 기본 설정
| 변수명 | 설명 | 기본값/예시 |
|--------|------|------------|
| `OPENAI_API_KEY` | OpenAI API 키 | `sk-...` |
| `ANTHROPIC_API_KEY` | Anthropic API 키 | `sk-ant-...` |
| `RETRIEVAL_MODE` | 검색 모드 | `hybrid` |
| `ENABLE_ANSWER_CACHE` | Redis 캐싱 활성화 | `false` |
| `RESPONSE_MODE` | 응답 처리 방식 | `legacy` / `minimal` / `adaptive` |

### 모델 설정
| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `MODEL_SUPERVISOR` | Supervisor 모델 (라우팅/조율) | `gpt-4o` |
| `MODEL_DRAFT_AGENT` | Draft Agent 모델 (답변 생성) | `gpt-4o` |
| `MODEL_REVIEW_AGENT` | Review Agent 모델 (법률 검토) | `gpt-4o` |

### 임베딩 설정
| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `EMBEDDING_MODEL` | 임베딩 모델 | `text-embedding-3-large` |
| `EMBEDDING_DIMENSION` | 임베딩 차원 | `1536` |
| `USE_OPENAI_EMBEDDING` | OpenAI 임베딩 사용 | `true` |

### RDS 테스트 설정
| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `DB_TEST_HOST` | RDS 테스트 호스트 | (RDS endpoint) |
| `DB_TEST_USER` | READ_ONLY 계정 | `readonly_user` |
| `USE_RDS_FOR_TESTS` | RDS 테스트 모드 활성화 | `false` |

---

## 6. Architecture

### 전체 시스템 구조 (MAS Supervisor v2)
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

        subgraph "MAS Supervisor v2 (Hub-Spoke)"
            G --> SUP[Supervisor<br/>gpt-4o]
            SUP --> H[Query Analysis<br/>쿼리 확장 + 의도 분류]
            SUP --> I[Selective Retrieval<br/>Law/Criteria/Case]
            I --> RM[Retrieval Merge<br/>결과 병합 + 품목 필터링]
            RM --> SUP
            SUP --> J[Answer Generation<br/>gpt-4o]
            SUP --> K[Legal Review<br/>gpt-4o]
        end
    end

    subgraph "Data & Infrastructure"
        I --> L[(PostgreSQL/pgvector<br/>text-embedding-3-large)]
        J --> M[(Redis Cache<br/>L1~L5 Multi-level Cache)]
        G --> O[Prometheus/Grafana]
    end

    subgraph "External LLM"
        J -.-> P[OpenAI gpt-4o]
        K -.-> P
        SUP -.-> P
    end
```

### 에이전트별 모델 할당
| 에이전트 | 모델 | Fallback |
|---------|------|----------|
| **Supervisor** | gpt-4o | Claude 3.5 Sonnet → Rule-based |
| **Draft Agent** | gpt-4o | gpt-4o-mini → rule_based → safe_fallback |
| **Review Agent** | gpt-4o | 규칙 기반 검토 |

### 에이전트 데이터 흐름 (v2)
```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as API Gateway
    participant SUP as Supervisor (gpt-4o)
    participant QA as Query Analysis
    participant IR as Selective Retrieval
    participant MG as Retrieval Merge
    participant AG as Draft Agent (gpt-4o)
    participant LR as Review Agent (gpt-4o)

    FE->>API: POST /chat/stream
    API->>SUP: 워크플로우 시작
    SUP->>QA: 질의 분석 (의도/키워드/쿼리 확장)
    QA-->>SUP: 분석 결과 + retriever_types
    SUP->>IR: Selective Fan-out (Law/Criteria/Case)
    IR-->>MG: 개별 검색 결과
    MG-->>SUP: 병합된 RetrievalResult + 품목 필터링 + 출처
    SUP->>AG: 답변 초안 생성 (온보딩 컨텍스트 포함)
    AG-->>SUP: 초안 + 인용
    SUP->>LR: 법률 검토 및 가드레일
    LR-->>SUP: 최종 승인 (재생성 루프 가능, max 1회)
    SUP->>API: 최종 답변 + 출처
    API->>FE: SSE 스트리밍 응답
```

---

## 7. Documentation Hub

| 대상 | 문서 링크 | 설명 |
|------|-----------|------|
| **시작하기** | [EASY_START_GUIDE_KR.md](docs/guides/EASY_START_GUIDE_KR.md) | 상세 설치 및 실행 가이드 |
| **API** | [backend/app/api/README.md](backend/app/api/README.md) | 엔드포인트 및 데이터 모델 명세 |
| **아키텍처** | [backend/app/supervisor/README.md](backend/app/supervisor/README.md) | 에이전트 상세 설계 및 구현 가이드 |
| **인프라** | [docs/infrastructure/runpod-vllm-setup.md](docs/infrastructure/runpod-vllm-setup.md) | RunPod vLLM 서버 설정 가이드 |
| **로드맵** | [docs/plans/sprint-roadmap.md](docs/plans/sprint-roadmap.md) | 스프린트별 개발 계획 및 PR 목록 |
| **평가** | [docs/guides/evaluation-strategy.md](docs/guides/evaluation-strategy.md) | 에이전트별 평가 지표 및 전략 |
| **테스트** | [backend/scripts/testing/README.md](backend/scripts/testing/README.md) | 테스트 전략 및 데이터 파이프라인 |
