# Retrieval Agent (정보 검색 에이전트)

**최종 수정**: 2026-02-09 (문서 정확성 개선: 4-Agent 구조, 2-Tier Retriever 아키텍처, Graph 디스패치 현황 반영)

## 1. 개요 (Overview)

**Retrieval Agent**는 사용자의 질문에 답변하기 위해 필요한 근거(Evidence)를 PostgreSQL + pgvector 데이터베이스에서 찾아오는 역할을 합니다.

### Agent 구조

MAS Supervisor 아키텍처에서 **4개의 전문 Agent**가 구현되어 있습니다:

| Agent | 데이터 | Retriever | 특화 기능 |
|-------|--------|-----------|----------|
| **LawRetrievalAgent** | 법령 (법률, 시행령) | `LawRetriever` (specialized) | 조문 번호 직접 검색, LLM 쿼리 확장, 삭제 조문 필터링 |
| **CriteriaRetrievalAgent** | 분쟁해결기준 (행정규칙, 별표) | `CriteriaRetriever` (specialized) | 키워드 추출, 계층 확장 (부모/조건/하위), LLM 쿼리 확장 |
| **CaseRetrievalAgent** | 분쟁조정사례 (조정/해결) | `UnifiedRetriever` (SQL RRF) | `dataset_filter='case'` 도메인 필터 |
| **CounselRetrievalAgent** | 상담사례 (상담) | `UnifiedRetriever` (SQL RRF) | `dataset_filter='case'`, `category_filter='상담'` |

> **Graph 디스패치 현황**: MAS Graph (`graph_mas.py`)에서는 현재 **Law, Criteria, Case 3개 Agent만** Fan-out 디스패치됩니다. `CounselRetrievalAgent`는 완전히 구현되어 `__init__.py`에서 export되며, `registry.py`를 통한 동적 선택도 가능하지만, Graph 노드로는 아직 등록되지 않았습니다.

### 주요 책임

1. **전문화된 검색**: 각 Agent가 담당 데이터 유형에 최적화된 검색 수행
2. **병렬 실행**: LangGraph Fan-out/Fan-in으로 Agent 동시 실행
3. **결과 병합**: `retrieval_merge_node`에서 Agent 결과를 통합
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
                              │     [Selective Retrieval Router]     │
                              │  (QueryAnalysis 기반 Agent 선택)     │
                              └───────────────┬─────────────────────┘
                                              │
              ┌───────────────┬───────────────┤
              ▼               ▼               ▼
      ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
      │     Law      │ │   Criteria   │ │     Case     │
      │   Retrieval  │ │   Retrieval  │ │   Retrieval  │
      │    Agent     │ │    Agent     │ │    Agent     │
      │              │ │              │ │              │
      │ LawRetriever │ │ CriteriaRet │ │ UnifiedRet   │
      │ (Python RRF) │ │ (Python RRF)│ │ (SQL RRF)    │
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

* CounselRetrievalAgent는 구현 완료되었으나 현재 Graph 노드에 미등록
```

### 2.2 Two-Tier Retriever 아키텍처

검색 구현은 **두 계층**으로 나뉩니다:

#### Tier 1: SQL-Level RRF (UnifiedRetriever)
- **사용 Agent**: `CaseRetrievalAgent`, `CounselRetrievalAgent`
- **구현**: PostgreSQL `search_hybrid_rrf()` 함수 직접 호출
- **특징**: BM25 + Vector + RRF가 SQL 레벨에서 처리됨
- **장점**: 빠른 성능, 데이터베이스 최적화 활용
- **필터링**: `_get_search_filters()`로 도메인별 필터만 지정

```python
# CaseRetrievalAgent 예시
def _get_search_filters(self, metadata_filter=None):
    return {"dataset_filter": "case"}  # 단순 필터만 지정

# CounselRetrievalAgent 예시
def _get_search_filters(self, metadata_filter=None):
    return {"dataset_filter": "case", "category_filter": "상담"}
