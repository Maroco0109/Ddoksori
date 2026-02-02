# MAS 아키텍처 v2 설계 문서

**작성일**: 2026-01-28
**상태**: 완료 (Phase 8) - 테스트 통과

## 개요

기존 MAS(Multi-Agent System) 아키텍처를 개편하여 효율성과 정확성을 향상시킵니다.

### 주요 변경사항 요약

| 구성요소 | 현재 (v1) | 개편 후 (v2) |
|---------|----------|-------------|
| QueryAnalyst | 규칙 기반 쿼리 확장 | LLM 기반 다중 쿼리 확장 (gpt-4o-mini) |
| Supervisor | gpt-4o / 규칙 기반 | gpt-4o-mini, 하이브리드 에이전트 선택 |
| Retrieval | 4개 Agent (law, criteria, case, counsel) | 3개 Agent (law, criteria, case) + 메타데이터 필터 |
| AnswerDrafter | gpt-4o | gpt-4o + 사례 인용 기능 강화 |
| LegalReviewer | gpt-4o | gpt-4o + 재생성 루프 (max 1회) |

---

## 아키텍처 흐름

```
User Query
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 1. QueryAnalyst (gpt-4o-mini)                               │
│    - 의도 분석: general | information_search                │
│    - 쿼리 확장: 다중 쿼리 리스트 생성 (최대 5개)              │
│    - retriever_types 추출                                   │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. Supervisor (gpt-4o-mini)                                 │
│    - retriever_types 기반 검색 에이전트 선택/조정            │
│    - 각 에이전트별 키워드 추출                               │
│    - 검색 → 생성 → 검토 흐름 조율                           │
│    - 검토 실패 시 재생성 요청 (최대 1회)                     │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 3. Retrieval Agents (병렬 실행)                             │
│    ├─ LawRetrieval: 법령 검색 (임계치 무시)                  │
│    │   metadata_filter: {dataset_type: law_guide,           │
│    │                     document_types: [법률, 시행령]}     │
│    ├─ CriteriaRetrieval: 조정기준 검색 (임계치 무시)         │
│    │   metadata_filter: {dataset_type: law_guide,           │
│    │                     document_types: [행정규칙, 별표]}   │
│    └─ CaseRetrieval: 사례 검색                              │
│        metadata_filter: {categories: [조정, 해결, 상담]}     │
│        - 조정/해결: 2-3개 (우선)                             │
│        - 상담: 1-2개 (선택)                                  │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 4. AnswerDrafter (gpt-4o)                                   │
│    - 검색 결과 기반 답변 생성                                │
│    - claim-evidence 매핑                                    │
│    - 사례 인용 정보 포함 (CitedCase)                         │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ 5. LegalReviewer (gpt-4o)                                   │
│    - 할루시네이션 검증                                       │
│    - 법적 판단 여부 확인                                     │
│    - 금지표현 검토                                          │
│    - 질의-답변 정합성 확인                                   │
└─────────────────────────────────────────────────────────────┘
    ↓
Final Answer or Retry (max 1)
```

---

## 구현 현황

### 완료됨

1. **protocols_v2.py** - 새 인터페이스 정의
   - `QueryAnalysisOutputV2`: 의도, 확장 쿼리, retriever_types 포함
   - `RetrievalTaskInputV2`: 메타데이터 필터 지원
   - `GenerationOutputV2`: CitedCase 추가
   - `ReviewOutputV2`: Violation 상세 정보

2. **llm_expander.py** - LLM 기반 쿼리 확장
   - gpt-4o-mini 사용
   - 3초 타임아웃
   - 규칙 기반 폴백 지원

3. **expanders.py v2 함수** - 쿼리 확장 통합
   - `expand_query_with_llm_v2()`: LLM + 폴백
   - `generate_search_queries_v2()`: 다중 쿼리 정리

4. **query_analysis_node_v2** - v2 질의분석 노드
   - LLM 기반 쿼리 확장 적용
   - 의도 분류 ('general' | 'information_search')

