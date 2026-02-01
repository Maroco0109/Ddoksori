# Progressive Disclosure + Adaptive Query Routing 구현 문서

> **Status**: Phase A~E 구현 완료 (2026-01-31)
> **브랜치**: `feature/34-e2e`
> **설계 문서**: `docs/plans/2026-01-31-progressive-disclosure-design.md`

---

## 1. 개요

### 1.1 해결한 문제

| # | 문제 | 해결 Phase | 핵심 변경 |
|---|------|-----------|-----------|
| P1 | dispute 쿼리 시 모든 정보 한 번에 출력 (정보 과부하) | Phase C+E | Progressive Disclosure - 요약 먼저, 상세는 후속 대화에서 |
| P2 | 후속 질문 클릭 시 새 RAG 검색 실행 (기존 컨텍스트 미활용) | Phase D | FOLLOWUP_WITH_CONTEXT - 이전 턴 retrieval 재사용 |
| P3 | 메타 쿼리("뭘 물어봐야 할까?")에 무의미한 검색 실행 | Phase A+B+E | META_CONVERSATIONAL - RAG 없이 가이드 응답 |

### 1.2 A/B 테스트 전략

`RESPONSE_MODE` 환경변수로 동작 모드 전환:

| 모드 | 설명 | P1 | P2 | P3 |
|------|------|:--:|:--:|:--:|
| `legacy` (기본) | 기존 동작 100% 유지 | - | - | - |
| `minimal` | 규칙 기반 Progressive Disclosure | O | O | O |
| `adaptive` | LLM 판단 기반 (향후 구현) | O | O | O |

단일 Docker 인스턴스에서 환경변수만 변경하여 A/B 테스트 가능.

---

## 2. 아키텍처 변경

### 2.1 새로운 라우팅 모드

**파일**: `backend/app/supervisor/state/control.py`

기존 4개 모드에 2개 추가:

```
기존: NO_RETRIEVAL | NEED_RAG | CACHED_RAG | RESTRICTED_DOMAIN
추가: META_CONVERSATIONAL | FOLLOWUP_WITH_CONTEXT
```

| 모드 | 트리거 조건 | Retrieval | Generation |
|------|-------------|:---------:|:----------:|
| `META_CONVERSATIONAL` | 메타 쿼리 패턴 매칭 | 생략 | 가이드 템플릿 응답 |
| `FOLLOWUP_WITH_CONTEXT` | 후속 질문 + 이전 턴 retrieval 존재 | 생략 | 캐시된 retrieval로 상세 응답 |

### 2.2 MAS Supervisor 그래프 Fast Path

**파일**: `backend/app/supervisor/graph_mas.py`

`_route_mas_supervisor()` 에서 두 모드 모두 retrieval 단계 생략:

```
supervisor → (mode == META_CONVERSATIONAL or FOLLOWUP_WITH_CONTEXT)
           → retrieval 생략 → generation 직행
```

### 2.3 응답 흐름 다이어그램

```
사용자 쿼리 입력
    │
    ▼
classify_mode() ─── RESPONSE_MODE == "legacy"? ──→ 기존 동작 (변경 없음)
    │
    │ (minimal/adaptive)
    ▼
┌─── META_CONVERSATIONAL? ──→ 가이드 템플릿 응답 (RAG 미실행)
│
├─── FOLLOWUP_WITH_CONTEXT? ──→ 이전 턴 retrieval 재사용 → 상세 응답
│
├─── NEED_RAG? ──→ RAG 실행 → 충분성 검사 → summary 응답
│                                          + available_details
│                                          + 후속 질문 생성
│
└─── 기타 (NO_RETRIEVAL 등) ──→ 기존 동작
```

---

## 3. Phase별 구현 상세

### Phase A: 기반 인프라

#### A-1. ResponseConfig 설정 추가

**파일**: `backend/app/common/config.py`

```python
class ResponseConfig(BaseModel):
    response_mode: Literal["legacy", "minimal", "adaptive"] = "legacy"
    summary_max_length: int = 200
    followup_similarity_threshold: float = 0.8
```

**환경변수**:

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `RESPONSE_MODE` | `legacy` | 응답 모드 (`legacy` / `minimal` / `adaptive`) |
| `SUMMARY_MAX_LENGTH` | `200` | Progressive Disclosure 요약 최대 길이 (자) |
| `FOLLOWUP_SIMILARITY_THRESHOLD` | `0.8` | 후속 질문 매칭 유사도 임계값 |