```

#### Tier 2: Python-Level RRF (Specialized Retrievers)
- **사용 Agent**: `LawRetrievalAgent`, `CriteriaRetrievalAgent`
- **구현**: `specialized_retrievers.py` → `RDSInternalRetriever.search_hybrid_rrf_2()`
- **특징**: Python 레벨에서 다중 쿼리 RRF Fusion + 도메인별 추가 로직
- **추가 기능**:
  - **Law**: 직접 조문 검색 (`chunk_id LIKE` 매칭), 삭제 조문 필터링, LLM 쿼리 확장 (EXAONE 2.4B)
  - **Criteria**: 키워드 추출 (RRF 오염 방지), 계층 확장 (부모/조건/하위 청크), LLM 쿼리 확장 (EXAONE 2.4B)

### 2.3 클래스 계층 구조

```
BaseAgent (app/agents/base.py)
    │
    └── BaseRetrievalAgent (base_retrieval_agent.py)
            │
            ├── LawRetrievalAgent (law_agent.py)
            │       └─> _execute_search() 오버라이드
            │           → LawRetriever (specialized_retrievers.py) → Python RRF
            │
            ├── CriteriaRetrievalAgent (criteria_agent.py)
            │       └─> _execute_search() 오버라이드
            │           → CriteriaRetriever (specialized_retrievers.py) → Python RRF
            │
            ├── CaseRetrievalAgent (case_agent.py)
            │       └─> _get_search_filters() 오버라이드
            │           → UnifiedRetriever (unified_retriever.py) → SQL RRF
            │
            └── CounselRetrievalAgent (counsel_agent.py)
                    └─> _get_search_filters() 오버라이드
                        → UnifiedRetriever (unified_retriever.py) → SQL RRF
```

---

## 3. 코드 구조 (Code Structure)

```
backend/app/agents/retrieval/
├── __init__.py                  # 4개 Agent export (Law, Criteria, Case, Counsel)
├── base_retrieval_agent.py      # BaseRetrievalAgent 공통 베이스
├── law_agent.py                 # LawRetrievalAgent (법령 검색, LLM 확장)
├── criteria_agent.py            # CriteriaRetrievalAgent (기준 검색, 계층 확장)
├── case_agent.py                # CaseRetrievalAgent (분쟁조정사례)
├── counsel_agent.py             # CounselRetrievalAgent (상담사례)
├── registry.py                  # Agent 클래스 동적 선택 (v2 파이프라인 지원)
├── agent.py                     # [LEGACY] 통합 Retrieval 에이전트
├── tools/                       # 검색 도구 구현체
│   ├── unified_retriever.py       # UnifiedRetriever: SQL search_hybrid_rrf() (Tier 1)
│   ├── specialized_retrievers.py  # LawRetriever, CriteriaRetriever: Python RRF (Tier 2)
│   ├── rds_internal_retriever.py  # RDSInternalRetriever: search_hybrid_rrf_2() 등 DB 호출
│   ├── retriever.py               # SearchResult dataclass (현역) + [LEGACY] RAGRetriever
│   ├── embedding_client.py        # OpenAI text-embedding-3-large (1536d) 클라이언트
│   ├── base.py                    # [LEGACY] Document dataclass, BaseRetriever ABC
│   ├── hybrid_retriever.py        # [LEGACY] HybridRetriever
│   └── hyde.py                    # HyDE (Hypothetical Document Embeddings)
├── metrics.py                   # 검색 품질 메트릭
├── sufficiency.py               # 검색 결과 충분성 판단
├── trace.py                     # 검색 추적/로깅
└── services/                    # 외부 서비스 연동
    ├── __init__.py
    └── embedding_server.py        # 임베딩 서버 클라이언트
```

---

## 4. 검색 전략 (Retrieval Strategies)

### 4.1 Agent별 검색 파이프라인

#### LawRetrievalAgent (Tier 2: Python RRF)

`_execute_search()`를 완전 오버라이드하여 `LawRetriever`를 직접 사용합니다.

```
Input: user_query + task_input(expanded_queries, metadata_filter)
  ↓
