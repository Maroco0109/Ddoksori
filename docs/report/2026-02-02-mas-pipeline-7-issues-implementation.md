# MAS 파이프라인 7개 구조적 이슈 해결 보고서

**작성일**: 2026-02-02
**선행 문서**: `docs/report/2026-02-01-mas-pipeline-architecture-review.md`
**브랜치**: `refactor/40-integrate-branch`

---

## 1. 개요

2026-02-01 아키텍처 리뷰에서 발견된 7개 구조적 이슈를 4개 PR 단위로 구현 완료하였다.

| PR | 해결 이슈 | 우선순위 | 상태 |
|----|-----------|----------|------|
| **PR-A** | #1 응답 빌더 중복, #3 Sources 이중 경로, #4 Agency 미연결 | CRITICAL+MEDIUM | ✅ 완료 |
| **PR-B** | #5 expanded_queries 미사용, #6 rrf_k 하드코딩 | MEDIUM | ✅ 완료 |
| **PR-C** | #2 protocols.py 불일치 | HIGH | ✅ 완료 |
| **PR-D** | #7 Dead code + Sufficiency | LOW | ✅ 완료 |

---

## 2. PR-A: 공통 응답 빌더 + Sources 통일 + Agency 연결

### 2.1 문제점

- `/chat` 엔드포인트(Pydantic 모델)와 `/chat/stream` 엔드포인트(raw dict)가 각각 독립적으로 응답을 구성
- sources 경로 불일치: `/chat`은 `state['sources']`, `/chat/stream`은 `retrieval` dict에서 재구성
- `retrieval_merge`에서 `agency={}` 초기화만 하고 실제 데이터를 넣지 않음

### 2.2 해결 방안

공통 응답 빌더 함수를 신규 생성하여 양쪽 엔드포인트에서 동일하게 호출하도록 통일하고, agency 정보를 query_analysis의 restricted domain 데이터에서 채우도록 연결하였다.

### 2.3 수정 파일 및 변경 내용

| 파일 | 변경 내용 |
|------|-----------|
| `backend/app/api/response_builder.py` | **신규 생성** — `build_chat_response_data(session_id, final_state)` 공통 빌더 |
| `backend/app/api/chat.py` | 양쪽 엔드포인트가 공통 빌더 호출 (95줄 감소) |
| `backend/app/api/models.py` | `AgencyRecommendation`에 프론트엔드 호환 필드 추가 |
| `backend/app/supervisor/nodes/retrieval_merge.py` | `merged['agency']`에 restricted domain 정보 연결 |
| `frontend/src/shared/types/chat.types.ts` | SSE 타입들 백엔드 실제 구조에 맞게 정렬 |
| `frontend/src/features/chat/ChatPage.tsx` | 미사용 `awaiting_user_choice` 조건 제거 |

### 2.4 상세 설명

#### response_builder.py 구조

```python
def build_chat_response_data(session_id: str, final_state: dict) -> dict:
    """
    /chat과 /chat/stream 양쪽에서 사용하는 공통 응답 빌더.
    final_state(그래프 출력)에서 프론트엔드 호환 응답 dict를 생성.
    """
```

내부 헬퍼 함수:
- `_build_sources(disputes, counsels, laws, criteria)` — 4섹션에서 `SSESourceInfo` 호환 리스트 생성 (섹션당 최대 3건)
- `_build_domain(agency_info)` — restricted domain agency 정보를 프론트엔드 `AgencyRecommendation` 호환 dict로 변환
- `_build_similar_cases(disputes, counsels)` — `{disputes: [...], counsels: [...]}` 구조
- `_build_related_laws(laws)` — `{law_name, article, full_path, similarity}` 리스트
- `_build_related_criteria(criteria)` — `{title, category, similarity}` 리스트

#### Agency 데이터 흐름

```
query_analysis_node
  → restricted_domain: "finance"
  → restricted_agency_info: {name: "금융분쟁조정위원회", organization: "금융감독원", url, phone}
    ↓
retrieval_merge_node
  → merged['agency'] = {domain, name, organization, url, phone, is_restricted: True}
    ↓
response_builder._build_domain()
  → {agency: "finance", agency_info: {name, org, url, phone}, is_restricted: True, ...}
    ↓
프론트엔드 SSECompleteData.domain
  → MessageBubble에서 restricted 안내 표시
```

#### 프론트엔드 타입 정렬

| 인터페이스 | 변경 사항 |
|-----------|----------|
| `SSESourceInfo` | `content`, `case_uid`, `product_name`, `law_name`, `article` 필드 추가 |
| `AgencyRecommendation` | `agency`, `agency_info` 구조체로 변경, `dispute_type`/`reason`/`confidence` 추가 |
| `SimilarCases` | `cases[]` → `disputes[]` + `counsels[]` 분리 |
| `LawReference` | `full_path`, `similarity` 추가, 필드 optional 처리 |
| `CriteriaReference` | `title`, `category`, `similarity` 구조로 변경 |
| `SSECompleteData` | `awaiting_user_choice` 제거 |

