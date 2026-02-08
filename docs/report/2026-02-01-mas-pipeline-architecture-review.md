# MAS 파이프라인 아키텍처 리뷰

**작성일**: 2026-02-01
**범위**: 리팩토링 이후 전체 MAS 파이프라인 구조 검토
**목적**: 프로토콜 준수, E2E 데이터 흐름, 구조적 문제점 비판적 검토

---

## 1. 시스템 개요

MAS (Multi-Agent System) Supervisor 그래프 구조도:

```
Entry → cache_check
  ├─[HIT] → cache_response → END
  └─[MISS] → input_guardrail
       ├─[blocked] → END
       └─[pass] → supervisor (중앙 조율자)
            ↓ (순환 라우팅)
            ├─ query_analysis → supervisor
            ├─ retrieval_team (Fan-out)
            │  ├─ retrieval_law     ─┐
            │  ├─ retrieval_criteria ─┼─→ retrieval_merge → supervisor
            │  └─ retrieval_case    ─┘
            ├─ generation → supervisor
            ├─ review → supervisor (retry 시 → generation → supervisor)
            └─ output_guardrail → memory_save → END
```

Happy path 실행 순서:
1. cache_check (MISS)
2. input_guardrail (pass)
3. supervisor → query_analysis
4. supervisor → retrieval_team (parallel fan-out) → retrieval_merge
5. supervisor → generation
6. supervisor → review (pass)
7. supervisor → output_guardrail → memory_save → END

### 주요 파일 위치

| 파일 | 역할 |
|------|------|
| `api/chat.py` | HTTP 엔드포인트 (`/chat`, `/chat/stream`) |
| `supervisor/graph_mas.py` | MAS 그래프 정의, 노드 등록, 라우팅 |
| `supervisor/state/__init__.py` | ChatState 통합 스키마 (~40 필드) |
| `supervisor/nodes/supervisor.py` | Supervisor 중앙 조율 로직 |
| `supervisor/nodes/retrieval_merge.py` | 병렬 검색 결과 병합 |
| `supervisor/nodes/memory_save.py` | 대화 메모리 저장 |
| `agents/query_analysis/agent.py` | 의도 분류, 쿼리 확장 |
| `agents/retrieval/{law,criteria,case,counsel}_agent.py` | 도메인별 검색 에이전트 |
| `agents/answer_generation/agent.py` | LLM 답변 생성 |
| `agents/legal_review/agent.py` | 법률 검토 |
| `agents/protocols.py` | 에이전트 간 인터페이스 정의 (TypedDict) |
| `guardrail/nodes.py` | 입출력 안전 가드레일 |

---

## 2. 프로토콜 준수 감사 (protocols.py vs 실제 구현)

### 2.1 QueryAnalysis Agent

**프로토콜** (`QueryAnalysisOutput`): `intent`, `original_query`, `expanded_queries`, `keywords`, `retriever_types`

**실제 반환** (`query_analysis_node_v2`):
```python
{
    "query_analysis": {
        "intent": str,           # ✓
        "original_query": str,   # ✓
        "expanded_queries": [],  # ✓
        "keywords": [],          # ✓
        "retriever_types": [],   # ✓
        # v1 호환 extra fields:
        "query_type": str,
        "extracted_info": dict,
        "rewritten_query": str,
        "search_queries": [],
        "query_complexity": str,
    },
    "mode": str,  # RoutingMode
}
```

**판정: COMPLIANT** — required 5 keys 모두 존재. extra fields는 하위호환.

### 2.2 Retrieval Agents

**프로토콜** (`RetrievalResult`): `source`, `documents`, `max_similarity`, `avg_similarity`, `search_time_ms`, `error`

**실제 흐름**:
1. `base_retrieval_agent.py`가 `report_to_supervisor(result={"results": [...], "sources": [...], ...})` 반환
2. `graph_mas.py:206-212`에서 adapter 변환:
   ```python
   individual_result = {
       'source': agent_type,                                    # 추가
       'documents': result.get('result', {}).get('results', []), # results → documents 변환
       'max_similarity': ...,
       'avg_similarity': ...,
       'search_time_ms': ...,
   }
   ```