1. 조문 번호 직접 검색 (regex 패턴: "제N조" → chunk_id LIKE 매칭)
  ↓ (direct_results 발견 시 최우선 스코어 10.0 부여)
2. LLM 쿼리 확장 (EXAONE 2.4B via expand_query_for_law_search)
   "환불" → "청약철회", "전자상거래법 제17조"
  ↓
3. 다중 쿼리 Hybrid RRF 검색 (최대 6개 쿼리)
   각 쿼리 → LawRetriever.hybrid_search()
           → RDSInternalRetriever.search_hybrid_rrf_2()
  ↓
4. Python-level RRF Fusion
   fused_scores[chunk_id] += 1.0 / (rrf_k + rank)
   direct_results 스코어 보존 (오버라이드 방지)
  ↓
5. 후처리
   - 삭제 조문 필터링 (regex: "()*삭제\\s*<")
   - 동일 조문(article_key) 최대 2건 제한
  ↓
Output: List[SimilarChunkResult] (top_k건)
```

#### CriteriaRetrievalAgent (Tier 2: Python RRF)

`_execute_search()`를 완전 오버라이드하여 `CriteriaRetriever`를 직접 사용합니다.

```
Input: user_query + task_input(expanded_queries, metadata_filter)
  ↓
1. 키워드 추출 (_extract_keywords_from_query)
   우선순위: metadata.item → COMMON_PRODUCTS 매칭 → 명사 추출 (조사 제거)
   "종묘에 관련된 분쟁이 생겼을 때" → "종묘"
  ↓
2. 검색 전략 결정
   - 키워드 추출 성공 → 키워드 단독 검색 (RRF 오염 방지)
   - 키워드 추출 실패 → 다중 쿼리 (원본 + LLM 확장 + expanded, 최대 6개)
  ↓
3. LLM 쿼리 확장 (EXAONE 2.4B via expand_query_for_criteria_search)
   "노트북 고장" → "컴퓨터 하자", "전자제품 수리 기준"
  ↓
4. Hybrid RRF 검색
   CriteriaRetriever.hybrid_search()
   → RDSInternalRetriever.search_hybrid_rrf_2()
   → filter_document_type=["행정규칙", "별표"]
  ↓
5. Python-level RRF Fusion
  ↓
6. 계층 확장 (부모/조건/하위 chunk 조합)
   - 하위(grandchild) chunk: [부모] + [조건] + [하위] 합성
   - 조건(child) chunk: [부모] + [조건] 합성
   - 동적 길이 배분 (최대 1000자, 하위→조건→부모 순 우선)
  ↓
Output: List[SimilarChunkResult] (top_k건)
```

#### CaseRetrievalAgent (Tier 1: SQL RRF)

Base `_execute_search()`를 그대로 사용하고, `_get_search_filters()`만 오버라이드합니다.

```
Input: user_query + task_input(expanded_queries)
  ↓
1. 도메인 필터: dataset_filter='case'
  ↓
2. expanded_queries 유무에 따라 분기:
   - 2개 이상 → UnifiedRetriever.search_multi() (Python-level RRF 추가)
   - 1개 이하 → UnifiedRetriever.search() (단일 쿼리)
  ↓
3. SQL search_hybrid_rrf() 호출
   - BM25 (text_tsv + JSONB metadata ILIKE) + Vector (cosine)
   - RRF Fusion at SQL level
   - 동적 RRF k값 (40~80, determine_rrf_k)
   - 동적 유사도 임계값 (0.35~0.70, adaptive_similarity_threshold)
  ↓
