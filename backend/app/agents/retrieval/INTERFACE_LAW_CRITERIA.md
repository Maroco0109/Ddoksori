# Legal & Criteria Retrieval Agent 인터페이스

> **담당 작업자**: Legal & Criteria
> **역할**: 법령 검색 (LawRetrievalAgent), 분쟁해결기준 검색 (CriteriaRetrievalAgent)

## 파이프라인 위치

```
[QueryAnalyst] → [LawAgent + CriteriaAgent] → [retrieval_merge] → [AnswerDrafter]
                        ↑
                   현재 에이전트들
                  (병렬 실행)
```

- **이전 단계**: QueryAnalyst (질의분석 결과)
- **다음 단계**: retrieval_merge 노드 (4개 Agent 결과 병합)
- **병렬 실행**: CaseAgent, CounselAgent와 동시에 실행됨

---

## 공통 입력 스펙 (Input Specification)

두 에이전트 모두 동일한 입력 형식을 사용합니다.

```python
from typing import List, Dict, Optional, Literal
from typing_extensions import TypedDict


class QueryAnalysisResult(TypedDict, total=False):
    """질의분석 결과"""
    query_type: Literal['dispute', 'general', 'law', 'criteria', 'system_meta', 'ambiguous']
    keywords: List[str]
    rewritten_query: str              # ⭐ 검색에 사용할 핵심 쿼리
    search_queries: List[str]         # 다중 검색용 쿼리 (최대 4개)
    needs_clarification: bool
    extracted_info: Dict[str, str]


class RetrievalAgentInput(TypedDict):
    """Retrieval Agent 공통 입력"""
    context: dict                     # 컨텍스트 정보 (필수)
    params: dict                      # 검색 파라미터 (필수)


# context 상세 구조
class RetrievalContext(TypedDict):
    """컨텍스트 상세"""
    user_query: str                   # 원본 사용자 쿼리
    query_analysis: QueryAnalysisResult  # 질의분석 결과


# params 상세 구조
class RetrievalParams(TypedDict, total=False):
    """검색 파라미터"""
    top_k: int                        # 검색 결과 개수 (기본값: 3)
```

### 입력 필드 설명

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `context.user_query` | `str` | ✅ | 사용자 원본 질문 |
| `context.query_analysis` | `QueryAnalysisResult` | ✅ | 질의분석 결과 |
| `params.top_k` | `int` | ❌ | 검색 결과 개수 (기본: 3) |

---

## LawRetrievalAgent 출력 스펙

```python
from typing import List, Optional
from typing_extensions import TypedDict


class LawDocument(TypedDict):
    """법령 문서"""
    law_name: str                     # 법령명 (예: "소비자기본법")
    full_path: str                    # 계층 경로 (예: "제1장 > 제1조 > 제1항")
    text: str                         # 법령 본문
    similarity: float                 # 유사도 점수 (0.0~1.0)
    unit_id: Optional[str]            # 청크 ID (선택)


class LawRetrievalOutput(TypedDict):
    """법령 검색 결과"""
    source: Literal["law"]            # 고정값: "law"
    documents: List[LawDocument]      # 검색된 법령 목록
    max_similarity: float             # 최대 유사도
    avg_similarity: float             # 평균 유사도
    search_time_ms: float             # 검색 소요 시간 (ms)
    error: Optional[str]              # 에러 메시지 (실패 시)
```

### LawDocument 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `law_name` | `str` | 법령 이름 (예: "소비자기본법", "전자상거래법") |
| `full_path` | `str` | 법령 내 위치 (예: "제2장 > 제7조 > 제1항") |
| `text` | `str` | 법령 조문 본문 |
| `similarity` | `float` | 쿼리와의 유사도 (0.0~1.0) |

---

## CriteriaRetrievalAgent 출력 스펙

