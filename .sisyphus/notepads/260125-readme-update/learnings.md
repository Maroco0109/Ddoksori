# Learnings - README Update Evidence Collection

## API Endpoints
- The README currently points to `/chat/query` (Line 137), but the actual endpoints are `/chat` and `/chat/stream` as per `backend/app/api/README.md`.
- `/guide/generate` is mentioned in the roadmap but not found in the current API implementation.

## Docker & Ports
- The Embedding API port in README is 8001, but `docker-compose.yml` uses 8003 for `bge_m3_embedding`.
- Several services (Redis, Prometheus, Grafana) are present in `docker-compose.yml` but missing from the README's architecture and tech stack sections.

## Environment
- The Conda environment name is `dsr` (Source of Truth: `.agent/rules/environment.md`), but README uses `ddoksori` (Line 641).
- README lacks a dedicated section for environment variables, which are crucial for setup (e.g., `OPENAI_API_KEY`, `DB_HOST`, `EXAONE_RUNPOD_URL`).

## Documentation Links
- 7 out of 9 documentation links in the README are broken, mostly due to files being moved to `docs/_archive/` or renamed.

## README Update Learnings (2026-01-25)
- **Structure Optimization**: Successfully reduced README from 650 to 169 lines by moving detailed roadmap and evaluation metrics to `docs/`.
- **Source of Truth Alignment**:
    - Updated API endpoints: `/chat/query` (incorrect) -> `/chat` and `/chat/stream` (correct).
    - Updated Docker ports: Embedding API port 8001 -> 8003.
    - Added missing services to architecture: Redis (6379), Prometheus (9090), Grafana (3000).
    - Corrected Conda environment name: `ddoksori` -> `dsr`.
- **Configuration Visibility**: Added a dedicated "Configuration" section with key environment variables from `.env.example`.
- **Documentation Hub**: Created a role-based documentation hub to improve navigability.

## Documentation Hub Link Fixes (2026-01-25 Final)

### Broken Links Fixed
1. **Line 166 - Architecture Link**:
   - ❌ BROKEN: `docs/guides/rag_architecture_expert_view.md` (file does not exist)
   - ✅ REPLACED WITH: `backend/app/orchestrator/README.md`
   - RATIONALE: Orchestrator README covers agent architecture, workflow design, state management, and LangGraph implementation - directly addresses "에이전트 상세 설계 및 구현 가이드" requirement.

2. **Line 169 - Data/Embedding Link**:
   - ❌ BROKEN: `docs/guides/embedding_process_guide.md` (file does not exist)
   - ✅ REPLACED WITH: `backend/scripts/testing/README.md`
   - RATIONALE: Testing README covers data pipeline, test structure, and data-related testing - addresses data normalization and pipeline aspects. Alternative considered: `docs/guides/etl_*` directories exist but lack comprehensive guide files.

### Verification Results
All 6 links in Documentation Hub now verified as existing:
- ✓ `docs/guides/EASY_START_GUIDE_KR.md`
- ✓ `backend/app/api/README.md`
- ✓ `backend/app/orchestrator/README.md` (NEW)
- ✓ `docs/plans/sprint-roadmap.md`
- ✓ `docs/guides/evaluation-strategy.md`
- ✓ `backend/scripts/testing/README.md` (NEW)

### Documentation Hub Status
- Total entries: 6 (was 6, maintained)
- Broken links: 0 (was 2)
- All links verified and functional

## [2026-01-25 23:40] WORK PLAN COMPLETE

### All Acceptance Criteria Met
1. ✅ Conda env unified to `dsr` (line 22 in README)
2. ✅ `/chat/query` removed (0 occurrences)
3. ✅ Endpoints match `backend/app/api/README.md` (/chat, /chat/stream)
4. ✅ Docker ports match `docker-compose.yml` (all 8 services documented)
5. ✅ Documentation Hub created with 6 role-based links (all verified)
6. ✅ README reduced to 169 lines (target: 150-250) with Quickstart at top

### Final Metrics
- **Before**: 650 lines, 28 sections, 7/9 broken links
- **After**: 169 lines, 7 sections, 0/6 broken links
- **Reduction**: 74% shorter, 100% link accuracy

### Files Created
- `docs/plans/sprint-roadmap.md` (8.3K) - Sprint 1/2 details
- `docs/guides/evaluation-strategy.md` (4.1K) - Agent metrics
- `.sisyphus/notepads/260125-readme-update/*.md` - Analysis artifacts

### Key Fixes Applied
- Conda env: `ddoksori` → `dsr`
- API endpoints: `/chat/query` → `/chat`, `/chat/stream`
- Docker ports: Embedding API `8001` → `8003`
- Added: Configuration section with env vars table
- Added: Documentation Hub with verified links
- Fixed: All broken links (rag_architecture_expert_view.md → orchestrator/README.md, embedding_process_guide.md → testing/README.md)

### Session Duration
- Total: ~23 minutes
- Task 0 (Baseline): 13m
- Task 1 (Evidence): 3m
- Task 2 (Rewrite): 7m
- Task 5 (Links): 1m

### Verification Status
All verifications passed:
- Line count: 169 ✓
- Conda env: dsr ✓
- Wrong endpoints: 0 ✓
- Wrong ports: 0 ✓
- Broken links: 0 ✓
- Structure: 7 sections ✓
