# PR-T3: Agent Mock 테스트 리페어 (Import 구조 개선 + 품질 향상)

**작성일**: 2026-01-23  
**상태**: 📋 Plan (검토 완료, 실행 대기)  
**목표**: Agent Mock 테스트 5개 실패 해결 + 에이전트 품질 개선

| 항목 | 상세 |
|------|------|
| **영향받는 테스트** | 5개 fail |
| **테스트 파일** | `test_agents_mock.py` (5개 테스트) |
| **예상 소요** | 0.5일 |
| **우선순위** | 🟡 높음 |

---

## 1. 배경 (Context)

### 문제 상황
에이전트 리팩토링 후 local import 패턴과 정규식 개선으로 인해 **5개 mock 테스트**가 실패하고 있습니다.
- 테스트 실패의 근본 원인: local import로 인한 mock patch 실패 + 정규식/파서 예상 입력 불일치

### 현황
테스트 파일: `backend/scripts/testing/test_agents_mock.py`
- ❌ `test_extract_info_from_message` (Behavioral 실패)
- ❌ `test_check_prohibited_expressions` (정규식 매칭 실패)
- ❌ `test_review_node_pass` (Infrastructure - local import로 mock 불가)
- ❌ `test_review_node_fail_retry` (Infrastructure - local import로 mock 불가)
- ❌ `test_generation_node_rag` (Infrastructure - local import로 mock 불가)

---

## 2. 근본 원인 분석 (RCA)

### 원인 1: Local Import 패턴 (Infrastructure 문제)

**파일**: `backend/app/agents/legal_review/agent.py`
```python
# Line 239 - review_node 내부에 local import
def review_node(state: ChatState) -> dict:
    # ...
    from ...common.config import AgentConfig  # ❌ Local import
```

**결과**: Mock patch 실패
```python
# 테스트에서 이렇게 해도 동작 안 함
with patch('app.agents.legal_review.agent.AgentConfig') as MockConfig:
    # AgentConfig가 함수 내부에서 import되므로 patch가 먹지 않음
```

**파일**: `backend/app/agents/answer_generation/agent.py`
```python
# Line 152 - generation_node 내부에 local import
def generation_node(state: ChatState) -> Dict:
    # ...
    from .cache import get_answer_cache  # ❌ Local import
```

### 원인 2: 정규식 및 파서 엄격성 (Behavioral 문제)

**파일**: `backend/app/agents/legal_review/agent.py`
```python
# Line 35 - 정규식이 "해야 합니다" 접미사 필수
PROHIBITED_PATTERNS = [
    (r'반드시\s+\S+해야\s*합니다', '반드시 ~해야 합니다'),
    # ❌ "반드시 승소합니다" 매칭 불가
]
```

**파일**: `backend/app/agents/query_analysis/agent.py`
```python
# Line 611-614 - 금액 추출이 "금액:" 접두사 기반
patterns = {
    "purchase_amount": [
        r"구매\s*금액[:\s]+([^\n,]+)",
        r"금액[:\s]+([^\n,]+)",  # ❌ "150만원에 샀는데" 미인식
    ],
}
```

---

## 3. 해결 방안 (Solution)

### 전략: 권장 방식 B (코드 품질 중심) + 품질 개선

목표:
1. **Import 구조 개선**: local import를 모듈 상단으로 이동 (테스트 용이성 + 코드 명확성)
2. **정규식 개선**: 패턴을 더 포용적으로 개선 (실제 사용 품질 향상)
3. **파서 개선**: 금액 추출 알고리즘 강화

---

## 4. 작업 항목 (Implementation Tasks)

### A. Import 구조 개선

#### Task A1: Legal Review Agent
**파일**: `backend/app/agents/legal_review/agent.py`
**현재** (Line 239):
```python
def review_node(state: ChatState) -> dict:
    from ...common.config import AgentConfig  # ❌ Local import
    # ...
```

**변경**:
```python
# 모듈 상단 (Line 20-23 주변)
from ...common.config import AgentConfig  # ✅ 모듈 레벨 import

def review_node(state: ChatState) -> dict:
    # AgentConfig 직접 사용
```

**주의**: import cycle 확인 필요 (현재는 `common/config`에서 legal_review를 import하지 않으므로 안전)

#### Task A2: Answer Generation Agent
**파일**: `backend/app/agents/answer_generation/agent.py`
**현재** (Line 152):
```python
def generation_node(state: ChatState) -> Dict:
    from .cache import get_answer_cache  # ❌ Local import
    # ...
```

