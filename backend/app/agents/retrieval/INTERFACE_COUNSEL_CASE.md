# Counsel & Dispute Retrieval Agent 인터페이스

> **담당 작업자**: Counsel & Dispute
> **역할**: 상담사례 검색 (CounselRetrievalAgent), 분쟁조정사례 검색 (CaseRetrievalAgent)

## 파이프라인 위치

```
[QueryAnalyst] → [CounselAgent + CaseAgent] → [retrieval_merge] → [AnswerDrafter]
                          ↑
                     현재 에이전트들
                     (병렬 실행)
```

- **이전 단계**: QueryAnalyst (질의분석 결과)
- **다음 단계**: retrieval_merge 노드 (4개 Agent 결과 병합)
- **병렬 실행**: LawAgent, CriteriaAgent와 동시에 실행됨

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

## CaseRetrievalAgent 출력 스펙 (분쟁조정사례)

```python
from typing import List, Optional
from typing_extensions import TypedDict


class CaseDocument(TypedDict):
    """분쟁조정사례 문서"""
    doc_title: str                    # 사례 제목
    content: str                      # 사례 내용 (요약 또는 전문)
    source_org: str                   # 기관명 (KCA, ECMC, KCDRC)
    decision_date: str                # 결정일자 (YYYY-MM-DD)
    similarity: float                 # 유사도 점수 (0.0~1.0)
    chunk_id: Optional[str]           # 청크 ID
    doc_id: Optional[str]             # 문서 ID
    chunk_type: Optional[str]         # 청크 유형 (summary, full 등)
    url: Optional[str]                # 원문 URL


class CaseRetrievalOutput(TypedDict):
    """분쟁조정사례 검색 결과"""
    source: Literal["case"]           # 고정값: "case"
    documents: List[CaseDocument]     # 검색된 사례 목록
    max_similarity: float             # 최대 유사도
    avg_similarity: float             # 평균 유사도
    search_time_ms: float             # 검색 소요 시간 (ms)
    error: Optional[str]              # 에러 메시지 (실패 시)
```

### CaseDocument 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `doc_title` | `str` | 분쟁조정 사례 제목 |
| `content` | `str` | 사례 내용 (분쟁 내용, 결정 사항 등) |
| `source_org` | `str` | 출처 기관 (KCA: 한국소비자원, ECMC: 전자거래분쟁조정위원회, KCDRC: 콘텐츠분쟁조정위원회) |
| `decision_date` | `str` | 조정 결정 일자 |
| `similarity` | `float` | 쿼리와의 유사도 (0.0~1.0) |

### source_org 코드 설명

| 코드 | 기관명 | 관할 |
|------|--------|------|
| `KCA` | 한국소비자원 | 일반 소비자 분쟁 |
| `ECMC` | 전자거래분쟁조정위원회 | 전자상거래 분쟁 |
| `KCDRC` | 콘텐츠분쟁조정위원회 | 디지털 콘텐츠 분쟁 |

---

## CounselRetrievalAgent 출력 스펙 (상담사례)

```python
from typing import List, Optional
from typing_extensions import TypedDict


class CounselDocument(TypedDict):
    """상담사례 문서"""
    content: str                      # 상담 내용 (질문+답변)
    source_org: str                   # 출처 (Consumer24 등)
    similarity: float                 # 유사도 점수 (0.0~1.0)
    chunk_id: Optional[str]           # 청크 ID
    doc_id: Optional[str]             # 문서 ID
    chunk_type: Optional[str]         # 청크 유형
    url: Optional[str]                # 원문 URL


class CounselRetrievalOutput(TypedDict):
    """상담사례 검색 결과"""
    source: Literal["counsel"]        # 고정값: "counsel"
    documents: List[CounselDocument]  # 검색된 상담 목록
    max_similarity: float             # 최대 유사도
    avg_similarity: float             # 평균 유사도
    search_time_ms: float             # 검색 소요 시간 (ms)
    error: Optional[str]              # 에러 메시지 (실패 시)
```

### CounselDocument 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `content` | `str` | 상담 내용 (소비자 질문과 상담원 답변) |
| `source_org` | `str` | 출처 (주로 Consumer24) |
| `similarity` | `float` | 쿼리와의 유사도 (0.0~1.0) |

---

