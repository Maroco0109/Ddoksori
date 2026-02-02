# AGENTS.md - Repository Guide for AI Coding Agents

## Project Overview

**DDOKSORI** - Korean consumer dispute resolution chatbot (RAG + multi-agent system)

| Layer | Stack |
|-------|-------|
| Frontend | React 19, TypeScript (strict), Vite, TailwindCSS, Zustand, TanStack Query |
| Backend | FastAPI, LangGraph, PostgreSQL 16 + pgvector, Pydantic v2 |
| Infra | Docker Compose (db, backend, frontend, bge-m3, redis, monitoring) |

**Key Directories**:
- `backend/app/` - FastAPI + agents + orchestrator (LangGraph)
- `backend/scripts/testing/` - pytest suite (primary tests)
- `frontend/src/features/` - feature modules (chat/auth/board/home/procedure)
- `frontend/src/shared/` - shared UI, api client, types, utils

---

## Environment Rules (Non-Negotiable)

### Python Environment
```bash
# ALL Python commands MUST use conda env "dsr"
conda run -n dsr <command>
# OR activate first
conda activate dsr && <command>
```
**NEVER use system Python or other venvs.**

### Safety Rules
- Never commit `.env` files or secrets
- Don't create markdown docs unless explicitly requested
- Don't add verification scripts inside implementation files

---

## Build & Run Commands

### Backend (workdir: `backend/`)
```bash
# Install dependencies
conda run -n dsr pip install -r requirements.txt

# Run API server (dev)
conda run -n dsr uvicorn app.main:app --reload  # http://localhost:8000

# Health check
curl http://localhost:8000/health
```

### Frontend (workdir: `frontend/`)
```bash
npm install          # Install
npm run dev          # Dev server (http://localhost:5173)
npm run build        # Production build
npm run lint         # ESLint (note: config only targets *.js/*.jsx)
```

### Docker Compose (repo root)
```bash
docker compose up --build     # Start full stack
docker compose up db -d       # Start only Postgres
docker compose down -v        # Stop and remove volumes
```

**Service Ports**: Postgres `5432`, Backend `8000`, Frontend `5173`, Redis `6379`, Prometheus `9090`, Grafana `3000`

---

## Testing Commands

### Run All Tests
```bash
# From repo root
conda run -n dsr pytest -c backend/pytest.ini backend/scripts/testing

# From backend/
conda run -n dsr pytest
```

### Run Single Test File
```bash
conda run -n dsr pytest backend/scripts/testing/orchestrator/test_pr3_graph.py
```

### Run Single Test Function
```bash
conda run -n dsr pytest backend/scripts/testing/orchestrator/test_pr3_graph.py::test_graph_has_all_nodes
```

### Run by Keyword or Marker
```bash
conda run -n dsr pytest -k "legal_review"      # Keyword match
conda run -n dsr pytest -m "unit"              # Unit tests only
conda run -n dsr pytest -m "not slow"          # Skip slow tests
conda run -n dsr pytest -m "integration"       # Integration tests
```

### Test Markers
| Marker | Description |
|--------|-------------|
| `unit` | No DB dependency |
| `integration` | Requires PostgreSQL |
| `slow` | LLM calls, long-running |
| `llm` | Requires OPENAI_API_KEY |
| `docker` | Requires RUN_DOCKER_TESTS=1 |
| `needs_db` | Requires DB connection |

### Load Test Data (for integration tests)
```bash
conda run -n dsr python backend/scripts/data_loading/load_all_test_data.py --all
conda run -n dsr python backend/scripts/data_loading/embed_all_data.py
```

---

## Backend Code Style (FastAPI / LangGraph)

### Imports
```python
# Prefer absolute imports from app
from app.common.logger import get_rag_logger
from app.orchestrator.state import ChatState
from app.agents.retrieval.tools import SearchTool

# Relative imports only within same package, if consistent with nearby files
from .cache import get_answer_cache
```

