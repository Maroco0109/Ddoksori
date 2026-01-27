# Query Analysis Agent 인터페이스

> **담당 작업자**: Query Analysis
> **역할**: 사용자 질의 분석, 의도 분류, 키워드 추출, 검색 쿼리 생성

## 파이프라인 위치

```
[사용자 입력] → [QueryAnalyst] → [Retrieval Agents]
                    ↑
               현재 에이전트
```

- **이전 단계**: 사용자 입력 (API 요청)
- **다음 단계**: 4개 Retrieval Agent (병렬 실행)

---

## 입력 스펙 (Input Specification)

```python
from typing import Optional, Literal
from typing_extensions import TypedDict


class OnboardingInfo(TypedDict, total=False):
    """온보딩 폼 데이터 (분쟁 상담 시 프론트엔드에서 수집)"""
    purchase_date: Optional[str]      # 구매일자 (YYYY-MM-DD)
    purchase_place: Optional[str]     # 구매처 (판매자 상호/브랜드)
    purchase_platform: Optional[str]  # 구매 플랫폼 (온라인/오프라인)
    purchase_item: Optional[str]      # 구매 품목
    purchase_amount: Optional[str]    # 구매 금액
    dispute_details: Optional[str]    # 분쟁 상세 내용


class QueryAnalysisInput(TypedDict):
    """질의분석 노드 입력"""
    user_query: str                              # 사용자가 입력한 원본 질문 (필수)
    chat_type: Literal['dispute', 'general']     # 채팅 유형 (필수)
    onboarding: Optional[OnboardingInfo]         # 온보딩 폼 데이터 (선택)
```

### 필드 설명

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `user_query` | `str` | ✅ | 사용자가 입력한 원본 질문 |
| `chat_type` | `Literal['dispute', 'general']` | ✅ | 채팅 유형 |
| `onboarding` | `OnboardingInfo` | ❌ | 분쟁 상담 시 온보딩 폼 데이터 |

---

## 출력 스펙 (Output Specification)

```python
from typing import List, Dict, Optional, Literal
from typing_extensions import TypedDict


QueryType = Literal['dispute', 'general', 'law', 'criteria', 'system_meta', 'ambiguous']
RoutingMode = Literal['NO_RETRIEVAL', 'NEED_RAG', 'NEED_USER_CLARIFICATION', 'NEED_CLARIFICATION']


class QueryAnalysisResult(TypedDict, total=False):
    """질의분석 결과 상세"""
    query_type: QueryType                    # 쿼리 유형 (필수)
    keywords: List[str]                      # 추출된 키워드 목록 (필수)
    agency_hint: Optional[str]               # 담당 기관 힌트 (KCA, ECMC, KCDRC)
    needs_clarification: bool                # 추가 정보 필요 여부 (필수)
    missing_fields: List[str]                # 누락된 필드 목록
    missing_fields_description: str          # 누락 필드 설명 (사용자 안내용)
    extracted_info: Dict[str, str]           # 추출된 정보 (품목, 금액 등)
    rewritten_query: str                     # 정규화/확장된 검색 쿼리 (필수)
    search_queries: List[str]                # 다중 쿼리 검색용 쿼리 리스트 (최대 4개)
    expansion_applied: str                   # 적용된 확장 규칙 설명


class QueryAnalysisOutput(TypedDict):
    """질의분석 노드 출력"""
    query_analysis: QueryAnalysisResult      # 분석 결과 상세 (필수)
    mode: RoutingMode                        # 라우팅 모드 (필수)
```

### 출력 필드 설명

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `query_type` | `QueryType` | ✅ | 분류된 쿼리 유형 |
| `keywords` | `List[str]` | ✅ | 검색에 사용할 핵심 키워드 |
| `rewritten_query` | `str` | ✅ | 정규화된 검색 쿼리 |
| `search_queries` | `List[str]` | ✅ | 다중 검색용 쿼리 (최대 4개) |
| `needs_clarification` | `bool` | ✅ | 추가 정보 요청 필요 여부 |
| `mode` | `RoutingMode` | ✅ | 다음 단계 라우팅 결정 |

### RoutingMode 값 설명