## 코드 예시

### 입력 예시

```python
# 분쟁조정사례 검색 입력
case_input = {
    "context": {
        "user_query": "헬스장 회원권 환불 사례가 있나요?",
        "query_analysis": {
            "query_type": "dispute",
            "keywords": ["헬스장", "회원권", "환불", "사례"],
            "rewritten_query": "헬스장 회원권 환불 분쟁조정 사례",
            "search_queries": [
                "헬스장 회원권 환불",
                "피트니스 중도해지 분쟁",
                "체육시설 환불 조정"
            ],
            "needs_clarification": False,
            "extracted_info": {"품목": "헬스장 회원권"}
        }
    },
    "params": {
        "top_k": 3
    }
}

# 상담사례 검색 입력 (동일 형식)
counsel_input = {
    "context": {
        "user_query": "헬스장 환불 관련 상담 내용 알려주세요",
        "query_analysis": {
            "query_type": "dispute",
            "keywords": ["헬스장", "환불", "상담"],
            "rewritten_query": "헬스장 회원권 환불 상담",
            "search_queries": [
                "헬스장 환불 상담",
                "피트니스 해지 문의"
            ],
            "needs_clarification": False,
            "extracted_info": {}
        }
    },
    "params": {
        "top_k": 3
    }
}
```

### CaseRetrievalAgent 출력 예시

```python
case_output = {
    "source": "case",
    "documents": [
        {
            "doc_title": "헬스장 회원권 중도해지 환불 분쟁",
            "content": """[분쟁 내용]
소비자가 헬스장 1년 회원권(150만원)을 구입한 후 3개월 이용 후 개인 사정으로 해지를 요청하였으나, 사업자가 위약금 30%를 공제한다고 주장함.

[결정 사항]
체육시설법 및 소비자분쟁해결기준에 따라 위약금은 10%를 초과할 수 없음.
- 환급액: 150만원 - (3개월분 37.5만원) - (위약금 15만원) = 97.5만원
- 사업자는 소비자에게 97.5만원을 환급해야 함.""",
            "source_org": "KCA",
            "decision_date": "2023-06-15",
            "similarity": 0.91,
            "chunk_id": "case_chunk_001",
            "doc_id": "kca_2023_0615",
            "chunk_type": "summary",
            "url": "https://www.kca.go.kr/case/2023/0615"
        },
        {
            "doc_title": "피트니스센터 장기계약 해지 분쟁",
            "content": """[분쟁 내용]
소비자가 2년 장기 회원권 계약 후 6개월 만에 이사로 인해 해지를 요청. 사업자는 장기할인을 적용했으므로 할인액을 환수하겠다고 주장.

[결정 사항]
장기할인 환수는 부당하며, 잔여기간 이용료에서 위약금 10% 공제 후 환급.
- 중도해지 시 할인 혜택 환수 조항은 소비자에게 부당하게 불리한 약관.""",
            "source_org": "KCA",
            "decision_date": "2023-08-22",
            "similarity": 0.85,
            "chunk_id": "case_chunk_002",
            "doc_id": "kca_2023_0822",
            "chunk_type": "summary",
            "url": None
        }
    ],
    "max_similarity": 0.91,
    "avg_similarity": 0.88,
    "search_time_ms": 167.5,
    "error": None
}
```

### CounselRetrievalAgent 출력 예시

```python
counsel_output = {
    "source": "counsel",
    "documents": [
        {
            "content": """[질문]
헬스장에서 1년 회원권을 끊었는데 3개월밖에 안 다녔어요. 환불받을 수 있나요? 계약서에는 환불 불가라고 적혀있는데...

[답변]
헬스장 회원권은 「체육시설의 설치·이용에 관한 법률」의 적용을 받습니다.
해당 법률에 따르면 회원권 계약 해지 시 잔여기간에 해당하는 이용료를 환급받을 수 있으며, 위약금은 10%를 초과할 수 없습니다.
계약서에 '환불 불가'라고 적혀있더라도 이는 법률에 반하는 조항으로 무효입니다.
환불을 거부할 경우 1372 소비자상담센터나 한국소비자원에 분쟁조정을 신청하실 수 있습니다.""",
            "source_org": "Consumer24",
            "similarity": 0.88,
            "chunk_id": "counsel_chunk_001",
            "doc_id": "c24_2023_10001",
            "chunk_type": "qa_pair",
            "url": None
        },
        {
            "content": """[질문]
PT 이용권도 환불 가능한가요? 50회 중 10회만 사용했어요.

[답변]
네, PT 이용권도 환불 가능합니다.
미이용 횟수(40회)에 해당하는 금액에서 위약금 10%를 공제하고 환급받으실 수 있습니다.
다만, PT는 회원권과 별도 계약이므로 각각 해지 절차를 진행해야 합니다.""",
            "source_org": "Consumer24",
            "similarity": 0.75,
            "chunk_id": "counsel_chunk_002",
            "doc_id": "c24_2023_10002",
            "chunk_type": "qa_pair",
            "url": None
        }
    ],
    "max_similarity": 0.88,
    "avg_similarity": 0.82,
    "search_time_ms": 132.8,
    "error": None
}
```