Output: List[SearchResult]
```

#### CounselRetrievalAgent (Tier 1: SQL RRF)

CaseRetrievalAgent와 동일한 로직, 추가 `category_filter='상담'` 필터.

```
도메인 필터: dataset_filter='case', category_filter='상담'
나머지 파이프라인은 CaseRetrievalAgent와 동일
```

### 4.2 LLM 쿼리 확장 (EXAONE 2.4B)

Law Agent와 Criteria Agent만 사용하는 도메인 특화 쿼리 확장 기능입니다.

| 기능 | 모듈 | 적용 Agent | 타임아웃 |
|------|------|-----------|---------|
| `expand_query_for_law_search()` | `query_analysis/llm_expander.py` | LawRetrievalAgent | 5초 |
| `expand_query_for_criteria_search()` | `query_analysis/llm_expander.py` | CriteriaRetrievalAgent | 5초 |

**변환 예시:**
- 법령: "온라인 환불" → "전자상거래법 청약철회", "소비자보호법 환급"
- 기준: "노트북 고장" → "컴퓨터 하자", "전자제품 수리 기준"

실패 시 graceful fallback: 빈 리스트 반환, 원본 쿼리로 검색 계속 진행.

### 4.3 Hybrid RRF 검색 파이프라인

```
Input: query_text + query_embedding (text-embedding-3-large, 1536d)
  ↓
┌─────────────────────────┬─────────────────────────┐
│   BM25 Search           │   Vector Search         │
│ (PostgreSQL FTS)        │ (pgvector cosine)       │
│ text_tsv @@             │ embedding <=>           │
│ plainto_tsquery('simple')│ query_embedding::vector │
│ + metadata ILIKE        │                         │
│ (소분류,중분류,품목,    │                         │
│  dispute_type,          │                         │
│  category_name 등)      │                         │
│ → ts_rank_cd로 랭킹     │ → 유사도 순 랭킹        │
│ LIMIT 100               │ LIMIT 100               │
└────────┬────────────────┴────────┬────────────────┘
         │                         │
         └──────────┬──────────────┘
                    ▼
         ┌───────────────────────┐
         │   RRF Fusion          │
         │ score = Σ 1/(k+rank)  │
         │ k = 40~80 (동적 결정) │
         │                       │
         │ k=40: 법령 직접 참조  │
         │ k=50: 분쟁해결기준    │
         │ k=60: 기본값          │
         │ k=80: 사례/일반 질문  │
         └──────────┬────────────┘
                    ▼
         ┌───────────────────────┐
         │ Threshold Filtering   │
         │ adaptive (0.35~0.70)  │
         │ max_sim * 0.70 기준   │
         │ (최소 3건 보장)       │
         └──────────┬────────────┘
                    ▼
         Output: sorted results
```

### 4.4 검색 도구 요약

| 도구 | 역할 | 사용처 |
|------|------|--------|
| `unified_retriever.py` | SQL search_hybrid_rrf() 호출, 동적 RRF k/threshold | Case, Counsel Agent (base `_execute_search`) |
| `specialized_retrievers.py` | LawRetriever, CriteriaRetriever (Python RRF + 도메인 로직) | Law, Criteria Agent (`_execute_search` 오버라이드) |
| `rds_internal_retriever.py` | `search_hybrid_rrf_2()` 등 DB stored function 호출 | Specialized retrievers 내부 |
| `retriever.py` | `SearchResult` dataclass, `_to_category_path()` 유틸 | UnifiedRetriever 결과 변환 |
| `embedding_client.py` | OpenAI text-embedding-3-large (1536d) | 공통 임베딩 생성 |

---

## 5. MAS Graph 통합

### 5.1 Fan-out/Fan-in 노드

MAS Supervisor 그래프에서 Agent는 Selective Retrieval Router를 통해 병렬 실행됩니다:

```python
# graph_mas.py - 실제 코드 구조

