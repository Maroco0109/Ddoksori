# 똑소리 답변 품질 개선 종합 계획

> 작성일: 2026-02-01
> 대상 브랜치: feature/34-e2e

## 현황 분석

### 이슈 1: 라우팅 오분류
- "ㅎㅇ"(인사) → NEED_RAG로 분류됨 (정상: NO_RETRIEVAL)
- "노트북 관련 기준 있어?" → NO_RETRIEVAL로 분류됨 (정상: NEED_RAG)
- Docker 컨테이너에서 `RESPONSE_MODE=adaptive` 활성화 확인됨
- 원인 추정: adaptive 모드의 LLM 기반 분류 개입 또는 Redis 캐시 오류

### 이슈 2: RESPONSE_MODE 환경변수 전달
- `.env`에 `RESPONSE_MODE=adaptive` 설정됨
- `docker-compose.yml`의 `${RESPONSE_MODE:-legacy}`와의 관계 정리 필요
- 배포 가이드에서 A/B 테스트 섹션이 너무 하단에 위치

### 이슈 3: 답변 생성 품질
- "피부관리서비스" 제목의 사례가 노트북 질문에 검색됨 → retrieval 유사도 문제
- DB 확인 결과: 피부관리서비스 사례는 실제 존재 (데이터 오류 아님), 검색 정확도 문제
- 반복적 동일 답변 출력 → 캐시 키에 session context 부족
- 온보딩 데이터(purchase_date, purchase_item 등)가 2턴 이후 유실
- FOLLOWUP_WITH_CONTEXT 모드에서 캐시된 retrieval 주입 로직 미구현

---

## 기대 사용자 경험

```
턴1: "노트북 지금 환불 되나?" + 온보딩(구매일:2026-01-09, 품목:갤럭시북 프로5, 금액:160만원)
  → 날짜 계산: 구매 후 23일 경과
  → 전자상거래법 청약철회(7일) 경과 안내
  → 소비자분쟁해결기준에 따른 품질보증기간 내 환불 가능성 안내
  → 후속 질문: ① 관련 법령 상세 ② 유사 사례 확인 ③ 조정신청 절차

턴2: "관련 법령을 자세히 알려드릴까요?" (후속 질문 클릭)
  → 캐시된 retrieval에서 법령 섹션만 상세 제공
  → 전자상거래법, 소비자기본법 관련 조항 안내

턴3: "비슷한 분쟁 조정 사례도 확인해볼까요?"
  → 캐시된 retrieval에서 노트북/전자제품 관련 사례만 필터하여 제공

턴4: "조정신청 절차가 궁금해요"
  → 조정신청 절차 탭 안내 + KCA/ECMC 신청서 작성 가이드
```

---

## 단계별 구현 계획

### Phase 1: 라우팅 버그 진단 및 수정

**수정 파일**:
- `backend/app/agents/query_analysis/classifiers.py`
- `backend/app/agents/query_analysis/agent.py`
- `backend/app/supervisor/nodes/supervisor.py`

**작업**:
1. classify_query_type_with_confidence, classify_mode 호출에 디버깅 로그 추가
2. adaptive 모드에서 LLM 분류 개입 경로 확인 및 수정
3. Redis 캐시 HIT으로 잘못된 결과 반환 여부 확인
4. 단위 테스트 작성

---

### Phase 2: RESPONSE_MODE 환경변수 정리 + 배포 가이드

**수정 파일**:
- `docker-compose.yml`
- `backend/.env.example`
- `docs/guides/deployment-execution-guide.md`

**작업**:
1. docker-compose.yml의 environment에서 RESPONSE_MODE 제거 (.env에서만 관리)
2. .env.example에 RESPONSE_MODE 항목 추가
3. 배포 가이드에서 A/B 테스트를 Section 2.3(환경변수 설정)으로 이동

---

### Phase 3: 답변 생성 파이프라인 개선 (핵심)

#### 3-A: 온보딩 데이터 영속화

**수정 파일**: `api/chat.py`, `supervisor/state/session.py`, `supervisor/conversation_manager.py`

1. 첫 턴에서 온보딩 데이터를 conversation DB metadata에 저장
2. 2턴 이후 DB에서 온보딩 복원 → state에 주입
3. dispute_slots 병합 시 온보딩 데이터 항상 포함

#### 3-B: 날짜 계산 및 환불 가능성 판단

**수정 파일**: `agents/query_analysis/extractors.py`, `agents/answer_generation/agent.py`, `agents/answer_generation/tools/generator.py`

1. purchase_date와 현재 날짜를 비교하여 경과 일수 자동 계산
2. 프롬프트에 "구매 후 {N}일 경과" 컨텍스트 포함
3. 품목별 청약철회/환불 기준 안내 지시 추가

#### 3-C: FOLLOWUP_WITH_CONTEXT 캐시 주입 완성