```python
from typing import List, Optional
from typing_extensions import TypedDict


class CriteriaDocument(TypedDict):
    """분쟁해결기준 문서"""
    source_label: str                 # 출처 (예: "소비자분쟁해결기준", "공정위 고시")
    category: str                     # 대분류 (예: "체육시설업", "전자상거래")
    item: str                         # 품목 (예: "헬스장 회원권", "노트북")
    unit_text: str                    # 기준 내용
    similarity: float                 # 유사도 점수
    title: Optional[str]              # 제목 (선택)
    unit_id: Optional[str]            # 청크 ID (선택)


class CriteriaRetrievalOutput(TypedDict):
    """분쟁해결기준 검색 결과"""
    source: Literal["criteria"]       # 고정값: "criteria"
    documents: List[CriteriaDocument] # 검색된 기준 목록
    max_similarity: float             # 최대 유사도
    avg_similarity: float             # 평균 유사도
    search_time_ms: float             # 검색 소요 시간 (ms)
    error: Optional[str]              # 에러 메시지 (실패 시)
```

### CriteriaDocument 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `source_label` | `str` | 기준 출처 |
| `category` | `str` | 업종/분야 대분류 |
| `item` | `str` | 구체적 품목 |
| `unit_text` | `str` | 해결 기준 내용 |
| `similarity` | `float` | 쿼리와의 유사도 |

---

## 코드 예시

### 입력 예시

```python
# 법령 검색 입력
law_input = {
    "context": {
        "user_query": "헬스장 회원권 환불 규정이 어떻게 되나요?",
        "query_analysis": {
            "query_type": "law",
            "keywords": ["헬스장", "회원권", "환불", "규정"],
            "rewritten_query": "체육시설 회원권 환불 법률 규정",
            "search_queries": [
                "헬스장 회원권 환불",
                "체육시설법 회원권 해지",
                "피트니스 환불 규정"
            ],
            "needs_clarification": False,
            "extracted_info": {"품목": "헬스장 회원권"}
        }
    },
    "params": {
        "top_k": 3
    }
}

# 분쟁해결기준 검색 입력 (동일 형식)
criteria_input = {
    "context": {
        "user_query": "헬스장 회원권 환불 기준이 어떻게 되나요?",
        "query_analysis": {
            "query_type": "criteria",
            "keywords": ["헬스장", "회원권", "환불", "기준"],
            "rewritten_query": "체육시설업 회원권 환불 분쟁해결기준",
            "search_queries": [
                "헬스장 환불 기준",
                "피트니스 위약금 기준"
            ],
            "needs_clarification": False,
            "extracted_info": {"품목": "헬스장 회원권"}
        }
    },
    "params": {
        "top_k": 3
    }
}
```

### LawRetrievalAgent 출력 예시

```python
law_output = {
    "source": "law",
    "documents": [
        {
            "law_name": "체육시설의 설치·이용에 관한 법률",
            "full_path": "제17조 (회원권의 양도) > 제1항",
            "text": "체육시설업자는 회원이 이용계약을 해제·해지하는 경우 회원에게 잔여 이용료를 반환하여야 한다.",
            "similarity": 0.92,
            "unit_id": "law_chunk_001"
        },
        {
            "law_name": "체육시설의 설치·이용에 관한 법률 시행령",
            "full_path": "제18조 (환불 기준) > 제2항",
            "text": "회원권 해지 시 위약금은 총 이용료의 10퍼센트를 초과할 수 없다.",
            "similarity": 0.88,
            "unit_id": "law_chunk_002"
        },
        {
            "law_name": "소비자기본법",
            "full_path": "제16조 (소비자의 권리) > 제3항",
            "text": "소비자는 물품 등의 사용으로 인하여 입은 피해에 대하여 신속·공정한 절차에 따라 적절한 보상을 받을 권리를 가진다.",
            "similarity": 0.75,
            "unit_id": "law_chunk_003"
        }
    ],
    "max_similarity": 0.92,
    "avg_similarity": 0.85,
    "search_time_ms": 145.3,
    "error": None
}
```

### CriteriaRetrievalAgent 출력 예시

