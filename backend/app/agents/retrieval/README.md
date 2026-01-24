# Retrieval Agent (정보 검색 에이전트)

## 1. 개요 (Overview)

**Retrieval Agent**는 사용자의 질문에 답변하기 위해 필요한 근거(Evidence)를 외부 데이터베이스에서 찾아오는 역할을 합니다. 단순한 키워드 매칭을 넘어, 의미 기반(Semantic) 벡터 검색과 전문 검색(Full-text Search)을 결합한 하이브리드 전략을 사용합니다.

### 주요 책임
1.  **다중 소스 검색**: 분쟁조정사례, 상담사례, 법령, 분쟁조정기준 등 4가지 섹션을 통합 검색합니다.
2.  **검색 전략 실행**: Query Analysis가 수립한 `Search Plan`에 따라 적절한 리트리버(Vector, Hybrid, SQL 등)를 선택하여 실행합니다.
3.  **결과 통합 및 정렬**: 여러 리트리버의 결과를 병합(Merge)하고, 유사도 점수에 따라 정렬하여 상위 문서를 선별합니다.
4.  **메타데이터 구성**: 답변 생성 시 인용(Citation)에 사용할 수 있도록 문서의 출처 정보(ID, 제목, URL 등)를 구조화합니다.

---

## 2. 아키텍처 (Architecture)

```mermaid
flowchart LR
    Input[Search Plan] --> Router{Retriever Type?}
    
    Router -- structured --> Structured[4-Section Retriever]
    Router -- hybrid --> Hybrid[Vector + Keyword (RRF)]
    Router -- law --> Law[Law Retriever]
    Router -- criteria --> Criteria[Criteria Retriever]
    Router -- rdb --> RDB[SQL Retriever]
    
    Structured --> Merge
    Hybrid --> Merge
    Law --> Merge
    Criteria --> Merge
    RDB --> Merge
    
    Merge[Merge Results] --> Format[Format RetrievalResult]
    Format --> Output[ChatState Update]
```

---

## 3. 검색 전략 (Retrieval Strategies)

이 에이전트는 상황에 따라 다양한 검색 도구(`tools/`)를 활용합니다.

| 전략 | 설명 | 사용 시나리오 |
|------|------|-------------|
| **Structured** | 기본 전략. 사례(Dispute/Counsel), 법령(Law), 기준(Criteria) 4개 섹션을 모두 검색합니다. | 일반적인 분쟁 상담 |
| **Hybrid** | Dense(Vector) 검색과 Sparse(BM25) 검색을 결합하여 RRF(Reciprocal Rank Fusion)로 재순위화합니다. | 키워드가 중요한 법률 용어 검색 |
| **Domain Specific** | 특정 도메인(법령, 기준 등)만 집중적으로 검색합니다. | "전자상거래법 보여줘"와 같은 명시적 요청 |
| **RDB (SQL)** | 날짜, 품목 등 정형 필터를 사용하여 DB를 직접 조회합니다. | "2024년 이후 사례만 찾아줘" |

---

## 4. 코드 구조 (Code Structure)

- **`agent.py`**: 에이전트 메인 진입점 (`retrieval_node`, `retrieval_node_v2`).
- **`tools/`**: 실제 검색을 수행하는 구현체들.
    - `specialized_retrievers.py`: `StructuredRetriever`, `LawRetriever` 등.
    - `hybrid_retriever.py`: 벡터+키워드 하이브리드 검색 구현.
    - `rdb_retriever.py`: SQLAlchemy 기반 RDB 검색 구현.
- **`metrics.py`**: 검색 품질 측정 지표 (Precision, Recall 등).

### 주요 함수
- `retrieval_node_v2(state)`: `search_plan`을 확인하고 동적으로 리트리버를 실행하는 최신 노드입니다.
- `_execute_retrieval_by_type(...)`: 리트리버 타입 문자열을 받아 실제 클래스를 인스턴스화하고 실행합니다.

---

## 5. 테스트 방법 (Testing)

검색 에이전트 테스트는 Mock을 활용한 단위 테스트로, DB 연결 없이 실행 가능합니다. 총 59개 테스트가 있습니다.

### 주요 테스트 스크립트