5. **graph_mas.py v2 함수** - v2 그래프
   - `create_mas_supervisor_graph_v2()`: 3개 Retrieval Agent
   - `_route_mas_supervisor_v2()`: 재생성 루프 지원
   - `_create_retrieval_agent_node_v2()`: 메타데이터 필터 적용

6. **Retrieval Agents 개별 수정** (2026-01-28)
   - `base_retrieval_agent.py`: `_execute_search` 시그니처에 metadata_filter, ignore_threshold 추가
   - `law_agent.py`: metadata_filter 파라미터 처리 (dataset_type, document_types)
   - `criteria_agent.py`: metadata_filter 파라미터 처리 (dataset_type)
   - `case_agent.py`: 카테고리별 검색 + 우선순위 로직 (조정/해결 2-3개, 상담 1-2개)

7. **AnswerDrafter 개편** (2026-01-28)
   - `generation_node_v2`: retry_context 처리, CitedCase 생성
   - `_extract_cited_cases()`: 검색 결과에서 인용 사례 추출
   - `_build_retry_prompt_supplement()`: 재생성 시 위반사항 프롬프트 보충

8. **LegalReviewer 개편** (2026-01-28)
   - `review_node_v2`: Violation 상세 정보 (type, description, location, severity, suggestion)
   - `_build_violation_details()`: 위반 상세 생성
   - `_build_retry_context()`: AnswerDrafter에 전달할 retry_context 구성
   - `next_agent='retry_generation'` 반환으로 재생성 루프 지원

### 미완료 (추후 작업)

1. **ChatState v2 업데이트**
   - supervisor/state/ 모듈 수정 (retry_context, cited_cases 필드 추가)

2. **config.py 모델 설정**
   - MODEL_QUERY_ANALYST: gpt-4o-mini
   - MODEL_SUPERVISOR: gpt-4o-mini

3. **통합 테스트**
   - v2 그래프 E2E 테스트
   - 재생성 루프 검증

---

## 에이전트 간 인터페이스

### 1. QueryAnalyst Output

```python
class QueryAnalysisOutputV2(TypedDict):
    intent: Literal['general', 'information_search']
    original_query: str
    expanded_queries: List[str]          # 다중 확장 쿼리 (최대 5개)
    keywords: List[str]
    retriever_types: List[Literal['law', 'criteria', 'case']]
    needs_clarification: bool
    missing_fields: List[str]
```

### 2. Supervisor → Retrieval Input

```python
class RetrievalTaskInputV2(TypedDict):
    expanded_queries: List[str]
    agent_keywords: List[str]
    metadata_filter: MetadataFilter
    top_k: int
    ignore_threshold: bool

class MetadataFilter(TypedDict, total=False):
    dataset_type: Optional[str]          # 'law_guide'
    document_types: Optional[List[str]]  # ['법률', '시행령'] or ['행정규칙', '별표']
    categories: Optional[List[str]]      # ['조정', '해결', '상담']
```

### 3. Retrieval → Supervisor Output

```python
class RetrievalResultV2(TypedDict):
    source: Literal['law', 'criteria', 'case']
    documents: List[RetrievedDocumentV2]
    max_similarity: float
    avg_similarity: float
    search_time_ms: float
    error: Optional[str]
```

### 4. Generation Output

```python
class GenerationOutputV2(TypedDict):
    draft_answer: str
    claim_evidence_map: List[ClaimEvidenceV2]
    cited_cases: List[CitedCase]         # NEW
    has_sufficient_evidence: bool
    generation_time_ms: float

class CitedCase(TypedDict):
    case_id: str
    category: Literal['조정', '해결', '상담']
    title: str
    summary: str
    relevance: str
```

### 5. Review Output

```python
class ReviewOutputV2(TypedDict):
    passed: bool
    violations: List[Violation]          # 상세 위반 정보
    final_answer: Optional[str]
    review_time_ms: float

class Violation(TypedDict):
    type: Literal['hallucination', 'legal_judgment', 'prohibited_expression', 'query_mismatch']
    description: str
    location: str
    severity: Literal['critical', 'warning']
    suggestion: Optional[str]
```

---

## 테스트 결과