---

### Phase B: 메타 쿼리 분류 (P3 해결)

#### B-1. META_CONVERSATIONAL 감지

**파일**: `backend/app/agents/query_analysis/classifiers.py`

`classify_mode()` 함수에 META_CONVERSATIONAL 분기 추가. `RESPONSE_MODE == "legacy"` 일 때는 기존 동작 유지.

감지 로직:
1. `is_meta_conversational()` 함수에서 패턴 매칭
2. 매칭 시 `META_CONVERSATIONAL` 모드 반환
3. 기존 `is_ambiguous_query()` 보다 우선 체크

#### B-2. 메타 쿼리 패턴

**파일**: `backend/app/agents/query_analysis/constants.py`

```python
META_CONVERSATIONAL_PATTERNS = [
    r"(뭘|무엇을?|어떤\s*걸?)\s*(물어|질문|문의)",
    r"(도와|도움)\s*(줘|주세요|줄래)",
    r"(어떻게|뭐부터)\s*(시작|해야)",
    # ...
]

META_CONVERSATIONAL_KEYWORDS = [
    "도와줘", "도움말", "사용법", "어떻게 해", ...
]
```

#### B-3. Supervisor 라우팅

META_CONVERSATIONAL 모드는 `_route_mas_supervisor()`에서 retrieval 생략 → generation 직행.

---

### Phase C: Progressive Disclosure (P1 해결)

#### C-1. OutputState 확장

**파일**: `backend/app/supervisor/state/output.py`, `backend/app/supervisor/state/__init__.py`

```python
# 신규 필드
response_depth: ResponseDepth  # Literal["summary", "detail", "full"]
available_details: Optional[Dict]  # 아직 제공하지 않은 상세 정보 메타데이터
```

`create_initial_state()` 기본값: `response_depth='full'`, `available_details=None`

#### C-2. Progressive Summary 생성

**파일**: `backend/app/agents/answer_generation/agent.py`

`_build_progressive_summary(answer, retrieval, max_length=200)` 함수:
- 마크다운 헤딩(`##`, `###`) 제거
- 면책 조항(`> 본 답변은...`) 제거
- 문장 경계에서 truncation
- 빈 답변 시 기본 메시지 반환

#### C-3. available_details 구축

`_build_available_details(retrieval)` 함수:

```python
# 입력: retrieval 결과
# 출력:
{
    "laws": {"count": 3, "preview": "소비자기본법 제17조 등"},
    "criteria": {"count": 2, "preview": "분쟁해결기준 환불 규정"},
    "cases": {"count": 5, "preview": "유사 조정사례 5건"}
}
```

- `laws`: retrieval['laws'] 문서 수 + 첫 문서 제목
- `criteria`: retrieval['criteria'] 문서 수 + 첫 문서 제목
- `cases`: retrieval['disputes'] + retrieval['counsels'] 합산

#### C-4. 후속 질문 생성 개선

`_build_progressive_followups(retrieval, available_details)` 함수:
- `available_details`의 섹션별로 구체적인 질문 생성
- 법령 상세, 사례 상세, 절차 안내 등 구분
- 최대 3개 후속 질문
- 상세가 없어도 기본 "절차 안내" 질문 포함

---

### Phase D: 후속 질문 컨텍스트 재활용 (P2 해결)

#### D-1. FOLLOWUP_WITH_CONTEXT 감지

**파일**: `backend/app/agents/query_analysis/detectors.py`

`is_followup_with_context()` 함수:

```python
def is_followup_with_context(
    user_query: str,
    last_turn_context: Optional[Dict]
) -> bool:
    """
    후속 질문 클릭 감지:
    1. last_turn_context 존재 (이전 턴에 retrieval 결과 있음)
    2. last_turn_context['followup_questions']에 현재 쿼리 매칭
    3. difflib.SequenceMatcher ratio >= 0.8 (minimal 모드)
    """
```

`detect_requested_detail_type()` 함수:

