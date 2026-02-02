"""
[LEGACY] 이 모듈은 더 이상 사용되지 않습니다.
대체: app.agents.retrieval.tools.unified_retriever.UnifiedRetriever

Document dataclass와 to_documents()는 HybridRetriever에서만 사용되었으며,
Phase 8 이후 UnifiedRetriever로 전환되어 직접 참조되지 않습니다.

---
(원본) 똑소리 프로젝트 - 리트리버 베이스 클래스
모든 리트리버가 구현해야 하는 추상 인터페이스를 정의합니다.
통일된 검색 결과 타입(Document)과 공통 메서드 시그니처를 제공합니다.
Sprint 3 - s3-4: 통합 리트리버 인터페이스 정의
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Document:
    """
    리트리버 검색 결과 표준 표현

    모든 리트리버가 반환하는 문서의 공통 스키마입니다.
    다양한 데이터 소스(분쟁사례, 법령, 상담 등)를 동일한 형식으로 표현합니다.

    Attributes:
        chunk_id: 청크 고유 ID
        doc_id: 원본 문서 ID
        content: 청크 텍스트 내용
        similarity: 유사도 점수 (0.0~1.0)
        doc_type: 문서 유형 (law, counsel_case, mediation_case, criteria)
        doc_title: 문서 제목
        chunk_type: 청크 유형 (article, paragraph, etc.)
        source_org: 출처 기관 (소비자원, 공정위 등)
        url: 원문 URL
        category_path: 카테고리 경로 (예: ['휘트니스', '헬스장'])
        metadata: 추가 메타데이터
    """

    chunk_id: str
    doc_id: str
    content: str
    similarity: float

    doc_type: Optional[str] = None
    doc_title: Optional[str] = None
    chunk_type: Optional[str] = None
    source_org: Optional[str] = None
    url: Optional[str] = None
    category_path: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseRetriever(ABC):
    """
    리트리버 추상 베이스 클래스

    모든 리트리버가 구현해야 하는 인터페이스를 정의합니다.

    필수 구현 메서드:
        - invoke(query, **kwargs) -> List[Document]: 검색 실행
        - connect(): 데이터베이스/API 연결
        - close(): 연결 종료

    선택적 메서드:
        - search_instrumented(): 타이밍 정보가 포함된 검색

    Example:
        >>> with MyRetriever(config) as retriever:
        ...     results = retriever.invoke("환불 규정", top_k=5)
        ...     for doc in results:
        ...         print(f"{doc.doc_title}: {doc.similarity:.2f}")
    """

    @abstractmethod
    def invoke(self, query: str, top_k: int = 10, **kwargs) -> List[Document]:
        """
        메인 검색 인터페이스

        Args:
            query: 검색 쿼리 문자열
            top_k: 반환할 결과 개수
            **kwargs: 추가 파라미터 (필터, 설정 등)

        Returns:
            관련도 순으로 정렬된 Document 리스트
        """
        pass

    @abstractmethod
    def connect(self) -> None:
        """데이터베이스/API 연결 수립"""
        pass

    @abstractmethod
    def close(self) -> None:
        """연결 종료"""
        pass

    def search_instrumented(
        self, query: str, top_k: int = 10, **kwargs
    ) -> Dict[str, Any]:
        """
        타이밍 및 진단 정보가 포함된 검색

        기본 구현은 invoke()를 래핑합니다.
        상세한 타이밍 분석이 필요하면 오버라이드하세요.

        Returns:
            {
                'results': List[Document],  # 검색 결과
                'total_time_ms': float,     # 총 소요 시간 (밀리초)
                'result_count': int,        # 결과 개수
                ...기타 메트릭...
            }
        """
        import time

        start = time.time()
        results = self.invoke(query, top_k, **kwargs)
        elapsed = (time.time() - start) * 1000

        return {
            "results": results,
            "total_time_ms": elapsed,
            "result_count": len(results),
        }

    def __enter__(self):
        """컨텍스트 매니저 진입"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        self.close()
        return False


def to_document(result: Any) -> Document:
    """
    다양한 검색 결과 타입을 Document로 변환

    다음 타입들을 처리합니다:
    - SearchResult (retriever.py에서 사용)
    - SimilarChunkResult (rds_retriever.py vector_chunks 기반 검색 결과)
    - 표준 필드를 가진 Dict

    Args:
        result: 변환할 검색 결과 객체

    Returns:
        Document 인스턴스
    """
    if isinstance(result, Document):
        return result

    if isinstance(result, dict):
        return Document(
            chunk_id=result.get("chunk_id") or result.get("unit_id", ""),
            doc_id=result.get("doc_id") or result.get("source_id", ""),
            content=result.get("content")
            or result.get("text")
            or result.get("unit_text", ""),
            similarity=float(result.get("similarity", 0.0)),
            doc_type=result.get("doc_type"),
            doc_title=result.get("doc_title") or result.get("title"),
            chunk_type=result.get("chunk_type") or result.get("level"),
            source_org=result.get("source_org") or result.get("source_label"),
            url=result.get("url"),
            category_path=result.get("category_path", []),
            metadata=result.get("metadata", {}),
        )

    if hasattr(result, "chunk_id"):
        return Document(
            chunk_id=result.chunk_id,
            doc_id=getattr(result, "doc_id", ""),
            content=getattr(result, "content", "") or getattr(result, "text", ""),
            similarity=float(getattr(result, "similarity", 0.0)),
            doc_type=getattr(result, "doc_type", None),
            doc_title=getattr(result, "doc_title", None),
            chunk_type=getattr(result, "chunk_type", None),
            source_org=getattr(result, "source_org", None),
            url=getattr(result, "url", None),
            category_path=getattr(result, "category_path", []),
            metadata=getattr(result, "metadata", {}),
        )

    if hasattr(result, "unit_id"):
        content = getattr(result, "text", None) or getattr(result, "unit_text", "")
        return Document(
            chunk_id=result.unit_id,
            doc_id=getattr(result, "law_id", "") or getattr(result, "source_id", ""),
            content=content,
            similarity=float(getattr(result, "similarity", 0.0)),
            doc_type="law" if hasattr(result, "law_name") else "criteria",
            doc_title=getattr(result, "law_name", None)
            or getattr(result, "source_label", None),
            chunk_type=getattr(result, "level", None),
            source_org=getattr(result, "source_label", None),
            url=None,
            category_path=[],
            metadata={
                "full_path": getattr(result, "full_path", None),
                "article_no": getattr(result, "article_no", None),
                "category": getattr(result, "category", None),
                "industry": getattr(result, "industry", None),
                "item_group": getattr(result, "item_group", None),
                "item": getattr(result, "item", None),
            },
        )

    raise ValueError(f"Cannot convert {type(result)} to Document")


def to_documents(results: List[Any]) -> List[Document]:
    """검색 결과 리스트를 Document 리스트로 변환"""
    return [to_document(r) for r in results]