def _create_retrieval_agent_node(agent_type: str):
    """Retrieval Agent를 LangGraph 노드로 생성"""
    from ..agents.retrieval.case_agent import case_retrieval_agent
    from ..agents.retrieval.criteria_agent import criteria_retrieval_agent
    from ..agents.retrieval.law_agent import law_retrieval_agent

    agent_map = {
        'law': law_retrieval_agent,
        'criteria': criteria_retrieval_agent,
        'case': case_retrieval_agent,
    }
    # ...

# 현재 3개 Agent 노드 등록 (counsel 제외)
for agent_type in ['law', 'criteria', 'case']:
    graph.add_node(f'retrieval_{agent_type}', ...)

# Selective Retrieval Router: QueryAnalysis 결과에 따라 필요한 Agent만 디스패치
def selective_retrieval_router(state):
    retriever_types = state.get("retriever_types", ["law", "criteria", "case"])
    fan_out_list = [Send(f"retrieval_{rt}", state) for rt in retriever_types]
    return fan_out_list  # 또는 결과 없으면 "generation" 직행

# Fan-in: 결과 병합
graph.add_node('retrieval_merge', retrieval_merge_node)
```

### 5.2 결과 병합 (retrieval_merge_node)

```python
def retrieval_merge_node(state: ChatState) -> Dict[str, Any]:
    """Agent의 IndividualRetrievalResult를 통합 병합"""
    individual_results = state.get("individual_retrieval_results", [])
    # source별로 분류: law, criteria, case
    # 유사도 점수 기반 정렬 및 중복 제거
    return {'retrieval': merged, 'sources': build_sources(merged)}
```

---

## 6. BaseRetrievalAgent 상세

### 6.1 공통 인터페이스

```python
class BaseRetrievalAgent(BaseAgent):
    """4개 Retrieval Agent의 공통 베이스"""

    required_inputs: ClassVar[List[str]] = ["user_query"]
    provided_outputs: ClassVar[List[str]] = [
        "results", "sources", "max_similarity", "avg_similarity"
    ]
    default_top_k: ClassVar[int] = 10
    domain_key: ClassVar[str] = ""  # 서브클래스에서 오버라이드 (law, criteria, case, counsel)

    async def process(self, request: Dict) -> Dict:
        """Supervisor 요청 처리 → report_to_supervisor() 표준 응답 반환"""

    def _get_search_filters(self, metadata_filter=None) -> Dict:
        """서브클래스에서 오버라이드: UnifiedRetriever에 전달할 필터 반환"""

    async def _execute_search(self, query, top_k, ...) -> List:
        """기본 구현: UnifiedRetriever 사용 (Case/Counsel Agent)
           Law/Criteria는 이 메서드를 완전 오버라이드"""

    @abstractmethod
    def _format_results(self, results) -> List[Dict]:
        """서브클래스에서 구현: 결과 포맷팅"""

    @abstractmethod
    def _build_sources(self, results) -> List[Dict]:
        """서브클래스에서 구현: 출처 정보 생성"""
```

### 6.2 확장 패턴

| 패턴 | 사용 Agent | 설명 |
|------|-----------|------|
| `_get_search_filters()` 오버라이드 | Case, Counsel | 도메인 필터만 변경, base `_execute_search()` 재사용 |
| `_execute_search()` 완전 오버라이드 | Law, Criteria | 독자적 검색 파이프라인 (Specialized Retriever 사용) |

### 6.3 process() 흐름

```
request → validate_request()
  ↓
context에서 user_query, query_analysis, retrieval_task_input 추출
  ↓
_execute_search(query, top_k, task_input) 호출
  ↓
결과 없음? → report_to_supervisor(status="failure", message="검색 결과 없음")
  ↓
_format_results(results) → formatted
_build_sources(results) → sources
max/avg similarity 계산
  ↓
