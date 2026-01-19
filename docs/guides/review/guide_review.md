# 팀원 D 가이드 - 검토 로직 + 프론트엔드 UI

> **역할**: 검토 노드, 추가 질문 노드, 프론트엔드 UI 개발
> **최종 수정**: 2026-01-16

---

## 1. 역할 개요

팀원 D는 ddoksori 시스템의 **안전 장치**와 **사용자 경험**을 담당합니다.

### 주요 책임
- Review Node: 금지 표현 탐지, 출처 검사
- Ask Clarification Node: 추가 질문 생성
- 프론트엔드 UI 개선
- 출처 모달, 안전 경고 UI 구현
- E2E 시나리오 테스트

---

## 2. 담당 파일 목록

### 2.1 백엔드 (backend/app/orchestrator/nodes/)

| 파일명 | 역할 | 우선순위 |
|--------|------|:--------:|
| `review.py` | 검토 노드 (금지 표현 탐지, 출처 검사) | ★★★ |
| `ask_clarification.py` | 추가 질문 생성 노드 | ★★★ |

### 2.2 프론트엔드 (frontend/src/)

| 폴더/파일 | 역할 | 우선순위 |
|-----------|------|:--------:|
| `features/chat/` | 채팅 UI 컴포넌트 | ★★★ |
| `widgets/` | 공통 UI 위젯 | ★★☆ |
| `shared/components/` | 공유 컴포넌트 | ★★☆ |
| `store/` | Zustand 상태 관리 | ★★☆ |

---

## 3. 백엔드 파일 상세

### 3.1 review.py - 검토 노드

**위치**: `backend/app/orchestrator/nodes/review.py`

**역할**: 생성된 답변의 안전성 검토

**핵심 함수**:
```python
def review_node(state: ChatState) -> dict:
    """
    규칙 기반 검토

    검토 항목:
    1. 금지 표현 탐지
    2. 출처 표시 검사
    3. 근거 충분성 평가

    반환:
    - passed: True/False
    - violations: 위반 사항 목록
    - filtered_answer: 완화된 답변 (선택)
    """
```

**금지 표현 패턴** (`PROHIBITED_PATTERNS`):
```python
PROHIBITED_PATTERNS = [
    # 단정적 표현
    r"반드시.*[해야|받아야]",           # "반드시 환불받아야 합니다"
    r"확실(히|하게)",                   # "확실히 승소합니다"
    r"100%|무조건",                     # "100% 환불 가능"
    r"틀림없(이|다)",                   # "틀림없이 이깁니다"

    # 법적 판단 표현
    r"법적(으로|인).*[책임|의무]",       # "법적으로 책임이 있습니다"
    r"위법|불법",                       # "이것은 위법입니다"
    r"소송.*[이기|승리|승소]",           # "소송에서 이길 수 있습니다"
    r"권리.*[있습니다|됩니다]",          # "권리가 있습니다" (문맥 따라)

    # 강제적 표현
    r"당장|즉시.*[해야|하세요]",         # "당장 신고하세요"
    r"[고소|고발].*[하세요|해야]",       # "고소하세요"
]
```

**처리 로직**:
```
1. 금지 표현 검사
   - 3개 이상 → 재생성 (max 2회)
   - 1-2개 → 완화 표현으로 필터링
   - 0개 → 통과

2. 출처 검사
   - "[출처:", "[참고:" 패턴 검색
   - 법령/기준 인용 확인

3. 근거 충분성
   - retrieval 결과 존재 여부
   - 분쟁조정사례 또는 법령 최소 1개 필요
```

**완화 표현 변환** (`SOFTENING_RULES`):
```python
SOFTENING_RULES = [
    (r"반드시.*해야", "~해 보시는 것이 좋겠습니다"),
    (r"확실히", "가능성이 높습니다"),
    (r"권리가 있습니다", "권리가 있을 수 있습니다"),
    (r"책임이 있습니다", "책임이 있을 수 있습니다"),
]
```

---

### 3.2 ask_clarification.py - 추가 질문 노드

**위치**: `backend/app/orchestrator/nodes/ask_clarification.py`

**역할**: 누락된 정보에 대한 추가 질문 생성

**핵심 함수**:
```python
def ask_clarification_node(state: ChatState) -> dict:
    """
    누락 필드별 추가 질문 생성

    반환:
    - clarifying_questions: 질문 리스트 (최대 3개)
    - final_answer: 질문 메시지
    """
```