### 2026-01-28 아키텍처 점검 (ralph-loop)

1. **모듈 import 테스트**: 통과
2. **v2 그래프 생성 테스트**: 통과 (13개 노드)
3. **쿼리 확장 테스트**: 통과 (폴백 동작 확인)

**알려진 이슈**:
- LLM 호출 시 config 오류 발생 (환경변수 미설정 시)
- 폴백으로 자동 전환되어 기본 기능 정상 동작

### 2026-01-28 v2 노드 구현 완료

1. **Retrieval Agents**: metadata_filter 지원 추가 - 통과
2. **generation_node_v2**: CitedCase + retry_context 지원 - 통과
3. **review_node_v2**: Violation 상세 + retry 루프 - 통과
4. **전체 Import 테스트**: 통과 (13개 노드 그래프)

**구현된 v2 노드들**:
- `query_analysis_node_v2`: LLM 기반 쿼리 확장
- `generation_node_v2`: 사례 인용 + 재생성 컨텍스트
- `review_node_v2`: 위반 탐지 강화 + 재생성 루프

### 2026-01-28 Ralph-loop 테스트 완료 (RDS 연동)

**테스트 실행**: `backend/scripts/testing/test_mas_v2_architecture.py`
**결과**: 15 passed, 2 warnings (49.80s)

| 테스트 카테고리 | 테스트 수 | 상태 |
|---------------|---------|------|
| Module Imports | 4 | ✅ PASSED |
| Graph Creation | 1 | ✅ PASSED |
| Query Analysis v2 | 2 | ✅ PASSED |
| Retrieval Agents v2 | 3 | ✅ PASSED |
| Generation v2 | 2 | ✅ PASSED |
| Review v2 | 2 | ✅ PASSED |
| E2E Pipeline | 1 | ✅ PASSED |

**수정된 이슈**:
- `query_analysis_node_v2` 시그니처에 `config` 파라미터 추가 (LangGraph 호환성)
- `.env` 파일 RDS 사용자명 오타 수정 (`postgres\`` → `postgres`)
- `Any` 타입 import 추가

---

## 수정 대상 파일 목록

### 신규 생성
- [x] `backend/app/agents/protocols_v2.py`
- [x] `backend/app/agents/query_analysis/llm_expander.py`
- [x] `backend/scripts/testing/test_mas_v2_architecture.py` - v2 통합 테스트

### 수정됨
- [x] `backend/app/agents/query_analysis/expanders.py` - v2 함수 추가
- [x] `backend/app/agents/query_analysis/agent.py` - v2 노드 추가
- [x] `backend/app/supervisor/graph_mas.py` - v2 그래프 추가
- [x] `backend/app/agents/retrieval/base_retrieval_agent.py` - v2 시그니처 추가
- [x] `backend/app/agents/retrieval/law_agent.py` - metadata_filter 지원
- [x] `backend/app/agents/retrieval/criteria_agent.py` - metadata_filter 지원
- [x] `backend/app/agents/retrieval/case_agent.py` - 카테고리 필터 + 우선순위
- [x] `backend/app/agents/answer_generation/agent.py` - generation_node_v2 추가
- [x] `backend/app/agents/legal_review/agent.py` - review_node_v2 추가

### 수정 필요 (미완료)
- [ ] `backend/app/supervisor/state/` - v2 필드 추가 (retry_context, cited_cases)
- [ ] `backend/app/common/config.py` - 모델 설정 추가

---

## 마이그레이션 전략

1. **Phase 1**: v2 함수를 별도로 추가 (v1 유지)
2. **Phase 2**: 피처 플래그로 v2 활성화 테스트
3. **Phase 3**: 성능/품질 검증 후 v2를 기본값으로 전환
4. **Phase 4**: v1 코드 아카이브

---

## 참고 자료

- 계획 파일: `/home/maroco/.claude/plans/immutable-growing-ember.md`
- 기존 MAS 문서: `backend/app/supervisor/README.md`
- v1 MAS 설계 (아카이브): `docs/_archive/plans/MAS_SUPERVISOR_PLAN.md`
