# 추가 질문(Followup) 기능 개선 구현 계획

## 목차
1. [개요](#개요)
2. [현재 시스템 분석](#현재-시스템-분석)
3. [PR #1: 추가 질문 버블 클릭 비활성화](#pr-1-추가-질문-버블-클릭-비활성화)
4. [PR #2: 프롬프트 파일에서 추가 질문 동적 추출](#pr-2-프롬프트-파일에서-추가-질문-동적-추출)
5. [PR #3: 추가 질문 응답 가능성 검토 (후속)](#pr-3-추가-질문-응답-가능성-검토-후속)

---

## 개요

### 요구사항 요약
1. **버블 클릭 비활성화**: 추가 질문 버블을 시각적으로 표시하되, 클릭 이벤트를 제거
2. **동적 추출**: 프롬프트 파일의 "버튼형 역질문" 섹션에서 추가 질문을 파싱하여 동적으로 제공
3. **응답 검토**: 모든 추가 질문에 대해 시스템 응답 가능 여부 검토 (별도 PR)

### 영향 범위
| 영역 | 파일 | 변경 유형 |
|------|------|----------|
| Frontend | `FollowupChips.tsx` | 수정 (클릭 비활성화) |
| Frontend | `MessageBubble.tsx` | 수정 (onSelect prop 제거 가능) |
| Backend | `template_loader.py` | 수정 (역질문 파싱 추가) |
| Backend | `generator.py` | 수정 (동적 질문 로딩) |
| Backend | `templates.py` | 수정 (템플릿 매핑 추가) |

---

## 현재 시스템 분석

### Frontend 구조

#### FollowupChips.tsx (현재)
```tsx
interface FollowupChipsProps {
  questions: string[];
  onSelect: (question: string) => void;  // 클릭 핸들러
}

export function FollowupChips({ questions, onSelect }: FollowupChipsProps) {
  return (
    <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-gray-200/50">
      {questions.slice(0, 3).map((question) => (
        <button
          key={question}
          onClick={() => onSelect(question)}  // 클릭 시 질문 전송
          className="px-3 py-1.5 text-sm bg-lavender/20 hover:bg-lavender/40 ... cursor-pointer"
        >
          {question}
        </button>
      ))}
    </div>
  );
}
```

#### MessageBubble.tsx (사용처)
```tsx
{message.followupQuestions && message.followupQuestions.length > 0 && onFollowupSelect && (
  <FollowupChips
    questions={message.followupQuestions}
    onSelect={onFollowupSelect}  // handleDisputeFollowupSelect 전달
  />
)}
```

#### ChatPage.tsx (핸들러)
```tsx
const handleDisputeFollowupSelect = useCallback(async (question: string) => {
  await sendDisputeMessage(question);  // 클릭 시 해당 질문을 메시지로 전송
}, [sendDisputeMessage]);
```

### Backend 구조

#### 프롬프트 파일 구조 (예: solution_template.md)
```markdown
{base_persona}

---

## ⚙️ 실행 지시 (Instruction)
...

## 🔘 버튼형 역질문 (반드시 3개 생성)
위 답변 내용을 더 쉽게 풀어서 설명해 주세요
상대방에게 보낼 메시지 초안을 작성해 줄 수 있나요?
해당 업체가 계속 거부할 경우 다음 단계는 무엇인가요?
```

#### 템플릿별 역질문 현황

| 템플릿 키 | 파일명 | 역질문 유형 |
|-----------|--------|-------------|
| `solution` | solution_template.md | 고정 3개 |
| `action` | action_guide_template.md | 고정 3개 |
| `execution` | execution_guide_template.md | 고정 3개 |
| `inquiry` | inquiry_template.md | 동적 생성 (5개 중 3개 선택) |
| `fallback` | fallback_template.md | 고정 3개 |
| `reject` | reject_template.md | 조건부 (데이터 연동) |

#### generator.py (현재 로직)
```python
def _generate_followup_questions(self, context: Dict) -> List[str]:
    # 0. 상황별 템플릿 우선 적용 (fallback, 기준만, 품목만)
    context_based = self._select_questions_by_context(context)
    if context_based:
        return context_based

    # 1. 분쟁 유형에 맞는 템플릿 필터링
    candidate_templates = get_templates_by_dispute_type(dispute_type)
    
    # 2. followup 타입만 필터링
    # 3. format_id 기반 우선 필터링
    # 4. 조건 매칭
    # 5. 우선순위 정렬
    # 6. 최대 개수 제한
```

#### templates.py (현재 구조)
- `REFUND_TEMPLATES`, `EXCHANGE_TEMPLATES` 등 분쟁 유형별 하드코딩
- `FORMAT_GUIDED_TEMPLATES` - format_id별 유도 질문
- `CLARIFYING_TEMPLATES` - 정보 부족 시 질문

---

## PR #1: 추가 질문 버블 클릭 비활성화

### 개요
- **목적**: 추가 질문 버블을 읽기 전용으로 변경 (시각적 표시만, 클릭 불가)
- **브랜치**: `fix/followup-disable-click`
- **라벨**: `type:bug` (기능 제한으로 인한 수정)

### 수정 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `frontend/src/features/chat/components/FollowupChips.tsx` | button -> span, 클릭 이벤트 제거, 스타일 수정 |

### 상세 변경 내용

#### 1. FollowupChips.tsx

**파일 경로**: `/home/maroco/LLM/frontend/src/features/chat/components/FollowupChips.tsx`

```diff
- interface FollowupChipsProps {
-   questions: string[];
-   onSelect: (question: string) => void;
- }
+ interface FollowupChipsProps {
+   questions: string[];
+ }

- export function FollowupChips({ questions, onSelect }: FollowupChipsProps) {
+ export function FollowupChips({ questions }: FollowupChipsProps) {
    if (!questions || questions.length === 0) return null;

    return (
      <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-gray-200/50">
        {questions.slice(0, 3).map((question) => (
-         <button
+         <span
            key={question}
-           onClick={() => onSelect(question)}
            className="
              px-3 py-1.5 text-sm
              bg-lavender/20
-             hover:bg-lavender/40
              text-deep-teal
              rounded-full
              border border-lavender/50
-             transition-colors duration-200
-             cursor-pointer
+             select-none
              text-left
            "
          >
            {question}
-         </button>
+         </span>
        ))}
      </div>
    );
  }
```

**변경 요약**:
- DELETE: `onSelect` prop 및 관련 인터페이스
- DELETE: `onClick` 핸들러
- DELETE: `hover:bg-lavender/40`, `transition-colors`, `cursor-pointer` 클래스
- KEEP: 기본 스타일 (배경, 테두리, 색상)
- INSERT: `select-none` 클래스 (텍스트 선택 방지)
- CHANGE: `<button>` -> `<span>` 태그

### 테스트 명령어

```bash
# Frontend 빌드 확인
cd /home/maroco/LLM/frontend && npm run build

# TypeScript 타입 체크
cd /home/maroco/LLM/frontend && npm run lint

# 개발 서버에서 시각적 확인
cd /home/maroco/LLM/frontend && npm run dev
```

### 성공 기준

1. **빌드 성공**: `npm run build` 오류 없이 완료
2. **타입 체크**: TypeScript 오류 없음
3. **시각적 확인**:
   - 추가 질문 버블이 기존과 동일하게 표시됨
   - 마우스 호버 시 커서가 포인터로 변경되지 않음
   - 클릭해도 아무 동작 없음
4. **회귀 테스트**: 메시지 버블 렌더링 정상 동작

---

## PR #2: 프롬프트 파일에서 추가 질문 동적 추출

### 개요
- **목적**: 하드코딩된 템플릿 대신 프롬프트 파일에서 역질문을 파싱하여 동적으로 제공
- **브랜치**: `feat/followup-dynamic-extraction`
- **라벨**: `type:feature`

### 수정 파일 목록

| 파일 | 변경 내용 |
|------|----------|
| `backend/app/agents/answer_generation/template_loader.py` | 역질문 파싱 기능 추가 |
| `backend/app/agents/followup/generator.py` | 동적 질문 로딩 로직 추가 |
| `backend/app/agents/followup/templates.py` | 템플릿-프롬프트 매핑 추가 |
| `backend/app/agents/answer_generation/agent.py` | template_key 전달 |

### 상세 변경 내용

#### 1. template_loader.py

**파일 경로**: `/home/maroco/LLM/backend/app/agents/answer_generation/template_loader.py`

```python
# === 추가할 import (파일 상단) ===
from typing import Dict, List, Optional

# === 추가할 상수 (기존 상수 아래) ===
# 역질문 섹션 헤더 패턴
_FOLLOWUP_SECTION_PATTERN = re.compile(
    r"##\s*🔘\s*버튼형\s*역질문.*?\n(.*?)(?=\n##|\Z)",
    re.DOTALL
)

# === TemplateLoader 클래스 내부에 추가할 메서드 ===
class TemplateLoader:
    # ... 기존 코드 유지 ...

    def get_followup_questions(self, template_key: str) -> List[str]:
        """
        프롬프트 파일에서 '버튼형 역질문' 섹션을 파싱하여 질문 목록을 반환합니다.

        Args:
            template_key: 템플릿 키 (solution, action, execution, fallback, reject, inquiry)

        Returns:
            역질문 목록 (최대 3개). 파싱 실패 시 빈 리스트.
        """
        if self._templates is None:
            logger.error("Templates not loaded")
            return []

        raw_template = self._templates.get(template_key, "")
        if not raw_template:
            logger.warning(f"Template '{template_key}' not found")
            return []

        # 역질문 섹션 추출
        match = _FOLLOWUP_SECTION_PATTERN.search(raw_template)
        if not match:
            logger.debug(f"No followup section found in template '{template_key}'")
            return []

        section_content = match.group(1).strip()
        
        # inquiry 템플릿의 경우 동적 생성 지시가 있으므로 빈 리스트 반환
        if template_key == "inquiry":
            logger.debug("Inquiry template uses dynamic generation")
            return []

        # 각 줄을 질문으로 파싱 (빈 줄, 주석, 괄호로 시작하는 줄 제외)
        questions = []
        for line in section_content.split("\n"):
            line = line.strip()
            if line and not line.startswith("(") and not line.startswith("#"):
                questions.append(line)

        return questions[:3]  # 최대 3개
```

**변경 요약**:
- INSERT: `List` import 추가
- INSERT: `_FOLLOWUP_SECTION_PATTERN` 정규식 상수
- INSERT: `get_followup_questions()` 메서드
- KEEP: 기존 모든 코드

#### 2. generator.py

**파일 경로**: `/home/maroco/LLM/backend/app/agents/followup/generator.py`

```python
# === 수정할 import 섹션 (라인 17-22) ===
from typing import Dict, List, Optional

from .templates import (
    QuestionTemplate,
    get_templates_by_dispute_type,
    TEMPLATE_KEY_TO_PROMPT_KEY,  # 새로 추가
)


# === FollowupQuestionGenerator 클래스 수정 ===
class FollowupQuestionGenerator:
    """후속 질문 생성기"""

    def __init__(
        self, max_followup_questions: int = 3, max_clarifying_questions: int = 2
    ):
        self.max_followup_questions = max_followup_questions
        self.max_clarifying_questions = max_clarifying_questions
        self._template_loader = None  # Lazy loading 추가

    # === 새로 추가할 property ===
    @property
    def template_loader(self):
        """TemplateLoader 인스턴스를 lazy loading으로 가져옵니다."""
        if self._template_loader is None:
            from ..answer_generation.template_loader import TemplateLoader
            self._template_loader = TemplateLoader()
        return self._template_loader

    # === generate_questions 메서드 수정 (라인 44-101) ===
    def generate_questions(
        self,
        query_analysis: Dict,
        retrieval: Dict,
        answer: str,
        format_id: Optional[str] = None,
        is_fallback: bool = False,
        template_key: Optional[str] = None,  # 새 파라미터 추가
    ) -> Dict[str, List[str]]:
        """
        후속 질문과 명확화 질문을 생성합니다.

        Args:
            query_analysis: 쿼리 분석 결과
            retrieval: 검색 결과
            answer: 생성된 답변
            format_id: 답변 형식 식별자
            is_fallback: Fallback 여부
            template_key: 사용된 템플릿 키 (solution, action, execution 등)

        Returns:
            {'followup_questions': [...], 'clarifying_questions': [...]}
        """
        # 1. 컨텍스트 구축
        context = self._build_context(
            query_analysis, retrieval, answer, format_id, is_fallback
        )

        # 2. 후속 질문 생성 (template_key 전달)
        followup_questions = self._generate_followup_questions(context, template_key)

        # 3. 명확화 질문 생성
        clarifying_questions = self._generate_clarifying_questions(context)

        return {
            "followup_questions": followup_questions,
            "clarifying_questions": clarifying_questions,
        }

    # === _generate_followup_questions 메서드 수정 (라인 201-252) ===
    def _generate_followup_questions(
        self, context: Dict, template_key: Optional[str] = None
    ) -> List[str]:
        """
        후속 질문을 생성합니다.

        우선순위:
        1. 프롬프트 파일의 '버튼형 역질문' 섹션 (template_key 기반)
        2. 상황별 템플릿 (fallback, 기준만, 품목만)
        3. 기존 하드코딩 템플릿 (분쟁 유형 기반)
        """
        # 우선순위 1: 프롬프트 파일에서 동적 추출
        if template_key:
            prompt_questions = self._get_questions_from_prompt(template_key)
            if prompt_questions:
                return prompt_questions

        # 우선순위 2: 상황별 템플릿 (fallback 등)
        context_based = self._select_questions_by_context(context)
        if context_based:
            return context_based

        # 우선순위 3: 기존 분쟁 유형 기반 템플릿 (fallback)
        dispute_type = context.get("dispute_type", "일반")
        format_id = context.get("format_id")

        candidate_templates = get_templates_by_dispute_type(dispute_type)
        followup_templates = [
            t for t in candidate_templates if t.question_type == "followup"
        ]

        if format_id:
            format_preferred = self._get_format_preferred_templates(format_id)
            if format_preferred:
                preferred_matched = self._match_templates(format_preferred, context)
                general_matched = self._match_templates(
                    [t for t in followup_templates if t not in format_preferred],
                    context,
                )
                matched_templates = preferred_matched + general_matched
            else:
                matched_templates = self._match_templates(followup_templates, context)
        else:
            matched_templates = self._match_templates(followup_templates, context)

        matched_templates.sort(key=lambda t: t.priority, reverse=True)
        selected_templates = matched_templates[: self.max_followup_questions]

        return [t.question_text for t in selected_templates]

    # === 새로 추가할 메서드 (_get_format_preferred_templates 위에) ===
    def _get_questions_from_prompt(self, template_key: str) -> List[str]:
        """
        프롬프트 파일에서 역질문을 추출합니다.

        Args:
            template_key: 템플릿 키 (solution, action, execution 등)

        Returns:
            역질문 목록 (파싱 실패 시 빈 리스트)
        """
        # template_key -> prompt_key 매핑 (동일한 경우가 많지만 명시적 매핑)
        prompt_key = TEMPLATE_KEY_TO_PROMPT_KEY.get(template_key)
        if not prompt_key:
            return []

        return self.template_loader.get_followup_questions(prompt_key)
```

**변경 요약**:
- INSERT: `_template_loader` 인스턴스 변수
- INSERT: `template_loader` property (lazy loading)
- INSERT: `template_key` 파라미터 (generate_questions)
- INSERT: `_get_questions_from_prompt()` 메서드
- MODIFY: `_generate_followup_questions()` 시그니처 및 로직
- KEEP: 기존 모든 메서드

#### 3. templates.py

**파일 경로**: `/home/maroco/LLM/backend/app/agents/followup/templates.py`

```python
# === 파일 끝에 추가 (라인 465 이후) ===

# ============================================================
# 템플릿 키 → 프롬프트 키 매핑
# ============================================================

TEMPLATE_KEY_TO_PROMPT_KEY: Dict[str, str] = {
    # TemplateRouter에서 반환하는 키 → TemplateLoader에서 사용하는 키
    "solution": "solution",
    "action": "action",
    "execution": "execution",
    "fallback": "fallback",
    "reject": "reject",
    "inquiry": "inquiry",
}

# === __all__ 리스트 수정 (라인 451-465) ===
__all__ = [
    "QuestionTemplate",
    "QUESTION_TEMPLATES",
    "FORMAT_GUIDED_TEMPLATES",
    "REFUND_TEMPLATES",
    "EXCHANGE_TEMPLATES",
    "REPAIR_TEMPLATES",
    "DELIVERY_TEMPLATES",
    "QUALITY_TEMPLATES",
    "CANCELLATION_TEMPLATES",
    "GENERAL_TEMPLATES",
    "CLARIFYING_TEMPLATES",
    "get_templates_by_dispute_type",
    "get_templates_by_question_type",
    "TEMPLATE_KEY_TO_PROMPT_KEY",  # 추가
]
```

**변경 요약**:
- INSERT: `TEMPLATE_KEY_TO_PROMPT_KEY` 딕셔너리
- MODIFY: `__all__` 리스트에 추가
- KEEP: 기존 모든 코드

#### 4. agent.py (generation_node_v2)

**파일 경로**: `/home/maroco/LLM/backend/app/agents/answer_generation/agent.py`

```python
# === _render_and_generate 함수 반환값 수정 (라인 845-916) ===
def _render_and_generate(
    state: Dict,
    user_query: str,
    retrieval: Dict,
    onboarding: Dict,
    retry_supplement,
    mode: str,
) -> tuple:
    """
    Phase 3-4: 템플릿 선택/렌더링 + LLM 생성을 수행합니다.

    Returns:
        (draft_answer, model_used, claim_evidence_map, template_key) 튜플
    """
    # ... 기존 코드 ...

    router = TemplateRouter()
    loader = TemplateLoader()
    ctx_builder = ContextBuilder()

    template_key = router.select_template(state)  # 이미 존재
    # ... 기존 코드 ...

    # 마지막 return 문 수정
    return (draft_answer, model_used, claim_evidence_map, template_key)  # template_key 추가


# === generation_node_v2 함수에서 template_key 전달 (라인 919-1035) ===
async def generation_node_v2(state: Dict, config: Any = None) -> Dict:
    # ... 기존 코드 (라인 942-988) ...

    # Phase 3-4: Template + LLM 생성 (라인 986-988 수정)
    draft_answer, model_used, claim_evidence_map, template_key = _render_and_generate(
        state, user_query, retrieval, onboarding, retry_supplement, mode
    )

    # ... 기존 코드 (라인 990-1003) ...

    # Phase 6: Generate followup questions (라인 994-1004 수정)
    query_analysis = state.get("query_analysis", {})
    followup_generator = FollowupQuestionGenerator()
    is_fallback = model_used in ("rule_based", "safe_fallback")
    followup_result = followup_generator.generate_questions(
        query_analysis=query_analysis,
        retrieval=retrieval,
        answer=draft_answer,
        is_fallback=is_fallback,
        template_key=template_key,  # 새 파라미터 전달
    )
    followup_questions = followup_result.get("followup_questions", [])

    # ... 나머지 코드 유지 ...
```

**변경 요약**:
- MODIFY: `_render_and_generate()` 반환값에 `template_key` 추가
- MODIFY: `generation_node_v2()`에서 `template_key` 변수 받기
- MODIFY: `followup_generator.generate_questions()` 호출 시 `template_key` 전달
- KEEP: 기존 모든 로직

### 테스트 명령어

```bash
# Ruff 린트 및 포맷
conda run -n dsr ruff check backend/app/agents --fix
cd /home/maroco/LLM && conda run -n dsr ruff format backend/app/agents

# 단위 테스트 실행
cd /home/maroco/LLM && conda run -n dsr pytest backend/scripts/testing/answer_generation/test_followup.py -v

# 통합 테스트 (followup context)
cd /home/maroco/LLM && conda run -n dsr pytest backend/scripts/testing/supervisor/test_followup_with_context.py -v

# 전체 MAS 테스트
cd /home/maroco/LLM && conda run -n dsr pytest backend/scripts/testing/supervisor/ -v -m "not slow"
```

### 성공 기준

1. **Ruff 통과**: 린트/포맷 오류 없음
2. **단위 테스트**: `test_followup.py` 모든 테스트 통과
3. **통합 테스트**: `test_followup_with_context.py` 통과
4. **기능 검증**:
   - `solution` 템플릿 사용 시 → 프롬프트 파일의 역질문 3개 반환
   - `action` 템플릿 사용 시 → 프롬프트 파일의 역질문 3개 반환
   - `inquiry` 템플릿 사용 시 → 기존 동적 생성 로직 사용
   - 파싱 실패 시 → 기존 하드코딩 템플릿으로 fallback

### 프롬프트별 예상 출력

| 템플릿 | 추출되는 역질문 |
|--------|----------------|
| solution | "위 답변 내용을 더 쉽게 풀어서 설명해 주세요", "상대방에게 보낼 메시지 초안을 작성해 줄 수 있나요?", "해당 업체가 계속 거부할 경우 다음 단계는 무엇인가요?" |
| action | "이 내용을 바탕으로 업체에 보낼 실제 메시지 초안을 짜주세요", "업체가 '규정상 안 된다'고 우길 때 할 수 있는 말이 있을까요?", "내용증명을 보낼 때 꼭 포함해야 하는 항목을 알려주세요" |
| execution | "소비자원 온라인 접수 페이지로 바로 가는 방법을 알려주세요", "피해구제 신청서에 꼭 적어야 하는 핵심 문구가 있나요?", "접수할 때 증거 자료로 어떤 것들을 준비해야 할까요?" |
| fallback | "해당 기관에 상담을 예약하는 방법을 알려주세요", "상담받으러 갈 때 어떤 서류들을 챙겨가야 하나요?", "이 사안의 경우 해결까지 대략 어느 정도 시간이 걸릴까요?" |
| inquiry | (기존 동적 생성 로직 사용) |
| reject | (base_persona 대체 질문 사용 - 조건부 로직 유지) |

---

## PR #3: 추가 질문 응답 가능성 검토 (후속)

### 개요
- **목적**: 프롬프트에서 추출된 모든 추가 질문에 대해 시스템이 응답 가능한지 검토
- **브랜치**: `docs/followup-capability-review`
- **라벨**: `type:docs`
- **선행 조건**: PR #1, PR #2 완료 후 진행

### 검토 대상 질문 목록

#### 1. solution_template.md (3개)
| 질문 | 응답 가능 여부 | 비고 |
|------|---------------|------|
| 위 답변 내용을 더 쉽게 풀어서 설명해 주세요 | O | LLM 재생성 |
| 상대방에게 보낼 메시지 초안을 작성해 줄 수 있나요? | O | LLM 생성 |
| 해당 업체가 계속 거부할 경우 다음 단계는 무엇인가요? | O | action 템플릿 연결 |

#### 2. action_guide_template.md (3개)
| 질문 | 응답 가능 여부 | 비고 |
|------|---------------|------|
| 이 내용을 바탕으로 업체에 보낼 실제 메시지 초안을 짜주세요 | O | LLM 생성 |
| 업체가 '규정상 안 된다'고 우길 때 할 수 있는 말이 있을까요? | O | 검색 + LLM |
| 내용증명을 보낼 때 꼭 포함해야 하는 항목을 알려주세요 | △ | 일반 가이드 제공 가능 |

#### 3. execution_guide_template.md (3개)
| 질문 | 응답 가능 여부 | 비고 |
|------|---------------|------|
| 소비자원 온라인 접수 페이지로 바로 가는 방법을 알려주세요 | △ | URL 제공 가능, 실시간 확인 불가 |
| 피해구제 신청서에 꼭 적어야 하는 핵심 문구가 있나요? | O | 템플릿 제공 가능 |
| 접수할 때 증거 자료로 어떤 것들을 준비해야 할까요? | O | 가이드 제공 가능 |

#### 4. fallback_template.md (3개)
| 질문 | 응답 가능 여부 | 비고 |
|------|---------------|------|
| 해당 기관에 상담을 예약하는 방법을 알려주세요 | △ | 일반 가이드, 실시간 예약 불가 |
| 상담받으러 갈 때 어떤 서류들을 챙겨가야 하나요? | O | 가이드 제공 가능 |
| 이 사안의 경우 해결까지 대략 어느 정도 시간이 걸릴까요? | △ | 일반적인 기간 안내만 가능 |

### 검토 결과 분류

- **O (응답 가능)**: 현재 시스템으로 충분히 응답 가능
- **△ (제한적)**: 일반적인 가이드만 제공 가능, 실시간/동적 정보 불가
- **X (응답 불가)**: 웹 검색 또는 외부 API 연동 필요

### 후속 작업 제안

1. **제한적 응답 개선**:
   - 소비자원 URL 등 정적 정보 → 데이터베이스에 저장
   - 절차 안내 템플릿 강화

2. **웹 검색 연동 검토** (필요 시):
   - 실시간 URL 유효성 확인
   - 최신 절차 정보 조회

---

## 구현 순서 요약

```
PR #1 (버블 비활성화)
    ↓
PR #2 (동적 추출)
    ↓
PR #3 (응답 검토 - 문서)
```

### GitHub Workflow

```bash
# PR #1
git checkout develop
git checkout -b fix/followup-disable-click
# ... 구현 ...
gh issue create --title "추가 질문 버블 클릭 비활성화" --label "type:bug" --assignee @me
gh pr create --base develop --title "fix: 추가 질문 버블 클릭 비활성화" --label "type:bug" --assignee @me

# PR #2
git checkout develop
git checkout -b feat/followup-dynamic-extraction
# ... 구현 ...
gh issue create --title "프롬프트 파일에서 추가 질문 동적 추출" --label "type:feature" --assignee @me
gh pr create --base develop --title "feat: 프롬프트 파일에서 추가 질문 동적 추출" --label "type:feature" --assignee @me
```

---

## Critical Files for Implementation

### PR #1
- `/home/maroco/LLM/frontend/src/features/chat/components/FollowupChips.tsx` - 클릭 비활성화 수정 대상

### PR #2
- `/home/maroco/LLM/backend/app/agents/answer_generation/template_loader.py` - 역질문 파싱 기능 추가
- `/home/maroco/LLM/backend/app/agents/followup/generator.py` - 동적 질문 로딩 로직
- `/home/maroco/LLM/backend/app/agents/followup/templates.py` - 템플릿 매핑 추가
- `/home/maroco/LLM/backend/app/agents/answer_generation/agent.py` - template_key 전달