```python
criteria_output = {
    "source": "criteria",
    "documents": [
        {
            "source_label": "소비자분쟁해결기준",
            "category": "체육시설업",
            "item": "회원권 (헬스장, 수영장 등)",
            "unit_text": "중도해지 시 잔여기간 이용료 환급. 위약금은 총 이용료의 10% 이내로 제한.",
            "similarity": 0.91,
            "title": "체육시설업 회원권 환불 기준",
            "unit_id": "criteria_chunk_001"
        },
        {
            "source_label": "소비자분쟁해결기준",
            "category": "체육시설업",
            "item": "PT(개인 트레이닝)",
            "unit_text": "PT 이용권 중도해지 시 미이용 횟수에 해당하는 금액 환급. 위약금 10% 이내.",
            "similarity": 0.78,
            "title": "PT 이용권 환불 기준",
            "unit_id": "criteria_chunk_002"
        }
    ],
    "max_similarity": 0.91,
    "avg_similarity": 0.85,
    "search_time_ms": 128.7,
    "error": None
}
```

### 에러 발생 시 출력 예시

```python
error_output = {
    "source": "law",  # 또는 "criteria"
    "documents": [],
    "max_similarity": 0.0,
    "avg_similarity": 0.0,
    "search_time_ms": 50.0,
    "error": "Database connection timeout"
}
```

---

## 테스트 가이드

### 단위 테스트 작성 방법

```python
# backend/scripts/testing/agents/test_retrieval_law_criteria.py

import pytest
from app.agents.retrieval.law_agent import LawRetrievalAgent
from app.agents.retrieval.criteria_agent import CriteriaRetrievalAgent


class TestLawRetrievalAgent:
    """LawRetrievalAgent 단위 테스트"""

    @pytest.fixture
    def agent(self):
        return LawRetrievalAgent()

    @pytest.fixture
    def sample_input(self) -> dict:
        return {
            "context": {
                "user_query": "헬스장 환불",
                "query_analysis": {
                    "query_type": "law",
                    "keywords": ["헬스장", "환불"],
                    "rewritten_query": "체육시설 회원권 환불",
                    "search_queries": ["헬스장 환불"],
                    "needs_clarification": False,
                    "extracted_info": {}
                }
            },
            "params": {"top_k": 3}
        }

    @pytest.mark.asyncio
    async def test_law_search_output_format(self, agent, sample_input):
        """출력 형식 테스트"""
        result = await agent.process(sample_input)

        # 필수 필드 확인
        assert result["source"] == "law"
        assert "documents" in result
        assert "max_similarity" in result
        assert "search_time_ms" in result

    @pytest.mark.asyncio
    async def test_law_document_structure(self, agent, sample_input):
        """법령 문서 구조 테스트"""
        result = await agent.process(sample_input)

        if result["documents"]:
            doc = result["documents"][0]
            assert "law_name" in doc
            assert "full_path" in doc
            assert "text" in doc
            assert "similarity" in doc
            assert 0.0 <= doc["similarity"] <= 1.0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_law_search_relevance(self, agent, sample_input):
        """검색 관련성 테스트 (DB 필요)"""
        result = await agent.process(sample_input)

        # 관련 법령이 검색되어야 함
        if result["documents"]:
            law_names = [d["law_name"] for d in result["documents"]]
            assert any("체육시설" in name or "소비자" in name for name in law_names)


class TestCriteriaRetrievalAgent:
    """CriteriaRetrievalAgent 단위 테스트"""

    @pytest.fixture
    def agent(self):
        return CriteriaRetrievalAgent()

    @pytest.fixture
    def sample_input(self) -> dict:
        return {
            "context": {
                "user_query": "헬스장 환불 기준",
                "query_analysis": {
                    "query_type": "criteria",
                    "keywords": ["헬스장", "환불", "기준"],
                    "rewritten_query": "체육시설업 환불 분쟁해결기준",
                    "search_queries": ["헬스장 환불 기준"],
                    "needs_clarification": False,
                    "extracted_info": {}
                }
            },
            "params": {"top_k": 3}
        }

    @pytest.mark.asyncio
    async def test_criteria_search_output_format(self, agent, sample_input):
        """출력 형식 테스트"""
        result = await agent.process(sample_input)

        assert result["source"] == "criteria"
        assert "documents" in result
        assert "max_similarity" in result

    @pytest.mark.asyncio
    async def test_criteria_document_structure(self, agent, sample_input):
        """기준 문서 구조 테스트"""
        result = await agent.process(sample_input)

        if result["documents"]:
            doc = result["documents"][0]
            assert "source_label" in doc
            assert "category" in doc
            assert "item" in doc
            assert "unit_text" in doc
            assert "similarity" in doc

    @pytest.mark.asyncio
    async def test_error_handling(self, agent):
        """에러 처리 테스트"""
        invalid_input = {
            "context": {
                "user_query": "",
                "query_analysis": {}
            },
            "params": {}
        }

        result = await agent.process(invalid_input)

        # 에러 시에도 기본 구조 유지
        assert "source" in result
        assert "documents" in result
        assert isinstance(result["documents"], list)
```