**변경**:
```python
# 모듈 상단 (Line 1-20 주변, 기존 import 중에)
from .cache import get_answer_cache  # ✅ 모듈 레벨 import (이미 __init__.py에 export됨)

def generation_node(state: ChatState) -> Dict:
    # get_answer_cache 직접 사용
```

**주의**: `__init__.py`에 이미 `get_answer_cache` export 되어있으므로 안전

---

### B. 정규식 개선 (품질 향상)

#### Task B1: 금지표현 패턴 완화
**파일**: `backend/app/agents/legal_review/agent.py`
**현재** (Line 33-55):
```python
PROHIBITED_PATTERNS = [
    (r'반드시\s+\S+해야\s*합니다', '반드시 ~해야 합니다'),  # ❌ "반드시 승소합니다" 매칭 실패
    (r'법적으로\s+\S+입니다', '법적으로 ~입니다'),
    (r'위법입니다', '위법입니다'),
    # ...
]
```

**변경** (권장):
```python
PROHIBITED_PATTERNS = [
    # "반드시 ~해야 합니다" + "반드시 ~합니다" (단정표현 모두 포함)
    (r'반드시\s+\S+(해야\s*합니다|합니다|하세요|입니다)', '반드시 ~합니다'),
    
    # "법적으로 ~입니다" (기존 유지)
    (r'법적으로\s+\S+입니다', '법적으로 ~입니다'),
    
    # "위법입니다" + "불법입니다" (기존 유지)
    (r'(위법|불법)입니다', '위법/불법입니다'),
    
    # 예측 표현 추가 (실제 사용 시나리오)
    (r'(승소|패소|이길)\s*수\s*있(습니다|어요)', '승소/패소할 수 있습니다'),
    
    # ... 나머지는 기존 유지
]
```

**효과**:
- `test_check_prohibited_expressions` 테스트 커버리지 개선
- 실제 사용자 입력에서 위험한 표현 더 많이 감지

---

### C. 금액 추출 개선 (품질 향상)

#### Task C1: 금액 패턴 강화
**파일**: `backend/app/agents/query_analysis/agent.py`
**현재** (Line 611-614):
```python
"purchase_amount": [
    r"구매\s*금액[:\s]+([^\n,]+)",
    r"금액[:\s]+([^\n,]+)",  # ❌ "150만원에 샀는데" 미인식
],
```

**변경** (권장):
```python
"purchase_amount": [
    r"구매\s*금액[:\s]+([^\n,]+)",
    r"금액[:\s]+([^\n,]+)",
    # 자연 문장에서 금액 직접 추출 (만원/원/천원 단위)
    r"(\d{1,}(?:만\s*)?원(?:에|에서|을|를)?)",  # 추가: "150만원에", "10,000원을"
],
```

**후처리**:
```python
# _extract_info_from_message에 추가 로직
if "purchase_amount" in info:
    # "150만원" → "1500000"으로 정규화
    amount_str = info["purchase_amount"]
    # 만 단위 변환
    if "만" in amount_str:
        base = re.search(r'(\d+(?:\.\d+)?)', amount_str)
        if base:
            amount = int(float(base.group(1)) * 10000)
            info["purchase_amount"] = str(amount)
```

**효과**:
- `test_extract_info_from_message` 테스트 통과
- 실제 사용자 입력 커버리지 개선 ("150만원에 샀는데" 같은 자연 문장 지원)

---

## 5. 구현 체크리스트

### A. Import 구조 개선
- [ ] `backend/app/agents/legal_review/agent.py` 수정
  - [ ] Line 20 주변: `from ...common.config import AgentConfig` 추가
  - [ ] Line 239 주변: review_node 내 local import 제거
  - [ ] 테스트: `pytest test_agents_mock.py::TestLegalReviewFunctions -v`
  
- [ ] `backend/app/agents/answer_generation/agent.py` 수정
  - [ ] Line 10 주변: `from .cache import get_answer_cache` 추가
  - [ ] Line 152 주근: generation_node 내 local import 제거
  - [ ] 테스트: `pytest test_agents_mock.py::TestAnswerGenerationFunctions -v`

### B. 정규식 개선
- [ ] `backend/app/agents/legal_review/agent.py` PROHIBITED_PATTERNS 수정
  - [ ] Line 35-50: 정규식 패턴 완화 (단정표현 다양화)
  - [ ] 테스트: `pytest test_agents_mock.py::TestLegalReviewFunctions::test_check_prohibited_expressions -v`

