# 응답 처리 방식 개선 설계 - Progressive Disclosure + Adaptive Query Routing

## 1. 문제 정의

### 현재 문제 3가지
| # | 문제 | 원인 | 영향 |
|---|------|------|------|
| P1 | dispute 쿼리 시 모든 정보 한 번에 출력 | 검색된 법령/기준/사례/상담을 전부 answer에 포함 | 사용자 정보 과부하 |
| P2 | 후속 질문 클릭 시 fallback 발생 | 새 RAG 검색 실행, 기존 컨텍스트 미활용 | 후속 채팅 무용 |
| P3 | 메타 쿼리("뭘 물어봐야 할까?") → 무의미한 검색 | NEED_RAG로 분류되어 유사도 검색 실행 | 부적절한 응답 |

### 해결 전략 요약
- **P1**: Progressive Disclosure - 첫 응답은 핵심 요약만, 상세는 후속 대화에서 단계적 제공
- **P2**: CACHED_RAG 확장 + Query Reformulation - 기존 검색 결과 재활용
- **P3**: META_CONVERSATIONAL 라우팅 모드 추가 - 대화형 안내 응답

### A/B 테스트 구조
- `RESPONSE_MODE` 환경변수로 전환: `legacy` (현재) / `minimal` (규칙 기반) / `adaptive` (LLM 판단)
- Docker 1개 인스턴스에서 환경변수만 변경하여 테스트

---

## 2. 아키텍처 변경

### 2.1 새로운 라우팅 모드 추가

**파일**: `backend/app/agents/query_analysis/classifiers.py`

현재 4개 모드에 2개 추가:

```
기존: NO_RETRIEVAL | NEED_RAG | CACHED_RAG | RESTRICTED_DOMAIN
추가: META_CONVERSATIONAL | FOLLOWUP_WITH_CONTEXT
```

| 모드 | 트리거 조건 | 동작 |
|------|-------------|------|
| `META_CONVERSATIONAL` | "뭘 물어봐야 할까?", "도와줘", "어떻게 시작해?" 등 | RAG 없이 가이드 응답 생성 |
| `FOLLOWUP_WITH_CONTEXT` | 후속 질문 클릭 + 이전 턴에 검색 결과 존재 | 기존 검색 결과로 답변, 신규 검색 생략 |

### 2.2 Progressive Disclosure 응답 구조

**파일**: `backend/app/agents/answer_generation/agent.py`

첫 응답(dispute 쿼리):
```json
{
  "answer": "핵심 요약 (2-3문장)",
  "response_depth": "summary",
  "available_details": {
    "laws": {"count": 3, "preview": "소비자기본법 제17조 등"},
    "criteria": {"count": 2, "preview": "분쟁해결기준 환불 규정"},
    "cases": {"count": 5, "preview": "유사 조정사례 5건"}
  },
  "followup_questions": [
    "관련 법령을 자세히 알려드릴까요?",
    "유사한 분쟁 조정 사례를 확인해보시겠어요?",
    "분쟁 해결 절차를 안내해드릴까요?"
  ]
}
```

후속 응답(후속 질문 클릭 시):
```json
{
  "answer": "요청한 섹션의 상세 정보",
  "response_depth": "detail",
  "detail_type": "laws",
  "followup_questions": ["다른 정보도 확인하시겠어요?"]
}
```

### 2.3 Query Reformulation (후속 질문 처리)

**파일**: 새 모듈 `backend/app/agents/query_analysis/reformulator.py`

후속 질문 감지 로직:
1. `session_id`가 있고 이전 턴에 retrieval 결과가 존재
2. 질문이 이전 응답의 `followup_questions` 중 하나와 매칭
3. → `FOLLOWUP_WITH_CONTEXT` 모드로 라우팅

| RESPONSE_MODE | 후속 질문 처리 방식 |
|---------------|---------------------|
| `minimal` | 규칙 기반 매칭 (문자열 유사도 ≥ 0.8) |
| `adaptive` | LLM (gpt-4o-mini) 으로 의도 분류 + 필요시 쿼리 재작성 |

### 2.4 META_CONVERSATIONAL 응답 생성

**파일**: `backend/app/agents/answer_generation/agent.py` (generation 노드 확장)

메타 쿼리 감지:
```python
META_QUERY_PATTERNS = [
    r"(뭘|무엇을?|어떤\s*걸?)\s*(물어|질문|문의)",
    r"(도와|도움)\s*(줘|주세요|줄래)",
    r"(어떻게|뭐부터)\s*(시작|해야)",
    r"(알려|가르쳐)\s*(줘|주세요)",
    r"^(안내|설명|소개)",
]
```

