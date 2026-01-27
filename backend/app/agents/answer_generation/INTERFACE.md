# Answer Generator Agent 인터페이스

> **담당 작업자**: Answer Generator
> **역할**: 검색 결과 기반 LLM 답변 생성, 주장-근거 매핑

## 파이프라인 위치

```
[Retrieval Agents] → [AnswerDrafter] → [LegalReviewer]
                          ↑
                     현재 에이전트
```

- **이전 단계**: 4개 Retrieval Agent (병합된 검색 결과)
- **다음 단계**: LegalReviewer (법률 검토)

---

## 입력 스펙 (Input Specification)

```python
from typing import List, Dict, Optional, Literal, Any
from typing_extensions import TypedDict


class QueryAnalysisResult(TypedDict, total=False):
    """질의분석 결과 (이전 단계에서 전달)"""
    query_type: Literal['dispute', 'general', 'law', 'criteria', 'system_meta', 'ambiguous']
    keywords: List[str]
    rewritten_query: str
    search_queries: List[str]
    needs_clarification: bool
    extracted_info: Dict[str, str]


class AgencyInfo(TypedDict, total=False):
    """기관 추천 정보"""
    agency: str               # KCA, ECMC, KCDRC
    dispute_type: str         # 1:N, 1:1, contents
    reason: str
    confidence: float
    matched_keywords: List[str]


class RetrievalResult(TypedDict, total=False):
    """4섹션 검색 결과 (Retrieval Agent들의 병합 결과)"""
    agency: AgencyInfo
    disputes: List[Dict[str, Any]]    # 분쟁조정 사례
    counsels: List[Dict[str, Any]]    # 상담 사례
    laws: List[Dict[str, Any]]        # 관련 법령
    criteria: List[Dict[str, Any]]    # 분쟁해결기준
    max_similarity: float
    avg_similarity: float


class OnboardingInfo(TypedDict, total=False):
    """온보딩 폼 데이터"""
    purchase_date: Optional[str]
    purchase_place: Optional[str]
    purchase_platform: Optional[str]
    purchase_item: Optional[str]
    purchase_amount: Optional[str]
    dispute_details: Optional[str]


class GenerationInput(TypedDict):
    """답변생성 노드 입력"""
    user_query: str                              # 원본 사용자 쿼리 (필수)
    retrieval: RetrievalResult                   # 검색 결과 (필수)
    query_analysis: QueryAnalysisResult          # 질의분석 결과 (필수)
    onboarding: Optional[OnboardingInfo]         # 온보딩 폼 데이터 (선택)
    chat_type: Literal['dispute', 'general']     # 채팅 유형 (필수)
```

### 입력 필드 설명

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `user_query` | `str` | ✅ | 사용자가 입력한 원본 질문 |
| `retrieval` | `RetrievalResult` | ✅ | 4개 Retrieval Agent 병합 결과 |
| `query_analysis` | `QueryAnalysisResult` | ✅ | QueryAnalyst 분석 결과 |
| `onboarding` | `OnboardingInfo` | ❌ | 분쟁 상담 시 온보딩 데이터 |
| `chat_type` | `Literal['dispute', 'general']` | ✅ | 채팅 유형 |

---

## 출력 스펙 (Output Specification)

```python
from typing import List
from typing_extensions import TypedDict


class ClaimEvidenceMapping(TypedDict):
    """주장-근거 매핑 (LegalReviewer 검증용)"""
    claim: str                        # 답변에 포함된 주장
    evidence_chunk_ids: List[str]     # 근거 청크 ID 목록
    evidence_texts: List[str]         # 근거 텍스트 목록
    grounded: bool                    # 근거 충분 여부


class GenerationOutput(TypedDict):
    """답변생성 노드 출력"""
    draft_answer: str                            # LLM이 생성한 초안 답변 (필수)
    has_sufficient_evidence: bool                # 근거 충분 여부 (필수)
    clarifying_questions: List[str]              # 추가 질문 목록 (필수)
    claim_evidence_map: List[ClaimEvidenceMapping]  # 주장-근거 매핑 (필수)
```