```python
def detect_requested_detail_type(user_query: str) -> Optional[str]:
    """
    키워드 기반으로 요청된 상세 섹션 감지:
    - "법령", "법률", "조문" → "laws"
    - "사례", "조정", "분쟁" → "cases"
    - "기준", "규정", "별표" → "criteria"
    - "절차", "방법", "단계" → "procedure"
    """
```

#### D-2. 이전 턴 컨텍스트 보존

**파일**: `backend/app/supervisor/nodes/memory_save.py`

`memory_save_node`에서 현재 턴의 retrieval 결과, followup_questions, available_details를 `_last_turn_context`에 저장:

```python
# _last_turn_context 구조
{
    "retrieval": { ... },           # 이전 턴 retrieval 결과
    "followup_questions": [...],    # 이전 턴 생성된 후속 질문
    "available_details": { ... }    # 이전 턴 available_details
}
```

**파일**: `backend/app/supervisor/state/__init__.py`

```python
# ChatState에 추가
_last_turn_context: Optional[Dict[str, Any]]
```

#### D-3. 후속 상세 응답 생성

**파일**: `backend/app/agents/answer_generation/agent.py`

`_followup_detail_response(state)` 함수:

```python
def _followup_detail_response(state):
    """
    FOLLOWUP_WITH_CONTEXT 모드 응답 생성:
    1. _last_turn_context에서 이전 retrieval 가져옴
    2. detect_requested_detail_type()으로 요청 섹션 파악
    3. _filter_retrieval_for_detail()로 해당 섹션만 필터링
    4. LLM에게 상세 답변 생성 요청
    """
```

`_filter_retrieval_for_detail(retrieval, detail_type)`:
- `detail_type == "laws"`: retrieval에서 laws 섹션만 포함
- `detail_type == "cases"`: disputes + counsels 섹션만 포함
- `detail_type == "criteria"`: criteria 섹션만 포함
- `detail_type == "procedure"` or None: 전체 retrieval 사용

---

### Phase E: 답변 생성 노드 통합

#### E-1. generation_node_v2 분기 로직

**파일**: `backend/app/agents/answer_generation/agent.py`

```python
async def generation_node_v2(state):
    mode = state["mode"]
    response_mode = get_config().response.response_mode

    if response_mode == "legacy":
        return _legacy_generation(state)  # 기존 동작

    if mode == "META_CONVERSATIONAL":
        return _meta_conversational_response(state)

    if mode == "FOLLOWUP_WITH_CONTEXT":
        return _followup_detail_response(state)

    if mode == "NEED_RAG" and response_mode == "minimal":
        # RAG 결과로 summary 생성
        full_answer = _legacy_generation(state)  # LLM 호출
        summary = _build_progressive_summary(full_answer, retrieval)
        details = _build_available_details(retrieval)
        followups = _build_progressive_followups(retrieval, details)
        return {
            'draft_answer': summary,
            'response_depth': 'summary',
            'available_details': details,
            'followup_questions': followups,
        }

    return _legacy_generation(state)  # 나머지는 기존 동작
```

#### E-2. 메타 대화 응답 생성

`_meta_conversational_response(state)`:
- 온보딩 정보 없음: 일반 가이드 ("다음 정보를 알려주시면 도움을 드릴 수 있습니다: 1. 구매 품목...")
- 온보딩 정보 있음: 맞춤 가이드 ("에어팟 관련 문의시군요. 어떤 문제 상황인지...")
- `generation_model_used = 'meta_conversational_template'`
- `response_depth = 'full'`

---

## 4. 변경 파일 목록

### 신규 파일

| 파일 | Phase | 설명 |
|------|-------|------|
| `backend/app/agents/query_analysis/detectors.py` | D | 후속 질문 감지, 상세 섹션 탐지 |
| `backend/scripts/testing/supervisor/test_followup_with_context.py` | D | Phase D 테스트 33건 |
| `backend/scripts/testing/supervisor/test_progressive_disclosure.py` | C+E | Phase C+E 테스트 |

### 수정 파일

