# v2 태그 삭제 및 코드 정규화

**작성일**: 2026-01-29
**상태**: 완료
**브랜치**: `feature/34-e2e`

---

## 개요

MAS v2가 유일한 구현으로 확정됨에 따라, 코드베이스에서 모든 `_v2` / `V2` 접미사와 v1 롤백 코드를 제거했습니다.

### 목표

- v1/v2 구분 없이 단일 구현만 존재하도록 정규화
- 불필요한 하위 호환 코드 제거
- 파일명에서 v2 제거

---

## 변경 내역

### PR-1: v1 코드 완전 제거

| 파일 | 변경 내용 |
|------|----------|
| `app/supervisor/graph.py` | `MAS_USE_V2` 환경변수 분기 제거, deprecated 함수 삭제 |
| `app/supervisor/graph_mas.py` | v1 전용 함수 삭제 (`_create_noop_node`, v1 라우터, v1 그래프 등) |

**삭제된 항목:**
- `MAS_USE_V2` 환경변수 참조
- `_create_noop_node()` 함수
- `_create_retrieval_agent_node()` (v1 버전)
- `_route_mas_supervisor()` (v1 버전)
- `create_mas_supervisor_graph()` (v1 버전)
- `get_mas_supervisor_graph()` (v1 버전)
- `_mas_compiled_graph` (v1 전역변수)

---

### PR-2: 함수명 `_v2` 접미사 제거

| 현재 이름 | 변경 후 | 파일 |
|----------|--------|------|
| `_create_retrieval_agent_node_v2` | `_create_retrieval_agent_node` | `supervisor/graph_mas.py` |
| `_route_mas_supervisor_v2` | `_route_mas_supervisor` | `supervisor/graph_mas.py` |
| `create_mas_supervisor_graph_v2` | `create_mas_supervisor_graph` | `supervisor/graph_mas.py` |
| `get_mas_supervisor_graph_v2` | `get_mas_supervisor_graph` | `supervisor/graph_mas.py` |
| `_mas_v2_compiled_graph` | `_mas_compiled_graph` | `supervisor/graph_mas.py` |

**import 전략**: agent 내부 함수(`query_analysis_node_v2` 등)는 `graph_mas.py`에서 alias import로 처리:
```python
from ..agents.query_analysis.agent import query_analysis_node_v2 as qa_node
from ..agents.answer_generation.agent import generation_node_v2 as gen_node
from ..agents.legal_review.agent import review_node_v2 as rev_node
```

---

### PR-3: 타입명 `V2` 접미사 제거

`protocols_v2.py` 내부 타입 리네임 (20개+):

| 카테고리 | 변경 전 | 변경 후 |
|---------|--------|--------|
| QueryAnalysis | `QueryAnalysisInputV2` | `QueryAnalysisInput` |
| | `QueryAnalysisOutputV2` | `QueryAnalysisOutput` |
| | `QueryAnalysisProtocolV2` | `QueryAnalysisProtocol` |
| Supervisor | `SupervisorStateV2` | `SupervisorState` |
| Retrieval | `RetrievalTaskInputV2` | `RetrievalTaskInput` |
| | `DocumentMetadataV2` | `DocumentMetadata` |
| | `RetrievedDocumentV2` | `RetrievedDocument` |
| | `RetrievalResultV2` | `RetrievalResult` |
| | `RetrievalProtocolV2` | `RetrievalProtocol` |
| Generation | `GenerationInputV2` | `GenerationInput` |
| | `ClaimEvidenceV2` | `ClaimEvidence` |
| | `GenerationOutputV2` | `GenerationOutput` |
| | `GenerationProtocolV2` | `GenerationProtocol` |
| Review | `ReviewInputV2` | `ReviewInput` |
| | `ReviewOutputV2` | `ReviewOutput` |
| | `ReviewProtocolV2` | `ReviewProtocol` |
| State | `ChatStateV2` | `ProtocolChatState` |
| Validation | `validate_*_v2` (4개) | `validate_*` |

---

### PR-4: 파일 리네임 및 정리

| 작업 | 원본 | 대상 |
|------|------|------|
| 삭제 | `app/agents/protocols.py` (deprecated v1) | - |
| 리네임 | `app/agents/protocols_v2.py` | `app/agents/protocols.py` |
| 리네임 | `scripts/testing/test_mas_v2_architecture.py` | `scripts/testing/test_mas_architecture.py` |

**추가 정리:**
- `app/agents/retrieval/__init__.py`: v1 하위 호환 코드 제거 (counsel_agent stub import)

---

## 테스트 결과

```
15 passed, 2 warnings in 49.43s
```

| 테스트 | 결과 |
|--------|------|
| `test_protocols_import` | PASSED |
| `test_retrieval_agents_import` | PASSED |
| `test_v2_nodes_import` | PASSED |
| `test_graph_v2_import` | PASSED |
| `test_create_graph_v2` | PASSED |
| `test_query_analysis_node_v2_dispute` | PASSED |
| `test_query_analysis_node_v2_general` | PASSED |
| `test_law_agent_with_metadata_filter` | PASSED |
| `test_criteria_agent_with_metadata_filter` | PASSED |
| `test_case_agent_with_category_filter` | PASSED |
| `test_extract_cited_cases` | PASSED |
| `test_build_retry_prompt_supplement` | PASSED |
| `test_build_violation_details` | PASSED |
| `test_build_retry_context` | PASSED |
| `test_full_pipeline_dispute_query` (E2E) | PASSED |

---

## RDS 연결 테스트

리팩토링 후 RDS 연결 테스트를 수행하여 프로덕션 DB 접근을 검증했습니다.

### 접속 정보

| 항목 | 값 |
|------|-----|
| Host | `ddoksori-postgres.czocsimuw0dc.ap-northeast-2.rds.amazonaws.com` |
| User | `ddoksori_ro` (읽기 전용) |
| Database | `ddoksori` |
| PostgreSQL | 17.2 |

### 데이터 확인

| 항목 | 결과 |
|------|------|
| 접속 가능 테이블 | `vector_chunks`, `search_quality_logs` |
| 전체 행 수 | 38,680 rows |
| 임베딩 차원 | 1536 |
| 임베딩 커버리지 | 100% (38,680/38,680) |

### 데이터 분포

| dataset_type | 건수 |
|-------------|------|
| case | 32,603 |
| law_guide | 6,077 |

### 환경변수 설정 (`backend/.env`)

```bash
DB_TEST_HOST=ddoksori-postgres.czocsimuw0dc.ap-northeast-2.rds.amazonaws.com
DB_TEST_USER=ddoksori_ro
DB_TEST_PASSWORD=<secret>
DB_TEST_NAME=ddoksori
```

---

## 롤백 계획

v1 코드가 완전히 삭제되었으므로, 롤백이 필요한 경우:
```bash
git revert HEAD~4..HEAD
```

---

## 남은 작업

- [ ] agent 내부 함수명 `_v2` 제거 (`query_analysis_node_v2`, `generation_node_v2`, `review_node_v2`, `expand_query_with_llm_v2` 등) - 현재 alias import로 처리 중
- [ ] 테스트 클래스명에서 `V2` 제거 (`TestV2ModuleImports` → `TestModuleImports` 등)
- [ ] `graph_mas.py` 주석에서 "v2" 언급 정리
