# 팀장 가이드 - 통합/오케스트레이션 + 질의분석

> **역할**: 그래프 워크플로우, 상태 관리, 질의 분류, 전체 조율
> **최종 수정**: 2026-01-16

---

## 1. 역할 개요

팀장은 ddoksori 멀티에이전트 RAG 시스템의 **핵심 오케스트레이션**을 담당합니다.

### 주요 책임
- LangGraph 기반 워크플로우 설계 및 관리
- 상태(State) 스키마 정의 및 확장
- 도메인 분류 로직 고도화 (KCA/ECMC/KCDRC/FSS/K_MEDI/KOPICO)
- 라우팅 조건 및 엣지 관리
- 팀 코드 리뷰 및 통합 테스트 조율

---

## 2. 담당 파일 목록

| 파일명 | 경로 | 역할 | 우선순위 |
|--------|------|------|:--------:|
| `graph.py` | `backend/app/orchestrator/graph.py` | LangGraph StateGraph 정의, 노드 등록, 조건부 엣지 | ★★★ |
| `state.py` | `backend/app/orchestrator/state.py` | ChatState, QueryAnalysisResult 등 TypedDict 스키마 | ★★★ |
| `classifier.py` | `backend/app/domain/classifier.py` | DomainClassifier 클래스, 기관 분류 로직 | ★★★ |
| `config.py` | `backend/app/domain/config.py` | AGENCY_INFO, 키워드 상수 (FINANCE, MEDICAL 등) | ★★☆ |
| `query_analysis.py` | `backend/app/orchestrator/nodes/query_analysis.py` | 질의 분석 노드 (타입 분류, 키워드 추출) | ★★☆ |

---

## 3. 파일별 상세 설명

### 3.1 graph.py - 그래프 워크플로우

**위치**: `backend/app/orchestrator/graph.py`

**핵심 구조**:
```
[query_analysis]
    ↓ (조건 분기: needs_clarification)
    ├─→ [ask_clarification] → END
    └─→ [retrieval] → [generation] → [review]
                                        ↓ (조건 분기: passed)
                                        ├─→ [generation] (재생성)
                                        └─→ END
```

**주요 함수**:
| 함수 | 역할 |
|------|------|
| `create_chat_graph()` | StateGraph 생성, 노드/엣지 등록 |
| `get_compiled_graph()` | 싱글톤 컴파일된 그래프 반환 |
| `_route_after_query_analysis()` | needs_clarification 분기 |
| `_route_after_review()` | 재생성 필요 여부 판단 |

**수정 시 주의사항**:
- 새 노드 추가 시 `add_node()` 후 반드시 엣지 연결
- 조건부 엣지는 `add_conditional_edges()` 사용
- Checkpointer 설정은 환경변수로 분기 (memory/postgresql)

---

### 3.2 state.py - 상태 스키마

**위치**: `backend/app/orchestrator/state.py`

**핵심 TypedDict**:

```python
class ChatState(MessagesState):
    query_analysis: QueryAnalysisResult  # 질의 분석 결과
    retrieval: RetrievalResult           # 4섹션 검색 결과
    draft_answer: str                    # 초안 답변
    review: ReviewResult                 # 검토 결과
    final_answer: str                    # 최종 답변
    onboarding: OnboardingInfo           # 온보딩 폼 데이터
    retry_count: int                     # 재생성 횟수

class QueryAnalysisResult(TypedDict):
    query_type: str          # 'dispute', 'general', 'law', 'criteria'
    keywords: List[str]      # 검색용 키워드
    agency_hint: str         # 추천 기관 힌트
    needs_clarification: bool
    missing_fields: List[str]

class RetrievalResult(TypedDict):
    agency: dict             # 추천 기관 정보
    disputes: List[dict]     # 분쟁조정사례
    counsels: List[dict]     # 상담사례
    laws: List[dict]         # 관련 법령
    criteria: List[dict]     # 관련 기준
```

**수정 시 주의사항**:
- 새 필드 추가 시 Optional로 시작 (하위 호환성)
- reducer 패턴 필요 시 `Annotated` 사용