| 파일 | Phase | 변경 내용 |
|------|-------|-----------|
| `backend/app/common/config.py` | A | `ResponseConfig` 추가 |
| `backend/app/agents/query_analysis/constants.py` | B | `META_CONVERSATIONAL_PATTERNS/KEYWORDS` 추가 |
| `backend/app/agents/query_analysis/classifiers.py` | B, D | `is_meta_conversational()`, FOLLOWUP_WITH_CONTEXT 분기 |
| `backend/app/agents/query_analysis/agent.py` | B | META_CONVERSATIONAL 분류 통합 |
| `backend/app/agents/answer_generation/agent.py` | C, D, E | Progressive Disclosure + 메타 응답 + 후속 상세 응답 |
| `backend/app/supervisor/state/control.py` | A | `RoutingMode`에 2개 모드 추가 |
| `backend/app/supervisor/state/output.py` | C | `response_depth`, `available_details` 필드 |
| `backend/app/supervisor/state/__init__.py` | C, D | ChatState 필드 추가, 초기값 설정 |
| `backend/app/supervisor/graph_mas.py` | D | FOLLOWUP_WITH_CONTEXT fast path |
| `backend/app/supervisor/nodes/memory_save.py` | D | `_last_turn_context` 저장 |

---

## 5. 환경변수

| 변수 | 기본값 | 설명 | Phase |
|------|--------|------|-------|
| `RESPONSE_MODE` | `legacy` | 응답 모드 (`legacy` / `minimal` / `adaptive`) | A |
| `SUMMARY_MAX_LENGTH` | `200` | 요약 최대 길이 (자) | A |
| `FOLLOWUP_SIMILARITY_THRESHOLD` | `0.8` | 후속 질문 매칭 유사도 임계값 | A |

---

## 6. 테스트

### 6.1 Phase C+E 테스트 (test_progressive_disclosure.py)

| 클래스 | 테스트 수 | 내용 |
|--------|-----------|------|
| TestOutputStateExtension | 3 | response_depth, available_details 필드 존재 확인 |
| TestProgressiveSummary | 5 | 요약 truncation, 마크다운 제거, 면책 제거, 빈 답변 |
| TestAvailableDetails | 5 | 법령/기준/사례 섹션별 구축 |
| TestProgressiveFollowups | 4 | 후속 질문 생성, 최대 3개 제한 |
| TestMetaConversationalResponse | 3 | 기본/온보딩 응답, messages 필드 |
| TestGenerationNodeV2Branching | 3 | legacy/meta/minimal 모드 분기 |
| TestMASRoutingMetaConversational | 1 | META_CONVERSATIONAL retrieval 생략 |

### 6.2 Phase D 테스트 (test_followup_with_context.py)

| 클래스 | 테스트 수 | 내용 |
|--------|-----------|------|
| TestDetectRequestedDetailType | 7 | 키워드 기반 상세 섹션 감지 |
| TestIsFollowupWithContext | 6 | 후속 질문 매칭 (유사도 0.8 기준) |
| TestClassifyModeFollowup | 3 | classify_mode() FOLLOWUP_WITH_CONTEXT 분기 |
| TestFilterRetrievalForDetail | 4 | retrieval 필터링 (laws/cases/criteria/전체) |
| TestFollowupDetailResponse | 3 | 후속 상세 응답 생성 |
| TestMemorySaveLastTurnContext | 3 | _last_turn_context 저장 |
| TestMASRoutingFollowup | 2 | 그래프 라우팅 fast path |
| TestChatStateLastTurnContext | 2 | ChatState 필드 존재/초기값 |
| TestControlStateRoutingMode | 3 | RoutingMode 타입 검증 |

### 6.3 회귀 테스트 결과

```
556 passed, 5 failed (all pre-existing), 14 skipped
```

Phase C/D/E 변경으로 인한 regression: **0건**

5개 기존 실패:
- `test_rrf_weights_configuration`: RRF_WEIGHT_SPARSE import 오류 (기존)
- `test_repeated_query_uses_cache`: 비결정적 타이밍 테스트 (기존)
- `test_supervisor_optimization` 3건: iteration 기대값 불일치 (기존)

---

## 7. 참조 문서

- **설계 문서**: `docs/plans/2026-01-31-progressive-disclosure-design.md`
- **PR-A/B/C 보고서**: `docs/report/2026-01-31-pr-abc-implementation-report.md`
- **MAS 아키텍처**: `docs/feature/MAS_SUPERVISOR_ARCHITECTURE.md`
- **배포 가이드**: `docs/guides/deployment-execution-guide.md` (A/B 테스트 섹션)

---

**작성일**: 2026-01-31
**마지막 업데이트**: 2026-01-31