### Type Hints
```python
# Full type hints for public functions
def process_query(user_query: str, top_k: int = 5) -> Dict[str, Any]:
    ...

# Use Pydantic models for API I/O
class ChatRequest(BaseModel):
    message: str
    top_k: int = 10
```

### Async Patterns
```python
# FastAPI endpoints are async def
@router.post("/chat")
async def chat_endpoint(request: ChatRequest) -> ChatResponse:
    # Offload blocking graph execution
    result = await asyncio.to_thread(graph.invoke, state)
    return ChatResponse(**result)
```

### Error Handling
```python
# API endpoints: use HTTPException
from fastapi import HTTPException

if not result:
    raise HTTPException(status_code=404, detail="Resource not found")

# Log before raising, keep messages safe (no secrets)
logger.error(f"Failed to process query: {query_id}")
raise HTTPException(status_code=500, detail="Processing failed")
```

### Orchestrator Patterns
- State schema: `backend/app/orchestrator/state.py` (ChatState)
- **Don't invent ad-hoc state keys** - use defined schema
- Follow Unified ReAct Graph in `backend/app/orchestrator/README_orchestrator.md`

### Logging
```python
# Use RAG logger, not print()
from app.common.logger import get_rag_logger
logger = get_rag_logger(__name__)
logger.info(f"Processing query: {query[:50]}...")
```

---

## Frontend Code Style (React / TypeScript)

### Project Structure
```
src/
  app/        # App wiring, routes, providers
  features/   # Feature modules (chat/, auth/, board/)
  shared/     # Shared UI, api, types, utils
  widgets/    # Cross-feature UI (Sidebar)
  store/      # Global Zustand stores
```

### Imports
```typescript
// Use @/ alias for src/
import { Button } from '@/shared/ui/button'
import { useChatStore } from '@/features/chat/chat.store'
import type { ChatMessage } from '@/shared/types'
```

### TypeScript
- `strict: true` is enabled - avoid `any`
- Define explicit types for props and state
- Use type imports: `import type { X } from '...'`

### State Management
```typescript
// Client state: Zustand stores
const { messages, addMessage } = useChatStore()

// Server state: TanStack Query
const { data, isLoading } = useQuery({
  queryKey: ['chat', sessionId],
  queryFn: () => fetchChat(sessionId)
})
```

### Styling
```typescript
// Tailwind utility classes
<div className="flex items-center gap-2 p-4 bg-ivory">

// Conditional classes: use cn() helper
import { cn } from '@/shared/lib/utils'
<button className={cn("btn", isActive && "btn-active")}>
```

### Naming Conventions
| Type | Convention | Example |
|------|------------|---------|
| Components | PascalCase | `MessageBubble.tsx` |
| Hooks | useX | `useChatMutation.ts` |
| Stores | feature.store.ts | `chat.store.ts` |
| Types | PascalCase | `ChatMessage`, `APIResponse` |

---

## Common Pitfalls

### Backend
- **Wrong**: Using system Python or pip directly
- **Right**: Always `conda run -n dsr` or activate `dsr` first

- **Wrong**: Inventing new ChatState keys
- **Right**: Use defined schema in `orchestrator/state.py`

- **Wrong**: Using `print()` for debugging
- **Right**: Use `get_rag_logger()` from `app.common.logger`

### Frontend
- **Wrong**: Using `any` type
- **Right**: Define proper TypeScript types

- **Wrong**: Direct localStorage access
- **Right**: Use `@/shared/lib/storage.ts` wrapper

- **Wrong**: Hardcoded API URLs
- **Right**: Use `VITE_API_BASE_URL` env variable

---

## Quick Reference

```bash
# Backend: run single test
conda run -n dsr pytest backend/scripts/testing/path/to/test.py::test_function_name -v

# Backend: run API server
conda run -n dsr uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend: dev server
cd frontend && npm run dev

# Docker: fresh start
docker compose down -v && docker compose up --build
```
