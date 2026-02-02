#### 공통 Input: `RetrievalTaskInput`

```python
class RetrievalTaskInput(TypedDict):
    """
    Supervisor → Retrieval Agent 입력 (v2).

    Attributes:
        expanded_queries: 확장 쿼리 리스트
        agent_keywords: 해당 에이전트용 추출 키워드
        metadata_filter: 메타데이터 필터
        top_k: 반환 문서 수
        ignore_threshold: 임계치 무시 여부
    """
    expanded_queries: List[str]
    agent_keywords: List[str]
    metadata_filter: MetadataFilter
    top_k: int
    ignore_threshold: bool
```

#### 메타데이터 필터: `MetadataFilter`

```python
class MetadataFilter(TypedDict, total=False):
    """
    검색 메타데이터 필터.

    Attributes:
        dataset_type: 데이터셋 타입 ('law_guide' 등)
        document_types: 문서 타입 목록 (['법률', '시행령'] or ['행정규칙', '별표'])
        categories: 카테고리 목록 (['조정', '해결', '상담'])
    """
    dataset_type: Optional[str]
    document_types: Optional[List[str]]
    categories: Optional[List[str]]
```

**에이전트별 메타데이터 필터**:

| Agent | dataset_type | document_types | categories |
|-------|-------------|----------------|-----------|
| **LawRetrieval** | `law_guide` | `['법률', '시행령']` | - |
| **CriteriaRetrieval** | `law_guide` | `['행정규칙', '별표']` | - |
| **CaseRetrieval** | - | - | `['조정', '해결', '상담']` |


#### 검색 에이전트 Output 형식

class RetrievalResult(TypedDict):
    """
    Retrieval Agent → Supervisor 출력 (v2).

    Attributes:
        source: 검색 소스 ('law' | 'criteria' | 'case')
        documents: 검색된 문서 목록
        max_similarity: 최대 유사도
        avg_similarity: 평균 유사도
        search_time_ms: 검색 소요 시간 (ms)
        error: 오류 메시지 (실패 시)
    """
    source: RetrieverType  # 'law' | 'criteria' | 'case'
    documents: List[RetrievedDocument]
    max_similarity: float
    avg_similarity: float
    search_time_ms: float
    error: Optional[str]
    ```

#### 에이전트별 Document 형식

**LawDocument** (법령 문서):
```python
class LawDocument(TypedDict):
    chunk_id: str           # 청크 ID
    content: str            # 법령 본문
    metadata: {
        law_name: str       # 법령명 (예: "소비자기본법")
        full_path: str      # 계층 경로 (예: "제2장 > 제7조 > 제1항")
        article: str        # 조문 번호
        document_type: str  # 문서 타입 ('법률', '시행령')
        dataset_type: str   # 'law_guide'
    }
    similarity: float       # 유사도 점수
```

**CriteriaDocument** (분쟁해결기준 문서):
```python
class CriteriaDocument(TypedDict):
    chunk_id: str           # 청크 ID
    content: str            # 기준 내용
    metadata: {
        source_label: str   # 출처 (예: "표1", "표2")
        category: str       # 대분류 (예: "물품", "서비스")
        item: str           # 품목 (예: "헬스장")
        title: str          # 제목
        document_type: str  # '행정규칙', '별표'
        dataset_type: str   # 'law_guide'
    }
    similarity: float
```