3. `retrieval_merge.py`가 4섹션 구조(`laws`, `disputes`, `counsels`, `criteria`)로 재구성

**판정: COMPLIANT (adapter 패턴)** — `graph_mas.py`가 adapter 역할 수행. 단, protocols.py의 `RetrievalResult` TypedDict는 단일 에이전트 결과 구조(= `IndividualRetrievalResult`)이고, 실제 시스템의 merged `RetrievalResult`는 `state/__init__.py`에 별도 정의된 4섹션 구조. **protocols.py의 정의가 outdated**.

### 2.3 Answer Generation Agent

**프로토콜** (`GenerationOutput`): `draft_answer`, `claim_evidence_map`, `cited_cases`, `has_sufficient_evidence`, `generation_time_ms`, `response_depth`, `available_details`, `followup_questions`, `detail_type`

**실제 반환** (`generation_node_v2`):
```python
{
    'draft_answer': str,              # ✓
    'claim_evidence_map': [],         # ✓
    'cited_cases': [],                # ✓
    'has_sufficient_evidence': bool,  # ✓
    'generation_time_ms': float,      # ✓
    'response_depth': str,            # ✓
    'available_details': dict|None,   # ✓
    'followup_questions': [],         # ✓
    # extra (ChatState가 수용):
    'retrieval_confidence': float,
    'messages': [AIMessage],
    'generation_model_used': str,
    'is_followup': bool,
    '_cache_hit': bool,
}
```

**판정: COMPLIANT** — required 9 keys 중 `detail_type`만 미설정 (Optional이므로 문제 없음). Extra fields는 ChatState reducer가 수용.

### 2.4 Legal Review Agent

**프로토콜** (`ReviewOutput`): `passed`, `violations`, `final_answer`, `review_time_ms`

**실제 반환** (`review_node_v2`):
```python
{
    'review': {                    # ← 중첩 구조!
        'passed': bool,            # ✓ (nested)
        'violations': [],          # ✓ (nested)
        'final_answer': str,       # ✓ (nested)
        'review_time_ms': float,   # ✓ (nested)
        'strict_mode': bool,       # extra
    },
    'final_answer': str,           # 별도 top-level key
}
```

**판정: STRUCTURAL MISMATCH** — 프로토콜은 flat dict를 기대하나, 실제는 `review` key로 wrap하여 반환. ChatState의 `review` 필드가 이 nested dict를 수용하므로 런타임 에러는 없으나, 프로토콜 정의와 불일치.

### 2.5 protocols.py 자체의 구조적 괴리

| # | 문제 | 상세 |
|---|------|------|
| 1 | `RetrievalResult` 정의 outdated | protocols.py는 단일 에이전트 결과(`source`, `documents`), 실제 merged result는 4섹션(`laws`, `disputes`, `counsels`, `criteria`). `IndividualRetrievalResult`에 해당하는 것을 `RetrievalResult`로 명명 |
| 2 | `RetrieverType`에 `counsel` 누락 | `Literal['law', 'criteria', 'case']` — 실제 4개 에이전트(law, criteria, case, counsel) 운영 |
| 3 | `OnboardingInfo` 키 불일치 | 프로토콜: `purchase_item`, `purchase_amount` / 프론트엔드 실제: `product`, `issue`, `request` |
| 4 | `GenerationOutput.detail_type` Dead field | 선언만 있고 설정하는 코드 없음 |
| 5 | 런타임 참조 부재 | protocols.py를 import하는 에이전트 코드가 거의 없음. 문서 역할만 수행 |

---

## 3. 검색 에이전트별 검색 방식

### 3.1 공통 기반

모든 에이전트는 PostgreSQL의 `search_hybrid_rrf()` SQL 함수를 기반으로 **BM25 + pgvector(text-embedding-3-large, 1536d) RRF Fusion** 수행.

