# Retrieval Agent (정보 검색 에이전트)

**최종 수정**: 2026-01-27 (Phase 8: Pre-retrieval LLM 도입)

## 1. 개요 (Overview)

**Retrieval Agent**는 사용자의 질문에 답변하기 위해 필요한 근거(Evidence)를 외부 데이터베이스에서 찾아오는 역할을 합니다.

### Phase 7 변경사항

MAS Supervisor 아키텍처 전환으로, **단일 Retrieval Agent가 4개의 전문 Agent로 분리**되었습니다:

| Agent | 데이터 | RAG 전략 | 최적화 포인트 |
|-------|--------|---------|-------------|
| **LawRetrievalAgent** | 법령 (체계적, 정형화) | 키워드 + 계층 필터 | 조항 번호 매칭, 정식 용어 |
| **CriteriaRetrievalAgent** | 조정기준 (모호, 임계값 기반) | 범주 + 범위 탐색 | 분쟁 유형 분류, 금액 임계값 |
| **CaseRetrievalAgent** | 분쟁사례 (서사형, 맥락) | 의미 유사도 + 유추 | 시나리오 매칭, 사건 유형 유사도 |
| **CounselRetrievalAgent** | 상담사례 (대화형, 실무) | Q&A 포맷 + 의도 기반 | 대화 패턴, 문제 분류 |

**왜 4개인가?** 단일 Retrieval Agent는 모든 데이터 타입에 최적화할 수 없음 → 각 데이터의 고유 특성에 맞춘 독립적 RAG 전략으로 정확도 극대화

### 주요 책임

1. **전문화된 검색**: 각 Agent가 담당 데이터 유형에 최적화된 검색 수행
2. **병렬 실행**: LangGraph Fan-out/Fan-in으로 4개 Agent 동시 실행 (검색 시간 최대 4배 단축)
3. **결과 병합**: `retrieval_merge_node`에서 4개 Agent 결과를 통합
4. **메타데이터 구성**: 답변 생성 시 인용(Citation)에 사용할 출처 정보 구조화

---

## 2. 아키텍처 (Architecture)

### 2.1 MAS Supervisor 아키텍처 (Phase 7 현재)

```
                              ┌─────────────────────────────────────┐
                              │          [SUPERVISOR]                │
                              │         (Central Brain)              │
                              └───────────────┬─────────────────────┘
                                              │
                                              ▼
                              ┌─────────────────────────────────────┐
                              │        [Retrieval Fan-out]          │
                              │   (4개 Agent 병렬 디스패치)          │
                              └───────────────┬─────────────────────┘
                                              │
              ┌───────────────┬───────────────┼───────────────┬───────────────┐
              ▼               ▼               ▼               ▼
      ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
      │     Law      │ │   Criteria   │ │     Case     │ │   Counsel    │
      │   Retrieval  │ │   Retrieval  │ │   Retrieval  │ │   Retrieval  │
      │    Agent     │ │    Agent     │ │    Agent     │ │    Agent     │
      └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
              │               │               │               │
              └───────────────┴───────────────┼───────────────┴───────────────┘
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
            ├── CaseRetrievalAgent (case_agent.py)
            │
            └── CounselRetrievalAgent (counsel_agent.py)
```

---

## 3. 코드 구조 (Code Structure)

```
backend/app/agents/retrieval/
├── __init__.py                  # 4개 Agent export
├── base_retrieval_agent.py      # BaseRetrievalAgent 공통 베이스
├── law_agent.py                 # LawRetrievalAgent (법령 검색)
├── criteria_agent.py            # CriteriaRetrievalAgent (기준 검색)
├── case_agent.py                # CaseRetrievalAgent (분쟁사례 검색)
├── counsel_agent.py             # CounselRetrievalAgent (상담사례 검색)
├── agent.py                     # [DEPRECATED] 레거시 통합 Retrieval
├── tools/                       # 검색 도구 구현체
│   ├── specialized_retrievers.py  # LawRetriever, CriteriaRetriever 등
│   ├── hybrid_retriever.py        # Vector + Keyword (RRF)
│   ├── rdb_retriever.py           # SQL 기반 정형 검색
│   ├── embedding_client.py        # OpenAI 임베딩 클라이언트
│   └── base.py                    # 검색 결과 데이터 클래스
├── services/                    # 외부 서비스 연동
│   ├── bge_m3_server.py           # BGE-M3 임베딩 서버
│   ├── embedding_server.py        # 임베딩 서버 클라이언트
│   └── splade_server.py           # SPLADE 스파스 임베딩
└── metrics.py                   # 검색 품질 측정 지표
```