---

## 3. PR-B: Expanded Queries + RRF Config

### 3.1 문제점

- Case/Counsel 에이전트가 expanded_queries를 무시하고 단일 쿼리만 사용
- Law/Criteria 에이전트의 Python-level RRF에서 `rrf_k=60` 하드코딩 (config의 `rrf_k=10`은 SQL 레벨용)

### 3.2 해결 방안

`UnifiedRetriever`에 `search_multi()` 메서드를 추가하고, `BaseRetrievalAgent`에서 expanded_queries 존재 시 자동 분기하도록 구현하였다. RRF k값은 config에서 관리하도록 추출하였다.

### 3.3 수정 파일 및 변경 내용

| 파일 | 변경 내용 |
|------|-----------|
| `backend/app/agents/retrieval/tools/unified_retriever.py` | `search_multi()` 메서드 추가 |
| `backend/app/agents/retrieval/base_retrieval_agent.py` | `task_input` 파라미터 + expanded_queries 분기 로직 |
| `backend/app/common/config.py` | `rrf_k_python=60` 설정 추가 (기존 `rrf_k=10`은 SQL용 유지) |
| `backend/app/agents/retrieval/law_agent.py` | `rrf_k=60` → `get_config().retrieval.rrf_k_python` |
| `backend/app/agents/retrieval/criteria_agent.py` | 동일 변경 |

### 3.4 상세 설명

#### RRF 이중 계층 구조 정리

```
[SQL 레벨 RRF] — config.retrieval.rrf_k (기본값: 10)
  ├─ search_hybrid_rrf() SQL 함수 내부
  └─ BM25 + pgvector(1536d) 점수 융합

[Python 레벨 RRF] — config.retrieval.rrf_k_python (기본값: 60)
  ├─ UnifiedRetriever.search_multi()
  ├─ LawRetrievalAgent._execute_search()
  └─ CriteriaRetrievalAgent._execute_search()
  └─ expanded_queries 여러 쿼리 결과를 하나로 융합
```

#### search_multi() 동작 방식

```python
def search_multi(self, queries: List[str], top_k=10, rrf_k=None, **filters):
    # 1. 쿼리가 1개면 일반 search()로 위임
    # 2. 각 쿼리별 search() 실행 (per_query_k = max(top_k, 12))
    # 3. RRF Fusion: score = Σ 1/(rrf_k + rank)
    # 4. 융합 점수로 정렬 후 상위 top_k 반환
```

#### BaseRetrievalAgent 변경

Case/Counsel 에이전트는 `BaseRetrievalAgent._execute_search()`를 상속받아 사용한다. 이제 `task_input`에 `expanded_queries`가 있으면 자동으로 `search_multi()`를 호출한다.

```python
expanded_queries = (task_input or {}).get('expanded_queries', [])
if expanded_queries and len(expanded_queries) > 1:
    results = retriever.search_multi(queries=expanded_queries, top_k=top_k, **filters)
else:
    results = retriever.search(query=query, top_k=top_k, **filters)
```

Law/Criteria 에이전트는 자체 `_execute_search()` override를 유지하되, 하드코딩 `rrf_k=60`을 config에서 읽도록 변경하였다.

---

## 4. PR-C: protocols.py 실제 구조 반영

### 4.1 문제점

- 23개 TypedDict, 0건 런타임 import — 문서 역할이지만 실제 구조와 불일치
- `RetrieverType`에 `'counsel'` 누락
- `RetrievalResult`가 개별 에이전트 결과 구조 — 병합 결과(`state['retrieval']`) 구조 없음
- `GenerationOutput.detail_type` dead field
- 4개 Protocol 클래스 미사용

### 4.2 해결 방안

파일 전체를 실제 코드 구조에 맞게 재작성하였다. 문서/참조 역할을 유지하되 실제 런타임 구조를 정확히 반영하도록 하였다.

### 4.3 주요 변경 사항

| 항목 | Before | After |
|------|--------|-------|
| `RetrieverType` | `'law', 'criteria', 'case'` | `'law', 'criteria', 'case', 'counsel'` |
| `RetrievalResult` | 개별 에이전트 출력 | `IndividualRetrievalResult`로 rename |
| (신규) | — | `MergedRetrievalResult` (4섹션 병합 구조) |
| `GenerationOutput.detail_type` | 존재 | 삭제 (dead field) |
| Protocol 클래스 4개 | 존재 | 삭제 (0 import) |
| `ProtocolChatState.retrieval_results` | `List[RetrievalResult]` | `individual_retrieval_results` + `retrieval: MergedRetrievalResult` |
| 각 TypedDict | 주석 없음 | "Used in: 파일경로" 주석 추가 |