---

### 3.3 classifier.py - 도메인 분류기

**위치**: `backend/app/domain/classifier.py`

**분류 우선순위**:
1. **FSS** (금융감독원) - 보험, 투자, 대출 → `is_restricted=True`
2. **K_MEDI** (한국의료분쟁조정중재원) - 의료사고 → `is_restricted=True`
3. **KOPICO** (개인정보분쟁조정위원회) - 개인정보 유출 → `is_restricted=True`
4. **KCDRC** (콘텐츠분쟁조정위원회) - 게임, OTT, 영화
5. **ECMC** (전자거래분쟁조정위원회) - 중고거래, 개인간 거래
6. **KCA** (한국소비자원) - 기본값

**핵심 클래스**:
```python
class DomainClassifier:
    def classify(self, query: str) -> ClassificationResult
    def _match_keywords(self, query: str, keywords: List[str]) -> int

class ClassificationResult:
    agency: str           # 'KCA', 'ECMC', 'KCDRC', 'FSS', 'K_MEDI', 'KOPICO'
    reason: str           # 분류 근거
    confidence: float     # 신뢰도 (0.0 ~ 1.0)
    is_restricted: bool   # 전문가 상담 권유 여부
```

**수정 시 주의사항**:
- 새 기관 추가 시 `config.py`의 `AGENCY_INFO`도 함께 수정
- 키워드 우선순위 조정 시 테스트 필수

---

### 3.4 config.py - 기관 및 키워드 상수

**위치**: `backend/app/domain/config.py`

**주요 상수**:
```python
AGENCY_INFO = {
    'KCA': {'name': '한국소비자원', 'url': '...', 'phone': '1372'},
    'ECMC': {'name': '전자거래분쟁조정위원회', ...},
    'KCDRC': {'name': '콘텐츠분쟁조정위원회', ...},
    'FSS': {'name': '금융감독원', ...},
    'K_MEDI': {'name': '한국의료분쟁조정중재원', ...},
    'KOPICO': {'name': '개인정보분쟁조정위원회', ...},
}

# 키워드 상수
CONTENT_KEYWORDS = ['게임', '영화', 'OTT', '음원', '웹툰', ...]
INDIVIDUAL_KEYWORDS = ['중고', '당근마켓', '번개장터', '직거래', ...]
FINANCE_KEYWORDS = ['보험', '투자', '대출', '카드', '펀드', ...]
MEDICAL_KEYWORDS = ['수술', '진료', '의료사고', '병원', ...]
PRIVACY_KEYWORDS = ['개인정보', '유출', '해킹', '동의', ...]
```

---

### 3.5 query_analysis.py - 질의 분석 노드

**위치**: `backend/app/orchestrator/nodes/query_analysis.py`

**주요 함수**:
| 함수 | 역할 |
|------|------|
| `query_analysis_node(state)` | 메인 노드 함수 |
| `_classify_query_type()` | dispute/general/law/criteria 분류 |
| `_extract_keywords()` | 검색용 키워드 추출 (불용어 제거) |
| `_determine_agency_hint()` | DomainClassifier 호출 |
| `_check_missing_onboarding_fields()` | 누락 필드 확인 |

**분류 기준**:
- `dispute`: 분쟁, 환불, 피해, 보상 등 키워드 포함
- `general`: 인사말, 단순 질문
- `law`: 법령 조회 요청
- `criteria`: 기준 조회 요청

---

## 4. 테스트 스크립트

### 4.1 State 테스트
```bash
conda activate dsr
pytest backend/scripts/testing/orchestrator/test_pr1_state.py -v
```

**테스트 항목**:
- ChatState 초기화 (general/dispute)
- OnboardingInfo 필드 검증
- Checkpointer 메모리/PostgreSQL 선택
- MultiTurn 세션 테스트

### 4.2 Graph 테스트
```bash
pytest backend/scripts/testing/orchestrator/test_pr3_graph.py -v
```

