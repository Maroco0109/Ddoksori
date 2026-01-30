# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**DDOKSORI (똑소리)** - Korean consumer dispute resolution chatbot using RAG + Multi-Agent System (MAS).

- **Frontend**: React 19, TypeScript (strict), Vite, TailwindCSS, Zustand, TanStack React Query
- **Backend**: FastAPI, LangGraph, PostgreSQL (pgvector), Pydantic
- **Infrastructure**: Docker Compose (db, backend, frontend, redis, prometheus, grafana)

## Essential Commands

### Environment Setup

**All Python commands MUST use Conda environment `dsr`**:
```bash
conda activate dsr
# or prefix commands with: conda run -n dsr <command>
```

### Backend (workdir: `backend/`)

```bash
# Install dependencies
conda run -n dsr pip install -r requirements.txt

# Run API server
conda run -n dsr uvicorn app.main:app --reload

# Health check: GET http://localhost:8000/health
```

### Frontend (workdir: `frontend/`)

```bash
npm install          # Install dependencies
npm run dev          # Dev server (http://localhost:5173)
npm run build        # Production build
npm run lint         # ESLint
```

### Docker Compose (repo root)

```bash
docker compose up -d                      # Start stack (cloudbeaver, backend, frontend, redis)
```

Services: Backend:8000, Frontend:5173, CloudBeaver:8978, Redis:6379

### Testing

```bash
# All backend tests
conda run -n dsr pytest -c backend/pytest.ini backend/scripts/testing

# From backend/ directory
conda run -n dsr pytest

# Single test file
conda run -n dsr pytest backend/scripts/testing/supervisor/test_pr3_graph.py

# Single test function
conda run -n dsr pytest backend/scripts/testing/supervisor/test_pr3_graph.py::test_function_name

# By marker
conda run -n dsr pytest -m "not integration"  # Skip DB-dependent tests
conda run -n dsr pytest -m unit               # Unit tests only
```

**Test markers**: `unit` (no DB), `integration` (requires PostgreSQL), `slow`, `docker`, `skip_ci`, `llm` (needs OPENAI_API_KEY), `e2e` (full workflow), `asyncio`

**Notes**:
- API/integration tests require running Docker services and populated DB
- Some tests skip if `OPENAI_API_KEY` is missing
- Docker tests require `RUN_DOCKER_TESTS=1` env var

### Data Loading (to unblock tests with empty DB)

```bash
# Load JSONL datasets
conda run -n dsr python backend/scripts/data_loading/load_all_test_data.py --all

# Generate embeddings
conda run -n dsr python backend/scripts/data_loading/embed_all_data.py
```

## Architecture

### Multi-Agent System (MAS Supervisor - Phase 7)

Hub-Spoke 패턴의 MAS Supervisor 그래프로 전문 에이전트들을 조율합니다:

```
Entry → InputGuardrail → Supervisor ←→ [Agents] → OutputGuardrail → END

[Supervisor가 조율하는 Agent 흐름]
1. QueryAnalyst → 의도 분류/키워드 추출
2. RetrievalTeam (Fan-out) → 4개 Retrieval Agent 병렬 실행
   - LawRetrievalAgent: 법령 검색
   - CriteriaRetrievalAgent: 분쟁해결기준 검색
   - CaseRetrievalAgent: 분쟁조정사례 검색
   - CounselRetrievalAgent: 상담사례 검색
3. AnswerDrafter → LLM + Fallback 답변 생성
4. LegalReviewer → 사실 검증/금지표현 검토
```

**에이전트 위치** (`backend/app/agents/`):
- `query_analysis/` - 의도 분류, 키워드 추출, 라우팅 힌트, 모호한 쿼리 탐지
- `retrieval/` - 4개 전문 Retrieval Agent (BaseRetrievalAgent 상속)
  - `law_agent.py` - 법령 검색
  - `criteria_agent.py` - 분쟁해결기준 검색
  - `case_agent.py` - 분쟁조정사례 검색
  - `counsel_agent.py` - 상담사례 검색
- `answer_generation/` - LLM 기반 답변 생성 + Fallback 체인
- `legal_review/` - 사실 검증, 금지 표현 탐지, 인용 검증
**Fallback 체인** (답변 생성 실패 시):
1. `gpt-4o-mini` (OpenAI) - 기본
2. `claude-3-haiku` (Anthropic) - 1차 폴백
3. `rule_based` (Local) - 2차 폴백
4. `safe_fallback` - 최종 안전 메시지

**Fast Path 최적화**:
- `general`/`system_meta` 쿼리는 legal_review 생략
- `restricted` 도메인 (금융/의료)은 전문기관 안내 메시지로 처리

**Supervisor** (`backend/app/supervisor/`):
- `graph.py` - 엔트리포인트 및 공통 유틸리티 (get_graph_for_chat_type)
- `graph_mas.py` - MAS Supervisor 그래프 (현재 운영)
- `state/` - ChatState 분할 모듈 (session, agent_results, output, control, supervisor, memory)
- `nodes/` - 개별 그래프 노드 (supervisor.py, retrieval_merge.py 등)

**[ARCHIVED]** ReAct 패턴 및 Legacy 그래프는 `backend/_archive/`로 이동됨 (Phase 7)

### Database Schema