**필드별 질문 템플릿** (`FIELD_QUESTIONS`):
```python
FIELD_QUESTIONS = {
    'purchase_item': {
        'question': "어떤 제품이나 서비스에 대한 분쟁인가요?",
        'example': "예: 헬스장 이용권, 휴대폰, 가전제품 등"
    },
    'dispute_details': {
        'question': "어떤 문제가 발생했는지 자세히 설명해 주시겠어요?",
        'example': "예: 환불 거절, 제품 불량, 서비스 불만 등"
    },
    'purchase_date': {
        'question': "언제 구매하셨나요?",
        'example': "예: 2024년 1월, 약 3개월 전 등"
    },
    'purchase_place': {
        'question': "어디서 구매하셨나요?",
        'example': "예: 온라인 쇼핑몰, 오프라인 매장, 중고거래 등"
    },
    'purchase_amount': {
        'question': "구매 금액은 얼마인가요?",
        'example': "예: 50만원, 약 100만원 등"
    },
}
```

**우선순위 순서**:
1. `purchase_item` (가장 중요)
2. `dispute_details`
3. `purchase_date`
4. `purchase_place`
5. `purchase_amount`

---

## 4. 프론트엔드 구조

### 4.1 폴더 구조

```
frontend/src/
├── app/              # 앱 설정
│   ├── App.tsx
│   └── routes.tsx
├── features/         # 기능 모듈
│   ├── chat/
│   │   ├── ChatPage.tsx         ★
│   │   ├── ChatInput.tsx        ★
│   │   ├── ChatMessage.tsx      ★
│   │   ├── SourceModal.tsx      ★ (신규/개선)
│   │   └── SafetyWarning.tsx    ★ (신규/개선)
│   └── onboarding/
│       └── OnboardingForm.tsx
├── shared/           # 공유 컴포넌트
│   ├── components/
│   │   ├── Button.tsx
│   │   ├── Modal.tsx
│   │   └── Loading.tsx
│   └── utils/
├── store/            # 상태 관리
│   ├── chatStore.ts
│   └── userStore.ts
└── widgets/          # UI 위젯
    ├── Header.tsx
    └── Footer.tsx
```

### 4.2 주요 컴포넌트

| 컴포넌트 | 역할 | 개선 포인트 |
|----------|------|------------|
| `ChatPage.tsx` | 채팅 메인 페이지 | 레이아웃 최적화 |
| `ChatInput.tsx` | 메시지 입력창 | 자동 완성, 힌트 |
| `ChatMessage.tsx` | 메시지 버블 | 스트리밍 UI |
| `SourceModal.tsx` | 출처 상세 모달 | 클릭 시 상세 정보 |
| `SafetyWarning.tsx` | 안전 경고 박스 | 오렌지 경고 UI |

---

## 5. 테스트 스크립트

### 5.1 Review 노드 테스트
```bash
conda activate dsr
cd backend
python -m pytest scripts/testing/orchestrator/test_pr2_nodes.py::TestReviewNode -v -p no:asyncio
```

**테스트 항목**:
| 테스트 | 검증 내용 |
|--------|----------|
| `test_general_query_passes_review` | 일반 대화는 검토 통과 |
| `test_prohibited_expression_detected` | 금지 표현 탐지 |
| `test_no_prohibited_expression` | 안전한 표현 통과 |
| `test_citation_presence_check` | 출처 포함 검증 |

### 5.2 Clarification 노드 테스트
```bash
cd backend
python -m pytest scripts/testing/orchestrator/test_pr2_nodes.py::TestAskClarificationNode -v -p no:asyncio
```

**테스트 항목**:
| 테스트 | 검증 내용 |
|--------|----------|
| `test_generates_questions_for_missing_fields` | 누락 필드 질문 생성 |
| `test_no_missing_fields_fallback` | 완전 정보 시 처리 |

### 5.3 에러 처리 테스트
```bash
cd backend
python -m pytest scripts/testing/api/test_api_error_handling.py -v -p no:asyncio
```

### 5.4 프론트엔드 개발 서버
```bash
cd frontend
npm install    # 최초 1회
npm run dev    # http://localhost:5173
```

### 5.5 프론트엔드 빌드 테스트
```bash
cd frontend
npm run build
npm run lint
```