| RESPONSE_MODE | 메타 쿼리 응답 |
|---------------|----------------|
| `minimal` | 규칙 기반 템플릿 ("다음과 같은 정보를 알려주시면 도움을 드릴 수 있습니다: 1. 구매 품목 2. 구매일자 3. 문제 상황...") |
| `adaptive` | LLM이 대화 이력 기반으로 맞춤 가이드 생성 (온보딩 정보 참고) |

---

## 3. 구현 계획

### Phase A: 기반 인프라 (환경변수 + 설정)

#### A-1. RESPONSE_MODE 설정 추가
**파일**: `backend/app/common/config.py`

```python
class ResponseConfig(BaseModel):
    response_mode: Literal["legacy", "minimal", "adaptive"] = "legacy"
    summary_max_length: int = 200  # 요약 최대 길이
    followup_similarity_threshold: float = 0.8  # 후속 질문 매칭 임계값
    meta_query_use_llm: bool = False  # adaptive 모드에서만 True
```

환경변수:
- `RESPONSE_MODE=legacy|minimal|adaptive`
- `SUMMARY_MAX_LENGTH=200`
- `FOLLOWUP_SIMILARITY_THRESHOLD=0.8`

#### A-2. Docker Compose 환경변수 프로필
**파일**: `docker-compose.yml` 수정

```yaml
backend:
  environment:
    - RESPONSE_MODE=${RESPONSE_MODE:-legacy}  # 기본값: legacy (현재 동작)
```

테스트 시:
```bash
RESPONSE_MODE=minimal docker compose up backend  # A 모드
RESPONSE_MODE=adaptive docker compose up backend  # B 모드
```

### Phase B: 쿼리 분류 개선 (P3 해결)

#### B-1. META_CONVERSATIONAL 라우팅 모드 추가
**파일**: `backend/app/agents/query_analysis/classifiers.py`

- `classify_mode()` 함수에 META_CONVERSATIONAL 분기 추가
- 기존 `is_ambiguous_query()` 앞에 `is_meta_conversational()` 체크 추가 (우선순위 높음)
- `RESPONSE_MODE == "legacy"` 일 때는 기존 동작 유지 (하위 호환)

#### B-2. 메타 쿼리 감지 함수
**파일**: `backend/app/agents/query_analysis/classifiers.py` 또는 `detectors.py`

- `is_meta_conversational(query: str) -> bool` 함수 추가
- 규칙 기반 패턴 매칭 (minimal 모드)
- LLM fallback (adaptive 모드, confidence < 0.7 시)

#### B-3. constants.py에 메타 쿼리 패턴 추가
**파일**: `backend/app/agents/query_analysis/constants.py`

- `META_CONVERSATIONAL_PATTERNS` 리스트 추가
- `META_CONVERSATIONAL_KEYWORDS` 리스트 추가

### Phase C: Progressive Disclosure 구현 (P1 해결)

#### C-1. 응답 구조 변경 - StructuredResponse 모델
**파일**: `backend/app/agents/answer_generation/agent.py`

- `StructuredResponse` Pydantic 모델 정의
- `response_depth: Literal["summary", "detail", "full"]` 필드 추가
- `available_details` 필드로 아직 제공하지 않은 정보 메타데이터 포함
- generation 노드에서 RESPONSE_MODE에 따라 분기:
  - `legacy`: 기존 동작 (전체 정보 포함)
  - `minimal/adaptive`: 요약만 생성, 상세는 available_details로 안내

#### C-2. 요약 생성 로직
**파일**: `backend/app/agents/answer_generation/agent.py`

| RESPONSE_MODE | 요약 생성 방식 |
|---------------|----------------|
| `minimal` | retrieval 결과에서 max_similarity 상위 3개 문서의 핵심 문장 추출 (규칙 기반) |
| `adaptive` | LLM에게 "200자 이내 핵심 요약" 프롬프트 (기존 generation 프롬프트 변형) |

#### C-3. 후속 질문 생성 개선
**파일**: `backend/app/agents/answer_generation/agent.py`

현재 `_generate_retrieval_based_followups()`을 확장:
- 검색 결과 섹션별로 구체적인 후속 질문 생성
- 이전 턴에서 이미 제공한 정보는 제외
- `available_details`와 연동하여 "법령 상세", "사례 상세", "절차 안내" 등 구분