```sql
-- SQL search_hybrid_rrf() 내부 (의사코드)
WITH bm25_results AS (
  SELECT chunk_id, ts_rank_cd(text_tsv, plainto_tsquery('simple', query)) as score
  FROM vector_chunks WHERE text_tsv @@ query AND (filters)
  ORDER BY score DESC LIMIT 100
),
vector_results AS (
  SELECT chunk_id, 1 - (embedding <=> query_embedding::vector) as similarity
  FROM vector_chunks WHERE embedding IS NOT NULL AND (filters)
  ORDER BY similarity DESC LIMIT 100
),
rrf_combined AS (
  SELECT chunk_id,
         COALESCE(1.0/(rrf_k + bm25.rank), 0) + COALESCE(1.0/(rrf_k + vec.rank), 0) as rrf_score
  FROM bm25_results FULL OUTER JOIN vector_results ON chunk_id
)
SELECT * FROM rrf_combined ORDER BY rrf_score DESC LIMIT top_k
```

### 3.2 에이전트별 상세

| Agent | Retriever 클래스 | 검색 방식 | RRF k | 필터 | 특이사항 |
|-------|-----------------|-----------|-------|------|----------|
| **LawRetrieval** | `LawRetriever` → `RDSInternalRetriever.search_hybrid_rrf_2()` | expanded_queries 별 SQL RRF → **Python 2차 RRF fusion** | 60 | `dataset_type='law_guide'`, `document_types=['법률', '시행령']` | 삭제 조문 regex 필터, 조문당 max 2 chunks, `per_query_k = max(top_k, 12)` |
| **CriteriaRetrieval** | `CriteriaRetriever` → `RDSInternalRetriever.search_hybrid_rrf_2()` | Law와 동일한 2차 RRF | 60 | `dataset_type='law_guide'`, `document_types=['시행규칙', '별표']` | **계층 구조 증강**: parent/child/grandchild chunk을 DB에서 fetch하여 `[부모]...[조건]...[하위]...` 형태 조합. 동적 문자수 분배 (총 max 1000자) |
| **CaseRetrieval** | `UnifiedRetriever` → SQL `search_hybrid_rrf()` | 단일 쿼리 SQL 레벨 RRF | 10 | `dataset_filter='case'`, 전체 카테고리 | — |
| **CounselRetrieval** | `UnifiedRetriever` → SQL `search_hybrid_rrf()` | 단일 쿼리 SQL 레벨 RRF | 10 | `dataset_filter='case'`, `category_filter='상담'` | 상담사례만 필터 |

### 3.3 검색 흐름도

```
expanded_queries (query_analysis에서 생성, 최대 5개)
  ↓
Law/Criteria Agent:
  각 query별 → search_hybrid_rrf_2(query, embedding, filters, per_query_k=12)
  → 12건/query 반환 → Python 2차 RRF fusion (k=60):
      score[chunk_id] += 1.0 / (60 + rank)
  → 중복 chunk_id 합산 → top_k 반환
  → (Law) 삭제 조문 필터, 조문당 max 2 제한
  → (Criteria) 계층 구조 증강

Case/Counsel Agent:
  단일 query → UnifiedRetriever.search():
    → OpenAI embedding(text-embedding-3-large, 1536d) 생성
    → search_hybrid_rrf(query, embedding, filters, top_k, rrf_k=10)
  → top_k 반환
```

### 3.4 Sufficiency Check

`RetrievalSufficiencyChecker.evaluate()`:
- 현재 RRF 모드: `total_doc_count > 0` → sufficient, `== 0` → insufficient
- 임계값 기반 거부 없음 (`SIMILARITY_THRESHOLD_*` 환경변수는 RRF 모드에서 미사용)
- 결과: 1건이라도 검색되면 무조건 답변 생성 진행

---

## 4. E2E Happy Path 분석