---

## 6. 평가 스크립트

### 6.1 Review 평가
```bash
cd backend
python -m scripts.evaluation.evaluate_review \
  --golden-set ./data/golden_set/review.jsonl \
  --output ./results/review_eval.json
```

**평가 지표**:
| 지표 | 목표값 | 설명 |
|------|--------|------|
| Violation Detection Precision | ≥ 0.85 | 탐지 정확도 |
| Violation Detection Recall | ≥ 0.90 | 탐지 재현율 |
| False Positive Rate | ≤ 0.10 | 오탐률 |
| Binary Accuracy | ≥ 0.85 | 이진 분류 정확도 |

---

## 7. E2E 테스트 시나리오

### 7.1 시나리오 체크리스트

| # | 시나리오 | 확인 사항 | 상태 |
|---|---------|----------|:----:|
| 1 | 분쟁 상담 + 스트리밍 | "헬스장 환불" 질의 → 실시간 타이핑, 면책 문구 | [ ] |
| 2 | 인라인 출처 확인 | `[1]`, `[2]` 클릭 → 출처 상세 모달 | [ ] |
| 3 | 안전 장치 | 모호한 질문 → 오렌지 경고 박스, 추가 질문 | [ ] |
| 4 | 일반 대화 | "안녕" → 스트리밍 응답, 출처 없음 | [ ] |
| 5 | 에러 처리 | 백엔드 중지 후 질문 → 에러 메시지 | [ ] |

### 7.2 시나리오별 테스트 방법

**시나리오 1: 분쟁 상담 + 스트리밍**
```
1. http://localhost:5173 접속
2. "헬스장 환불 문의드립니다" 입력
3. 확인:
   - 답변이 실시간으로 타이핑되는지
   - 4섹션 (기관/사례/법령/기준) 표시되는지
   - 면책 문구 포함되는지
```

**시나리오 2: 인라인 출처 확인**
```
1. 분쟁 상담 답변 받은 후
2. 답변 내 [1], [2] 등 출처 번호 클릭
3. 확인:
   - 출처 모달이 열리는지
   - 출처 상세 정보 표시되는지
```

**시나리오 3: 안전 장치**
```
1. "환불" 만 입력 (모호한 질문)
2. 확인:
   - 오렌지 경고 박스 표시되는지
   - 추가 질문 목록 표시되는지
```

**시나리오 4: 일반 대화**
```
1. "안녕하세요" 입력
2. 확인:
   - 인사 응답이 오는지
   - 출처 섹션이 없는지
```

**시나리오 5: 에러 처리**
```
1. 백엔드 서버 중지 (Ctrl+C)
2. 프론트엔드에서 질문 입력
3. 확인:
   - 에러 메시지 표시되는지
   - "다시 시도" 버튼 동작하는지
```

---

## 8. 완료 기준

| 지표 | 목표값 | 확인 방법 |
|------|--------|----------|
| Violation Detection Precision | ≥ 0.85 | `evaluate_review.py` |
| Review 테스트 | 100% 통과 | pytest |
| Clarification 테스트 | 100% 통과 | pytest |
| E2E 시나리오 | 5/5 통과 | 수동 테스트 |
| 프론트엔드 빌드 | 성공 | `npm run build` |

---

## 9. 주차별 작업

### 1주차
- [ ] 프로젝트 구조 학습
- [ ] Review 코드 분석
- [ ] 프론트엔드 구조 파악
- [ ] 개선 포인트 정리

### 2주차
- [ ] Review 패턴 확장
- [ ] Ask Clarification 개선
- [ ] 위반 탐지 테스트
- [ ] 평가 실행

### 3주차
- [ ] **프론트엔드 UI 개선**
- [ ] **출처 모달 구현**
- [ ] **안전 경고 UI 구현**
- [ ] UX 마무리, 반응형

---

## 10. 프론트엔드 개발 가이드

### 10.1 개발 환경 설정

```bash
# Node.js 버전 확인 (18+ 권장)
node -v

# 의존성 설치
cd frontend
npm install

# 개발 서버 실행
npm run dev

# 빌드
npm run build

# 린트 검사
npm run lint
```

### 10.2 기술 스택

| 기술 | 용도 |
|------|------|
| React 18 | UI 프레임워크 |
| TypeScript | 타입 안전성 |
| TailwindCSS | 스타일링 |
| Zustand | 상태 관리 |
| React Query | 서버 상태 관리 |

