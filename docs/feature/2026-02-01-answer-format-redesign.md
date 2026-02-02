# 답변 양식 재설계 (Answer Format Redesign)

**작성일**: 2026-02-01
**버전**: v1.0
**상태**: 구현 완료

## 1. 개요

DDOKSORI 챗봇의 AnswerDrafter 답변 생성 시스템을 재설계하여 질문 유형별로 최적화된 응답 구조를 제공합니다.

### 주요 변경사항

- **기존 3-format 체계**(`full_dispute`/`simple_general`/`info_only`)를 **7-format 체계**로 확장
- 질문 유형별(법령/기준/사례/종합분쟁/일반) 구조화된 응답 생성
- 인사 및 일반 대화에서 분쟁 상담으로 자연스럽게 유도하는 followup 질문 추가
- legacy(전체 응답) 및 minimal(요약→상세) 모드 모두 지원
- 하위 호환성 보장: `answer_format_mode = "fixed"` 시 기존 동작 유지

### 설계 목표

1. **컨텍스트 적합성**: 검색 결과 구성(법령만, 기준만, 혼합 등)에 따라 최적 format 자동 선택
2. **사용자 경험 개선**: 일반 대화 → 분쟁 상담으로 자연스러운 전환
3. **구조화된 응답**: 질문 유형별 일관된 답변 템플릿
4. **확장성**: 새 format 추가 시 기존 코드 변경 최소화

---

## 2. 변경 사항

### 2.1 수정 파일 목록

총 9개 파일 수정 (경로: `backend/app/agents/answer_generation/`)

| 파일 | 변경 수준 | 핵심 변경 내용 |
|-----|----------|--------------|
| `formats/config.py` | Major | 3→7개 format 정의, `closing_prompt` 필드 추가 |
| `formats/selector.py` | Major | `FormatSelector` 클래스 구현, `onboarding` 파라미터 추가, 8단계 우선순위 매칭 로직 |
| `formats/prompt_builder.py` | Major | `PromptBuilder` 클래스 구현, 7개 format별 system/user prompt 빌더 |
| `formats/__init__.py` | Minor | `FormatSelector`, `PromptBuilder` export 추가 |
| `followup/templates.py` | Medium | `FORMAT_GUIDED_TEMPLATES` 6개 분쟁 유도 템플릿 추가 |
| `followup/generator.py` | Medium | `format_id` 기반 템플릿 필터링 로직 추가 |
| `fallback.py` | Medium | `system_prompt`/`user_prompt` 파라미터 패스스루 |
| `tools/generator.py` | Medium | 외부 프롬프트 우선 사용 로직 추가 |
| `agent.py` | Medium | `FormatSelector` 호출 및 followup 통합 |

### 2.2 새로운 7개 응답 Format

| format_id | 트리거 조건 | 출력 구조 | closing_prompt |
|-----------|-----------|----------|----------------|
| `law_response` | query_type=law, 온보딩 없음 | 법령 계층 구조 → 요약 | "더 자세한 정보를 원하시나요?" |
| `law_onboarding` | query_type=law/dispute + 온보딩 + has_laws | 상황 요약 → 적용 법령 → 근거 | - |
| `criteria_response` | query_type=criteria | 품질보증기간 → 교환/환불 기준 → 주의사항 | - |
| `case_response` | query_type=dispute, 사례만 있을 때 | 조정사례 3건 + 상담사례 2건 → 시사점 | - |
| `comprehensive_dispute` | query_type=dispute + 온보딩 + (법령 or 기준) | 법령 → 기준 → 다음 단계 | "유사한 사례에 대해 궁금하신가요?" |
| `general_greeting` | query_type=general/system_meta/meta_conversational | 자연스러운 대화 + 분쟁 유도 | (프롬프트에서 처리) |
| `info_only` | query_type=restricted | 전문 기관 안내 | - |

#### Format별 상세 설명