### 주요 클래스

#### BaseRetrievalAgent

```python
class BaseRetrievalAgent(BaseAgent):
    """4개 Retrieval Agent의 공통 베이스"""

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

    async def _execute_search(self, query: str, top_k: int) -> List[LawSearchResult]:
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
| **CounselRetrievalAgent** | `CounselRetriever` | Hybrid (Vector + BM25) | Q&A 패턴 매칭 |

### 4.2 공통 도구 (tools/)

| 도구 | 설명 | 사용 Agent |
|------|------|-----------|
| **specialized_retrievers.py** | 도메인별 특화 Retriever | Law, Criteria |
| **hybrid_retriever.py** | Dense + Sparse + RRF Fusion | Case, Counsel |
| **rdb_retriever.py** | SQL 기반 정형 필터 | 공통 (필터 조건 시) |
| **embedding_client.py** | OpenAI text-embedding-3-large (1536d) | 공통 |

### 4.3 Pre-retrieval LLM (Phase 8)

검색 전 쿼리 재작성을 통해 도메인 특화 검색 정확도를 높입니다.

| 설정 | 값 | 환경변수 |
|------|-----|---------|
| 기본 모델 | EXAONE-4.0-1.2B (vLLM) | `MODEL_RETRIEVAL_LLM` |
| Fallback 모델 | gpt-4.1-nano | `MODEL_RETRIEVAL_FALLBACK` |
| vLLM 포트 | 19010 | `PORT_EXAONE_VLLM` |
| 타임아웃 | 3초 | - |

#### BaseRetrievalAgent 메서드

```python
class BaseRetrievalAgent:
    async def _rewrite_query_for_domain(self, query: str) -> str:
        """도메인별 프롬프트로 쿼리 재작성"""
        # 1. EXAONE 호출 시도 (3초 타임아웃)
        # 2. 실패 시 gpt-4.1-nano 폴백
        # 3. 최종 실패 시 original query 반환
```

#### Agent별 도메인 프롬프트

| Agent | `domain_rewrite_prompt` 예시 |
|-------|------------------------------|
| **LawRetrievalAgent** | "법령 검색에 적합하도록 법률 용어와 조항 번호를 명시하세요" |
| **CriteriaRetrievalAgent** | "분쟁해결기준 검색을 위해 분쟁 유형과 금액 범위를 명확히 하세요" |
| **CaseRetrievalAgent** | "유사 분쟁사례 검색을 위해 분쟁 상황과 결과를 요약하세요" |
| **CounselRetrievalAgent** | "상담사례 검색을 위해 소비자 문의 핵심을 추출하세요" |

#### Fallback 체인

```
EXAONE-4.0-1.2B (3초 타임아웃)
    ↓ 실패
gpt-4.1-nano (빠른 폴백)
    ↓ 실패
original query (쿼리 재작성 없이 검색)
```

---

## 5. MAS Graph 통합

### 5.1 Fan-out/Fan-in 노드

MAS Supervisor 그래프에서 4개 Agent는 병렬로 실행됩니다:

```python
# graph_mas.py
def _create_retrieval_agent_node(agent_type: str):
    """4개 Retrieval Agent를 LangGraph 노드로 생성"""
    agents = {
        'law': law_retrieval_agent,
        'criteria': criteria_retrieval_agent,
        'case': case_retrieval_agent,
        'counsel': counsel_retrieval_agent,
    }
    return agents[agent_type].as_node()

# Fan-out: 4개 Agent 병렬 디스패치
graph.add_node("retrieval_law", _create_retrieval_agent_node('law'))
graph.add_node("retrieval_criteria", _create_retrieval_agent_node('criteria'))
graph.add_node("retrieval_case", _create_retrieval_agent_node('case'))
graph.add_node("retrieval_counsel", _create_retrieval_agent_node('counsel'))