**테스트 항목**:
- 그래프 노드 존재 여부 (5개)
- 라우팅 함수 동작 검증
- 싱글톤 패턴 검증
- 멀티턴 세션 독립성

### 4.3 도메인 분류 테스트
```bash
pytest backend/scripts/testing/domain/test_domain_classification.py -v
```

**테스트 항목**:
- Golden Set 62개 기반 정확도 측정
- FSS(금융) 특화 테스트 (12개)
- K_MEDI(의료) 특화 테스트 (12개)
- KOPICO(개인정보) 특화 테스트 (12개)
- KCA(일반) 분류 테스트 (12개)

### 4.4 노드 단위 테스트
```bash
pytest backend/scripts/testing/orchestrator/test_pr2_nodes.py::TestQueryAnalysisNode -v
```

**테스트 항목**:
- dispute 질의 분류
- general 질의 분류
- 누락 필드 탐지
- 기관 힌트 결정

---

## 5. 평가 스크립트

### 5.1 Query Analysis 평가
```bash
cd backend
python -m scripts.evaluation.evaluate_query_analysis \
  --golden-set ./data/golden_set/query_analysis.jsonl \
  --output ./results/qa_eval.json
```

**평가 지표**:
| 지표 | 목표 | 설명 |
|------|------|------|
| Query Type Accuracy | ≥ 0.90 | dispute/general/law/criteria 분류 정확도 |
| Agency Hint Accuracy | ≥ 0.85 | 기관 추천 정확도 |

### 5.2 Golden Set 위치
- 도메인 분류: `backend/scripts/testing/domain/golden_set.py` (62개 샘플)
- Query Analysis: `backend/data/golden_set/query_analysis.jsonl`

---

## 6. 완료 기준

| 지표 | 목표값 | 확인 방법 |
|------|--------|----------|
| Query Type Accuracy | ≥ 0.90 | `evaluate_query_analysis.py` 실행 |
| 도메인 분류 정확도 | ≥ 80% | `test_domain_classification.py` 통과 |
| State 테스트 | 100% | `test_pr1_state.py` 통과 |
| Graph 테스트 | 100% | `test_pr3_graph.py` 통과 |

---

## 7. 주차별 작업

### 1주차
- [ ] 아키텍처 설계 검토
- [ ] 인터페이스 정의 (State 스키마 확정)
- [ ] 통합 스크립트 작성
- [ ] 품질 리포트 통합

### 2주차
- [ ] 도메인 분류 고도화 (KOPICO 추가 완료)
- [ ] 라우팅 로직 강화
- [ ] 상태 스키마 최적화
- [ ] 팀 코드 리뷰

### 3주차
- [ ] E2E 테스트 시나리오 실행
- [ ] 버그 수정 조율
- [ ] 최종 통합
- [ ] 데모 준비

---

## 8. 참고 문서

| 문서 | 경로 | 설명 |
|------|------|------|
| 프로젝트 계획서 | `/plans/plans.md` | 전체 3주 계획 |
| RAG 아키텍처 | `/docs/guides/system_architecture.md` | 시스템 구조 |
| 도메인 분류 확장 | `/docs/guides/2026-01-15_domain_classification_expansion.md` | KOPICO 추가 |
| AGENTS.md | `/AGENTS.md` | AI 코딩 에이전트 가이드 |

---

## 9. 자주 사용하는 명령어 모음

```bash
# 환경 활성화
conda activate dsr

# 전체 오케스트레이터 테스트
pytest backend/scripts/testing/orchestrator/ -v

# 도메인 테스트만
pytest backend/scripts/testing/domain/ -v

# 특정 테스트 클래스만
pytest backend/scripts/testing/orchestrator/test_pr1_state.py::TestChatState -v

# 상세 로그 출력
pytest backend/scripts/testing/orchestrator/ -vv -s

# 전체 테스트 (API, 통합, 데이터)
./backend/run_local_rag_tests.sh all
```

---

*이 문서는 팀장이 독립적으로 작업할 수 있도록 구성되었습니다.*