**1. law_response** (법령 질문)
- 사용자가 법령 정보만 요청한 경우
- 조문 계층 구조(법 → 조 → 항 → 호) 제시
- 핵심 내용 요약 및 추가 질문 유도

**2. law_onboarding** (온보딩 후 법령 적용)
- 사용자가 구체적 상황을 제공한 경우
- 상황 요약 → 적용 가능한 법령 → 법적 근거 순서로 제시
- 실제 분쟁 해결에 바로 활용 가능한 형식

**3. criteria_response** (품목별 기준)
- 특정 품목의 품질보증기준 조회
- 품질보증기간 → 교환/환불 기준 → 주의사항 구조화
- 표 형식으로 가독성 향상

**4. case_response** (사례 중심 답변)
- 법령/기준 없이 사례만 검색된 경우
- 조정사례 최대 3건 + 상담사례 최대 2건 제시
- 각 사례의 시사점 요약

**5. comprehensive_dispute** (종합 분쟁 상담)
- 온보딩 데이터 + 법령/기준이 모두 있는 경우
- 적용 법령 → 품목별 기준 → 권장 조치 → 다음 단계 안내
- 가장 완전한 형태의 답변

**6. general_greeting** (일반 대화)
- 인사, 감사, 잡담 등 분쟁과 무관한 질문
- 자연스러운 응답 + 분쟁 상담 유도 질문
- 사용자를 핵심 기능으로 부드럽게 안내

**7. info_only** (제한 도메인)
- 금융, 의료 등 전문 기관 안내가 필요한 영역
- 관련 전문 기관 연락처 및 안내 정보 제공

### 2.3 Format 선택 우선순위

`FormatSelector.select_format()` 메서드는 다음 8단계 우선순위로 format을 결정합니다:

```python
1. general/system_meta/meta_conversational → general_greeting
2. restricted → info_only
3. law + 온보딩 + has_laws → law_onboarding
4. law → law_response
5. criteria → criteria_response
6. dispute + 온보딩 + (has_laws OR has_criteria) → comprehensive_dispute
7. dispute + has_cases + NOT has_laws + NOT has_criteria → case_response
8. fallback → comprehensive_dispute
```

**우선순위 설계 원칙**:
- 일반 대화와 제한 도메인을 최우선 처리
- 온보딩 데이터가 있으면 상황별 맞춤 format 우선
- 검색 결과 구성(has_laws, has_criteria, has_cases)에 따라 적합한 format 선택
- 모든 조건에 해당하지 않으면 가장 포괄적인 `comprehensive_dispute` 적용

### 2.4 분쟁 유도 Followup 템플릿

일반 대화에서 분쟁 상담으로 자연스럽게 전환하기 위한 6개 템플릿 추가 (`followup/templates.py`):

| template_id | 질문 예시 | 적용 format |
|-------------|---------|-------------|
| `guide_to_dispute` | "혹시 제품이나 서비스 관련 불편한 경험이 있으셨나요?" | general_greeting |
| `guide_onboarding` | "어떤 제품에서 문제가 발생했나요? 구매 시기와 증상을 알려주시면 더 정확한 안내가 가능합니다." | general_greeting |
| `ask_similar_cases` | "유사한 사례에 대해 궁금하신가요?" | comprehensive_dispute |
| `ask_law_detail` | "더 자세한 정보를 원하시나요?" | law_response |
| `ask_situation_apply` | "본인 상황에 이 법령이 어떻게 적용되는지 알려드릴까요?" | law_response |
| `ask_criteria_cases` | "이 기준이 적용된 실제 사례가 궁금하신가요?" | criteria_response |

**필터링 로직**: `FollowupQuestionGenerator`는 `format_id` 파라미터를 받아 해당 format에 적합한 템플릿만 선택합니다.

---

## 3. 사용 방법

### 3.1 활성화 방법

`backend/.env` 또는 config에서 다음 환경변수 설정:

```bash
# 새 7-format 시스템 활성화
ANSWER_FORMAT_MODE=flexible

# 기존 3-format 시스템 유지 (기본값)
ANSWER_FORMAT_MODE=fixed
```

- **`flexible`**: 새로운 7-format 시스템 활성화 (권장)
- **`fixed`**: 기존 3-format 동작 유지 (하위 호환성)

### 3.2 예시 시나리오

#### 시나리오 1: 법령 질문

```
User: "소비자 기본법 관련해서 알려줘"

→ QueryAnalyst: query_type = law
→ RetrievalTeam: LawRetrievalAgent만 실행
→ FormatSelector: law_response 선택
→ 출력:
  [법령 구조]
  소비자기본법 제16조 (소비자의 권리와 역할)
  - 제1항: 물품 등을 사용함에 있어서 거래상대방, 이웃 또는 환경에 대하여 ...
  - 제2항: ...

  [요약]
  소비자기본법은 소비자의 8가지 기본 권리를 명시하고 있으며, ...

→ Followup: "더 자세한 정보를 원하시나요?"
```

#### 시나리오 2: 온보딩 후 종합 분쟁

```
User: "온라인으로 구매한 노트북이 불량인데 환불 받고 싶어요"
     (온보딩 데이터: product_name="노트북", issue_type="불량", purchase_date="2개월 전")

→ QueryAnalyst: query_type = dispute
→ RetrievalTeam: LawRetrievalAgent + CriteriaRetrievalAgent + CaseRetrievalAgent
→ FormatSelector: comprehensive_dispute 선택
→ 출력:
  [적용 법령]
  1. 전자상거래법 제17조 (청약철회 등)
  2. 소비자기본법 제16조 ...

  [품목별 기준]
  ■ 노트북 (전자제품)
  - 품질보증기간: 1년
  - 교환 가능 조건: 구입 후 10일 이내 정상적인 사용 상태에서 ...

  [다음 단계]
  1. 판매자에게 환불 요청 (전자상거래법 제17조 근거)
  2. 거부 시 한국소비자원 1372 상담

→ Followup: "유사한 사례에 대해 궁금하신가요?"

User: "네"
→ FOLLOWUP_WITH_CONTEXT → case_response format으로 사례 제공
→ 출력:
  [조정사례 1] 노트북 화면 불량 - 전액 환불 결정
  [조정사례 2] 노트북 배터리 결함 - 제조사 수리 권고
  ...
```

#### 시나리오 3: 일반 대화 → 분쟁 유도

```
User: "안녕하세요"

→ QueryAnalyst: query_type = general
→ FormatSelector: general_greeting 선택
→ 출력:
  안녕하세요! 똑소리 AI 상담사입니다.
  소비자 분쟁 해결을 도와드리고 있어요.

→ Followup: "혹시 제품이나 서비스 관련 불편한 경험이 있으셨나요?"

User: "네, 환불 문제가 있어요"
→ 후속 질문: "어떤 제품에서 문제가 발생했나요? 구매 시기와 증상을 알려주시면 ..."
```

#### 시나리오 4: 기준 질문

```
User: "노트북의 경우 어떤 기준에 적합한지 알려줘"

→ QueryAnalyst: query_type = criteria
→ RetrievalTeam: CriteriaRetrievalAgent만 실행
→ FormatSelector: criteria_response 선택
→ 출력:
  [품질보증기간]
  노트북(전자제품): 1년

  [교환/환불 기준]
  1. 구입 후 10일 이내: 정상 사용 중 성능/기능상 하자 발견 시 교환
  2. 품질보증기간 내: 수리 불가능 시 동일 제품으로 교환
  3. 교환 불가 시: 구입가 환급

  [주의사항]
  - 소비자 과실로 인한 고장은 제외
  - 외관 손상이 있는 경우 제한적 적용

→ Followup: "이 기준이 적용된 실제 사례가 궁금하신가요?"
```

---

## 4. 아키텍처

### 4.1 전체 흐름도