### 4.1 시나리오 1: 법령 질문 — "소비자보호법이 뭐야?"

```
User → /chat/stream (chat_type=dispute)
  → cache_check: MISS
  → input_guardrail: pass
  → supervisor → query_analysis:
      query_type='law', mode='NEED_RAG', retriever_types=['law']
  → supervisor → retrieval_team:
      Fan-out: retrieval_law only (retriever_types에 따라 선택적)
  → retrieval_merge: laws=[소비자기본법 제4조, ...], disputes=[], criteria=[]
  → supervisor → generation:
      Phase 3: FormatSelector → 'law_response' format
      Phase 4: LLM generation
      Phase 5: followup_questions 생성, cited_cases 추출
  → supervisor → review: pass (citations 존재)
  → output_guardrail: final_answer 설정
  → memory_save: _last_turn_context 저장
  → SSE complete event:
      answer: "소비자기본법 제4조 (소비자의 기본적 권리)..."
      sources: [{type:'law', law_name:'소비자기본법', article:'제4조'}]
      followup_questions: [3개]
```

### 4.2 시나리오 2: 온보딩 + 분쟁 — "내 상황에 적용되는 기준은?" (TV 온보딩)

```
User → /chat/stream (chat_type=dispute, onboarding={product:TV, issue:화면불량, request:교환})
  → cache_check: MISS
  → input_guardrail: pass
  → supervisor → query_analysis:
      query_type='criteria', mode='NEED_RAG', retriever_types=['law','criteria','case']
  → supervisor → retrieval_team:
      Fan-out: retrieval_law + retrieval_criteria + retrieval_case (3 parallel)
  → retrieval_merge: laws=[...], criteria=[...], disputes=[...], product_relevance 적용
  → supervisor → generation:
      Phase 3: FormatSelector → 'criteria_response' format (onboarding 참조)
      Phase 4: LLM generation (onboarding 컨텍스트 포함)
      Phase 5: followup_questions, cited_cases
  → supervisor → review: pass
  → output_guardrail → memory_save → END
```

### 4.3 시나리오 3: 일반 인사 — "안녕"

```
User → /chat/stream (chat_type=dispute)
  → cache_check: MISS
  → input_guardrail: pass
  → supervisor → query_analysis:
      query_type='general', mode='NO_RETRIEVAL', intent='general'
  → supervisor → generation:
      Phase 0: general query in flexible mode
      → FormatSelector → 'general_greeting' format
      → LLM generation (greeting + 분쟁 상담 안내)
      → 조기 반환 (retrieval/review 스킵)
  → supervisor → output_guardrail → memory_save → END
  ⚠ followup_questions: [] (Phase 0 조기 반환으로 생성 안됨)
  ⚠ review 노드: 스킵됨 (Fast Path)
```

---

## 5. 구조적 문제점 (심각도별)

### CRITICAL: `/chat` vs `/chat/stream` 응답 구성 불일치

두 엔드포인트가 동일 그래프를 실행하나 **응답 변환 로직이 완전히 다름**.

| 항목 | `/chat` (`chat.py:224-305`) | `/chat/stream` (`chat.py:557-613`) |
|------|----------------------------|------------------------------------|
| sources | `state.get('sources', [])` — state 직접 사용 | `retrieval` dict에서 **재구성** (laws[:3], disputes[:3] 등) |
| similar_cases | `CaseReference(**d)` — Pydantic 검증 | `{'doc_title': d.get('doc_title'), ...}` — raw dict |
| related_laws | `LawReference(**law)` — Pydantic 검증 | `{'law_name': l.get('law_name'), ...}` — raw dict |
| domain | `AgencyRecommendation(**agency_info)` | raw dict |

**리스크:**
- `/chat`은 Pydantic validation → retrieval 데이터 필드 불일치 시 500 에러 가능
- `/chat/stream`은 raw dict → API 스키마 없는 필드도 전송, 일부 필드 누락
- 같은 쿼리인데 두 엔드포인트의 응답 구조가 다를 수 있음

