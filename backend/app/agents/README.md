# DDOKSORI 에이전트 인터페이스 가이드

> **목적**: 각 작업자가 담당 에이전트를 독립적으로 개발할 수 있도록 입출력 인터페이스를 정의합니다.

## 전체 아키텍처

```
사용자 입력
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  QueryAnalyst (질의분석)                                    │
│  담당: Query Analysis 작업자                                 │
│  문서: query_analysis/INTERFACE.md                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
    ┌────────────┬───────┴───────┬────────────┐
    ▼            ▼               ▼            ▼
┌────────┐  ┌────────┐  ┌────────────┐  ┌────────────┐
│  Law   │  │Criteria│  │   Case     │  │  Counsel   │
│ Agent  │  │ Agent  │  │   Agent    │  │   Agent    │
└────────┘  └────────┘  └────────────┘  └────────────┘
    │            │               │            │
    └──────┬─────┴───────┬───────┴────────────┘
           │             │
           ▼             ▼
┌──────────────────┐  ┌──────────────────────┐
│ Legal & Criteria │  │ Counsel & Dispute    │
│ 작업자           │  │ 작업자               │
│ INTERFACE_LAW_   │  │ INTERFACE_COUNSEL_   │
│ CRITERIA.md      │  │ CASE.md              │
└────────┬─────────┘  └──────────┬───────────┘
         │                       │
         └───────────┬───────────┘
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  AnswerDrafter (답변생성)                                   │
│  담당: Answer Generator 작업자                               │
│  문서: answer_generation/INTERFACE.md                        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  LegalReviewer (법률검토)                                   │
│  담당: Legal Review 작업자                                   │
│  문서: legal_review/INTERFACE.md                             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
                    최종 답변
```

## 작업자별 담당 문서

| 작업자 | 담당 에이전트 | 인터페이스 문서 |
|--------|--------------|-----------------|
| Query Analysis | QueryAnalyst | `query_analysis/INTERFACE.md` |
| Answer Generator | AnswerDrafter | `answer_generation/INTERFACE.md` |
| Legal & Criteria | LawRetrievalAgent, CriteriaRetrievalAgent | `retrieval/INTERFACE_LAW_CRITERIA.md` |
| Counsel & Dispute | CounselRetrievalAgent, CaseRetrievalAgent | `retrieval/INTERFACE_COUNSEL_CASE.md` |
| Legal Review | LegalReviewer | `legal_review/INTERFACE.md` |

## 데이터 흐름 요약

```python
# 1. QueryAnalyst 출력 → 모든 Retrieval Agent 입력
QueryAnalysisResult → RetrievalInput.query_analysis

# 2. 4개 Retrieval Agent 출력 → 병합 → AnswerDrafter 입력
IndividualRetrievalResult[] → RetrievalResult → GenerationInput.retrieval

# 3. AnswerDrafter 출력 → LegalReviewer 입력
GenerationOutput.draft_answer → ReviewInput.draft_answer
GenerationOutput.claim_evidence_map → ReviewInput.claim_evidence_map

# 4. LegalReviewer 출력 → 최종 응답
ReviewOutput.final_answer → API Response
```

## 공통 타입 정의

모든 에이전트가 공유하는 타입은 `protocols.py`에 정의되어 있습니다:

```python
from app.agents.protocols import (
    # 공통
    OnboardingInfo,
    ChatType,        # Literal['dispute', 'general']
    QueryType,       # Literal['dispute', 'general', 'law', 'criteria', 'system_meta', 'ambiguous']
    RoutingMode,     # Literal['NO_RETRIEVAL', 'NEED_RAG', 'NEED_USER_CLARIFICATION', 'NEED_CLARIFICATION']

    # 질의분석
    QueryAnalysisInput,
    QueryAnalysisResult,
    QueryAnalysisOutput,

    # 정보검색
    RetrievalInput,
    RetrievalResult,
    RetrievalOutput,
    AgencyInfo,

    # 답변생성
    GenerationInput,
    GenerationOutput,
    ClaimEvidenceMapping,

    # 법률검토
    ReviewInput,
    ReviewOutput,
    ReviewResult,
)
```

## 테스트 실행 방법

```bash
# 전체 테스트
conda run -n dsr pytest backend/scripts/testing/

# 특정 에이전트 테스트
conda run -n dsr pytest backend/scripts/testing/agents/test_query_analysis.py
conda run -n dsr pytest backend/scripts/testing/agents/test_retrieval.py
conda run -n dsr pytest backend/scripts/testing/agents/test_generation.py
conda run -n dsr pytest backend/scripts/testing/agents/test_review.py

# 단위 테스트만 (DB 불필요)
conda run -n dsr pytest -m unit
```

## 주의사항

1. **타입 준수 필수**: `protocols.py`에 정의된 TypedDict 형식을 정확히 따라야 합니다.
2. **State 직접 수정 금지**: 에이전트는 결과를 반환하고, Supervisor가 State를 업데이트합니다.
3. **에러 처리**: 에러 발생 시 적절한 기본값을 반환하고 로깅해야 합니다.
4. **비동기 필수**: 모든 에이전트 메서드는 `async def`로 구현합니다.