### C. 금액 추출 개선
- [ ] `backend/app/agents/query_analysis/agent.py` 수정
  - [ ] Line 611-614: 금액 패턴 강화
  - [ ] 금액 정규화 로직 추가
  - [ ] 테스트: `pytest test_agents_mock.py::TestQueryAnalysisFunctions::test_extract_info_from_message -v`

### D. 회귀 테스트
- [ ] 5개 mock 테스트 모두 PASS 확인
  - [ ] `pytest backend/scripts/testing/test_agents_mock.py -v`
- [ ] 기존 legal_review 테스트 회귀 없음
  - [ ] `pytest backend/scripts/testing/legal_review/ -v`
- [ ] 기존 query_analysis 테스트 회귀 없음
  - [ ] `pytest backend/scripts/testing/query_analysis/ -v`

---

## 6. 완료 기준 (Acceptance Criteria)

| 기준 | 검증 방법 |
|------|----------|
| ✅ `test_extract_info_from_message` 통과 | `pytest test_agents_mock.py::TestQueryAnalysisFunctions::test_extract_info_from_message -v` |
| ✅ `test_check_prohibited_expressions` 통과 | `pytest test_agents_mock.py::TestLegalReviewFunctions::test_check_prohibited_expressions -v` |
| ✅ `test_review_node_pass` 통과 | `pytest test_agents_mock.py::TestLegalReviewFunctions::test_review_node_pass -v` |
| ✅ `test_review_node_fail_retry` 통과 | `pytest test_agents_mock.py::TestLegalReviewFunctions::test_review_node_fail_retry -v` |
| ✅ `test_generation_node_rag` 통과 | `pytest test_agents_mock.py::TestAnswerGenerationFunctions::test_generation_node_rag -v` |
| ✅ 회귀 없음 | `pytest test_agents_mock.py -v` → 5개 모두 PASS |
| ✅ 5개 fail → 0개 fail | 전체 테스트 성공률: 93.8% → 94.3% (564 → 567 passed) |

---

## 7. 리스크 및 주의사항

### A. Import Cycle 위험
- **확인 필요**: `common/config.py`에서 legal_review를 import하지 않는지 확인
- **현재 상태**: 안전 (common은 순수 utility, legal_review는 app/agents 하위)

### B. 정규식 오탐 증가 가능성
- **새로운 패턴**: "승소/패소할 수 있습니다" 추가로 오탐 가능성 있음
- **완화 방법**: 기존 테스트 통과 후 금지표현 탐지 상황 수동 검증 권장
- **모니터링**: PR 이후 legal_review 통과율 추적

### C. 금액 추출 로직 복잡성
- **추가된 복잡도**: 정규화 로직 추가로 엣지 케이스 가능
- **테스트 범위**: "150만원", "10,000원", "500원" 등 다양한 입력 테스트 권장

### D. 의도적 동작 변화 (작음)
| 시나리오 | Before | After | 의도 |
|---------|--------|-------|------|
| "반드시 승소합니다" | 미감지 | 감지 ✅ | 위험표현 감지 강화 |
| "150만원에 샀는데" | 미추출 | 추출 ✅ | 자연 문장 지원 강화 |
| "금액: 100만원" | 추출 | 추출 ✅ | 변화 없음 |

---

## 8. 이전 사항 (Notes)

### 검토 의견 반영
- ✅ 권장 방식 B 선택: local import를 모듈 상단으로 이동 (코드 품질 + 테스트 용이성)
- ✅ 품질개선 포함: 정규식/파서 개선으로 실제 사용 커버리지 확대
- ✅ 리스크 분석: import cycle, 오탐 증가, 복잡성 추가 사항 명시

### 예상 효과
1. **테스트 안정화**: 5개 mock 테스트 모두 통과 (+5개)
2. **코드 품질 개선**: 테스트 용이성 증대 (mocking 단순화)
3. **사용자 경험 개선**: 자연 문장 지원, 위험표현 감지 강화

---

## 9. 다음 단계

### 즉시 실행 (이 PR 완료 후)
1. PR-T2 (Orchestrator) 완료 확인 ✅ (이미 완료)
2. PR-T3 구현 및 테스트 → 5개 fail → 0개 fail 전환
3. PR-T4 (API 에러) 준비

### 중기 계획
- PR-T4, T5, T6, T7 순차 진행
- 테스트 성공률: 93.8% → 97%+ (목표)

### 모니터링
- PR 이후 legal_review 정규식 오탐율 추적
- 금액 추출 정규화 안정성 모니터링

---

**상태**: 📋 Plan 완료 → ✅ Implementation 준비 완료
