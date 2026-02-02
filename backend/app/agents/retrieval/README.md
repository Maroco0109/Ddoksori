# Retrieval Agent (정보 검색 에이전트)

**최종 수정**: 2026-01-29 (Phase 11: 검색 파이프라인 단순화)

## 1. 개요 (Overview)

**Retrieval Agent**는 사용자의 질문에 답변하기 위해 필요한 근거(Evidence)를 외부 데이터베이스에서 찾아오는 역할을 합니다.

### Phase 7 변경사항

MAS Supervisor 아키텍처에서 **3개의 전문 Agent가 병렬 실행**됩니다:

| Agent | 데이터 | RAG 전략 | 최적화 포인트 |
|-------|--------|---------|-------------|
| **LawRetrievalAgent** | 법령 (체계적, 정형화) | 키워드 + 계층 필터 | 조항 번호 매칭, 정식 용어 |
| **CriteriaRetrievalAgent** | 조정기준 (모호, 임계값 기반) | 범주 + 범위 탐색 | 분쟁 유형 분류, 금액 임계값 |
| **CaseRetrievalAgent** | 분쟁사례 (서사형, 맥락) + 상담사례 | 의미 유사도 + 유추 | 시나리오 매칭, 사건 유형 유사도 |

> Note: `counsel_agent.py`는 레거시 파일로 여전히 디렉토리에 존재하지만, 현재 MAS 아키텍처에서는 CaseRetrievalAgent가 상담사례를 포함하여 검색을 담당합니다.

### 주요 책임

1. **전문화된 검색**: 각 Agent가 담당 데이터 유형에 최적화된 검색 수행
2. **병렬 실행**: LangGraph Fan-out/Fan-in으로 3개 Agent 동시 실행
3. **결과 병합**: `retrieval_merge_node`에서 3개 Agent 결과를 통합
4. **메타데이터 구성**: 답변 생성 시 인용(Citation)에 사용할 출처 정보 구조화

---

## 2. 아키텍처 (Architecture)

### 2.1 MAS Supervisor 아키텍처

```
                              ┌─────────────────────────────────────┐
                              │          [SUPERVISOR]                │
                              │         (Central Brain)              │
                              └───────────────┬─────────────────────┘
                                              │
                                              ▼
                              ┌─────────────────────────────────────┐
                              │        [Retrieval Fan-out]          │
                              │   (3개 Agent 병렬 디스패치)          │
                              └───────────────┬─────────────────────┘
                                              │
              ┌───────────────┬───────────────┤
              ▼               ▼               ▼
      ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
      │     Law      │ │   Criteria   │ │     Case     │
      │   Retrieval  │ │   Retrieval  │ │   Retrieval  │
      │    Agent     │ │    Agent     │ │    Agent     │
      └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
              │               │               │
              └───────────────┴───────┬───────┘
                                      │
                                      ▼
                              ┌─────────────────────────────────────┐
                              │        [Retrieval Merge]            │
                              │   (결과 통합 + 중복 제거)            │
                              └───────────────┬─────────────────────┘
                                              │
                                              ▼
                              ┌─────────────────────────────────────┐
                              │          [SUPERVISOR]                │
                              │      (다음 단계 결정)                │
                              └─────────────────────────────────────┘
```

### 2.2 클래스 계층 구조

```
BaseAgent (app/agents/base.py)
    │
    └── BaseRetrievalAgent (base_retrieval_agent.py)
            │
            ├── LawRetrievalAgent (law_agent.py)
            │
            ├── CriteriaRetrievalAgent (criteria_agent.py)
            │
            └── CaseRetrievalAgent (case_agent.py)
```

---

## 3. 코드 구조 (Code Structure)

```
backend/app/agents/retrieval/
├── __init__.py                  # 3개 Agent export
├── base_retrieval_agent.py      # BaseRetrievalAgent 공통 베이스
├── law_agent.py                 # LawRetrievalAgent (법령 검색)
├── criteria_agent.py            # CriteriaRetrievalAgent (기준 검색)
├── case_agent.py                # CaseRetrievalAgent (분쟁사례+상담사례 검색)
├── tools/                       # 검색 도구 구현체
│   ├── hybrid_retriever.py        # Vector + Keyword (RRF)
│   ├── retriever.py               # RAGRetriever (Dense search core)
│   ├── embedding_client.py        # OpenAI 임베딩 클라이언트
│   └── base.py                    # 검색 결과 데이터 클래스
```

### 주요 클래스

#### BaseRetrievalAgent

