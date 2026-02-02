# README Baseline Snapshot

## File Stats
- **Total lines**: 650
- **Sections**: 28 (including sub-sections)
- **Code blocks**: 12 (bash, mermaid, table, etc.)

## Section Structure
| Section | Lines | Notes |
|---------|-------|-------|
| 1. 프로젝트 개요 | 5-15 | High-level overview |
| 1.1. 리포지토리 구조 | 16-45 | Directory tree (backend/frontend) |
| 2. 시스템 아키텍처 | 46-47 | Header |
| 2.1. 전체 시스템 아키텍처 | 48-120 | Mermaid diagram (Architecture) |
| 2.2. 에이전트 간 데이터 흐름 | 121-185 | Mermaid sequence diagram |
| 2.3. 에이전트 역할 및 책임 분리 | 186-258 | Detailed agent descriptions |
| 2.4. 추천 검색/데이터 설계(운영안) | 259-306 | RAG table design & pipeline |
| 2.5. 배포 아키텍처 (AWS EC2 + Docker) | 307-359 | Mermaid diagram (Deployment) |
| 2.6. 기술 스택 상세 | 360-386 | Tech stack table |
| 2.7. AI 모델 및 파라미터 상세 | 387-395 | Model & parameter table |
| 3. PR 단위 개발 로드맵 | 396-402 | Roadmap intro |
| 3.1. 서비스 책임 범위(면책) 및 에스컬레이션 | 403-421 | Legal disclaimer & escalation |
| 3.2. 개인정보/프롬프트 처리 원칙 | 422-454 | Privacy & data handling |
| 3.3. 서비스 MVP 정의(Outcome 기준) | 455-464 | MVP goals |
| Sprint 1 — RAG 프로토타입(로컬) | 465-479 | Sprint 1 task table |
| Sprint 2 — MAS 확장 + 서버화 | 480-499 | Sprint 2 task table |
| 4. 평가 전략 | 500-501 | Evaluation intro |
| 4.1. 에이전트별 평가 지표 | 502-548 | Detailed metrics tables |
| 4.2. Golden Set 구축 전략 | 549-562 | Dataset structure |
| 4.3. 평가 스크립트 (CLI) | 563-578 | Evaluation commands |
| 4.4. 서비스 KPI (출시/개선 지표) | 579-584 | Business KPIs |
| 4.5. 운영 지표 (SLO) | 585-592 | Performance SLOs |
| 5. 실행 및 테스트 가이드 (Execution Guide) | 593-600 | Link to guide |
| 6. 문서 및 가이드 | 601-602 | Header |
| 6.1 프론트엔드 설계 결정 | 603-618 | UX/UI decisions |
| 6.2 데이터베이스 및 임베딩 | 619-629 | DB links |
| 6.2. RAG 시스템 테스트 | 630-644 | Interactive test tool & command |
| 6.3. 기타 문서 | 645-650 | Misc links |

## Execution Commands Found
1. Line 567: `python -m scripts.evaluation.evaluate_retrieval --golden-set ./data/golden_set/retrieval`
2. Line 570: `python -m scripts.evaluation.evaluate_generation --golden-set ./data/golden_set/generation`
3. Line 573: `python -m scripts.evaluation.evaluate_e2e --golden-set ./data/golden_set/e2e`
4. Line 576: `python -m scripts.evaluation.generate_report --output ./reports/`
5. Line 641: `conda activate ddoksori` ⚠️ **MISMATCH** (should be `dsr`)
6. Line 642: `python backend/scripts/evaluation/interactive_rag_test.py`

## API Endpoint References
1. Line 137: `POST /chat/query` ⚠️ **MISMATCH** (actual is `/chat` or `/chat/stream`)
2. Line 492: `/guide/generate` (Mentioned in Sprint 2 table)

## Environment Variables
1. Line 391: `GPT-4o-mini` (Model reference)
2. Line 378: `OpenAI GPT-4` (Model reference)
3. Line 379: `Anthropic Claude 3` (Model reference)
*Note: README lacks a dedicated environment variables section.*

## Links Inventory
1. Line 257: `[상세 설계 문서](docs/rag_architecture_expert_view.md)` - Status: ⚠️ **BROKEN** (File not found)
2. Line 597: `[실행 및 테스트 가이드 보러가기](docs/guides/EASY_START_GUIDE_KR.md)` - Status: ✓ **EXISTS**
3. Line 621: `[pgvector Schema 생성 - 임베딩 - 데이터 로드 가이드](docs/guides/embedding_process_guide.md)` - Status: ⚠️ **BROKEN**
4. Line 626: `[DB 시각화 및 접속 가이드 (DBeaver/CloudBeaver)](docs/guides/dbeaver_wsl2_guide.md)` - Status: ⚠️ **BROKEN** (Found in `docs/_archive/guides/`)
5. Line 632: `[인터랙티브 RAG 테스트 도구](backend/scripts/evaluation/interactive_rag_test.py)` - Status: ✓ **EXISTS**
6. Line 647: `[RAG 아키텍처 전문가 뷰](docs/guides/rag_architecture_expert_view.md)` - Status: ⚠️ **BROKEN**
7. Line 648: `[백엔드 스크립트 가이드](docs/backend/scripts/embedding_scripts.md)` - Status: ⚠️ **BROKEN**
8. Line 649: `[RAG 시스템 테스트 가이드](docs/backend/scripts/TEST_README.md)` - Status: ⚠️ **BROKEN**
9. Line 490: `[분쟁조정.md](docs/guides/분쟁조정.md)` - Status: ⚠️ **BROKEN** (Found in `docs/_archive/guides/`)

## Known Mismatches Summary
1. **Conda env name**: README uses `ddoksori` (Line 641), but actual is `dsr`.
2. **API endpoints**: README diagram shows `POST /chat/query` (Line 137), but actual endpoints are `/chat` and `/chat/stream`.
3. **Frontend env key**: Plan mentions `VITE_API_URL` vs `VITE_API_BASE_URL` mismatch (not explicitly detailed in README, but relevant for fix).
4. **Model descriptions**: README emphasizes Claude/GPT (Line 105, 106, 378, 379), but actual is `gpt-4o-mini` + `EXAONE`.
5. **Excessive detail**: Sections 3 and 4 (Roadmap and Evaluation) are very long (approx. 200 lines) and should be moved to separate docs.
