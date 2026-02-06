# 후속 질문 생성 모듈 (Followup Question Generator)

> **위치**: `backend/app/agents/followup/`
> **생성일**: 2026-01-28
> **목적**: 답변 생성 후 맥락에 맞는 후속 질문과 보완 질문을 자동 생성

---

## 개요

답변 생성 에이전트(`answer_generation`)의 최종 단계에서 호출되어, 사용자 대화를 확장하기 위한 후속 질문(최대 3개)과 보완 질문(최대 2개)을 생성합니다. LLM 호출 없이 **템플릿 매칭** 기반으로 동작합니다.

## MAS 파이프라인 내 위치

```
QueryAnalyst → Retrieval Agents → AnswerDrafter → LegalReviewer
                                        ↓
                                FollowupQuestionGenerator  ← 여기
                                        ↓
                                   API 응답 반환
```

## 코드 구조

| 파일 | 줄 수 | 설명 |
|------|:-----:|------|
| `__init__.py` | 18 | 모듈 공개 API 내보내기 |
| `generator.py` | 410 | `FollowupQuestionGenerator` 핵심 로직 |
| `templates.py` | 466 | `QuestionTemplate` 데이터 모델 + 50개 이상 템플릿 |

## 주요 클래스

### `FollowupQuestionGenerator`

```python
class FollowupQuestionGenerator:
    def __init__(
        self,
        max_followup_questions: int = 3,   # 후속 질문 최대 개수
        max_clarifying_questions: int = 2   # 보완 질문 최대 개수
    )

    def generate_questions(
        self,
        query_analysis: Dict,       # 의도 분류 + 누락 필드
        retrieval: Dict,            # 검색 결과 (사례/법령/기준)
        answer: str,                # 생성된 답변
        format_id: Optional[str],   # 응답 포맷 식별자
        is_fallback: bool,          # Fallback 답변 여부
        template_key: Optional[str] # 프롬프트 템플릿 키
    ) -> Dict[str, List[str]]
    # 반환: {"followup_questions": [...], "clarifying_questions": [...]}
```

### `QuestionTemplate`

```python
@dataclass
class QuestionTemplate:
    template_id: str                           # 고유 식별자
    question_type: Literal["followup", "clarifying"]
    dispute_types: List[str]                   # 적용 분쟁 유형
    question_text: str                         # 실제 질문 텍스트
    conditions: Dict[str, bool]                # 표시 조건
    priority: int = 1                          # 정렬 우선순위 (높을수록 먼저)
```

## 템플릿 카테고리

| 카테고리 | 유형 | 개수 | 예시 |
|----------|------|:----:|------|
| 환불 관련 | followup | 4 | 기한, 서류, 부분 환불, 거절 시 |
| 교환 관련 | followup | 3 | 기간, 배송비, 다른 제품 |
| 수리 관련 | followup | 3 | 보증, 비용, 수리 불가 |
| 배송 관련 | followup | 3 | 지연 보상, 분실, 파손 |
| 품질 관련 | followup | 3 | 하자 기준, 검수, 보상 |
| 해지 관련 | followup | 3 | 위약금, 절차, 환급 |
| 일반 | followup | 5 | 조정, 소송, 증거, 기한, 비용 |
| 보완 질문 | clarifying | 5 | 구매일, 품목, 상세, 판매자 응대, 금액 |
| 포맷 연동 | followup | 7 | 분쟁 안내, 유사 사례, 법령, 기준 |

## 생성 알고리즘

1. `query_analysis`, `retrieval`, `answer`에서 컨텍스트 플래그 추출
2. 분쟁 유형별 템플릿 필터링
3. 조건(conditions) 일치 검사
4. 응답 포맷(format_id)별 우선 템플릿 적용
5. 우선순위(priority) 내림차순 정렬
6. 최대 개수(3/2)로 잘라서 반환

## 특수 처리

| 조건 | 동작 |
|------|------|
| Fallback 답변 | 고정 3문항 반환 (환불 기준, 관련 법령, 유사 사례) |
| 기준만 존재 | 법적 근거 + 사례 질문 2문항 |
| 제품만 언급 | 법령 + 유사 사례 질문 2문항 |

## 의존성

- **내부**: `answer_generation.template_loader` (지연 임포트, 순환 참조 방지)
- **외부 API**: 없음 (순수 템플릿 기반)

## 연동 위치

`backend/app/agents/answer_generation/agent.py` (약 line 650, 750)에서 인스턴스 생성 후 `generate_questions()` 호출