### 출력 필드 설명

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `draft_answer` | `str` | ✅ | LLM이 생성한 초안 답변 |
| `has_sufficient_evidence` | `bool` | ✅ | 검색 결과로 충분한 근거가 있는지 |
| `clarifying_questions` | `List[str]` | ✅ | 근거 부족 시 사용자에게 물어볼 질문 |
| `claim_evidence_map` | `List[ClaimEvidenceMapping]` | ✅ | 각 주장의 근거 매핑 |

---

## 코드 예시

### 입력 예시

```python
input_example = {
    "user_query": "헬스장 회원권 환불받고 싶은데 어떻게 해야 하나요?",
    "chat_type": "dispute",
    "onboarding": {
        "purchase_date": "2024-01-15",
        "purchase_item": "헬스장 회원권",
        "purchase_amount": "150만원"
    },
    "query_analysis": {
        "query_type": "dispute",
        "keywords": ["헬스장", "회원권", "환불"],
        "rewritten_query": "헬스장 회원권 중도해지 환불",
        "search_queries": ["헬스장 환불", "피트니스 중도해지"],
        "needs_clarification": False,
        "extracted_info": {"품목": "헬스장 회원권", "금액": "1500000"}
    },
    "retrieval": {
        "agency": {
            "agency": "KCA",
            "dispute_type": "1:N",
            "reason": "다수 피해 발생 가능 업종",
            "confidence": 0.85,
            "matched_keywords": ["헬스장", "회원권"]
        },
        "disputes": [
            {
                "doc_title": "헬스장 회원권 환불 사례",
                "content": "소비자가 헬스장 1년 회원권 구입 후 3개월 만에 해지를 요청...",
                "source_org": "KCA",
                "decision_date": "2023-06-15",
                "similarity": 0.89
            }
        ],
        "counsels": [
            {
                "content": "헬스장 회원권 환불 시 위약금은 총 금액의 10%를 초과할 수 없습니다...",
                "source_org": "Consumer24",
                "similarity": 0.82
            }
        ],
        "laws": [
            {
                "law_name": "체육시설의 설치·이용에 관한 법률",
                "full_path": "제17조 (회원권의 양도) > 제1항",
                "text": "체육시설업자는 회원이 이용계약을 해제·해지하는 경우...",
                "similarity": 0.91
            }
        ],
        "criteria": [
            {
                "source_label": "소비자분쟁해결기준",
                "category": "체육시설업",
                "item": "회원권",
                "unit_text": "중도해지 시 잔여기간 이용료 환급, 위약금 10% 이내",
                "similarity": 0.88
            }
        ],
        "max_similarity": 0.91,
        "avg_similarity": 0.85
    }
}
```

### 출력 예시