### Phase D: 후속 질문 컨텍스트 재활용 (P2 해결)

#### D-1. FOLLOWUP_WITH_CONTEXT 라우팅 모드
**파일**: `backend/app/agents/query_analysis/classifiers.py`

감지 조건:
1. `session_id` 존재 (멀티턴)
2. 이전 턴의 `individual_retrieval_results`가 비어있지 않음
3. 현재 쿼리가 이전 `followup_questions` 중 하나와 매칭

매칭 방식:
| RESPONSE_MODE | 매칭 방식 |
|---------------|-----------|
| `minimal` | `difflib.SequenceMatcher` ratio ≥ 0.8 |
| `adaptive` | LLM 의도 분류 (이전 응답의 어떤 섹션 상세를 원하는지) |

#### D-2. Retrieval 결과 캐싱 확장
**파일**: `backend/app/supervisor/state/memory.py`

- `RAGConversationMemory`에 `last_retrieval_results` 필드 추가
- 이전 턴의 검색 결과를 세션 메모리에 보존
- `FOLLOWUP_WITH_CONTEXT` 모드에서 재활용

#### D-3. Supervisor 그래프 라우팅 변경
**파일**: `backend/app/supervisor/graph_mas.py`

- `_route_mas_supervisor()`에 `FOLLOWUP_WITH_CONTEXT` 분기 추가
- 기존 `CACHED_RAG` 로직 확장: retrieval 건너뛰고 바로 generation으로
- generation 노드에서 `response_depth="detail"` + 요청된 섹션만 상세 제공

#### D-4. Query Reformulation 모듈 (adaptive 모드 전용)
**파일**: 신규 `backend/app/agents/query_analysis/reformulator.py`

- `reformulate_followup_query(current_query, conversation_history, last_retrieval) -> ReformulatedQuery`
- adaptive 모드에서만 활성화
- LLM으로 후속 질문을 독립적인 검색 쿼리로 변환
  - 예: "그 법 조항은?" → "소비자기본법 제17조 청약철회 조항 상세"

### Phase E: 답변 생성 노드 통합

#### E-1. generation_node_v2 분기 로직
**파일**: `backend/app/agents/answer_generation/agent.py`

```python
def generation_node_v2(state):
    mode = state["mode"]
    response_mode = get_config().response.response_mode

    if response_mode == "legacy":
        return _legacy_generation(state)  # 기존 동작

    if mode == "META_CONVERSATIONAL":
        return _meta_conversational_response(state, response_mode)

    if mode == "FOLLOWUP_WITH_CONTEXT":
        return _followup_detail_response(state, response_mode)

    if mode == "NEED_RAG":
        return _progressive_summary_response(state, response_mode)

    # NO_RETRIEVAL, RESTRICTED_DOMAIN 등은 기존 로직
    return _legacy_generation(state)
```

#### E-2. 메타 대화 응답 생성
```python
def _meta_conversational_response(state, response_mode):
    if response_mode == "minimal":
        # 규칙 기반 템플릿
        return _template_guide_response(state)
    else:  # adaptive
        # LLM 기반 맞춤 가이드
        return _llm_guide_response(state)
```

#### E-3. 후속 상세 응답 생성
```python
def _followup_detail_response(state, response_mode):
    # 이전 턴의 retrieval 결과에서 요청된 섹션만 상세 제공
    detail_type = state.get("requested_detail_type")  # "laws" | "cases" | "criteria" | "procedure"
    cached_retrieval = state.get("cached_retrieval_results")
    # ... 해당 섹션만 상세 답변 생성
```

---

## 4. 수정 대상 파일 목록

| 파일 | 변경 내용 | 우선순위 |
|------|-----------|----------|
| `backend/app/common/config.py` | `ResponseConfig` 추가 | Phase A |
| `backend/app/agents/query_analysis/constants.py` | `META_CONVERSATIONAL_PATTERNS/KEYWORDS` 추가 | Phase B |
| `backend/app/agents/query_analysis/classifiers.py` | `is_meta_conversational()`, `classify_mode()` 확장 | Phase B |
| `backend/app/agents/query_analysis/agent.py` | META_CONVERSATIONAL 분류 통합 | Phase B |
| `backend/app/agents/answer_generation/agent.py` | Progressive Disclosure 응답 분기 | Phase C/E |
| `backend/app/supervisor/state/memory.py` | `last_retrieval_results` 캐싱 | Phase D |
| `backend/app/supervisor/state/control.py` | 새 라우팅 모드 타입 추가 | Phase B |
| `backend/app/supervisor/graph_mas.py` | FOLLOWUP_WITH_CONTEXT 라우팅 | Phase D |
| `backend/app/supervisor/nodes/supervisor.py` | 새 모드 핸들링 | Phase D |
| `backend/app/agents/query_analysis/reformulator.py` | **신규** - 쿼리 재작성 모듈 | Phase D |
| `docker-compose.yml` | RESPONSE_MODE 환경변수 추가 | Phase A |
| `backend/.env.example` | 새 환경변수 문서화 | Phase A |