### 4.4 MergedRetrievalResult 구조

```python
class MergedRetrievalResult(TypedDict, total=False):
    """retrieval_merge 노드 출력 — state['retrieval']에 저장됨.
    Used in: supervisor/nodes/retrieval_merge.py
    """
    agency: Dict[str, Any]          # restricted domain 기관 정보
    disputes: List[Dict[str, Any]]  # 분쟁조정사례
    counsels: List[Dict[str, Any]]  # 상담사례
    laws: List[Dict[str, Any]]      # 법령
    criteria: List[Dict[str, Any]]  # 분쟁해결기준
    max_similarity: float
    avg_similarity: float
```

---

## 5. PR-D: Dead Code 정리 + Sufficiency 개선

### 5.1 삭제된 Dead Code

| 함수 | 파일 | 사유 |
|------|------|------|
| `generation_node()` | `agents/answer_generation/agent.py` | `generation_node_v2()`로 대체됨, graph에서 미참조 |
| `generation_node_streaming()` | 동일 | 동일 |

약 191줄 삭제. `generation_node_v2()`와 그 헬퍼 함수들은 그대로 유지.

### 5.2 Sufficiency 임계값 개선

**문제**: `total_doc_count > 0` 이면 무조건 sufficient 판정 — RRF 점수가 극히 낮아도 통과

**해결**: marginal 레벨 도입

| 조건 | 판정 | 레벨 | confidence |
|------|------|------|-----------|
| `doc_count > 0 && max_sim >= 0.01` | sufficient | `sufficient` | 1.0 |
| `doc_count > 0 && max_sim < 0.01` | sufficient (경고) | `marginal` | 0.5 |
| `doc_count == 0` | insufficient | `insufficient` | 0.0 |

config 설정: `RETRIEVAL_SUFFICIENCY_MIN_SCORE=0.01` (기본값)

### 5.3 수정 파일

| 파일 | 변경 내용 |
|------|-----------|
| `backend/app/agents/answer_generation/agent.py` | dead function 2개 삭제 |
| `backend/app/agents/retrieval/sufficiency.py` | marginal 레벨 추가 |
| `backend/app/common/config.py` | `sufficiency_min_score` 설정 추가 |

---

## 6. 전체 수정 파일 요약

| 파일 | PR | 작업 |
|------|----|------|
| `backend/app/api/response_builder.py` | A | **신규** — 공통 응답 빌더 |
| `backend/app/api/chat.py` | A | 양쪽 엔드포인트 리팩토링 |
| `backend/app/api/models.py` | A | AgencyRecommendation 확장 |
| `backend/app/supervisor/nodes/retrieval_merge.py` | A | agency 연결 |
| `backend/app/agents/retrieval/tools/unified_retriever.py` | B | search_multi() 추가 |
| `backend/app/agents/retrieval/base_retrieval_agent.py` | B | expanded_queries 분기 |
| `backend/app/agents/retrieval/law_agent.py` | B | rrf_k → config |
| `backend/app/agents/retrieval/criteria_agent.py` | B | rrf_k → config |
| `backend/app/common/config.py` | B, D | rrf_k_python, sufficiency_min_score 추가 |
| `backend/app/agents/protocols.py` | C | 전체 재작성 |
| `backend/app/agents/answer_generation/agent.py` | D | dead function 삭제 |
| `backend/app/agents/retrieval/sufficiency.py` | D | marginal 레벨 추가 |
| `frontend/src/shared/types/chat.types.ts` | A | 타입 정렬 |
| `frontend/src/features/chat/ChatPage.tsx` | A | awaiting_user_choice 제거 |

**총 14개 파일** (백엔드 12, 프론트엔드 2), 신규 1개

---

## 7. 검증 결과

| 항목 | 결과 |
|------|------|
| 백엔드 import 검증 | ✅ 전체 통과 |
| 프론트엔드 TypeScript `tsc --noEmit` | ✅ 에러 없음 |
| 백엔드 단위 테스트 (340건 pass) | ✅ 기존과 동일 (37건 실패는 기존 이슈) |
| response_builder 수동 테스트 | ✅ 빈 state, agency 포함 state 모두 정상 |
| config 설정값 확인 | ✅ `rrf_k_python=60`, `sufficiency_min_score=0.01` |

---

## 8. 추가 환경변수

| 환경변수 | 기본값 | 설명 |
|---------|--------|------|
| `RETRIEVAL_RRF_K_PYTHON` | `60` | Python 2차 RRF fusion k값 (expanded_queries 병합용) |
| `RETRIEVAL_SUFFICIENCY_MIN_SCORE` | `0.01` | RRF 최소 품질 점수, 이하면 marginal 경고 |

기존 `RETRIEVAL_RRF_K=10` (SQL 레벨)은 변경 없음.
