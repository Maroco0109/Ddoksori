# MAS 아키텍처 분석 보고서

**작성일**: 2026-01-29
**분석 대상**: MAS Supervisor v2 (Phase 7)
**참조 문서**: `docs/guides/supervisor/agent-protocols.md`

---

## 목차

1. [top_k 하드코딩 분석](#1-top_k-하드코딩-분석)
2. [에이전트 독립성 분석](#2-에이전트-독립성-분석)
3. [프로토콜 vs 구현 차이](#3-프로토콜-vs-구현-차이)
4. [RDS 연결 구조 분석](#4-rds-연결-구조-분석)
5. [권고사항](#5-권고사항)

---

## 1. top_k 하드코딩 분석

### 현재 구현

Supervisor가 모든 Retrieval Agent에 동일한 `top_k=5`를 하드코딩으로 전달합니다.

**코드 위치**: `backend/app/supervisor/graph_mas.py:148-149`

```python
request = {
    'context': { ... },
    'params': {
        'top_k': 5,                                          # 하드코딩
        'metadata_filter': metadata_filter,
        'ignore_threshold': agent_type in ('law', 'criteria'), # 하드코딩
    },
}
```

**BaseRetrievalAgent의 기본값**: `backend/app/agents/retrieval/base_retrieval_agent.py`

```python
class BaseRetrievalAgent:
    default_top_k: ClassVar[int] = 3  # 사용되지 않음 — Supervisor가 항상 5를 전달
```

`process()` 메서드에서 `params.get("top_k", self.default_top_k)`로 읽지만, Supervisor가 항상 `top_k=5`를 전달하므로 `default_top_k=3`은 사실상 dead code입니다.

### 왜 Supervisor가 top_k를 결정하는가?

MAS Hub-Spoke 패턴에서 Supervisor는 **중앙 조율자**입니다. 현재 설계는 Supervisor가 모든 파라미터를 일괄 제어하여 일관성을 보장하는 방식을 선택했습니다:

| 파라미터 | 제어 주체 | 위치 |
|----------|-----------|------|
| `top_k` | Supervisor (하드코딩) | `graph_mas.py:149` |
| `metadata_filter` | Supervisor (agent_type별 분기) | `graph_mas.py:126-139` |
| `ignore_threshold` | Supervisor (하드코딩) | `graph_mas.py:151` |
| `similarity_threshold` | Agent 자체 (`AgentSettings`) | `config.py:352-372` |

### 문제점

1. **도메인별 차등 없음**: 법령(정확한 조문 소수) vs 사례(다양한 관점 다수) vs 기준(품목별 1-2건)의 최적 top_k가 다를 수 있으나 모두 5로 동일
2. **설정 불가**: `AgentSettings`에 `similarity_threshold_*` (도메인별 5종)은 있으나 `top_k_*`는 없음
3. **Dead code**: `BaseRetrievalAgent.default_top_k=3`이 실행되는 경로 없음
4. **환경변수 미지원**: .env로 오버라이드 불가

### similarity_threshold과의 비교

리팩토링에서 `AgentSettings`에 도메인별 threshold를 분리한 것은 모범적:

```python
# config.py — AgentSettings
similarity_threshold: float = 0.01           # 기본
similarity_threshold_dispute: float = 0.01   # 분쟁
similarity_threshold_law: float = 0.012      # 법령 (엄격)
similarity_threshold_criteria: float = 0.01  # 기준
similarity_threshold_general: float = 0.008  # 일반 (관대)
```

`top_k`도 동일 패턴으로 도메인별 설정이 가능하나, 현재는 미구현 상태입니다.

---

## 2. 에이전트 독립성 분석

### 제어 분담 현황

| 결정 사항 | Supervisor | Agent |
|-----------|:----------:|:-----:|
| 어떤 에이전트를 호출할지 | O | - |
| 호출 순서 (phase progression) | O | - |
| top_k (결과 수) | O | - |
| metadata_filter (검색 범위) | O | - |
| ignore_threshold (임계치 무시 여부) | O | - |
| similarity_threshold (유사도 기준) | - | O |
| chunk_type_filter (청크 타입) | - | O |
| search_query 구성 | - | O |
| 결과 포맷팅 및 정렬 | - | O |
| 재시도 여부 | O | - |
| 최대 반복 횟수 | O (max 10) | - |

**결론**: Supervisor가 **파라미터 결정권**의 약 60%를 가짐. Agent는 **실행 방법론**만 자체 결정.

### Supervisor의 라우팅 분석

`supervisor.py`의 `decide_next_action()`은 3-tier 결정 구조:

```
1. fast_path → NO_RETRIEVAL 쿼리 (일반 대화): QA → Generation → 종료
2. straightforward_rag → 법령/기준 쿼리: QA → Retrieval → Generation → 종료
3. llm_based → 분쟁 쿼리: QA → Retrieval → Generation → Review → 종료
```

실제로 LLM 기반 동적 라우팅은 fallthrough에서만 도달하며, **대부분 deterministic rule-based**입니다. 이는 안정성 면에서는 장점이지만, Supervisor의 "지능적 조율" 역할은 제한적입니다.

### Agent Registry와 실제 사용의 괴리

`agent_registry.py`는 각 에이전트의 `required_inputs`와 `provided_outputs`를 선언합니다:

```python
# 예: answer_drafter
registry.register(
    name="answer_drafter",
    required_inputs=["user_query", "retrieval_results"],
    provided_outputs=["draft_answer", "citations"],
)
```

그러나 **Supervisor는 Registry를 통해 에이전트를 선택하지 않습니다**. `graph_mas.py`에서 직접 import로 노드를 등록합니다:

```python
from ..agents.query_analysis.agent import query_analysis_node_v2 as qa_node
from ..agents.answer_generation.agent import generation_node_v2 as gen_node
from ..agents.legal_review.agent import review_node_v2 as rev_node
```

Registry의 `required_inputs`/`provided_outputs` 메타데이터는 참조되지 않아 **선언과 실제 동작이 검증되지 않는** 상태입니다.

### Registry 불일치 발견

`agent_registry.py:326-332`에 `retrieval_counsel`이 여전히 등록되어 있습니다:

```python
registry.register(
    name="retrieval_counsel",
    description="상담사례 검색",
    category="retrieval",
)
```

그러나 `counsel_agent.py`는 리팩토링에서 삭제되었고, `graph_mas.py`에서도 3개 Agent만 생성합니다:

```python
for agent_type in ['law', 'criteria', 'case']:
    node_fn = _create_retrieval_agent_node(agent_type)
```

**영향**: Registry를 신뢰하는 코드가 `retrieval_counsel`을 참조하면 실행 오류 발생 가능.

---

## 3. 프로토콜 vs 구현 차이

### 3.1 Retrieval Agent 입력 형식

| 항목 | 프로토콜 (`protocols.py`) | 실제 구현 (`graph_mas.py`) |
|------|---------------------------|---------------------------|
| **형식** | Flat dict (`RetrievalTaskInput`) | Nested dict `{context: {}, params: {}}` |
| **필드** | `expanded_queries, agent_keywords, metadata_filter, top_k, ignore_threshold` | `context: {user_query, query_analysis, expanded_queries, agent_keywords}` + `params: {top_k, metadata_filter, ignore_threshold}` |

```python
# 프로토콜 정의 (protocols.py:169-184)
class RetrievalTaskInput(TypedDict):
    expanded_queries: List[str]
    agent_keywords: List[str]
    metadata_filter: MetadataFilter
    top_k: int
    ignore_threshold: bool

# 실제 구현 (graph_mas.py:141-153)
request = {
    'context': {
        'user_query': user_query,
        'query_analysis': query_analysis,
        'expanded_queries': expanded_queries,
        'agent_keywords': keywords,
    },
    'params': {
        'top_k': 5,
        'metadata_filter': metadata_filter,
        'ignore_threshold': agent_type in ('law', 'criteria'),
    },
}
```

**불일치**: 프로토콜은 flat dict를 정의하지만, 실제로는 `context`/`params` 2레벨 nested dict를 사용.

### 3.2 QueryAnalysisOutput 추가 필드

프로토콜에 정의된 7개 필드 외에 실제 구현은 v1 호환 필드를 추가로 반환합니다:

| 필드 | 프로토콜 정의 | 실제 반환 |
|------|:------------:|:---------:|
| `intent` | O | O |
| `original_query` | O | O |
| `expanded_queries` | O | O |
| `keywords` | O | O |
| `retriever_types` | O | O |
| `needs_clarification` | O | O |
| `missing_fields` | O | O |
| `query_type` | X | O (v1 호환) |
| `extracted_info` | X | O (v1 호환) |
| `rewritten_query` | X | O (v1 호환) |
| `search_queries` | X | O (v1 호환) |

하위 호환성 측면에서는 문제 없으나, 프로토콜 문서와 실제 출력이 일치하지 않아 **새 에이전트 개발 시 혼란 유발** 가능.

### 3.3 Generation/Review의 State 직접 읽기

프로토콜은 `GenerationInput`, `ReviewInput` TypedDict를 정의했지만, 실제 구현은 **ChatState에서 직접 필드를 읽습니다**:

```python
# generation_node_v2 (실제 구현)
def generation_node_v2(state: ChatState) -> Dict:
    user_query = state.get('user_query', '')              # ChatState에서 직접
    retrieval = state.get('retrieval', {})                 # ChatState에서 직접
    retry_context = state.get('retry_context')             # ChatState에서 직접
```

`GenerationInput` TypedDict는 정의만 있고 실제로 인스턴스화되는 곳이 없습니다. 이는 LangGraph의 설계 패턴(state를 직접 전달)과 명시적 타입 프로토콜 사이의 구조적 괴리입니다.

### 3.4 counsel_agent 참조 잔존

| 위치 | 상태 |
|------|------|
| `protocols.py:66` — `EvidenceSource` | `'counsel'` 여전히 포함 |
| `agent_registry.py:326` — 기본 등록 | `retrieval_counsel` 여전히 등록 |
| `agent-protocols.md:624` — 참조 파일 | `INTERFACE_COUNSEL_CASE.md` 참조 |
| `graph_mas.py` — 그래프 노드 | counsel 노드 없음 (정상) |
| `graph_mas.py:9` — 모듈 docstring | "4개 Retrieval Agent" 언급 (불일치) |

---

## 4. RDS 연결 구조 분석

### 연결 분기 로직

`base_retrieval_agent.py:_get_db_config()`:

```
USE_RDS_FOR_TESTS=true?
  ├── Yes → DB_TEST_HOST, DB_TEST_USER(readonly_user), DB_TEST_PASSWORD
  └── No  → config.py DatabaseConfig (localhost:5432, postgres/postgres)
```

### RRF 스코어링 체계

RDS 환경에서는 Dense + Lexical Hybrid 검색 후 **RRF (Reciprocal Rank Fusion)**으로 점수 병합:

- 스코어 공식: `score = 1 / (k + rank)`, k=60
- 상위 1위: ~0.0164, 상위 5위: ~0.0154, 상위 20위: ~0.0125
- **threshold 범위**: 0.008 (general) ~ 0.012 (law)

이로 인해 cosine similarity 기반 threshold (0.5 등)는 사용 불가하며, RRF 호환 threshold가 필요합니다.

### Embedding Provider 추상화

리팩토링으로 `common/embedding/` 모듈이 도입:

```
common/embedding/
├── provider.py          # 추상 인터페이스
├── openai_provider.py   # text-embedding-3-large (1024차원)
├── local_provider.py    # KURE-v1 로컬
└── factory.py           # Provider 팩토리
```

Provider 선택은 `USE_OPENAI_EMBEDDING` 환경변수로 결정됩니다.

---

## 5. 권고사항

### 5.1 top_k 설정화 (우선순위: 중)

`AgentSettings`에 도메인별 top_k 추가:

```python
# config.py — AgentSettings (제안)
retrieval_top_k: int = Field(default=5, description="기본 검색 결과 수")
retrieval_top_k_law: int = Field(default=3, description="법령 검색 (소수 정확)")
retrieval_top_k_criteria: int = Field(default=3, description="기준 검색 (품목당 1-2건)")
retrieval_top_k_case: int = Field(default=5, description="사례 검색 (다수 관점)")
```

### 5.2 Agent Registry 정리 (우선순위: 높)

- `retrieval_counsel` 등록 제거
- `graph_mas.py:9` docstring "4개" → "3개" 수정
- `protocols.py:66` `EvidenceSource`에서 `'counsel'` 유지 여부 결정 (하위 호환성 고려)

### 5.3 프로토콜 정합성 강화 (우선순위: 중)

- `RetrievalTaskInput`를 실제 nested 구조에 맞게 업데이트하거나, 구현을 flat dict로 변경
- `GenerationInput`, `ReviewInput` TypedDict를 실제 state 읽기 패턴과 일치시키는 어댑터 레이어 도입 검토
- `QueryAnalysisOutput`에 v1 호환 필드 명시 (deprecated 마킹)

### 5.4 에이전트 자율성 확대 (우선순위: 낮)

현재 설계는 **안정성 우선 (deterministic routing)**으로 적절합니다.
장기적으로 Agent가 자체 파라미터를 선언하는 패턴 도입 검토:

```python
# 제안: Agent가 자체 config를 선언
class LawRetrievalAgent(BaseRetrievalAgent):
    preferred_top_k = 3
    preferred_ignore_threshold = True
    metadata_filter = {'dataset_type': 'law_guide', 'document_types': ['법률', '시행령']}
```

이를 통해 Supervisor는 Agent의 선언을 참조하되, 필요 시 오버라이드하는 방식으로 전환 가능합니다.

---

## 참조 파일

| 파일 | 역할 |
|------|------|
| `backend/app/supervisor/graph_mas.py` | MAS 그래프 구조, top_k/metadata_filter 하드코딩 |
| `backend/app/supervisor/nodes/supervisor.py` | Supervisor 라우팅 로직 (3-tier) |
| `backend/app/agents/protocols.py` | TypedDict 프로토콜 정의 |
| `backend/app/agents/retrieval/base_retrieval_agent.py` | 공통 Retrieval 로직, _get_db_config |
| `backend/app/agents/registry/agent_registry.py` | Agent Registry (counsel 불일치) |
| `backend/app/common/config.py` | AgentSettings (threshold 도메인별 분리) |
| `docs/guides/supervisor/agent-protocols.md` | 프로토콜 문서 (참조 기준) |