| 값 | 설명 | 다음 단계 |
|----|------|----------|
| `NO_RETRIEVAL` | 검색 불필요 (인사, 감사 등) | 직접 답변 생성 |
| `NEED_RAG` | RAG 검색 필요 | Retrieval Agents |
| `NEED_USER_CLARIFICATION` | 사용자에게 되물어야 함 | 사용자 응답 대기 |
| `NEED_CLARIFICATION` | 내부 정보 보완 필요 | Retrieval + 추가 처리 |

---

## 코드 예시

### 입력 예시

```python
# 분쟁 상담 케이스
input_dispute = {
    "user_query": "헬스장 회원권 환불받고 싶은데 어떻게 해야 하나요?",
    "chat_type": "dispute",
    "onboarding": {
        "purchase_date": "2024-01-15",
        "purchase_item": "헬스장 회원권",
        "purchase_amount": "150만원",
        "purchase_platform": "오프라인"
    }
}

# 일반 상담 케이스
input_general = {
    "user_query": "소비자보호법에서 청약철회 기간이 얼마인가요?",
    "chat_type": "general",
    "onboarding": None
}

# 인사 케이스
input_greeting = {
    "user_query": "안녕하세요",
    "chat_type": "general",
    "onboarding": None
}
```

### 출력 예시

```python
# 분쟁 상담 → RAG 검색 필요
output_dispute = {
    "query_analysis": {
        "query_type": "dispute",
        "keywords": ["헬스장", "회원권", "환불", "중도해지"],
        "agency_hint": "KCA",
        "needs_clarification": False,
        "missing_fields": [],
        "missing_fields_description": "",
        "extracted_info": {
            "품목": "헬스장 회원권",
            "금액": "1500000",
            "구매일자": "2024-01-15"
        },
        "rewritten_query": "헬스장 회원권 중도해지 환불 절차",
        "search_queries": [
            "헬스장 회원권 환불",
            "피트니스 중도해지 환불금",
            "체육시설 이용계약 해지",
            "회원권 환불 기준"
        ],
        "expansion_applied": "동의어 확장: 헬스장→피트니스/체육시설"
    },
    "mode": "NEED_RAG"
}

# 일반 법령 질문
output_law = {
    "query_analysis": {
        "query_type": "law",
        "keywords": ["청약철회", "기간", "소비자보호법"],
        "agency_hint": None,
        "needs_clarification": False,
        "missing_fields": [],
        "missing_fields_description": "",
        "extracted_info": {},
        "rewritten_query": "소비자보호법 청약철회 기간 규정",
        "search_queries": [
            "청약철회 기간",
            "소비자기본법 청약철회",
            "전자상거래법 청약철회 기간"
        ],
        "expansion_applied": ""
    },
    "mode": "NEED_RAG"
}

# 인사 → 검색 불필요
output_greeting = {
    "query_analysis": {
        "query_type": "general",
        "keywords": [],
        "agency_hint": None,
        "needs_clarification": False,
        "missing_fields": [],
        "missing_fields_description": "",
        "extracted_info": {},
        "rewritten_query": "",
        "search_queries": [],
        "expansion_applied": ""
    },
    "mode": "NO_RETRIEVAL"
}

# 정보 부족 → 되묻기
output_clarification = {
    "query_analysis": {
        "query_type": "dispute",
        "keywords": ["환불"],
        "agency_hint": None,
        "needs_clarification": True,
        "missing_fields": ["purchase_item", "purchase_date"],
        "missing_fields_description": "어떤 상품을 언제 구매하셨는지 알려주시면 더 정확한 안내가 가능합니다.",
        "extracted_info": {},
        "rewritten_query": "",
        "search_queries": [],
        "expansion_applied": ""
    },
    "mode": "NEED_USER_CLARIFICATION"
}
```

---

## 테스트 가이드

### 단위 테스트 작성 방법

