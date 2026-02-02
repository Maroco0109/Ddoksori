
## Model Architecture Refactor - Key Decisions (2026-01-27)

### Model Selection Rationale
- **GPT-5.1 for Supervisor**: Latest OpenAI model optimized for agentic tasks and reasoning
- **gpt-4o for Draft/Review**: High-quality output for user-facing content and legal review
- **EXAONE-4.0-1.2B for Retrieval**: Lightweight, domain-specific, cost-effective
- **gpt-4.1-nano for Fallback**: Fast, cost-efficient fallback option
- **text-embedding-3-large**: Superior embedding quality, 1536d Matryoshka support

### Architecture Decisions
- **Archive vs Delete**: Query Rewriter moved to _archive/ for potential rollback
- **Centralized Config**: ModelConfig/PortConfig pattern enables easy model swapping
- **Pre-retrieval LLM**: Domain-specific rewriting inside each agent vs centralized
- **Fallback Chains**: Multi-tier approach balances quality, cost, and reliability
- **RDS READ_ONLY**: Separate test credentials protect production data

### Implementation Choices
- **Async/Await**: Maintains responsiveness during LLM calls
- **3-second Timeout**: Balances quality and user experience for retrieval
- **5-second Timeout**: Allows more complex reasoning for supervisor decisions
- **Lazy Client Init**: Reduces startup time, initializes only when needed
- **Feature Flags**: USE_OPENAI_EMBEDDING, USE_RDS_FOR_TESTS enable gradual rollout

### Testing Strategy
- **Unit Tests**: No DB dependency, fast feedback
- **Integration Tests**: RDS READ_ONLY for safe testing
- **Health Checks**: Proactive monitoring of all LLM services
- **E2E Verification**: Manual testing with real queries

### Deployment Approach
- **RunPod vLLM**: Self-hosted EXAONE for cost control
- **SSH Tunneling**: Secure local development access
- **Docker Cleanup**: Complete removal of legacy infrastructure
- **RDS Migration**: Gradual transition with READ_ONLY testing phase
