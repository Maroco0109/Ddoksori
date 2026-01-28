# Evidence Collection Report (2026-01-25)

## 1. API Endpoints Comparison

### Source of Truth: `backend/app/api/README.md`
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Server info |
| `/health` | GET | Health check |
| `/search` | POST | Vector search (LLM 없이) |
| `/chat` | POST | 챗봇 응답 생성 |
| `/chat/stream` | POST | SSE 스트리밍 응답 |
| `/case/{uid}` | GET | 사례 전체 조회 |
| `/metrics/agents` | GET | 에이전트 메트릭 |
| `/metrics/agents/summary` | GET | 메트릭 요약 |
| `/metrics/agents/recent` | GET | 최근 메트릭 |

### README Current State
- **Line 137**: `POST /chat/query` ❌ **INCORRECT**
- **Line 492**: `/guide/generate` (Mentioned in Sprint 2 table as planned) ⚠️ **NOT IMPLEMENTED**
- **Recommendation**: 
    - Update all references of `/chat/query` to `/chat` and `/chat/stream`.
    - Clarify that `/guide/generate` is a planned feature or remove if not applicable to current MVP.

## 2. Docker Services Comparison

### Source of Truth: `docker-compose.yml`
| Service | Port | Profile | Notes |
|---------|------|---------|-------|
| `db` | 5432 | default | PostgreSQL + pgvector |
| `cloudbeaver` | 8978 | default | Web-based DB Manager |
| `backend` | 8000 | default | FastAPI |
| `frontend` | 5173 | default | React + Vite |
| `bge_m3_embedding` | 8003 | bge-m3 | Optional (BGE-M3) |
| `redis` | 6379 | default | Answer Caching |
| `prometheus` | 9090 | default | Monitoring |
| `grafana` | 3000 | default | Monitoring |

### README Current State
- **Line 322**: `Embedding API :8001` ❌ **MISMATCH** (Actual is 8003)
- **Line 341**: `D -->|HTTP| F` (F is Embedding API :8001) ❌ **MISMATCH**
- **Line 627**: `CloudBeaver: http://localhost:8978` ✅ **MATCH**
- **Recommendation**: 
    - Update architecture diagrams (Mermaid) to reflect correct ports (8003 for Embedding API).
    - Add missing services (Redis, Prometheus, Grafana) to the tech stack or architecture section.

## 3. Conda Environment

### Source of Truth: `.agent/rules/environment.md`
```markdown
모든 pip install, python, run 과 같은 명령어는 "conda activate dsr" 가상환경을 활성화 한 이후 진행한다
```

### README Current State
- **Line 641**: `conda activate ddoksori` ❌ **INCORRECT**
- **Recommendation**: Change `ddoksori` to `dsr` globally.

## 4. Environment Variables

### Source of Truth: `backend/.env.example` (Key Variables)
| Variable | Purpose | Default/Example |
|----------|---------|-----------------|
| `DB_HOST` | Database host | `localhost` |
| `DB_PORT` | Database port | `5432` |
| `OPENAI_API_KEY` | OpenAI API Key | `your_openai_api_key_here` |
| `ANTHROPIC_API_KEY` | Anthropic API Key | `your_anthropic_api_key_here` |
| `EMBEDDING_MODEL` | Embedding model name | `nlpai-lab/KURE-v1` |
| `RETRIEVAL_MODE` | Search mode | `hybrid` |
| `EXAONE_RUNPOD_URL` | EXAONE LLM API URL | `http://localhost:19080/v1` |
| `REDIS_HOST` | Redis host | `localhost` |
| `REDIS_PORT` | Redis port | `6379` |
| `ENABLE_ANSWER_CACHE` | Enable Redis caching | `false` |

### README Current State
- **Status**: No dedicated environment variables section exists.
- **Recommendation**: Add a "Configuration" or "Environment Variables" section listing these key variables to help users set up the project.

## 5. Summary of Required Changes
1. **API Endpoints**: Fix `/chat/query` -> `/chat` (Line 137).
2. **Conda Env**: Fix `ddoksori` -> `dsr` (Line 641).
3. **Docker Ports**: Fix Embedding API port 8001 -> 8003 (Lines 322, 341).
4. **Architecture**: Update Mermaid diagrams to include Redis and Monitoring services if appropriate.
5. **Configuration**: Add a new section for Environment Variables based on `.env.example`.
6. **Links**: Fix 7 broken documentation links identified in the baseline snapshot.
7. **Content Reduction**: Move Sprint 1/2 task tables and detailed evaluation metrics to separate files to reduce README length.
