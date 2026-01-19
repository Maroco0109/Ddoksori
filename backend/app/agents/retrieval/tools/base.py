"""
BaseRetriever - Abstract base class for all retrievers
Sprint 3 - s3-4: Unified retriever interface
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class Document:
    """Standard document representation for retriever outputs"""
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
    Abstract base class for all retrievers.
    
    All retrievers must implement:
    - invoke(query, **kwargs) -> List[Document]
    - connect() / close() for database connections
    
    Optional methods:
    - search_instrumented() for timing info
    """
    
    @abstractmethod
    def invoke(self, query: str, top_k: int = 10, **kwargs) -> List[Document]:
        """
        Main search interface.
        
        Args:
            query: Search query string
            top_k: Number of results to return
            **kwargs: Additional parameters (filters, etc.)
            
        Returns:
            List of Document objects sorted by relevance
        """
        pass
    
    @abstractmethod
    def connect(self) -> None:
        """Establish database/API connections"""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close connections"""
        pass
    
    def search_instrumented(
        self, 
        query: str, 
        top_k: int = 10, 
        **kwargs
    ) -> Dict[str, Any]:
        """
        Search with timing and diagnostic info.
        
        Default implementation wraps invoke().
        Override for detailed timing breakdown.
        
        Returns:
            {
                'results': List[Document],
                'total_time_ms': float,
                ...additional metrics...
            }
        """
        import time
        start = time.time()
        results = self.invoke(query, top_k, **kwargs)
        elapsed = (time.time() - start) * 1000
        
        return {
            'results': results,
            'total_time_ms': elapsed,
            'result_count': len(results)
        }
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
        return False


def to_document(result: Any) -> Document:
    """
    Convert various result types to Document.
    
    Handles:
    - SearchResult (from retriever.py)
    - LawSearchResult (from specialized_retrievers.py)
    - CriteriaSearchResult (from specialized_retrievers.py)
    - Dict with standard fields
    """
    if isinstance(result, Document):
        return result
    
    if isinstance(result, dict):
        return Document(
            chunk_id=result.get('chunk_id') or result.get('unit_id', ''),
            doc_id=result.get('doc_id') or result.get('source_id', ''),
            content=result.get('content') or result.get('text') or result.get('unit_text', ''),
            similarity=float(result.get('similarity', 0.0)),
            doc_type=result.get('doc_type'),
            doc_title=result.get('doc_title') or result.get('title'),
            chunk_type=result.get('chunk_type') or result.get('level'),
            source_org=result.get('source_org') or result.get('source_label'),
            url=result.get('url'),
            category_path=result.get('category_path', []),
            metadata=result.get('metadata', {})
        )
    
    if hasattr(result, 'chunk_id'):
        return Document(
            chunk_id=result.chunk_id,
            doc_id=getattr(result, 'doc_id', ''),
            content=getattr(result, 'content', ''),
            similarity=float(getattr(result, 'similarity', 0.0)),
            doc_type=getattr(result, 'doc_type', None),
            doc_title=getattr(result, 'doc_title', None),
            chunk_type=getattr(result, 'chunk_type', None),
            source_org=getattr(result, 'source_org', None),
            url=getattr(result, 'url', None),
            category_path=getattr(result, 'category_path', []),
            metadata=getattr(result, 'metadata', {})
        )
    
    if hasattr(result, 'unit_id'):
        content = getattr(result, 'text', None) or getattr(result, 'unit_text', '')
        return Document(
            chunk_id=result.unit_id,
            doc_id=getattr(result, 'law_id', '') or getattr(result, 'source_id', ''),
            content=content,
            similarity=float(getattr(result, 'similarity', 0.0)),
            doc_type='law' if hasattr(result, 'law_name') else 'criteria',
            doc_title=getattr(result, 'law_name', None) or getattr(result, 'source_label', None),
            chunk_type=getattr(result, 'level', None),
            source_org=getattr(result, 'source_label', None),
            url=None,
            category_path=[],
            metadata={
                'full_path': getattr(result, 'full_path', None),
                'article_no': getattr(result, 'article_no', None),
                'category': getattr(result, 'category', None),
                'industry': getattr(result, 'industry', None),
                'item_group': getattr(result, 'item_group', None),
                'item': getattr(result, 'item', None),
            }
        )
    
    raise ValueError(f"Cannot convert {type(result)} to Document")


def to_documents(results: List[Any]) -> List[Document]:
    """Convert list of results to Documents"""
    return [to_document(r) for r in results]
