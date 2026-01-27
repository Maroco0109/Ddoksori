# Legal Review Agent 인터페이스

> **담당 작업자**: Legal Review
> **역할**: 답변 검토, 금지표현 탐지, 출처 검증, 할루시네이션 검사

## 파이프라인 위치

```
[AnswerDrafter] → [LegalReviewer] → [최종 응답]
                        ↑
                   현재 에이전트
```

- **이전 단계**: AnswerDrafter (초안 답변)
- **다음 단계**: 최종 응답 (API Response)

---

## 입력 스펙 (Input Specification)

```python
from typing import List, Dict, Optional, Any
from typing_extensions import TypedDict


class ClaimEvidenceMapping(TypedDict):
    """주장-근거 매핑 (AnswerDrafter에서 전달)"""
    claim: str                        # 답변에 포함된 주장
    evidence_chunk_ids: List[str]     # 근거 청크 ID 목록
    evidence_texts: List[str]         # 근거 텍스트 목록
    grounded: bool                    # 근거 충분 여부


class RetrievalResult(TypedDict, total=False):
    """검색 결과 (출처 검증용)"""
    disputes: List[Dict[str, Any]]    # 분쟁조정 사례
    counsels: List[Dict[str, Any]]    # 상담 사례
    laws: List[Dict[str, Any]]        # 관련 법령
    criteria: List[Dict[str, Any]]    # 분쟁해결기준
    max_similarity: float
    avg_similarity: float


class ReviewInput(TypedDict):
    """법률검토 노드 입력"""
    draft_answer: str                              # 검토할 초안 답변 (필수)
    retrieval: RetrievalResult                     # 검색 결과 (필수)
    sources: List[Dict[str, Any]]                  # 인용 출처 목록 (필수)
    claim_evidence_map: List[ClaimEvidenceMapping] # 주장-근거 매핑 (필수)
```

### 입력 필드 설명

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `draft_answer` | `str` | ✅ | AnswerDrafter가 생성한 초안 답변 |
| `retrieval` | `RetrievalResult` | ✅ | 검색 결과 (출처 존재 여부 확인용) |
| `sources` | `List[Dict]` | ✅ | 답변에서 인용한 출처 목록 |
| `claim_evidence_map` | `List[ClaimEvidenceMapping]` | ✅ | 각 주장의 근거 매핑 |

---

## 출력 스펙 (Output Specification)

```python
from typing import List, Optional
from typing_extensions import TypedDict


class ReviewResult(TypedDict, total=False):
    """검토 결과 상세"""
    passed: bool                      # 검토 통과 여부 (필수)
    violations: List[str]             # 발견된 위반 사항 목록 (필수)
    filtered_answer: Optional[str]    # 위반 사항 수정 후 답변 (선택)


class ReviewOutput(TypedDict):
    """법률검토 노드 출력"""
    review: ReviewResult              # 검토 결과 상세 (필수)
    final_answer: Optional[str]       # 최종 확정 답변 (필수)
    retry_count: int                  # 재검토 횟수 (필수, 무한 루프 방지)
```

### 출력 필드 설명

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `review.passed` | `bool` | ✅ | 검토 통과 여부 |
| `review.violations` | `List[str]` | ✅ | 발견된 위반 사항 목록 |
| `review.filtered_answer` | `str` | ❌ | 자동 수정된 답변 (위반 시) |
| `final_answer` | `str` | ✅ | 최종 확정 답변 |
| `retry_count` | `int` | ✅ | 재검토 횟수 (최대 2회) |

---

## 검토 항목

### 1. 금지 표현 탐지

법률 도메인에서 사용하면 안 되는 표현을 탐지합니다.

| 유형 | 예시 | 심각도 |
|------|------|--------|
| 단정적 표현 | "반드시 ~해야 합니다", "100% ~" | HIGH |
| 법적 판단 | "승소하실 수 있습니다", "패소 가능성이 높습니다" | HIGH |
| 보장 표현 | "확실히 ~", "틀림없이 ~" | MEDIUM |
| 전문가 사칭 | "법적으로 ~입니다" (비전문가 답변에서) | MEDIUM |

### 2. 출처 검증

검색 결과가 있는데 인용이 없으면 위반입니다.