report_to_supervisor(status="success", result={results, sources, similarity, search_time_ms})
```

---

## 7. 테스트 방법 (Testing)

### 7.1 테스트 구조

```
backend/scripts/testing/
├── retrieval/                         # Retrieval 전용 테스트
│   ├── test_embedding_client.py         # 임베딩 클라이언트 테스트
│   ├── test_retrieval_agents.py         # Agent 단위 테스트
│   ├── test_merge_results.py            # 결과 병합 테스트
│   └── smoke_case_counsel.py            # Case/Counsel 스모크 테스트
├── supervisor/
│   ├── test_retrieval_merge.py          # 검색 결과 병합 검증
│   └── test_selective_retrieval.py      # 선택적 검색 로직
└── e2e/
    └── test_merged_retrieval.py         # E2E 검색 통합 테스트
```

### 7.2 테스트 실행

```bash
# Retrieval 단위 테스트 (전체)
conda run -n dsr pytest backend/scripts/testing/retrieval/ -v

# 개별 테스트 파일
conda run -n dsr pytest backend/scripts/testing/retrieval/test_retrieval_agents.py -v
conda run -n dsr pytest backend/scripts/testing/retrieval/test_embedding_client.py -v
conda run -n dsr pytest backend/scripts/testing/retrieval/test_merge_results.py -v

# Supervisor 통합 테스트 (Retrieval Merge + Selective Retrieval)
conda run -n dsr pytest backend/scripts/testing/supervisor/test_retrieval_merge.py -v
conda run -n dsr pytest backend/scripts/testing/supervisor/test_selective_retrieval.py -v

# E2E 테스트 (전체 워크플로우)
conda run -n dsr pytest backend/scripts/testing/e2e/test_merged_retrieval.py -v
```

### 7.3 테스트 영역

| 영역 | 파일 | 설명 |
|------|------|------|
| 임베딩 | `test_embedding_client.py` | OpenAI 임베딩 클라이언트 동작 검증 |
| Agent 검색 | `test_retrieval_agents.py` | 개별 Agent 검색 로직 검증 |
| 결과 병합 | `test_merge_results.py`, `test_retrieval_merge.py` | 병합/중복 제거 로직 |
| 선택적 검색 | `test_selective_retrieval.py` | QueryAnalysis 기반 Agent 선택 |
| 스모크 | `smoke_case_counsel.py` | Case/Counsel Agent 기본 동작 |
| E2E 통합 | `test_merged_retrieval.py` | 전체 파이프라인 통합 검증 |

---

## 8. Import 방법

```python
# MAS Supervisor에서 사용 (4개 Agent 클래스)
from app.agents.retrieval import (
    LawRetrievalAgent,
    CriteriaRetrievalAgent,
    CaseRetrievalAgent,
    CounselRetrievalAgent,
)

# 싱글톤 인스턴스 import
from app.agents.retrieval import (
    law_retrieval_agent,
    criteria_retrieval_agent,
    case_retrieval_agent,
    counsel_retrieval_agent,
)