**수정 파일**: `supervisor/graph_mas.py`, `supervisor/cache.py`, `supervisor/nodes/memory_save.py`

1. FOLLOWUP_WITH_CONTEXT 라우팅에 `_last_turn_context.retrieval` 주입
2. generation_node_v2에서 요청된 detail_type별 섹션만 상세 제공

#### 3-D: 검색 정확도 개선

**수정 파일**: `agents/answer_generation/agent.py`, `agents/retrieval/tools/retriever.py` 또는 `hybrid_retriever.py`

1. 온보딩 purchase_item 기반 검색 결과 reranking/필터
2. 관련 없는 사례(피부관리 등) 필터링 (post-retrieval 검증)

#### 3-E: 반복 답변 방지

**수정 파일**: `agents/answer_generation/agent.py`, `supervisor/cache.py`

1. 캐시 키에 session_id + turn_number 포함
2. 이전 답변과 중복 체크 → 새로운 정보 위주 재구성

---

### Phase 4: Progressive Disclosure 답변 구조 개선

**수정 파일**: `agents/answer_generation/agent.py`, `agents/answer_generation/tools/generator.py`, `agents/query_analysis/detectors.py`

1. 첫 턴: "핵심 판단 + 근거 법령명 + 후속 질문 3개" 구조
2. 후속 질문 유형: ① 법령 상세 ② 유사 사례 ③ 조정신청 절차
3. `detect_requested_detail_type()` 강화
4. detail_type별 프롬프트 분리

---

### Phase 5: 조정신청 양식 안내 (후순위)

**수정 파일**: `agents/answer_generation/tools/generator.py`

1. KCA/ECMC 신청 양식 핵심 항목을 프롬프트 상수로 정의
2. 온보딩 정보 → 양식 항목 매핑 가이드
3. (추후) Web 검색으로 양식 정보 수집

---

## protocols.py 수정 사항

### OnboardingInfo 확장
```python
class OnboardingInfo(TypedDict, total=False):
    # 기존 필드 유지
    purchase_date: Optional[str]
    purchase_place: Optional[str]
    purchase_platform: Optional[str]
    purchase_item: Optional[str]
    purchase_amount: Optional[str]
    dispute_details: Optional[str]
    # 추가
    days_since_purchase: Optional[int]     # 구매 후 경과 일수 (자동 계산)
    product_category: Optional[str]        # 품목 카테고리 (전자제품, 의류 등)
```

### RetrievedDocument 확장
```python
class RetrievedDocument(TypedDict):
    chunk_id: str
    content: str
    metadata: DocumentMetadata
    similarity: float
    # 추가
    product_relevance: Optional[float]     # 온보딩 품목 관련성 (0.0~1.0)
```

### GenerationOutput 확장
```python
class GenerationOutput(TypedDict):
    draft_answer: str
    claim_evidence_map: List[ClaimEvidence]
    cited_cases: List[CitedCase]
    has_sufficient_evidence: bool
    generation_time_ms: float
    # 추가
    response_depth: Optional[str]          # "summary" | "detail" | "full"
    available_details: Optional[Dict]      # 미표시 상세 정보 메타
    followup_questions: Optional[List[str]]# 제안 후속 질문
    detail_type: Optional[str]             # "laws" | "cases" | "procedure"
```

---

## 수정 대상 파일 (18개)

| 파일 | Phase | 내용 |
|------|-------|------|
| `agents/query_analysis/classifiers.py` | 1 | 분류 디버깅, adaptive 수정 |
| `agents/query_analysis/agent.py` | 1 | 로그 보강 |
| `supervisor/nodes/supervisor.py` | 1 | 라우팅 로그 보강 |
| `docker-compose.yml` | 2 | RESPONSE_MODE 정리 |
| `.env.example` | 2 | RESPONSE_MODE 문서화 |
| `docs/guides/deployment-execution-guide.md` | 2 | A/B 섹션 이동 |
| `api/chat.py` | 3-A | 온보딩 영속화 |
| `supervisor/state/session.py` | 3-A | 온보딩 복원 |
| `supervisor/conversation_manager.py` | 3-A | 슬롯 병합 |
| `agents/query_analysis/extractors.py` | 3-B | 날짜 추출 |
| `agents/answer_generation/agent.py` | 3-B~E,4 | 핵심 수정 |
| `agents/answer_generation/tools/generator.py` | 3-B,4,5 | 프롬프트 |
| `supervisor/graph_mas.py` | 3-C | 캐시 주입 노드 |
| `supervisor/cache.py` | 3-C,E | 캐시 키 개선 |
| `supervisor/nodes/memory_save.py` | 3-C | retrieval 캐시 |
| `agents/retrieval/tools/retriever.py` | 3-D | 품목 필터 |
| `agents/query_analysis/detectors.py` | 4 | detail type 감지 |
| `agents/protocols.py` | 3,4 | TypedDict 확장 |