| 조건 | 판단 |
|------|------|
| 검색 결과 O, 인용 O | ✅ 통과 |
| 검색 결과 O, 인용 X | ❌ 위반 (출처 누락) |
| 검색 결과 X, 인용 X | ✅ 통과 (해당 없음) |

### 3. 할루시네이션 검사

`claim_evidence_map`을 기반으로 근거 없는 주장을 탐지합니다.

| 조건 | 판단 |
|------|------|
| `grounded: true` | ✅ 통과 |
| `grounded: false` | ⚠️ 경고 (근거 부족) |
| 매핑 없는 주장 | ❌ 위반 (할루시네이션 의심) |

---

## 코드 예시

### 입력 예시

```python
review_input = {
    "draft_answer": """헬스장 회원권 환불에 대해 안내해 드리겠습니다.

**환불 기준**
체육시설법 제17조에 따르면, 헬스장 회원권 중도해지 시:
- 잔여기간에 해당하는 이용료를 반드시 환급받으실 수 있습니다
- 위약금은 총 금액의 10%를 초과할 수 없습니다

**추천 기관**
한국소비자원(KCA)에 분쟁조정을 신청하시면 100% 해결됩니다.""",

    "retrieval": {
        "laws": [
            {"law_name": "체육시설법", "text": "...", "similarity": 0.9}
        ],
        "criteria": [
            {"unit_text": "위약금 10% 이내", "similarity": 0.85}
        ],
        "disputes": [
            {"doc_title": "헬스장 환불 사례", "similarity": 0.88}
        ],
        "counsels": [],
        "max_similarity": 0.9,
        "avg_similarity": 0.87
    },

    "sources": [
        {"type": "law", "name": "체육시설법", "article": "제17조"},
        {"type": "case", "title": "헬스장 환불 사례", "org": "KCA"}
    ],

    "claim_evidence_map": [
        {
            "claim": "위약금은 총 금액의 10%를 초과할 수 없습니다",
            "evidence_chunk_ids": ["law_001", "criteria_001"],
            "evidence_texts": ["체육시설법...", "위약금 10% 이내"],
            "grounded": True
        },
        {
            "claim": "분쟁조정을 신청하시면 100% 해결됩니다",
            "evidence_chunk_ids": [],
            "evidence_texts": [],
            "grounded": False
        }
    ]
}
```

### 출력 예시 - 위반 사항 발견

```python
output_with_violations = {
    "review": {
        "passed": False,
        "violations": [
            "금지표현 탐지: '반드시 환급받으실 수 있습니다' - 단정적 표현",
            "금지표현 탐지: '100% 해결됩니다' - 보장 표현",
            "근거 부족: '분쟁조정을 신청하시면 100% 해결됩니다' - grounded=False"
        ],
        "filtered_answer": """헬스장 회원권 환불에 대해 안내해 드리겠습니다.

**환불 기준**
체육시설법 제17조에 따르면, 헬스장 회원권 중도해지 시:
- 잔여기간에 해당하는 이용료를 환급받으실 수 있습니다
- 위약금은 총 금액의 10%를 초과할 수 없습니다

**추천 기관**
한국소비자원(KCA)에 분쟁조정을 신청하실 수 있습니다."""
    },
    "final_answer": """헬스장 회원권 환불에 대해 안내해 드리겠습니다.

**환불 기준**
체육시설법 제17조에 따르면, 헬스장 회원권 중도해지 시:
- 잔여기간에 해당하는 이용료를 환급받으실 수 있습니다
- 위약금은 총 금액의 10%를 초과할 수 없습니다

**추천 기관**
한국소비자원(KCA)에 분쟁조정을 신청하실 수 있습니다.""",
    "retry_count": 0
}
```

### 출력 예시 - 검토 통과

```python
output_passed = {
    "review": {
        "passed": True,
        "violations": [],
        "filtered_answer": None
    },
    "final_answer": """헬스장 회원권 환불에 대해 안내해 드리겠습니다.

체육시설법 제17조에 따르면, 헬스장 회원권 중도해지 시 잔여기간에 해당하는 이용료를 환급받으실 수 있으며, 위약금은 총 금액의 10%를 초과할 수 없습니다.

추가 도움이 필요하시면 한국소비자원(KCA)에 분쟁조정을 신청하실 수 있습니다.""",
    "retry_count": 0
}
```

### 출력 예시 - 재검토 필요 (심각한 위반)

