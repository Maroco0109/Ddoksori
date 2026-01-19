"""
RDB 직접 조회 모듈 (Sprint 3 s3-2)

criteria_units, law_units 테이블에서 정형 데이터를 직접 조회.
벡터 검색 없이 SQL 파라미터 바인딩으로 정확한 결과 반환.
"""

import logging
import psycopg2
from psycopg2 import sql
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CriteriaRDBResult:
    unit_id: str
    source_id: str
    source_label: str
    category: Optional[str]
    industry: Optional[str]
    item_group: Optional[str]
    item: Optional[str]
    dispute_type: Optional[str]
    unit_text: str
    doc: Dict[str, Any]


@dataclass
class LawRDBResult:
    doc_id: str
    law_id: str
    law_name: str
    level: str
    article_no: Optional[str]
    paragraph_no: Optional[str]
    item_no: Optional[str]
    subitem_no: Optional[str]
    path: str
    text: str


class CriteriaRDBRetriever:
    """
    분쟁조정기준 RDB 직접 조회기
    
    criteria_units 테이블에서 category, industry, item_group, item,
    dispute_type 등의 조건으로 직접 조회.
    """

    def __init__(self, db_config: Dict[str, str]):
        self.db_config = db_config
        self.conn = None

    def connect(self):
        self.conn = psycopg2.connect(**self.db_config)

    def close(self):
        if self.conn:
            self.conn.close()

    def search(
        self,
        category: Optional[str] = None,
        industry: Optional[str] = None,
        item_group: Optional[str] = None,
        item: Optional[str] = None,
        dispute_type: Optional[str] = None,
        source_id: Optional[str] = None,
        top_k: int = 10,
    ) -> List[CriteriaRDBResult]:
        """
        정형 조건으로 criteria_units 검색
        
        파라미터화된 쿼리로 SQL injection 방지.
        """
        conditions = []
        params = []

        if category:
            conditions.append("cu.category ILIKE %s")
            params.append(f"%{category}%")
        
        if industry:
            conditions.append("cu.industry ILIKE %s")
            params.append(f"%{industry}%")
        
        if item_group:
            conditions.append("cu.item_group ILIKE %s")
            params.append(f"%{item_group}%")
        
        if item:
            conditions.append("cu.item ILIKE %s")
            params.append(f"%{item}%")
        
        if dispute_type:
            conditions.append("cu.dispute_type ILIKE %s")
            params.append(f"%{dispute_type}%")
        
        if source_id:
            conditions.append("cu.source_id = %s")
            params.append(source_id)

        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        params.append(top_k)

        query = f"""
            SELECT
                cu.unit_id,
                cu.source_id,
                c.source_label,
                cu.category,
                cu.industry,
                cu.item_group,
                cu.item,
                cu.dispute_type,
                cu.unit_text,
                cu.doc
            FROM criteria_units cu
            JOIN criteria c ON cu.source_id = c.source_id
            WHERE {where_clause}
            ORDER BY cu.unit_id
            LIMIT %s
        """

        with self.conn.cursor() as cur:
            cur.execute(query, params)
            
            return [
                CriteriaRDBResult(
                    unit_id=row[0],
                    source_id=row[1],
                    source_label=row[2],
                    category=row[3],
                    industry=row[4],
                    item_group=row[5],
                    item=row[6],
                    dispute_type=row[7],
                    unit_text=row[8],
                    doc=row[9] if row[9] else {},
                )
                for row in cur.fetchall()
            ]

    def search_by_item_keyword(
        self,
        keyword: str,
        top_k: int = 10,
    ) -> List[CriteriaRDBResult]:
        """
        품목 관련 키워드로 전문 검색
        
        item, item_group, industry, unit_text 필드에서 키워드 매칭.
        """
        query = """
            SELECT
                cu.unit_id,
                cu.source_id,
                c.source_label,
                cu.category,
                cu.industry,
                cu.item_group,
                cu.item,
                cu.dispute_type,
                cu.unit_text,
                cu.doc
            FROM criteria_units cu
            JOIN criteria c ON cu.source_id = c.source_id
            WHERE
                cu.item ILIKE %s
                OR cu.item_group ILIKE %s
                OR cu.industry ILIKE %s
                OR cu.unit_text ILIKE %s
            ORDER BY
                CASE
                    WHEN cu.item ILIKE %s THEN 1
                    WHEN cu.item_group ILIKE %s THEN 2
                    WHEN cu.industry ILIKE %s THEN 3
                    ELSE 4
                END
            LIMIT %s
        """
        
        pattern = f"%{keyword}%"
        params = [pattern] * 7 + [top_k]

        with self.conn.cursor() as cur:
            cur.execute(query, params)
            
            return [
                CriteriaRDBResult(
                    unit_id=row[0],
                    source_id=row[1],
                    source_label=row[2],
                    category=row[3],
                    industry=row[4],
                    item_group=row[5],
                    item=row[6],
                    dispute_type=row[7],
                    unit_text=row[8],
                    doc=row[9] if row[9] else {},
                )
                for row in cur.fetchall()
            ]

    def search_dispute_resolution(
        self,
        item_keyword: str,
        dispute_type: Optional[str] = None,
        top_k: int = 5,
    ) -> List[CriteriaRDBResult]:
        """
        분쟁 해결 기준 검색 (위약금, 환불 규정 등)
        
        DoD: "헬스장 3개월 해지" → 위약금 기간 직접 조회
        """
        conditions = ["(cu.item ILIKE %s OR cu.item_group ILIKE %s OR cu.unit_text ILIKE %s)"]
        pattern = f"%{item_keyword}%"
        params = [pattern, pattern, pattern]

        if dispute_type:
            conditions.append("cu.dispute_type ILIKE %s")
            params.append(f"%{dispute_type}%")
        
        conditions.append("cu.source_id IN ('table2', 'table3')")

        where_clause = " AND ".join(conditions)
        params.append(top_k)

        query = f"""
            SELECT
                cu.unit_id,
                cu.source_id,
                c.source_label,
                cu.category,
                cu.industry,
                cu.item_group,
                cu.item,
                cu.dispute_type,
                cu.unit_text,
                cu.doc
            FROM criteria_units cu
            JOIN criteria c ON cu.source_id = c.source_id
            WHERE {where_clause}
            ORDER BY
                CASE cu.source_id
                    WHEN 'table2' THEN 1
                    WHEN 'table3' THEN 2
                    ELSE 3
                END,
                cu.unit_id
            LIMIT %s
        """

        with self.conn.cursor() as cur:
            cur.execute(query, params)
            
            return [
                CriteriaRDBResult(
                    unit_id=row[0],
                    source_id=row[1],
                    source_label=row[2],
                    category=row[3],
                    industry=row[4],
                    item_group=row[5],
                    item=row[6],
                    dispute_type=row[7],
                    unit_text=row[8],
                    doc=row[9] if row[9] else {},
                )
                for row in cur.fetchall()
            ]