### 10.3 출처 모달 구현 예시

```tsx
// features/chat/SourceModal.tsx

interface SourceModalProps {
  isOpen: boolean;
  onClose: () => void;
  source: {
    type: string;      // 'case', 'law', 'criteria'
    title: string;
    content: string;
    url?: string;
  };
}

export function SourceModal({ isOpen, onClose, source }: SourceModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center">
      <div className="bg-white rounded-lg p-6 max-w-lg w-full mx-4">
        <h3 className="text-lg font-bold mb-2">{source.title}</h3>
        <span className="text-xs bg-blue-100 text-blue-800 px-2 py-1 rounded">
          {source.type}
        </span>
        <div className="mt-4 text-sm text-gray-700">
          {source.content}
        </div>
        {source.url && (
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:underline mt-2 block"
          >
            원문 보기
          </a>
        )}
        <button
          onClick={onClose}
          className="mt-4 w-full bg-gray-200 hover:bg-gray-300 py-2 rounded"
        >
          닫기
        </button>
      </div>
    </div>
  );
}
```

### 10.4 안전 경고 UI 구현 예시

```tsx
// features/chat/SafetyWarning.tsx

interface SafetyWarningProps {
  questions: string[];
  onQuestionClick?: (question: string) => void;
}

export function SafetyWarning({ questions, onQuestionClick }: SafetyWarningProps) {
  return (
    <div className="bg-orange-50 border-l-4 border-orange-400 p-4 my-2">
      <div className="flex">
        <div className="flex-shrink-0">
          <svg className="h-5 w-5 text-orange-400" viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
        </div>
        <div className="ml-3">
          <p className="text-sm text-orange-700 font-medium">
            더 정확한 답변을 위해 추가 정보가 필요합니다
          </p>
          <ul className="mt-2 text-sm text-orange-600 list-disc list-inside">
            {questions.map((q, i) => (
              <li
                key={i}
                className="cursor-pointer hover:text-orange-800"
                onClick={() => onQuestionClick?.(q)}
              >
                {q}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
```

---

## 11. 참고 문서

| 문서 | 경로 | 설명 |
|------|------|------|
| 프로젝트 계획서 | `/plans/plans.md` | 전체 3주 계획 |
| 프론트-백엔드 통합 | `/docs/guides/frontend_backend_integration.md` | API 연동 |
| LangGraph 통합 | `/docs/guides/2026-01-14_frontend_langgraph_integration.md` | 프론트 연동 |
| 구조화 응답 | `/docs/guides/2026-01-13_structured_response_implementation.md` | 4섹션 구현 |

---

## 12. 자주 사용하는 명령어 모음

```bash
# 환경 활성화
conda activate dsr

# Review 노드 테스트 (backend 디렉토리에서)
cd backend
python -m pytest scripts/testing/orchestrator/test_pr2_nodes.py::TestReviewNode -v -p no:asyncio

# Clarification 노드 테스트
python -m pytest scripts/testing/orchestrator/test_pr2_nodes.py::TestAskClarificationNode -v -p no:asyncio

# 에러 처리 테스트
python -m pytest scripts/testing/api/test_api_error_handling.py -v -p no:asyncio

# Review 평가
python -m scripts.evaluation.evaluate_review \
  --golden-set ./data/golden_set/review.jsonl \
  --output ./results/review_eval.json

# 프론트엔드 개발 서버
cd frontend && npm run dev

# 프론트엔드 빌드
cd frontend && npm run build

# 전체 스택 실행 (Docker)
docker-compose up --build

# 백엔드만 실행
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 13. 금지 표현 패턴 추가 방법

```python
# review.py

# 기존 패턴에 추가
PROHIBITED_PATTERNS = [
    # ... 기존 패턴 ...

    # 새로 추가할 패턴
    r"새로운.*금지.*표현",
]

# 완화 규칙 추가
SOFTENING_RULES = [
    # ... 기존 규칙 ...

    # 새로 추가할 규칙
    (r"새로운 표현", "완화된 표현"),
]
```

**패턴 테스트 방법**:
```python
import re

pattern = r"반드시.*해야"
text = "반드시 환불을 해야 합니다"

if re.search(pattern, text):
    print("탐지됨!")
```