```python
output_retry_needed = {
    "review": {
        "passed": False,
        "violations": [
            "심각한 위반: 법적 판단 제공 - '이 사건은 소비자가 승소할 것입니다'",
            "출처 없는 법령 인용: '민법 제750조' - 검색 결과에 없음"
        ],
        "filtered_answer": None  # 자동 수정 불가, 재생성 필요
    },
    "final_answer": None,  # 재생성 트리거
    "retry_count": 1       # 1회 재시도됨
}
```

---

## 테스트 가이드

### 단위 테스트 작성 방법

```python
# backend/scripts/testing/agents/test_review.py

import pytest
from app.agents.legal_review.agent import LegalReviewAgent
from app.agents.protocols import ReviewInput, ReviewOutput, validate_review_output


class TestLegalReviewAgent:
    """LegalReviewAgent 단위 테스트"""

    @pytest.fixture
    def agent(self):
        return LegalReviewAgent()

    @pytest.fixture
    def clean_input(self) -> ReviewInput:
        """위반 없는 입력"""
        return {
            "draft_answer": "체육시설법에 따르면 환불이 가능합니다.",
            "retrieval": {
                "laws": [{"text": "체육시설법...", "similarity": 0.9}],
                "criteria": [],
                "disputes": [],
                "counsels": [],
                "max_similarity": 0.9,
                "avg_similarity": 0.9
            },
            "sources": [{"type": "law", "name": "체육시설법"}],
            "claim_evidence_map": [
                {
                    "claim": "환불이 가능합니다",
                    "evidence_chunk_ids": ["law_001"],
                    "evidence_texts": ["체육시설법..."],
                    "grounded": True
                }
            ]
        }

    @pytest.fixture
    def violation_input(self) -> ReviewInput:
        """위반 있는 입력"""
        return {
            "draft_answer": "반드시 100% 환불받으실 수 있습니다!",
            "retrieval": {
                "laws": [],
                "criteria": [],
                "disputes": [],
                "counsels": [],
                "max_similarity": 0.0,
                "avg_similarity": 0.0
            },
            "sources": [],
            "claim_evidence_map": []
        }

    @pytest.mark.asyncio
    async def test_review_clean_answer_passes(self, agent, clean_input):
        """깨끗한 답변 통과 테스트"""
        result = await agent.review(clean_input)

        assert validate_review_output(result)
        assert result["review"]["passed"] == True
        assert len(result["review"]["violations"]) == 0
        assert result["final_answer"] is not None

    @pytest.mark.asyncio
    async def test_review_detects_prohibited_expressions(self, agent, violation_input):
        """금지 표현 탐지 테스트"""
        result = await agent.review(violation_input)

        assert result["review"]["passed"] == False
        violations = result["review"]["violations"]
        assert any("반드시" in v or "100%" in v for v in violations)

    @pytest.mark.asyncio
    async def test_review_filters_answer(self, agent, violation_input):
        """답변 필터링 테스트"""
        result = await agent.review(violation_input)

        if result["review"]["filtered_answer"]:
            filtered = result["review"]["filtered_answer"]
            assert "반드시" not in filtered
            assert "100%" not in filtered

    @pytest.mark.asyncio
    async def test_review_retry_count_limit(self, agent, violation_input):
        """재시도 횟수 제한 테스트"""
        result = await agent.review(violation_input)

        assert result["retry_count"] <= 2  # 최대 2회

    @pytest.mark.asyncio
    async def test_source_citation_check(self, agent):
        """출처 인용 검사 테스트"""
        input_no_citation = {
            "draft_answer": "법령에 따르면 환불 가능합니다.",
            "retrieval": {
                "laws": [{"text": "관련 법령", "similarity": 0.85}],
                "criteria": [],
                "disputes": [],
                "counsels": [],
                "max_similarity": 0.85,
                "avg_similarity": 0.85
            },
            "sources": [],  # 출처 없음!
            "claim_evidence_map": []
        }

        result = await agent.review(input_no_citation)

        # 검색 결과가 있는데 출처가 없으면 경고
        violations = result["review"]["violations"]
        assert any("출처" in v or "인용" in v for v in violations)

    @pytest.mark.asyncio
    async def test_hallucination_detection(self, agent):
        """할루시네이션 탐지 테스트"""
        input_hallucination = {
            "draft_answer": "민법 제999조에 따르면 전액 환불됩니다.",
            "retrieval": {
                "laws": [],  # 민법 검색 결과 없음
                "criteria": [],
                "disputes": [],
                "counsels": [],
                "max_similarity": 0.0,
                "avg_similarity": 0.0
            },
            "sources": [{"type": "law", "name": "민법", "article": "제999조"}],
            "claim_evidence_map": [
                {
                    "claim": "민법 제999조에 따르면 전액 환불됩니다",
                    "evidence_chunk_ids": [],
                    "evidence_texts": [],
                    "grounded": False
                }
            ]
        }

        result = await agent.review(input_hallucination)

        assert result["review"]["passed"] == False
        violations = result["review"]["violations"]
        assert any("근거" in v or "grounded" in v.lower() for v in violations)
```