### 에러 발생 시 출력 예시

```python
error_output = {
    "source": "case",  # 또는 "counsel"
    "documents": [],
    "max_similarity": 0.0,
    "avg_similarity": 0.0,
    "search_time_ms": 45.0,
    "error": "Search timeout: exceeded 5000ms"
}
```

---

## 테스트 가이드

### 단위 테스트 작성 방법

```python
# backend/scripts/testing/agents/test_retrieval_counsel_case.py

import pytest
from app.agents.retrieval.case_agent import CaseRetrievalAgent
from app.agents.retrieval.counsel_agent import CounselRetrievalAgent


class TestCaseRetrievalAgent:
    """CaseRetrievalAgent 단위 테스트"""

    @pytest.fixture
    def agent(self):
        return CaseRetrievalAgent()

    @pytest.fixture
    def sample_input(self) -> dict:
        return {
            "context": {
                "user_query": "헬스장 환불 사례",
                "query_analysis": {
                    "query_type": "dispute",
                    "keywords": ["헬스장", "환불"],
                    "rewritten_query": "헬스장 회원권 환불 분쟁",
                    "search_queries": ["헬스장 환불"],
                    "needs_clarification": False,
                    "extracted_info": {}
                }
            },
            "params": {"top_k": 3}
        }

    @pytest.mark.asyncio
    async def test_case_search_output_format(self, agent, sample_input):
        """출력 형식 테스트"""
        result = await agent.process(sample_input)

        assert result["source"] == "case"
        assert "documents" in result
        assert "max_similarity" in result
        assert "search_time_ms" in result

    @pytest.mark.asyncio
    async def test_case_document_structure(self, agent, sample_input):
        """사례 문서 구조 테스트"""
        result = await agent.process(sample_input)

        if result["documents"]:
            doc = result["documents"][0]
            assert "doc_title" in doc
            assert "content" in doc
            assert "source_org" in doc
            assert "decision_date" in doc
            assert "similarity" in doc
            assert doc["source_org"] in ["KCA", "ECMC", "KCDRC"]

    @pytest.mark.asyncio
    async def test_top_k_limit(self, agent, sample_input):
        """top_k 제한 테스트"""
        sample_input["params"]["top_k"] = 2
        result = await agent.process(sample_input)

        assert len(result["documents"]) <= 2


class TestCounselRetrievalAgent:
    """CounselRetrievalAgent 단위 테스트"""

    @pytest.fixture
    def agent(self):
        return CounselRetrievalAgent()

    @pytest.fixture
    def sample_input(self) -> dict:
        return {
            "context": {
                "user_query": "헬스장 환불 상담",
                "query_analysis": {
                    "query_type": "dispute",
                    "keywords": ["헬스장", "환불", "상담"],
                    "rewritten_query": "헬스장 환불 상담사례",
                    "search_queries": ["헬스장 환불 상담"],
                    "needs_clarification": False,
                    "extracted_info": {}
                }
            },
            "params": {"top_k": 3}
        }

    @pytest.mark.asyncio
    async def test_counsel_search_output_format(self, agent, sample_input):
        """출력 형식 테스트"""
        result = await agent.process(sample_input)

        assert result["source"] == "counsel"
        assert "documents" in result
        assert "max_similarity" in result

    @pytest.mark.asyncio
    async def test_counsel_document_structure(self, agent, sample_input):
        """상담 문서 구조 테스트"""
        result = await agent.process(sample_input)

        if result["documents"]:
            doc = result["documents"][0]
            assert "content" in doc
            assert "source_org" in doc
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

def create_mock_case_output(
    num_docs: int = 2,
    max_sim: float = 0.88,
    source_org: str = "KCA"
) -> dict:
    """테스트용 분쟁조정사례 결과 생성"""
    docs = [
        {
            "doc_title": f"테스트 분쟁사례 {i+1}",
            "content": f"분쟁 내용 및 결정 사항 {i+1}...",
            "source_org": source_org,
            "decision_date": f"2023-0{i+1}-15",
            "similarity": max_sim - (i * 0.1),
            "chunk_id": f"case_chunk_{i:03d}",
            "doc_id": f"case_doc_{i:03d}",
            "chunk_type": "summary",
            "url": None
        }
        for i in range(num_docs)
    ]

    return {
        "source": "case",
        "documents": docs,
        "max_similarity": max_sim,
        "avg_similarity": sum(d["similarity"] for d in docs) / len(docs) if docs else 0,
        "search_time_ms": 150.0,
        "error": None
    }


def create_mock_counsel_output(
    num_docs: int = 2,
    max_sim: float = 0.82
) -> dict:
    """테스트용 상담사례 결과 생성"""
    docs = [
        {
            "content": f"[질문] 테스트 질문 {i+1}\n[답변] 테스트 답변 {i+1}",
            "source_org": "Consumer24",
            "similarity": max_sim - (i * 0.1),
            "chunk_id": f"counsel_chunk_{i:03d}",
            "doc_id": f"counsel_doc_{i:03d}",
            "chunk_type": "qa_pair",
            "url": None
        }
        for i in range(num_docs)
    ]

    return {
        "source": "counsel",
        "documents": docs,
        "max_similarity": max_sim,
        "avg_similarity": sum(d["similarity"] for d in docs) / len(docs) if docs else 0,
        "search_time_ms": 120.0,
        "error": None
    }
```