| 파일 | 테스트 수 | 설명 |
|------|----------|------|
| `test_search_plan_retriever.py` | 28개 | V2 노드, 검색 계획 생성, 리트리버 선택 로직 |
| `test_rdb_retriever.py` | 16개 | RDB 리트리버 (SQL 기반 분쟁조정기준/법령 검색) |
| `test_embedding_client.py` | 15개 | 임베딩 클라이언트 (OpenAI text-embedding-3-large) |

### 테스트 항목 상세

#### test_search_plan_retriever.py (28개 테스트)

**TestRetrieverSelection (6개)**: 쿼리 타입에 따른 리트리버 선택
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_dispute_type_selects_hybrid_dispute_counsel` | dispute 타입 → hybrid, dispute, counsel 리트리버 선택 |
| `test_law_type_selects_law_hybrid` | law 타입 → law, hybrid 리트리버 선택 |
| `test_criteria_type_selects_criteria_hybrid` | criteria 타입 → criteria, hybrid 리트리버 선택 |
| `test_general_type_selects_hybrid_only` | general 타입 → hybrid만 선택 |
| `test_keywords_add_law_retriever` | '법률' 키워드 → law 리트리버 추가 |
| `test_keywords_add_criteria_retriever` | '기준' 키워드 → criteria 리트리버 추가 |

**TestTopKDetermination (5개)**: 쿼리 타입별 top_k 결정
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_dispute_default_top_k` | dispute → top_k=10 |
| `test_law_default_top_k` | law → top_k=5 |
| `test_general_default_top_k` | general → top_k=5 |
| `test_with_filters_increases_top_k` | 필터 있으면 top_k 증가 |
| `test_top_k_max_limit` | top_k 최대 20 제한 |

**TestRerankDecision (4개)**: 리랭킹 적용 여부
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_dispute_should_rerank` | dispute → rerank=True |
| `test_law_should_rerank` | law → rerank=True |
| `test_criteria_should_rerank` | criteria → rerank=True |
| `test_general_should_not_rerank` | general → rerank=False |

**TestSearchPlanNode (3개)**: 검색 계획 노드 통합
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_creates_plan_with_dispute_analysis` | dispute 분석 → 올바른 계획 생성 |
| `test_creates_plan_with_law_analysis` | law 분석 → 올바른 계획 생성 |
| `test_round_increases_top_k` | 2차 검색 라운드 → top_k 증가 |

**TestBuildSearchQueryFromPlan (3개)**: 검색 쿼리 구성
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_uses_plan_query_if_present` | plan.query 우선 사용 |
| `test_falls_back_to_state_query` | plan.query 없으면 state.query 사용 |
| `test_no_plan_uses_state_query` | plan 없으면 state.query 사용 |

**TestMergeRetrievalResults (3개)**: 결과 병합
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_merges_disputes_from_multiple_results` | 여러 리트리버 결과 병합 |
| `test_deduplicates_by_chunk_id` | chunk_id 기준 중복 제거 |
| `test_merges_all_sections` | 4개 섹션 모두 병합 |

**TestRetrievalNodeV2 (3개)**: V2 노드 통합
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_no_retrieval_mode_returns_empty` | NO_RETRIEVAL 모드 → 빈 결과 |
| `test_uses_search_plan_retrievers` | search_plan의 리트리버 사용 |
| `test_handles_error_gracefully` | DB 오류 시 graceful 처리 |

**TestV2GraphWithRetrieval (1개)**: 그래프 통합
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_v2_graph_uses_retrieval_node_v2` | V2 그래프에 retrieval, search_plan, sufficiency 노드 존재 |

#### test_rdb_retriever.py (16개 테스트)

**TestSqlParamsCandidate (2개)**: SQL 파라미터 스키마
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_schema_has_criteria_fields` | 분쟁조정기준 필드 (category, item_group 등) |
| `test_schema_has_law_fields` | 법령 필드 (law_name, article_no 등) |

**TestSelectRetrieversWithRDB (3개)**: RDB 리트리버 선택
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_rdb_added_when_enabled` | enable_rdb_query=True → RDB 리트리버 추가 |
| `test_rdb_not_added_when_disabled` | enable_rdb_query=False → RDB 미추가 |
| `test_rdb_not_added_when_no_sql_params` | sql_params 없으면 RDB 미추가 |

