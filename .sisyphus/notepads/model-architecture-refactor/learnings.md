
## Phase 3: Pre-retrieval LLM Query Rewriting (2026-01-27)

### Implementation Pattern
- Added `_rewrite_query_for_domain()` async method to `BaseRetrievalAgent`
- Uses `asyncio.wait_for()` with 3-second timeout for non-blocking LLM calls
- Fallback chain: EXAONE → gpt-4.1-nano → original query

### Key Design Decisions
1. **ClassVar for clients**: Used `_exaone_client` and `_openai_client` as ClassVar to share across instances
2. **Lazy initialization**: Clients only created when first needed (via `_get_*_client()` methods)
3. **Config integration**: Uses `config.models.retrieval_llm` and `config.models.retrieval_fallback` from centralized config
4. **Domain prompts as ClassVar**: Each agent defines `domain_rewrite_prompt` as ClassVar for easy override

### Domain-Specific Prompts
- **Law**: "Convert this user query into a formal legal search query focusing on relevant laws and regulations"
- **Criteria**: "Convert this everyday language query into a dispute resolution criteria search query"
- **Case**: "Convert this problem description into a similar case search query"
- **Counsel**: "Convert this conversational query into a counseling case search query"

### Logging Strategy
- INFO level: Successful rewrites with before/after query
- WARNING level: Timeouts and failures
- INFO level: Fallback to original query

### Test Results
- All 138 unit tests passing
- Import verification successful for all 4 agents

### RunPod vLLM Setup & Health Checks
- Created comprehensive guide for RunPod vLLM setup in `docs/infrastructure/runpod-vllm-setup.md`.
- Added health check endpoints for LLM services in `backend/app/api/health.py`:
  - `/health/llm/supervisor`: Checks OpenAI API connection.
  - `/health/llm/exaone`: Checks vLLM server connection.
  - `/health/embedding`: Checks embedding server connection (OpenAI or local).
- Updated `.env` with `MODEL_*` and `PORT_*` variables for centralized model management.
- Verified endpoints using `curl` against a live (temporary) server instance.

## Model Architecture Refactor - Learnings (2026-01-27)

### Config Pattern
- Pydantic BaseSettings provides excellent centralized configuration management
- env_prefix allows clean namespace separation (MODEL_, PORT_, DB_TEST_)
- Backward compatibility maintained by keeping existing config classes
- get_config() singleton pattern works well for application-wide settings

### Pre-retrieval LLM Implementation
- BaseRetrievalAgent pattern allows shared functionality across 4 agents
- Domain-specific prompts significantly improve query quality
- 3-second timeout prevents blocking, async/await maintains responsiveness
- Fallback chain (EXAONE → gpt-4.1-nano → original) ensures robustness

### Supervisor Model Integration
- AsyncLLMWrapper successfully unifies OpenAI and Anthropic clients
- _try_llm_decision() pattern enables clean fallback handling
- Logging model names in decisions aids debugging and monitoring
- 5-second timeout balances quality and responsiveness

### RDS Integration
- RDS schema differs from local: vector_chunks vs documents/chunks/mv_searchable_chunks
- conftest.py RDS mode detection prevents schema validation failures
- READ_ONLY account successfully prevents accidental data modification
- USE_RDS_FOR_TESTS flag enables safe integration testing

### Fallback Strategies
- Multi-tier fallbacks provide excellent resilience
- Supervisor: GPT-5.1 → Claude 3.5 Sonnet → Rule-based
- Draft: gpt-4o → gpt-4o-mini → rule_based
- Retrieval: EXAONE → gpt-4.1-nano → original query
- Each tier logs failures, enabling monitoring and debugging

### Testing Insights
- 421 unit tests passed without DB dependency
- Integration tests work with RDS READ_ONLY account
- Health check endpoints provide valuable service monitoring
- Docker cleanup essential for clean RDS transition

### Documentation Value
- RunPod vLLM setup guide reduces deployment friction
- Health check endpoints enable proactive monitoring
- .env.example documentation prevents configuration errors
- Notepad system captures institutional knowledge effectively