# Fan-in: 결과 병합
graph.add_node("retrieval_merge", retrieval_merge_node)
```

### 5.2 결과 병합 (retrieval_merge_node)

```python
def retrieval_merge_node(state: ChatState) -> Dict[str, Any]:
    """4개 Agent의 IndividualRetrievalResult를 RetrievalResult로 병합"""
    individual_results = state.get("individual_retrieval_results", [])

    merged = {
        'disputes': [],
        'counsels': [],
        'laws': [],
        'criteria': [],
    }

    for result in individual_results:
        agent_type = result['agent_type']
        if agent_type == 'retrieval_law':
            merged['laws'].extend(result['results'])
        elif agent_type == 'retrieval_criteria':
            merged['criteria'].extend(result['results'])
        # ... 나머지 병합 로직

    return {'retrieval': merged, 'sources': build_sources(merged)}
```

---

## 6. 테스트 방법 (Testing)

### 6.1 테스트 구조

```
backend/scripts/testing/
├── retrieval/                    # Retrieval 전용 테스트
│   ├── test_search_plan_retriever.py   # 검색 계획 + 리트리버 선택
│   ├── test_rdb_retriever.py           # SQL 기반 검색
│   └── test_embedding_client.py        # 임베딩 클라이언트
└── orchestrator/
    ├── test_mas_graph.py               # MAS 그래프 구조 검증
    └── test_e2e_queries.py             # E2E 통합 테스트
```

### 6.2 테스트 실행

```bash
# Retrieval 단위 테스트
conda run -n dsr pytest backend/scripts/testing/retrieval/ -v

# MAS 그래프 통합 테스트 (Retrieval Fan-out/Fan-in)
conda run -n dsr pytest backend/scripts/testing/orchestrator/test_mas_graph.py -v

# E2E 테스트 (전체 워크플로우)
conda run -n dsr pytest backend/scripts/testing/orchestrator/test_e2e_queries.py -m unit -v
```

### 6.3 테스트 결과 (2026-01-26)

```
# Retrieval 테스트
59 passed in 0.44s

# MAS Graph 테스트 (Retrieval 관련)
12 passed (Fan-out/Fan-in 검증 포함)

# E2E 테스트
15 passed (전체 워크플로우 검증)
```

---

## 7. 레거시 코드 (Deprecated)

### 7.1 agent.py

`agent.py`의 `retrieval_node`는 **deprecated**되었습니다. 이 모듈은 `graph_legacy.py` 롤백용으로만 유지됩니다.

```python
# ❌ 사용하지 마세요 (deprecated)
from app.agents.retrieval.agent import retrieval_node

# ✅ 새로운 방식 (MAS Supervisor)
from app.agents.retrieval import (
    LawRetrievalAgent,
    CriteriaRetrievalAgent,
    CaseRetrievalAgent,
    CounselRetrievalAgent,
)
```

### 7.2 마이그레이션 가이드

| 기존 (Legacy) | 신규 (MAS) | 비고 |
|--------------|-----------|------|
| `retrieval_node(state)` | 4개 Agent `.as_node()` | Supervisor가 조율 |
| `retrieval_node_v2(state)` | `retrieval_merge_node` | 결과 병합만 담당 |
| `SearchPlan` 기반 동적 선택 | Supervisor 의사결정 | LLM + 규칙 기반 |

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

---

## 9. 고도화 계획 (To-Be)

1. **Re-ranking Model**: Cross-Encoder 기반 정밀 재순위화 (각 Agent별 적용)
2. **Query Decomposition**: 복잡한 질문을 하위 질문으로 분해 (Multi-hop)
3. **Adaptive RRF**: 쿼리 특성에 따라 Dense/Sparse 가중치 동적 조절
4. **Agent간 협력**: 한 Agent 결과가 다른 Agent 검색을 트리거하는 체인 검색
5. **성능 메트릭**: 각 Agent별 Precision/Recall/Latency 모니터링

---

## 참조 문서

- **MAS 아키텍처**: `docs/guides/MAS_SUPERVISOR_ARCHITECTURE.md`
- **진행 기록**: `AI_MEMO.md` (Phase 1-7 상세)
- **BaseAgent 프로토콜**: `backend/app/agents/base.py`