### 테스트 실행

```bash
# Counsel & Case Retrieval 테스트
conda run -n dsr pytest backend/scripts/testing/agents/test_retrieval_counsel_case.py -v

# 단위 테스트만 (DB 불필요)
conda run -n dsr pytest backend/scripts/testing/agents/test_retrieval_counsel_case.py -m "not integration" -v

# 특정 에이전트만
conda run -n dsr pytest backend/scripts/testing/agents/test_retrieval_counsel_case.py::TestCaseRetrievalAgent -v
```

---

## 결과 병합 방식

4개 Retrieval Agent 결과는 `retrieval_merge` 노드에서 병합됩니다:

```python
# retrieval_merge 노드에서의 처리
merged_retrieval = {
    "laws": law_output["documents"],           # LawRetrievalAgent
    "criteria": criteria_output["documents"],  # CriteriaRetrievalAgent
    "disputes": case_output["documents"],      # CaseRetrievalAgent ⭐
    "counsels": counsel_output["documents"],   # CounselRetrievalAgent ⭐
    "max_similarity": max(all_max_similarities),
    "avg_similarity": average(all_avg_similarities)
}
```

---

## 데이터 소스 정보

| 소스 | 건수 | 설명 |
|------|------|------|
| 분쟁조정사례 (KCA) | ~2,500건 | 한국소비자원 분쟁조정 결정 |
| 분쟁조정사례 (ECMC) | ~500건 | 전자거래분쟁조정위원회 결정 |
| 분쟁조정사례 (KCDRC) | ~200건 | 콘텐츠분쟁조정위원회 결정 |
| 상담사례 (Consumer24) | ~13,500건 | 소비자상담센터 상담 기록 |

---

## 참고 파일

| 파일 | 설명 |
|------|------|
| `app/agents/protocols.py` | 전체 타입 정의 |
| `app/agents/retrieval/base_retrieval_agent.py` | Retrieval 베이스 클래스 |
| `app/agents/retrieval/case_agent.py` | CaseRetrievalAgent 구현 |
| `app/agents/retrieval/counsel_agent.py` | CounselRetrievalAgent 구현 |
| `app/supervisor/nodes/retrieval_merge.py` | 결과 병합 로직 |