```python
# backend/scripts/testing/agents/test_query_analysis.py

import pytest
from app.agents.query_analysis.agent import QueryAnalysisAgent
from app.agents.protocols import QueryAnalysisInput, QueryAnalysisOutput


class TestQueryAnalysisAgent:
    """QueryAnalysisAgent 단위 테스트"""

    @pytest.fixture
    def agent(self):
        """에이전트 인스턴스 생성"""
        return QueryAnalysisAgent()

    @pytest.mark.asyncio
    async def test_dispute_query_classification(self, agent):
        """분쟁 쿼리 분류 테스트"""
        input_data: QueryAnalysisInput = {
            "user_query": "헬스장 회원권 환불받고 싶어요",
            "chat_type": "dispute",
            "onboarding": {"purchase_item": "헬스장 회원권"}
        }

        result = await agent.analyze(input_data)

        # 타입 검증
        assert "query_analysis" in result
        assert "mode" in result

        # 분류 검증
        assert result["query_analysis"]["query_type"] == "dispute"
        assert "헬스장" in result["query_analysis"]["keywords"]
        assert result["mode"] == "NEED_RAG"

    @pytest.mark.asyncio
    async def test_greeting_no_retrieval(self, agent):
        """인사 쿼리 → NO_RETRIEVAL 테스트"""
        input_data: QueryAnalysisInput = {
            "user_query": "안녕하세요",
            "chat_type": "general",
            "onboarding": None
        }

        result = await agent.analyze(input_data)

        assert result["mode"] == "NO_RETRIEVAL"

    @pytest.mark.asyncio
    async def test_ambiguous_query_clarification(self, agent):
        """모호한 쿼리 → 되묻기 테스트"""
        input_data: QueryAnalysisInput = {
            "user_query": "환불해주세요",
            "chat_type": "dispute",
            "onboarding": None
        }

        result = await agent.analyze(input_data)

        assert result["query_analysis"]["needs_clarification"] == True
        assert len(result["query_analysis"]["missing_fields"]) > 0
        assert result["mode"] == "NEED_USER_CLARIFICATION"

    @pytest.mark.asyncio
    async def test_keyword_extraction(self, agent):
        """키워드 추출 테스트"""
        input_data: QueryAnalysisInput = {
            "user_query": "노트북 액정 파손으로 AS 요청했는데 거부당했어요",
            "chat_type": "dispute",
            "onboarding": None
        }

        result = await agent.analyze(input_data)

        keywords = result["query_analysis"]["keywords"]
        assert any(k in keywords for k in ["노트북", "액정", "AS", "파손"])

    @pytest.mark.asyncio
    async def test_search_queries_generation(self, agent):
        """다중 검색 쿼리 생성 테스트"""
        input_data: QueryAnalysisInput = {
            "user_query": "헬스장 환불",
            "chat_type": "dispute",
            "onboarding": None
        }

        result = await agent.analyze(input_data)

        search_queries = result["query_analysis"]["search_queries"]
        assert len(search_queries) >= 1
        assert len(search_queries) <= 4
```

### Mock 데이터 생성

```python
# backend/scripts/testing/fixtures/query_analysis_fixtures.py

def create_mock_input(
    query: str = "테스트 쿼리",
    chat_type: str = "general",
    onboarding: dict = None
) -> QueryAnalysisInput:
    """테스트용 입력 데이터 생성"""
    return {
        "user_query": query,
        "chat_type": chat_type,
        "onboarding": onboarding
    }


def create_mock_output(
    query_type: str = "general",
    keywords: list = None,
    mode: str = "NEED_RAG"
) -> QueryAnalysisOutput:
    """테스트용 출력 데이터 생성"""
    return {
        "query_analysis": {
            "query_type": query_type,
            "keywords": keywords or [],
            "agency_hint": None,
            "needs_clarification": False,
            "missing_fields": [],
            "missing_fields_description": "",
            "extracted_info": {},
            "rewritten_query": "",
            "search_queries": [],
            "expansion_applied": ""
        },
        "mode": mode
    }
```

### 테스트 실행

```bash
# Query Analysis 테스트만 실행
conda run -n dsr pytest backend/scripts/testing/agents/test_query_analysis.py -v

# 특정 테스트 함수만 실행
conda run -n dsr pytest backend/scripts/testing/agents/test_query_analysis.py::TestQueryAnalysisAgent::test_dispute_query_classification -v

# 단위 테스트만 (DB 불필요)
conda run -n dsr pytest backend/scripts/testing/agents/test_query_analysis.py -m unit -v
```

---

## 검증 함수

```python
from app.agents.protocols import validate_query_analysis_output

# 출력 유효성 검증
output = await agent.analyze(input_data)
is_valid = validate_query_analysis_output(output)
assert is_valid, "출력이 프로토콜을 만족하지 않습니다"
```

---

## 참고 파일

| 파일 | 설명 |
|------|------|
| `app/agents/protocols.py` | 전체 타입 정의 |
| `app/agents/query_analysis/agent.py` | 에이전트 구현체 |
| `app/supervisor/state/__init__.py` | ChatState 정의 |