**TestSearchPlanWithRDB (2개)**: RDB 검색 계획
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_rdb_retriever_selected_for_criteria_query` | 기준 쿼리 → RDB 리트리버 선택 |
| `test_combined_filters_include_sql_params` | filters에 sql_params 병합 |

**TestCriteriaRDBRetriever (2개)**: 분쟁조정기준 RDB
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_search_builds_correct_query` | 올바른 SQL 쿼리 생성 (ILIKE) |
| `test_search_dispute_resolution_targets_table2_table3` | 별표2/3 테이블 대상 검색 |

**TestLawRDBRetriever (2개)**: 법령 RDB
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_search_normalizes_article_number` | "제17조" → "17" 정규화 |
| `test_get_article_with_children_orders_by_level` | 조/항/호 계층 정렬 |

**TestRDBRetriever (2개)**: 통합 RDB 리트리버
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_search_from_params_routes_to_criteria` | criteria_units → CriteriaRDBRetriever |
| `test_search_from_params_routes_to_law` | law_units → LawRDBRetriever |

**TestExecuteRetrievalByTypeRDB (2개)**: 리트리버 타입 실행
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_rdb_type_uses_rdb_retriever` | 'rdb' 타입 → RDBRetriever 사용 |
| `test_rdb_type_converts_results_to_standard_format` | 결과를 표준 형식으로 변환 |

**TestRetrievalNodeV2WithRDB (1개)**: V2 노드 + RDB
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_uses_rdb_when_in_search_plan` | search_plan에 RDB 있으면 실행 |

#### test_embedding_client.py (15개 테스트)

**TestEmbeddingClient (9개)**: OpenAI 임베딩 클라이언트
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_init` | text-embedding-3-large, 1536차원 초기화 |
| `test_embed_single_text` | 단일 텍스트 임베딩 |
| `test_embed_multiple_texts` | 복수 텍스트 임베딩 |
| `test_embed_query` | 쿼리 임베딩 |
| `test_embed_empty_list_raises` | 빈 리스트 → ValueError |
| `test_embed_query_empty_raises` | 빈 쿼리 → ValueError |
| `test_embed_handles_empty_strings` | 빈 문자열 → 공백 대체 |
| `test_embed_batch` | 배치 처리 (100개씩) |
| `test_embed_batch_empty` | 빈 배치 → 빈 리스트 |

**TestEmbeddingAdapter (4개)**: 임베딩 어댑터
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_adapter_raises_when_openai_disabled` | USE_OPENAI_EMBEDDING=false → NotImplementedError |
| `test_adapter_raises_when_env_not_set` | 환경변수 미설정 → NotImplementedError |
| `test_adapter_works_when_openai_enabled` | USE_OPENAI_EMBEDDING=true → 정상 동작 |
| `test_adapter_embed_delegates_to_client` | embed 메서드 위임 |

**TestGetEmbeddingDimensions (1개)**: 차원 함수
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_returns_1536` | 1536 반환 |

**TestEmbeddingDimensionsConstant (1개)**: 상수
| 테스트 | 검증 내용 |
|--------|-----------|
| `test_constant_is_1536` | EMBEDDING_DIMENSIONS=1536 |

### 실행 방법
```bash
conda activate dsr
cd backend
pytest scripts/testing/retrieval/ -v
```

### 최신 테스트 결과 (2026-01-22)
```
59 passed in 0.44s
```

모든 테스트 통과:
- **PASSED**: 59개
- **SKIP**: 0개
- **FAIL**: 0개

---

## 6. 변경 이력 (History)

| 날짜 | PR | 내용 |
|------|----|------|
| 2026-01-14 | **Sprint 1** | 초기 `StructuredRetriever` 구현. 4개 섹션 단순 병렬 검색. |
| 2026-01-22 | **PR 2** | `HybridRetriever` 도입 (Vector + Keyword). `SearchPlan` 기반의 동적 리트리버 선택 기능 추가 (`retrieval_node_v2`). |

---

## 7. 고도화 계획 (To-Be)

1.  **Re-ranking Model**: 검색된 후보군(Candidates)에 대해 Cross-Encoder 기반의 정밀 재순위화(Re-ranking) 적용.
2.  **Query Decomposition**: 복잡한 질문을 여러 개의 하위 질문으로 쪼개서 검색(Multi-hop Retrieval).
3.  **Adaptive RRF**: 쿼리 특성에 따라 Dense와 Sparse의 가중치를 동적으로 조절.