### Mock 데이터 생성

```python
# backend/scripts/testing/fixtures/retrieval_fixtures.py

def create_mock_law_output(
    num_docs: int = 2,
    max_sim: float = 0.9
) -> dict:
    """테스트용 법령 검색 결과 생성"""
    docs = [
        {
            "law_name": f"테스트법률 {i+1}",
            "full_path": f"제{i+1}조 > 제1항",
            "text": f"테스트 법령 내용 {i+1}",
            "similarity": max_sim - (i * 0.1),
            "unit_id": f"law_chunk_{i:03d}"
        }
        for i in range(num_docs)
    ]

    return {
        "source": "law",
        "documents": docs,
        "max_similarity": max_sim,
        "avg_similarity": sum(d["similarity"] for d in docs) / len(docs) if docs else 0,
        "search_time_ms": 100.0,
        "error": None
    }


def create_mock_criteria_output(
    num_docs: int = 2,
    max_sim: float = 0.85
) -> dict:
    """테스트용 분쟁해결기준 결과 생성"""
    docs = [
        {
            "source_label": "소비자분쟁해결기준",
            "category": f"테스트업종 {i+1}",
            "item": f"테스트품목 {i+1}",
            "unit_text": f"테스트 기준 내용 {i+1}",
            "similarity": max_sim - (i * 0.1),
            "unit_id": f"criteria_chunk_{i:03d}"
        }
        for i in range(num_docs)
    ]

    return {
        "source": "criteria",
        "documents": docs,
        "max_similarity": max_sim,
        "avg_similarity": sum(d["similarity"] for d in docs) / len(docs) if docs else 0,
        "search_time_ms": 80.0,
        "error": None
    }
```

### 테스트 실행

```bash
# Law & Criteria Retrieval 테스트
conda run -n dsr pytest backend/scripts/testing/agents/test_retrieval_law_criteria.py -v

# 단위 테스트만 (DB 불필요)
conda run -n dsr pytest backend/scripts/testing/agents/test_retrieval_law_criteria.py -m "not integration" -v

# 특정 에이전트만
conda run -n dsr pytest backend/scripts/testing/agents/test_retrieval_law_criteria.py::TestLawRetrievalAgent -v
```

---

## 결과 병합 방식

4개 Retrieval Agent 결과는 `retrieval_merge` 노드에서 병합됩니다:

```python
# retrieval_merge 노드에서의 처리
merged_retrieval = {
    "laws": law_output["documents"],           # LawRetrievalAgent
    "criteria": criteria_output["documents"],  # CriteriaRetrievalAgent
    "disputes": case_output["documents"],      # CaseRetrievalAgent
    "counsels": counsel_output["documents"],   # CounselRetrievalAgent
    "max_similarity": max(all_max_similarities),
    "avg_similarity": average(all_avg_similarities)
}
```

---

## 참고 파일

| 파일 | 설명 |
|------|------|
| `app/agents/protocols.py` | 전체 타입 정의 |
| `app/agents/retrieval/base_retrieval_agent.py` | Retrieval 베이스 클래스 |
| `app/agents/retrieval/law_agent.py` | LawRetrievalAgent 구현 |
| `app/agents/retrieval/criteria_agent.py` | CriteriaRetrievalAgent 구현 |
| `app/supervisor/nodes/retrieval_merge.py` | 결과 병합 로직 |