**권장: 공통 응답 빌더 함수 추출**

### HIGH: protocols.py와 실제 구조 괴리

protocols.py가 "문서" 역할만 하고 런타임에 참조되지 않음. 실제 구조와 크게 다른 정의가 유지되고 있어 신규 개발자에게 오해를 유발.

**권장: protocols.py를 실제 구조에 맞게 업데이트하거나, ChatState 기반으로 통합**

### MEDIUM: sources 이중 경로

- `retrieval_merge`가 `state['sources']`에 `operator.add`로 누적
- `/chat/stream`은 이를 무시하고 `state['retrieval']`에서 재구성
- `/chat`은 `state['sources']`를 사용하나 포맷 검증 없음

**권장: retrieval_merge의 sources를 chat.py 양쪽에서 공통 사용하도록 통일**

### MEDIUM: agency/domain 미설정

- `retrieval_merge`가 `merged['agency'] = {}` 초기화만 하고 실제 설정 없음
- `ChatResponse.domain` 필드가 항상 `None`
- restricted domain (금융/의료) 시에만 `generation_node_v2`에서 agency 정보 반환하나, retrieval dict가 아닌 별도 경로

**권장: agency 설정 로직을 retrieval_merge 또는 별도 노드로 분리**

### MEDIUM: Case/Counsel expanded_queries 미활용

- Law/Criteria는 expanded_queries(최대 5개)로 다중 검색 후 2차 RRF
- Case/Counsel은 단일 쿼리만 사용하여 검색 품질 차이 발생 가능

**권장: UnifiedRetriever에도 expanded_queries 기반 다중 검색 옵션 추가**

### MEDIUM: rrf_k 값 불일치 (60 vs 10)

- Law/Criteria의 Python 2차 RRF: `rrf_k = 60` (hardcoded)
- Case/Counsel의 SQL RRF: `rrf_k = 10` (config)
- 값이 클수록 순위 차이가 smooth → 60은 보수적, 10은 공격적

**권장: rrf_k를 config 기반으로 통일하거나 의도를 문서화**

### LOW: Sufficiency Check 무력화

- RRF 모드에서 `total_doc_count > 0` 이면 무조건 sufficient
- `SIMILARITY_THRESHOLD_*` 환경변수가 사실상 미사용
- 저품질 결과(similarity 0.2)도 답변 생성에 그대로 전달

**권장: RRF score 기반 최소 임계값 도입 검토**

### LOW: Dead Code / LEGACY 잔존

| 항목 | 위치 | 상태 |
|------|------|------|
| `clarifying_questions` | ChatResponse, ChatState, protocols.py | 항상 `[]`. LEGACY 주석 |
| `detail_type` | protocols.py GenerationOutput | 미설정 Dead field |
| `_build_general_response()` | answer_generation/agent.py | flexible 모드에서 미사용 |

---

## 6. 권장 개선 우선순위

| 순위 | 개선안 | 영향 범위 | 난이도 |
|------|--------|-----------|--------|
| 1 | `/chat`과 `/chat/stream`의 응답 빌더 공통화 | `api/chat.py` | 중 |
| 2 | protocols.py를 실제 구조에 맞게 갱신 | `agents/protocols.py` | 저 |
| 3 | sources 구성 로직 통일 (retrieval_merge에서 최종 형태로) | `retrieval_merge.py`, `chat.py` | 중 |
| 4 | Case/Counsel에 expanded_queries 다중 검색 도입 | `case_agent.py`, `counsel_agent.py`, `UnifiedRetriever` | 중 |
| 5 | agency 설정 로직 정비 | `retrieval_merge.py` 또는 새 노드 | 저 |
| 6 | RRF score 기반 sufficiency 임계값 도입 | `sufficiency.py` | 저 |
| 7 | Dead code 정리 (clarifying_questions, detail_type 등) | 여러 파일 | 저 |

---

*끝*