```
generation_node_v2() (backend/app/supervisor/nodes/answer_generation_v2.py)
│
├─ 1. answer_format_mode 확인
│   ├─ 'flexible' → 새 시스템 진입
│   └─ 'fixed' → 기존 로직 유지
│
├─ 2. FormatSelector.select_format(query_analysis, retrieval, onboarding)
│   ├─ 입력: query_type, 검색 결과 구성, 온보딩 데이터 유무
│   └─ 출력: format_id (7개 중 1개)
│
├─ 3. PromptBuilder.build_system_prompt(format)
│   └─ format별 system prompt 생성
│
├─ 4. PromptBuilder.build_user_prompt(format, context, query, ...)
│   └─ format별 user prompt 생성
│
├─ 5. AnswerGenerationFallback.generate_with_fallback(
│       ..., system_prompt=..., user_prompt=...)
│   │
│   └─ RAGGenerator.generate_structured_answer(
│       ..., system_prompt=..., user_prompt=...)
│       │
│       ├─ 외부 prompt 있으면 우선 사용
│       └─ 없으면 기존 방식 (format_type 기반)
│
└─ 6. FollowupQuestionGenerator.generate_questions(
       ..., format_id=selected_format_id)
    │
    └─ format_id에 적합한 템플릿만 필터링하여 후속 질문 생성
```

### 4.2 클래스 다이어그램

```
FormatSelector
├─ select_format(query_analysis, retrieval, onboarding) → AnswerFormat
└─ 8단계 우선순위 매칭 로직

PromptBuilder
├─ build_system_prompt(format) → str
├─ build_user_prompt(format, context, query, ...) → str
└─ 7개 format별 빌더 메서드

AnswerFormat (dataclass)
├─ format_id: str
├─ description: str
├─ closing_prompt: Optional[str]  # 추가된 필드
└─ trigger_conditions: List[str]

FollowupTemplate (dataclass)
├─ template_id: str
├─ question: str
├─ category: str
├─ target_formats: List[str]  # 적용 가능한 format_id 목록
└─ priority: int
```

### 4.3 파일 구조

```
backend/app/agents/answer_generation/
├── formats/
│   ├── __init__.py          # FormatSelector, PromptBuilder export
│   ├── config.py            # 7개 ANSWER_FORMATS 정의
│   ├── selector.py          # FormatSelector 클래스
│   └── prompt_builder.py    # PromptBuilder 클래스
├── followup/
│   ├── templates.py         # FORMAT_GUIDED_TEMPLATES 추가
│   └── generator.py         # format_id 기반 필터링
├── tools/
│   └── generator.py         # 외부 prompt 우선 사용 로직
├── agent.py                 # FormatSelector 호출 통합
└── fallback.py              # system/user prompt 패스스루
```

---

## 5. 하위 호환성

새로운 시스템은 **완전한 하위 호환성**을 보장합니다:

### 5.1 기존 동작 보존

- `answer_format_mode = "fixed"` 설정 시 기존 3-format 동작 100% 보존
- `generation_node()` (v1) 미변경 - 기존 호출 코드 영향 없음
- 스트리밍, claim-evidence mapping, citation 시스템 미변경
- `retry_context` (LegalReviewer 재생성 요청) 동일 동작

### 5.2 선택적 파라미터

모든 새로운 파라미터는 `Optional` 타입으로 기본값 제공:

```python
def select_format(
    query_analysis: Dict[str, Any],
    retrieval: Dict[str, Any],
    onboarding: Optional[Dict[str, Any]] = None  # 기본값 None
) -> AnswerFormat:
    ...

def generate_with_fallback(
    ...,
    system_prompt: Optional[str] = None,  # 기본값 None
    user_prompt: Optional[str] = None     # 기본값 None
) -> Dict[str, Any]:
    ...
```

기존 호출 코드는 새 파라미터 없이도 정상 동작합니다.

### 5.3 점진적 마이그레이션