```python
# 충분한 근거가 있는 경우
output_with_evidence = {
    "draft_answer": """헬스장 회원권 환불에 대해 안내해 드리겠습니다.

**환불 기준**
체육시설법 제17조와 소비자분쟁해결기준에 따르면, 헬스장 회원권 중도해지 시:
- 잔여기간에 해당하는 이용료를 환급받을 수 있습니다
- 위약금은 총 금액의 10%를 초과할 수 없습니다

**환불 절차**
1. 헬스장에 서면으로 해지 의사 통보
2. 이용 기간과 잔여 금액 계산
3. 환급금 = 총 금액 - (이용 금액 + 위약금)

**유사 사례**
2023년 KCA 조정 사례에서 3개월 이용 후 해지 시 잔여 9개월분에서 위약금 10%를 공제하고 환급받은 사례가 있습니다.

추가 도움이 필요하시면 한국소비자원(KCA)에 분쟁조정을 신청하실 수 있습니다.""",

    "has_sufficient_evidence": True,

    "clarifying_questions": [],

    "claim_evidence_map": [
        {
            "claim": "위약금은 총 금액의 10%를 초과할 수 없습니다",
            "evidence_chunk_ids": ["chunk_criteria_001", "chunk_law_017"],
            "evidence_texts": [
                "중도해지 시 잔여기간 이용료 환급, 위약금 10% 이내",
                "체육시설업자는 회원이 이용계약을 해제·해지하는 경우..."
            ],
            "grounded": True
        },
        {
            "claim": "잔여기간에 해당하는 이용료를 환급받을 수 있습니다",
            "evidence_chunk_ids": ["chunk_criteria_001"],
            "evidence_texts": ["중도해지 시 잔여기간 이용료 환급, 위약금 10% 이내"],
            "grounded": True
        }
    ]
}

# 근거가 부족한 경우
output_insufficient_evidence = {
    "draft_answer": "죄송합니다. 제공해주신 정보만으로는 정확한 안내가 어렵습니다. 아래 정보를 추가로 알려주시면 더 정확한 답변을 드릴 수 있습니다.",

    "has_sufficient_evidence": False,

    "clarifying_questions": [
        "헬스장과 계약한 회원권 기간은 얼마인가요?",
        "현재까지 이용한 기간은 얼마나 되나요?",
        "계약서에 해지 관련 특약 조항이 있나요?"
    ],

    "claim_evidence_map": []
}
```

---

## 테스트 가이드

### 단위 테스트 작성 방법

```python
# backend/scripts/testing/agents/test_generation.py

import pytest
from app.agents.answer_generation.agent import AnswerGenerationAgent
from app.agents.protocols import GenerationInput, GenerationOutput, validate_generation_output


class TestAnswerGenerationAgent:
    """AnswerGenerationAgent 단위 테스트"""

    @pytest.fixture
    def agent(self):
        return AnswerGenerationAgent()

    @pytest.fixture
    def sample_input(self) -> GenerationInput:
        """테스트용 샘플 입력"""
        return {
            "user_query": "헬스장 환불 어떻게 하나요?",
            "chat_type": "dispute",
            "onboarding": None,
            "query_analysis": {
                "query_type": "dispute",
                "keywords": ["헬스장", "환불"],
                "rewritten_query": "헬스장 환불",
                "search_queries": ["헬스장 환불"],
                "needs_clarification": False,
                "extracted_info": {}
            },
            "retrieval": {
                "agency": {"agency": "KCA", "confidence": 0.8},
                "disputes": [{"content": "환불 사례...", "similarity": 0.85}],
                "counsels": [],
                "laws": [{"text": "체육시설법...", "similarity": 0.9}],
                "criteria": [],
                "max_similarity": 0.9,
                "avg_similarity": 0.87
            }
        }

    @pytest.mark.asyncio
    async def test_generate_answer_with_evidence(self, agent, sample_input):
        """근거가 있는 경우 답변 생성 테스트"""
        result = await agent.generate(sample_input)

        # 출력 형식 검증
        assert validate_generation_output(result)

        # 필수 필드 존재 확인
        assert "draft_answer" in result
        assert "has_sufficient_evidence" in result
        assert "claim_evidence_map" in result

        # 답변이 비어있지 않은지 확인
        assert len(result["draft_answer"]) > 0

    @pytest.mark.asyncio
    async def test_claim_evidence_mapping(self, agent, sample_input):
        """주장-근거 매핑 테스트"""
        result = await agent.generate(sample_input)

        if result["has_sufficient_evidence"]:
            # 근거가 있으면 매핑이 존재해야 함
            assert len(result["claim_evidence_map"]) > 0

            for mapping in result["claim_evidence_map"]:
                assert "claim" in mapping
                assert "evidence_chunk_ids" in mapping
                assert "grounded" in mapping

    @pytest.mark.asyncio
    async def test_insufficient_evidence_handling(self, agent):
        """근거 부족 시 처리 테스트"""
        input_no_evidence = {
            "user_query": "완전히 새로운 질문",
            "chat_type": "general",
            "onboarding": None,
            "query_analysis": {
                "query_type": "general",
                "keywords": [],
                "rewritten_query": "",
                "search_queries": [],
                "needs_clarification": False,
                "extracted_info": {}
            },
            "retrieval": {
                "disputes": [],
                "counsels": [],
                "laws": [],
                "criteria": [],
                "max_similarity": 0.0,
                "avg_similarity": 0.0
            }
        }

        result = await agent.generate(input_no_evidence)

        # 근거 부족 시 clarifying_questions가 있거나 has_sufficient_evidence=False
        if not result["has_sufficient_evidence"]:
            assert len(result["clarifying_questions"]) > 0 or "죄송" in result["draft_answer"]

    @pytest.mark.asyncio
    @pytest.mark.llm
    async def test_answer_quality(self, agent, sample_input):
        """답변 품질 테스트 (LLM 필요)"""
        result = await agent.generate(sample_input)

        # 답변에 핵심 키워드 포함 확인
        answer = result["draft_answer"].lower()
        assert any(kw in answer for kw in ["헬스장", "환불", "회원권"])
```