PostgreSQL with pgvector extension:
- `documents` - 소스 메타데이터 (law, counsel_case, mediation_case, criteria)
- `chunks` - 텍스트 청크 + 1024차원 임베딩 (기본: KURE-v1, 옵션: text-embedding-3-large)
- `chunk_relations` - 계층 관계 (법조문 → 항 → 호)
- `mv_searchable_chunks` - Hybrid 검색용 Materialized View

### Backend Module Structure (Phase 7 MAS Supervisor 완료)

```
backend/app/
├── common/
│   ├── logging/          # 통합 로깅 모듈
│   │   ├── config.py     # 로깅 설정
│   │   ├── handlers.py   # 파일/콘솔/JSON 핸들러
│   │   └── rag_logger.py # RAG 전용 구조화 로거
│   └── config.py         # Pydantic Settings 기반 설정 관리
├── api/                  # API 라우트 분리
│   ├── chat.py           # /chat, /chat/stream
│   ├── search.py         # /search
│   ├── case.py           # /case/{case_uid}
│   ├── health.py         # /health
│   └── metrics.py        # /metrics/*
├── supervisor/           # MAS Supervisor (구 orchestrator)
│   ├── graph.py          # 그래프 엔트리포인트
│   ├── graph_mas.py      # MAS Supervisor 그래프
│   ├── state/            # ChatState 분할
│   │   ├── session.py    # SessionState
│   │   ├── agent_results.py  # AgentResultsState
│   │   ├── output.py     # OutputState
│   │   ├── control.py    # ControlState
│   │   ├── supervisor.py # SupervisorState
│   │   └── memory.py     # MemoryState
│   └── nodes/            # 그래프 노드 구현
└── agents/
    └── protocols.py      # 에이전트 간 인터페이스 정의
```

### Frontend Structure (`frontend/src/`)

```
app/        # App entry, global config
features/   # Feature modules (chat, auth, board, home, procedure)
shared/     # Shared UI components, API client, types, utils
store/      # Zustand stores
widgets/    # Cross-feature composite widgets
```

## Code Style Guidelines

### Backend (Python)

- **Imports**: 절대 경로 import 사용 (예: `from app.common.logger import get_rag_logger`)
- **Typing**: 공개 함수에 타입 힌트 필수; API I/O는 Pydantic 모델 사용
- **Async**: FastAPI 엔드포인트는 `async def`; 블로킹 작업은 `await asyncio.to_thread()` 사용
- **Errors**: `fastapi.HTTPException`으로 안전한 메시지 반환; 로깅 후 예외 발생
- **Supervisor**: `backend/app/supervisor/README.md` 패턴 준수; 임의 state 키 생성 금지
- **Logging**: `backend/app/common/logging/` 모듈의 RAG 로거 사용 (print 금지)
- **Config**: `get_config()` 함수로 설정 접근 (예: `get_config().agent.similarity_threshold`)

### Frontend (TypeScript/React)

- **Path alias**: Use `@/` for `frontend/src` (configured in tsconfig/vite)
- **TypeScript**: `strict: true`; avoid `any`
- **State**: Zustand for client state; TanStack React Query for server state
- **Styling**: Tailwind utility classes; use `cn()` from `@/shared/lib/utils.ts` for conditional classes
- **Naming**: PascalCase components, `useX` hooks, `*.store.ts` for stores

## Key Configuration Files

- `backend/pytest.ini` - Pytest 설정 (마커: unit, integration, slow, docker, api, needs_db, e2e, llm)
- `backend/.env` - 백엔드 환경변수 (DB, API 키, 에이전트 설정)
- `backend/.env.example` - 환경변수 템플릿 (상세 설명 포함)
- `backend/app/common/config.py` - Pydantic Settings 기반 설정 관리
- `docker-compose.yml` - Local dev stack (RDS + CloudBeaver + Redis)
- `docker-compose.prod.yml` - Production stack (ECR images)
- `.agent/rules/environment.md` - 항상 활성화 규칙: `conda activate dsr` 사용

### 주요 환경변수 카테고리

- **MAS 그래프 설정**: `MAS_SUPERVISOR_ENABLED`, `MAS_SUPERVISOR_CANARY_PERCENT`
- **모델 선택**: `MODEL_SUPERVISOR`, `MODEL_DRAFT_AGENT`, `MODEL_REVIEW_AGENT`
- **에이전트 튜닝**: `SIMILARITY_THRESHOLD`, `MAX_SUPERVISOR_ITERATIONS`, `PROHIBITED_VIOLATION_THRESHOLD`
- **캐싱**: `ENABLE_ANSWER_CACHE`, `REDIS_*`
- **임베딩**: `EMBEDDING_MODEL`, `USE_OPENAI_EMBEDDING`, `BGE_M3_REMOTE_URL`

## Data Sources

- Dispute mediation cases: KCA, ECMC, KCDRC (3,173 cases)
- Consultation cases: Consumer24 (13,544 cases)
- Laws: 11 consumer protection statutes
- Dispute resolution criteria: Tables 1-4

## Important Notes

- `.env` 파일이나 비밀 정보를 커밋하지 마세요
- 검증 스크립트는 구현 파일이 아닌 `backend/scripts/testing/`에 작성
- 법률 도메인은 인용 검증 필수 - 출처가 있는 답변은 반드시 참조 포함
- Fast path 최적화: `general`/`system_meta` 쿼리는 legal_review 생략
- Restricted 도메인 (금융/의료): 전문기관 안내 메시지로 처리
- Fallback 체인: LLM 실패 시 자동으로 다음 모델로 전환 (gpt-4o-mini → claude-3-haiku → rule_based → safe_fallback)