```
Phase 1 (현재): answer_format_mode = "fixed" (기본값)
  → 모든 시스템 기존 방식 동작
  → 새 코드는 호출되지 않음

Phase 2 (테스트): answer_format_mode = "flexible" (개발/스테이징)
  → 새 format 시스템 활성화
  → 프로덕션은 여전히 "fixed"

Phase 3 (배포): answer_format_mode = "flexible" (프로덕션)
  → 충분한 테스트 후 프로덕션 적용
  → 문제 발생 시 "fixed"로 즉시 롤백 가능
```

---

## 6. 테스트

### 6.1 단위 테스트

```bash
# FormatSelector 테스트
conda run -n dsr pytest backend/scripts/testing/agents/answer_generation/test_format_selector.py

# PromptBuilder 테스트
conda run -n dsr pytest backend/scripts/testing/agents/answer_generation/test_prompt_builder.py

# Followup 템플릿 필터링 테스트
conda run -n dsr pytest backend/scripts/testing/agents/answer_generation/test_followup_generator.py
```

### 6.2 통합 테스트

```bash
# 전체 generation_node_v2 테스트
conda run -n dsr pytest backend/scripts/testing/supervisor/test_generation_node_v2.py

# 7개 format 시나리오 테스트
conda run -n dsr pytest backend/scripts/testing/e2e/test_answer_formats.py
```

### 6.3 수동 테스트 시나리오

1. **법령 질문**: "소비자기본법 알려줘"
2. **온보딩 후 분쟁**: "2개월 전에 산 냉장고가 고장났어요" (온보딩 데이터 포함)
3. **기준 질문**: "냉장고 품질보증기준 알려줘"
4. **사례 질문**: "냉장고 환불 사례 알려줘"
5. **일반 대화**: "안녕하세요" → 분쟁 유도 확인
6. **제한 도메인**: "신용카드 분쟁 상담해줘" → 금융위원회 안내 확인

---

## 7. 관련 문서

- **설계 문서**: [`docs/plans/2026-02-01-answer-quality-improvement.md`](../plans/2026-02-01-answer-quality-improvement.md)
- **구현 계획**: [`.omc/plans/eager-tinkering-hejlsberg.md`](../../.omc/plans/eager-tinkering-hejlsberg.md)
- **Backend README**: [`backend/README.md`](../../backend/README.md)
- **Answer Generation README**: [`backend/app/agents/answer_generation/README.md`](../../backend/app/agents/answer_generation/README.md)

---

## 8. 향후 확장 가능성

### 8.1 새 Format 추가

`formats/config.py`에 새 `AnswerFormat` 추가 후, `selector.py`와 `prompt_builder.py`에 로직만 추가하면 됩니다:

```python
# formats/config.py
ANSWER_FORMATS["new_format"] = AnswerFormat(
    format_id="new_format",
    description="새 형식 설명",
    closing_prompt="마무리 멘트",
    trigger_conditions=["조건1", "조건2"]
)

# formats/selector.py
def select_format(...):
    ...
    if <new_format 조건>:
        return ANSWER_FORMATS["new_format"]
    ...

# formats/prompt_builder.py
def build_user_prompt(self, format: AnswerFormat, ...):
    ...
    elif format.format_id == "new_format":
        return self._build_new_format_prompt(...)
    ...
```

### 8.2 A/B 테스트 지원

환경변수를 확장하여 format별 활성화 제어:

```bash
ANSWER_FORMAT_MODE=flexible
ENABLE_FORMATS=law_response,criteria_response,general_greeting
```

### 8.3 다국어 지원

`PromptBuilder`에서 언어별 템플릿 분리:

```python
def build_system_prompt(self, format: AnswerFormat, language: str = "ko") -> str:
    if language == "ko":
        return self._build_ko_prompt(format)
    elif language == "en":
        return self._build_en_prompt(format)
    ...
```

---

## 변경 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v1.0 | 2026-02-01 | 초안 작성 (7-format 시스템 구현 완료) |