---

## 5. 테스트 전략

### 단위 테스트
| 테스트 대상 | 파일 | 내용 |
|-------------|------|------|
| 메타 쿼리 감지 | `test_classifier.py` 확장 | "뭘 물어봐야 할까?" 등 10+ 케이스 |
| 후속 질문 매칭 | 신규 `test_followup_matching.py` | 문자열 유사도/LLM 매칭 테스트 |
| Progressive Disclosure | 신규 `test_progressive_disclosure.py` | 요약 생성, available_details 구조 검증 |
| RESPONSE_MODE 전환 | `test_supervisor.py` 확장 | legacy/minimal/adaptive 모드별 동작 |

### 통합 테스트
| 시나리오 | 기대 결과 |
|----------|-----------|
| dispute 쿼리 (minimal) | 요약 응답 + 3개 후속 질문 |
| 후속 질문 클릭 (minimal) | 기존 검색 결과 재활용, 상세 응답 |
| "뭘 물어봐야 할까?" (minimal) | 가이드 템플릿 응답, RAG 미실행 |
| dispute 쿼리 (adaptive) | LLM 요약 + 맞춤 후속 질문 |
| 후속 질문 클릭 (adaptive) | LLM 쿼리 재작성 + 캐시 활용 |
| "뭘 물어봐야 할까?" (adaptive) | LLM 맞춤 가이드 응답 |
| 모든 시나리오 (legacy) | 기존 동작 100% 유지 |

### A/B 비교 테스트
```bash
# 기존 동작 확인
RESPONSE_MODE=legacy docker compose up backend
curl -X POST http://localhost:8000/chat/stream -d '{"message":"노트북 환불","chat_type":"dispute"}'

# minimal 모드 테스트
RESPONSE_MODE=minimal docker compose up backend
curl -X POST http://localhost:8000/chat/stream -d '{"message":"노트북 환불","chat_type":"dispute"}'

# adaptive 모드 테스트
RESPONSE_MODE=adaptive docker compose up backend
curl -X POST http://localhost:8000/chat/stream -d '{"message":"노트북 환불","chat_type":"dispute"}'
```

---

## 6. 리서치 기반 근거

| 적용 패턴 | 출처 | 적용 부분 |
|-----------|------|-----------|
| Progressive Disclosure | Perplexity AI, Honra.ai | Phase C - 요약 먼저, 상세는 요청 시 |
| Adaptive-RAG | Jeong et al. 2024 (NAACL) | RESPONSE_MODE adaptive - 쿼리별 LLM 판단 |
| Query Reformulation | Perplexity, Haystack ConvRAG | Phase D - 후속 질문 재작성 |
| Proactive Conversation | CHI 2025, PCA Framework | Phase B - 메타 쿼리 시 능동적 가이드 |
| Slot-Filling Intake | 법률똑똑이 (대한법률구조공단) | 메타 쿼리 응답에서 필요 정보 안내 |
| Layered Response | ThoughtRiver, V7Labs | Phase C - TL;DR → 법적 근거 → 사례 → 다음 단계 |
| CACHED_RAG Reuse | Self-RAG (Asai 2023) | Phase D - 이전 검색 결과 재활용 |

---

## 7. 구현 순서 (권장)

```
Phase A: 기반 인프라 (config + 환경변수)
  ↓
Phase B: 메타 쿼리 분류 (P3 해결) - 가장 간단, 빠른 효과
  ↓
Phase C: Progressive Disclosure (P1 해결) - 핵심 변경
  ↓
Phase D: 후속 질문 컨텍스트 재활용 (P2 해결)
  ↓
Phase E: 답변 생성 통합 + 테스트
```

각 Phase는 독립적으로 테스트 가능하며, legacy 모드 하위 호환 보장.