```python
class BaseRetrievalAgent(BaseAgent):
    """3개 Retrieval Agent의 공통 베이스"""

    required_inputs: ClassVar[List[str]] = ["user_query"]
    provided_outputs: ClassVar[List[str]] = ["results", "sources", "max_similarity", "avg_similarity"]
    default_top_k: ClassVar[int] = 3

    async def process(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Supervisor 요청 처리 → 표준 응답 형식 반환"""

    @abstractmethod
    async def _execute_search(self, query: str, top_k: int) -> List[Any]:
        """서브클래스에서 구현: 실제 검색 수행"""

    @abstractmethod
    def _format_results(self, results: List[Any]) -> List[Dict[str, Any]]:
        """서브클래스에서 구현: 결과 포맷팅"""

    @abstractmethod
    def _build_sources(self, results: List[Any]) -> List[Dict[str, Any]]:
        """서브클래스에서 구현: 출처 정보 생성"""
```

#### 전문 Agent 예시 (LawRetrievalAgent)

```python
class LawRetrievalAgent(BaseRetrievalAgent):
    """법령(소비자보호법, 전자상거래법 등) 검색 에이전트"""

    agent_name: ClassVar[str] = "retrieval_law"
    agent_description: ClassVar[str] = "관련 법령 조항을 검색합니다. 법률적 근거가 필요할 때 호출됩니다."

    async def _execute_search(self, query: str, top_k: int) -> List[SimilarChunkResult]:
        retriever = LawRetriever(db_config, embed_url)
        return await asyncio.to_thread(retriever.search_two_stage, query, top_k)
```

---

## 4. 검색 전략 (Retrieval Strategies)

### 4.1 Agent별 검색 전략

| Agent | Retriever | 검색 방식 | 특화 기능 |
|-------|-----------|----------|----------|
| **LawRetrievalAgent** | `LawRetriever` | Two-stage (조문 → 항/호) | 법령 계층 구조 탐색 |
| **CriteriaRetrievalAgent** | `CriteriaRetriever` | Two-stage (표 → 항목) | 분쟁유형별 필터링 |
| **CaseRetrievalAgent** | `CaseRetriever` | Hybrid (Vector + BM25) | 사건 유형 클러스터링 |

### 4.2 공통 도구 (tools/)

| 도구 | 설명 | 사용 Agent |
|------|------|-----------|
| **hybrid_retriever.py** | Dense + Lexical + 2-Way RRF Fusion | Law, Criteria, Case |
| **retriever.py** | RAGRetriever (pgvector Dense search core) | 공통 (HybridRetriever 내부) |
| **embedding_client.py** | OpenAI text-embedding-3-large (1536d) | 공통 |

### 4.3 검색 파이프라인 (Simplified)

```
Input: user_query + query_analysis(keywords, expanded_queries)
  ↓
1. Dense Search (pgvector cosine similarity)
2. Lexical Search (PostgreSQL FTS)
  ↓
3. 2-Way RRF Fusion (Dense + Lexical)
  ↓
4. Similarity Threshold Filtering
  ↓
5. Agent-specific metadata filtering (keywords 기반)
  ↓
Output: agent-protocols.md에 정의된 형식
```

> Note: Pre-retrieval LLM Query Rewriting (EXAONE/gpt-4.1-nano) 및 BGE-M3 Sparse Search는
> Phase 11에서 제거되었습니다. 쿼리 확장은 QueryAnalysisAgent가 담당합니다.

---

## 5. MAS Graph 통합

### 5.1 Fan-out/Fan-in 노드

MAS Supervisor 그래프에서 3개 Agent는 병렬로 실행됩니다:

```python
# graph_mas.py
def _create_retrieval_agent_node(agent_type: str):
    """3개 Retrieval Agent를 LangGraph 노드로 생성"""
    agents = {
        'law': law_retrieval_agent,
        'criteria': criteria_retrieval_agent,
        'case': case_retrieval_agent,
    }

# Fan-out: 3개 Agent 병렬 디스패치
for agent_type in ['law', 'criteria', 'case']:
    graph.add_node(f'retrieval_{agent_type}', _create_retrieval_agent_node(agent_type))

# Fan-in: 결과 병합
graph.add_node('retrieval_merge', retrieval_merge_node_sync)
```

### 5.2 결과 병합 (retrieval_merge_node)