# 동적 Agent 선택 (v2 파이프라인)
from app.agents.retrieval.registry import get_case_agent_class, get_counsel_agent_class
```

> Note: `agent.py`는 레거시 통합 Retrieval 파일로 여전히 존재하지만, MAS 아키텍처에서는 전문 Agent를 사용합니다.

---

## 9. 설정 (Configuration)

### 9.1 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `OPENAI_API_KEY` | (필수) | OpenAI 임베딩/LLM API 키 |
| `EMBEDDING_MODEL` | `text-embedding-3-large` | 임베딩 모델 |
| `EMBEDDING_DIMENSION` | `1536` | 임베딩 차원 (Matryoshka) |
| `ENABLE_DOCUMENT_LEVEL_SIMILARITY` | `true` | 문서 수준 유사도 검색 활성화 |
| `ENABLE_DISPUTE_METADATA_EXTRACTION` | `true` | 분쟁사례 EXAONE 메타데이터 추출 |
| `DOCUMENT_SIMILARITY_CANDIDATE_MULTIPLIER` | `5` | 문서 유사도 후보 배수 (top_k * N) |
| `USE_INTENT_PIPELINE_V2` | `0` | v2 파이프라인 Agent 사용 |

### 9.2 Retrieval Config (`app/common/config.py`)

| 설정 | 경로 | 설명 |
|------|------|------|
| `rrf_k_python` | `get_config().retrieval.rrf_k_python` | Python-level RRF k 파라미터 (기본 60) |

### 9.3 SQL 사전 조건

- `vector_chunks` 테이블: 임베딩(`embedding`) + BM25 tsvector(`text_tsv`) 저장
- `search_hybrid_rrf` SQL 함수: `004_add_rrf_search_functions.sql`로 생성
- pgvector 확장: HNSW 인덱스, `ef_search=100`으로 설정 (UnifiedRetriever.connect() 시)

---

## 10. 변경 이력 (History)

| 날짜 | 버전 | 내용 |
|------|------|------|
| 2026-01-14 | Sprint 1 | 초기 `StructuredRetriever` 구현. 4개 섹션 단순 병렬 검색. |
| 2026-01-22 | PR 2 | `HybridRetriever` 도입. `SearchPlan` 기반 동적 리트리버 선택. |
| 2026-01-26 | **Phase 4** | 4개 전문 Retrieval Agent 분리 (Law, Criteria, Case, Counsel). |
| 2026-01-26 | **Phase 5** | MAS Graph Fan-out/Fan-in 통합. `retrieval_merge_node` 추가. |
| 2026-01-26 | **Phase 7** | `agent.py` deprecated 표시. MAS 기본 운영 전환 완료. |
| 2026-01-27 | **Phase 8** | UnifiedRetriever 도입. Pre-retrieval LLM (EXAONE) 도입. text-embedding-3-large (1536d) 전환. |
| 2026-01-29 | **Phase 10** | Graph에서 counsel_agent 노드 제거, 3개 Agent Fan-out으로 전환. CounselRetrievalAgent 클래스는 유지. protocols.py 리네임. |
| 2026-01-29 | **Phase 11** | 검색 파이프라인 단순화: Pre-retrieval LLM Query Rewriting 제거 (Law/Criteria Agent 내부 확장으로 이관), BGE-M3 Sparse Search 제거, Hybrid RRF (BM25 + Vector) 유지. |
| 2026-02-09 | **문서 개선** | README 전면 개정: 4-Agent 구조 + Graph 디스패치 현황 정확 반영, Two-Tier Retriever 아키텍처 문서화, LLM 쿼리 확장(EXAONE 2.4B) 파이프라인 기술, 테스트 파일 목록 갱신, 설정 섹션 추가. |

---

## 11. 고도화 계획 (To-Be)

1. **CounselAgent Graph 통합**: `CounselRetrievalAgent`를 MAS Graph 노드로 등록하여 4-Agent 병렬 디스패치 완성
2. **Re-ranking Model**: Cross-Encoder 기반 정밀 재순위화 (각 Agent별 적용)
3. **Query Decomposition**: 복잡한 질문을 하위 질문으로 분해 (Multi-hop)
4. **Adaptive RRF**: 쿼리 특성에 따라 Dense/Lexical 가중치 동적 조절
5. **Agent간 협력**: 한 Agent 결과가 다른 Agent 검색을 트리거하는 체인 검색
6. **성능 메트릭**: 각 Agent별 Precision/Recall/Latency 모니터링
7. **Fine-tuned EXAONE**: 쿼리 확장 모델을 도메인 특화 Fine-tuning

---

## 참조 문서

- **MAS 아키텍처**: `docs/guides/MAS_SUPERVISOR_ARCHITECTURE.md`
- **진행 기록**: `AI_MEMO.md` (Phase 1-11 상세)
- **BaseAgent 프로토콜**: `backend/app/agents/base.py`
- **쿼리 분석 에이전트**: `backend/app/agents/query_analysis/README.md`
- **LLM 쿼리 확장**: `backend/app/agents/query_analysis/llm_expander.py`
- **SQL 함수**: `backend/migrations/004_add_rrf_search_functions.sql`