class LawRDBRetriever:
    """
    법령 RDB 직접 조회기
    
    law_units 테이블에서 법령명, 조/항/호/목 조건으로 직접 조회.
    """

    def __init__(self, db_config: Dict[str, str]):
        self.db_config = db_config
        self.conn = None

    def connect(self):
        self.conn = psycopg2.connect(**self.db_config)

    def close(self):
        if self.conn:
            self.conn.close()

    def search(
        self,
        law_name: Optional[str] = None,
        law_id: Optional[str] = None,
        article_no: Optional[str] = None,
        paragraph_no: Optional[str] = None,
        item_no: Optional[str] = None,
        top_k: int = 10,
    ) -> List[LawRDBResult]:
        """
        정형 조건으로 law_units 검색
        """
        conditions = []
        params = []

        if law_name:
            conditions.append("l.law_name ILIKE %s")
            params.append(f"%{law_name}%")
        
        if law_id:
            conditions.append("lu.law_id = %s")
            params.append(law_id)
        
        if article_no:
            normalized = article_no.replace("제", "").replace("조", "").strip()
            conditions.append("lu.article_no = %s")
            params.append(normalized)
        
        if paragraph_no:
            normalized = paragraph_no.replace("제", "").replace("항", "").strip()
            conditions.append("lu.paragraph_no = %s")
            params.append(normalized)
        
        if item_no:
            normalized = item_no.replace("제", "").replace("호", "").strip()
            conditions.append("lu.item_no = %s")
            params.append(normalized)

        where_clause = " AND ".join(conditions) if conditions else "TRUE"
        params.append(top_k)

        query = f"""
            SELECT
                lu.doc_id,
                lu.law_id,
                l.law_name,
                lu.level,
                lu.article_no,
                lu.paragraph_no,
                lu.item_no,
                lu.subitem_no,
                lu.path,
                lu.text
            FROM law_units lu
            JOIN laws l ON lu.law_id = l.law_id
            WHERE {where_clause}
            ORDER BY
                lu.article_no::int NULLS LAST,
                lu.paragraph_no::int NULLS LAST,
                lu.item_no::int NULLS LAST
            LIMIT %s
        """

        with self.conn.cursor() as cur:
            cur.execute(query, params)
            
            return [
                LawRDBResult(
                    doc_id=row[0],
                    law_id=row[1],
                    law_name=row[2],
                    level=row[3],
                    article_no=row[4],
                    paragraph_no=row[5],
                    item_no=row[6],
                    subitem_no=row[7],
                    path=row[8] or "",
                    text=row[9],
                )
                for row in cur.fetchall()
            ]

    def search_by_keyword(
        self,
        keyword: str,
        law_name: Optional[str] = None,
        top_k: int = 10,
    ) -> List[LawRDBResult]:
        """
        법령 본문 키워드 검색
        """
        conditions = ["lu.text ILIKE %s"]
        params = [f"%{keyword}%"]

        if law_name:
            conditions.append("l.law_name ILIKE %s")
            params.append(f"%{law_name}%")

        where_clause = " AND ".join(conditions)
        params.append(top_k)

        query = f"""
            SELECT
                lu.doc_id,
                lu.law_id,
                l.law_name,
                lu.level,
                lu.article_no,
                lu.paragraph_no,
                lu.item_no,
                lu.subitem_no,
                lu.path,
                lu.text
            FROM law_units lu
            JOIN laws l ON lu.law_id = l.law_id
            WHERE {where_clause}
            ORDER BY lu.search_stage, lu.article_no::int NULLS LAST
            LIMIT %s
        """

        with self.conn.cursor() as cur:
            cur.execute(query, params)
            
            return [
                LawRDBResult(
                    doc_id=row[0],
                    law_id=row[1],
                    law_name=row[2],
                    level=row[3],
                    article_no=row[4],
                    paragraph_no=row[5],
                    item_no=row[6],
                    subitem_no=row[7],
                    path=row[8] or "",
                    text=row[9],
                )
                for row in cur.fetchall()
            ]

    def get_article_with_children(
        self,
        law_id: str,
        article_no: str,
    ) -> List[LawRDBResult]:
        """
        특정 조문과 그 하위 항/호/목 전체 조회
        """
        normalized = article_no.replace("제", "").replace("조", "").strip()

        query = """
            SELECT
                lu.doc_id,
                lu.law_id,
                l.law_name,
                lu.level,
                lu.article_no,
                lu.paragraph_no,
                lu.item_no,
                lu.subitem_no,
                lu.path,
                lu.text
            FROM law_units lu
            JOIN laws l ON lu.law_id = l.law_id
            WHERE lu.law_id = %s AND lu.article_no = %s
            ORDER BY
                CASE lu.level
                    WHEN 'article' THEN 1
                    WHEN 'paragraph' THEN 2
                    WHEN 'item' THEN 3
                    WHEN 'subitem' THEN 4
                    ELSE 5
                END,
                lu.paragraph_no::int NULLS LAST,
                lu.item_no::int NULLS LAST,
                lu.subitem_no NULLS LAST
        """

        with self.conn.cursor() as cur:
            cur.execute(query, (law_id, normalized))
            
            return [
                LawRDBResult(
                    doc_id=row[0],
                    law_id=row[1],
                    law_name=row[2],
                    level=row[3],
                    article_no=row[4],
                    paragraph_no=row[5],
                    item_no=row[6],
                    subitem_no=row[7],
                    path=row[8] or "",
                    text=row[9],
                )
                for row in cur.fetchall()
            ]