```python
def retrieval_merge_node_sync(state: ChatState) -> Dict[str, Any]:
    """3개 Agent의 IndividualRetrievalResult를 통합 병합"""
    individual_results = state.get("individual_retrieval_results", [])
    # source별로 분류: law, criteria, case
    # 유사도 점수 기반 정렬 및 중복 제거
    return {'retrieval': merged, 'sources': build_sources(merged)}
```

---

## 6. 테스트 방법 (Testing)

### 6.1 테스트 구조

```
backend/scripts/testing/
├── retrieval/                    # Retrieval 전용 테스트
│   └── test_embedding_client.py        # 임베딩 클라이언트
├── supervisor/
│   ├── test_retrieval_merge.py         # 검색 결과 병합 검증
│   └── test_selective_retrieval.py     # 선택적 검색 로직
└── e2e/
    └── test_merged_retrieval.py        # E2E 검색 통합 테스트
```

### 6.2 테스트 실행

```bash
# Retrieval 단위 테스트
conda run -n dsr pytest backend/scripts/testing/retrieval/ -v

# Supervisor 통합 테스트 (Retrieval Merge)
conda run -n dsr pytest backend/scripts/testing/supervisor/test_retrieval_merge.py -v
conda run -n dsr pytest backend/scripts/testing/supervisor/test_selective_retrieval.py -v

# E2E 테스트 (전체 워크플로우)
conda run -n dsr pytest backend/scripts/testing/e2e/test_merged_retrieval.py -v
```

### 6.3 테스트 상태

Retrieval 관련 테스트는 다음 영역을 검증합니다:
- 임베딩 클라이언트 동작 (`test_embedding_client.py`)
- 검색 결과 병합 로직 (`test_retrieval_merge.py`)
- 선택적 검색 전략 (`test_selective_retrieval.py`)
- E2E 통합 검색 (`test_merged_retrieval.py`)

---

## 7. Import 방법

```python
# MAS Supervisor에서 사용
from app.agents.retrieval import (
    LawRetrievalAgent,
    CriteriaRetrievalAgent,
    CaseRetrievalAgent,
)
```

> Note: `agent.py`는 레거시 통합 Retrieval 파일로 여전히 존재하지만, MAS 아키텍처에서는 3개의 전문 Agent를 사용합니다. `counsel_agent.py`는 레거시 파일입니다.

---

## 8. 변경 이력 (History)

| 날짜 | 버전 | 내용 |
|------|------|------|
| 2026-01-14 | Sprint 1 | 초기 `StructuredRetriever` 구현. 4개 섹션 단순 병렬 검색. |
| 2026-01-22 | PR 2 | `HybridRetriever` 도입. `SearchPlan` 기반 동적 리트리버 선택. |
| 2026-01-26 | **Phase 4** | 4개 전문 Retrieval Agent 분리 (Law, Criteria, Case, Counsel). |
| 2026-01-26 | **Phase 5** | MAS Graph Fan-out/Fan-in 통합. `retrieval_merge_node` 추가. |
| 2026-01-26 | **Phase 7** | `agent.py` deprecated 표시. MAS 기본 운영 전환 완료. |
| 2026-01-27 | **Phase 8** | Pre-retrieval LLM (EXAONE-4.0-1.2B) 도입. 도메인별 쿼리 재작성 구현. text-embedding-3-large (1536d) 전환. |
| 2026-01-29 | **Phase 10** | v2 태그 삭제: counsel_agent 제거, 3개 Agent로 정규화, protocols.py 리네임 |
| 2026-01-29 | **Phase 11** | 검색 파이프라인 단순화: Pre-retrieval LLM Query Rewriting 제거, BGE-M3 Sparse Search 제거, 2-Way RRF (Dense + Lexical) 유지 |

---

## 9. 고도화 계획 (To-Be)

1. **Re-ranking Model**: Cross-Encoder 기반 정밀 재순위화 (각 Agent별 적용)
2. **Query Decomposition**: 복잡한 질문을 하위 질문으로 분해 (Multi-hop)
3. **Adaptive RRF**: 쿼리 특성에 따라 Dense/Lexical 가중치 동적 조절
4. **Agent간 협력**: 한 Agent 결과가 다른 Agent 검색을 트리거하는 체인 검색
5. **성능 메트릭**: 각 Agent별 Precision/Recall/Latency 모니터링

---

## 참조 문서

- **MAS 아키텍처**: `docs/guides/MAS_SUPERVISOR_ARCHITECTURE.md`
- **진행 기록**: `AI_MEMO.md` (Phase 1-7 상세)
- **BaseAgent 프로토콜**: `backend/app/agents/base.py`