### Mock 데이터 생성

```python
# backend/scripts/testing/fixtures/generation_fixtures.py

def create_mock_retrieval_result(
    max_similarity: float = 0.85,
    has_disputes: bool = True,
    has_laws: bool = True
) -> dict:
    """테스트용 검색 결과 생성"""
    return {
        "agency": {"agency": "KCA", "confidence": 0.8} if max_similarity > 0.7 else None,
        "disputes": [
            {"content": "환불 사례 내용...", "similarity": 0.85, "doc_title": "사례1"}
        ] if has_disputes else [],
        "counsels": [],
        "laws": [
            {"text": "관련 법령 내용...", "similarity": 0.9, "law_name": "소비자기본법"}
        ] if has_laws else [],
        "criteria": [],
        "max_similarity": max_similarity,
        "avg_similarity": max_similarity * 0.9
    }


def create_mock_generation_input(
    query: str = "테스트 질문",
    with_evidence: bool = True
) -> GenerationInput:
    """테스트용 입력 생성"""
    return {
        "user_query": query,
        "chat_type": "dispute",
        "onboarding": None,
        "query_analysis": {
            "query_type": "dispute",
            "keywords": query.split()[:3],
            "rewritten_query": query,
            "search_queries": [query],
            "needs_clarification": False,
            "extracted_info": {}
        },
        "retrieval": create_mock_retrieval_result(
            max_similarity=0.85 if with_evidence else 0.2,
            has_disputes=with_evidence,
            has_laws=with_evidence
        )
    }
```

### 테스트 실행

```bash
# Answer Generation 테스트만 실행
conda run -n dsr pytest backend/scripts/testing/agents/test_generation.py -v

# LLM 테스트 제외 (API 키 불필요)
conda run -n dsr pytest backend/scripts/testing/agents/test_generation.py -v -m "not llm"

# 특정 테스트만 실행
conda run -n dsr pytest backend/scripts/testing/agents/test_generation.py::TestAnswerGenerationAgent::test_generate_answer_with_evidence -v
```

---

## Fallback 체인

답변 생성 실패 시 자동으로 다음 모델로 전환됩니다:

```
1. gpt-4o-mini (OpenAI) - 기본
       ↓ (타임아웃/실패)
2. claude-3-haiku (Anthropic) - 1차 폴백
       ↓ (타임아웃/실패)
3. rule_based (Local) - 2차 폴백
       ↓ (실패)
4. safe_fallback - 최종 안전 메시지
```

---

## 검증 함수

```python
from app.agents.protocols import validate_generation_output

output = await agent.generate(input_data)
is_valid = validate_generation_output(output)
assert is_valid, "출력이 프로토콜을 만족하지 않습니다"
```

---

## 참고 파일

| 파일 | 설명 |
|------|------|
| `app/agents/protocols.py` | 전체 타입 정의 |
| `app/agents/answer_generation/agent.py` | 에이전트 구현체 |
| `app/agents/answer_generation/prompts.py` | LLM 프롬프트 |