class RDBRetriever:
    """
    통합 RDB Retriever
    
    SqlParamsCandidate를 받아서 적절한 테이블에서 조회.
    """

    def __init__(self, db_config: Dict[str, str]):
        self.db_config = db_config
        self.criteria_retriever = CriteriaRDBRetriever(db_config)
        self.law_retriever = LawRDBRetriever(db_config)

    def connect(self):
        self.criteria_retriever.connect()
        self.law_retriever.connect()

    def close(self):
        self.criteria_retriever.close()
        self.law_retriever.close()

    def search_from_params(
        self,
        sql_params: Dict[str, Any],
        top_k: int = 10,
    ) -> Dict[str, Any]:
        """
        SqlParamsCandidate 기반 통합 검색
        
        Returns:
            {
                'criteria': List[CriteriaRDBResult],
                'laws': List[LawRDBResult],
            }
        """
        result: Dict[str, Any] = {
            'criteria': [],
            'laws': [],
        }

        preferred_tables = sql_params.get('preferred_tables', [])
        
        should_search_criteria = (
            'criteria_units' in preferred_tables
            or sql_params.get('category')
            or sql_params.get('industry')
            or sql_params.get('item_group')
            or sql_params.get('item')
            or sql_params.get('dispute_type')
            or sql_params.get('source_id')
        )
        
        should_search_law = (
            'law_units' in preferred_tables
            or sql_params.get('law_name')
            or sql_params.get('law_id')
            or sql_params.get('article_no')
        )

        if should_search_criteria:
            criteria_results = self.criteria_retriever.search(
                category=sql_params.get('category'),
                industry=sql_params.get('industry'),
                item_group=sql_params.get('item_group'),
                item=sql_params.get('item'),
                dispute_type=sql_params.get('dispute_type'),
                source_id=sql_params.get('source_id'),
                top_k=top_k,
            )
            result['criteria'] = criteria_results

        if should_search_law:
            law_results = self.law_retriever.search(
                law_name=sql_params.get('law_name'),
                law_id=sql_params.get('law_id'),
                article_no=sql_params.get('article_no'),
                paragraph_no=sql_params.get('paragraph_no'),
                item_no=sql_params.get('item_no'),
                top_k=top_k,
            )
            result['laws'] = law_results

        return result

    def search_dispute_resolution_by_keyword(
        self,
        keyword: str,
        dispute_type: Optional[str] = None,
        top_k: int = 5,
    ) -> List[CriteriaRDBResult]:
        """
        분쟁 해결 기준 키워드 검색 (편의 메서드)
        
        Example: search_dispute_resolution_by_keyword("헬스장", "해지")
        """
        return self.criteria_retriever.search_dispute_resolution(
            item_keyword=keyword,
            dispute_type=dispute_type,
            top_k=top_k,
        )