### Mock 데이터 생성

```python
# backend/scripts/testing/fixtures/review_fixtures.py

def create_mock_review_input(
    answer: str = "테스트 답변",
    has_evidence: bool = True,
    has_violations: bool = False
) -> ReviewInput:
    """테스트용 검토 입력 생성"""

    if has_violations:
        answer = "반드시 100% 승소합니다! " + answer

    return {
        "draft_answer": answer,
        "retrieval": {
            "laws": [{"text": "관련 법령", "similarity": 0.9}] if has_evidence else [],
            "criteria": [],
            "disputes": [],
            "counsels": [],
            "max_similarity": 0.9 if has_evidence else 0.0,
            "avg_similarity": 0.9 if has_evidence else 0.0
        },
        "sources": [{"type": "law", "name": "테스트법"}] if has_evidence else [],
        "claim_evidence_map": [
            {
                "claim": answer[:50],
                "evidence_chunk_ids": ["chunk_001"] if has_evidence else [],
                "evidence_texts": ["근거 텍스트"] if has_evidence else [],
                "grounded": has_evidence
            }
        ]
    }


def create_mock_review_output(
    passed: bool = True,
    violations: list = None,
    answer: str = "최종 답변"
) -> ReviewOutput:
    """테스트용 검토 출력 생성"""
    return {
        "review": {
            "passed": passed,
            "violations": violations or [],
            "filtered_answer": None if passed else "수정된 답변"
        },
        "final_answer": answer,
        "retry_count": 0
    }
```

### 테스트 실행

```bash
# Legal Review 테스트
conda run -n dsr pytest backend/scripts/testing/agents/test_review.py -v

# 특정 테스트만 실행
conda run -n dsr pytest backend/scripts/testing/agents/test_review.py::TestLegalReviewAgent::test_review_detects_prohibited_expressions -v

# 단위 테스트만 (LLM 불필요)
conda run -n dsr pytest backend/scripts/testing/agents/test_review.py -m "not llm" -v
```

---

## 금지 표현 패턴 (참고)

```python
PROHIBITED_PATTERNS = [
    # 단정적 표현
    r"반드시\s+.{0,20}(해야|하셔야|합니다)",
    r"100%",
    r"확실히",
    r"틀림없이",
    r"절대(로)?",

    # 법적 판단
    r"승소.{0,10}(할|하실|됩니다)",
    r"패소.{0,10}(할|하실|됩니다)",
    r"(승소|패소)\s*가능성",
    r"법적으로\s+.{0,30}(입니다|됩니다)",

    # 보장 표현
    r"보장.{0,10}(합니다|드립니다)",
    r"(해결|환불).{0,10}(됩니다|받으실)",
]
```

---

## Fast Path 최적화

특정 쿼리 유형은 Legal Review를 건너뜁니다:

| query_type | Legal Review |
|------------|--------------|
| `general` | ❌ 스킵 |
| `system_meta` | ❌ 스킵 |
| `dispute` | ✅ 실행 |
| `law` | ✅ 실행 |
| `criteria` | ✅ 실행 |

---

## 검증 함수

```python
from app.agents.protocols import validate_review_output

output = await agent.review(input_data)
is_valid = validate_review_output(output)
assert is_valid, "출력이 프로토콜을 만족하지 않습니다"
```

---

## 참고 파일

| 파일 | 설명 |
|------|------|
| `app/agents/protocols.py` | 전체 타입 정의 |
| `app/agents/legal_review/agent.py` | 에이전트 구현체 |
| `app/agents/legal_review/patterns.py` | 금지 표현 패턴 |
| `app/agents/legal_review/prompts.py` | LLM 검토 프롬프트 |
