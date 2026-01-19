#!/usr/bin/env python3
"""
분쟁조정기준 기본 쿼리 함수 (S1-D3)
- 품목 검색, 계층 탐색, 기준 조회 등
"""

import os
from typing import List, Dict, Optional, Any
import psycopg2
from psycopg2.extras import RealDictCursor

# 데이터베이스 설정
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'ddoksori'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres')
}


def get_db_connection():
    """데이터베이스 연결 생성"""
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)


def search_items_by_category(category: str, industry: Optional[str] = None, item_group: Optional[str] = None) -> List[Dict]:
    """
    별표1 품목 분류에서 카테고리/업종/품목그룹으로 검색

    Args:
        category: 대분류 (예: "상품(재화)", "용역")
        industry: 업종 (예: "농수축산물", "가전제품")
        item_group: 품목그룹 (예: "란류", "냉난방기")

    Returns:
        검색된 품목 리스트
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            unit_id,
            category,
            industry,
            item_group,
            item,
            unit_text,
            path_hint,
            doc->>'payload'->'items' as items_list
        FROM criteria_units
        WHERE source_id = 'table1'
          AND category = %s
    """
    params = [category]

    if industry:
        query += " AND industry = %s"
        params.append(industry)

    if item_group:
        query += " AND item_group = %s"
        params.append(item_group)

    query += " ORDER BY unit_id"

    cursor.execute(query, params)
    results = cursor.fetchall()

    conn.close()
    return results


def search_items_by_keyword(keyword: str) -> List[Dict]:
    """
    키워드로 품목 검색 (카테고리, 업종, 품목그룹, 품목명, 텍스트 내용)

    Args:
        keyword: 검색 키워드 (예: "계란", "에어컨", "스마트폰")

    Returns:
        검색된 품목 리스트
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            unit_id,
            category,
            industry,
            item_group,
            item,
            unit_text,
            path_hint
        FROM criteria_units
        WHERE source_id = 'table1'
          AND (
              category ILIKE %s
              OR industry ILIKE %s
              OR item_group ILIKE %s
              OR unit_text ILIKE %s
          )
        ORDER BY unit_id
        LIMIT 20
    """

    search_pattern = f"%{keyword}%"
    cursor.execute(query, [search_pattern] * 4)
    results = cursor.fetchall()

    conn.close()
    return results


def get_resolution_criteria(item_group: Optional[str] = None, dispute_type: Optional[str] = None) -> List[Dict]:
    """
    별표2 해결기준 조회

    Args:
        item_group: 품목그룹 필터 (예: "란류", "냉난방기")
        dispute_type: 분쟁 유형 필터 (예: "환불", "수리")

    Returns:
        해결기준 리스트
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            unit_id,
            item_group,
            dispute_type,
            unit_text,
            path_hint,
            doc
        FROM criteria_units
        WHERE source_id = 'table2'
    """
    params = []

    if item_group:
        query += " AND item_group ILIKE %s"
        params.append(f"%{item_group}%")

    if dispute_type:
        query += " AND unit_text ILIKE %s"
        params.append(f"%{dispute_type}%")

    query += " ORDER BY unit_id LIMIT 50"

    cursor.execute(query, params)
    results = cursor.fetchall()

    conn.close()
    return results


def get_warranty_period(item_keyword: str) -> List[Dict]:
    """
    별표3 품질보증기간 조회

    Args:
        item_keyword: 품목 키워드 (예: "계란", "에어컨")

    Returns:
        품질보증기간 정보 리스트
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            unit_id,
            unit_text,
            path_hint,
            doc
        FROM criteria_units
        WHERE source_id = 'table3'
          AND unit_text ILIKE %s
        ORDER BY unit_id
    """

    cursor.execute(query, [f"%{item_keyword}%"])
    results = cursor.fetchall()

    conn.close()
    return results


def get_product_lifespan(item_keyword: str) -> List[Dict]:
    """
    별표4 내용연수 조회

    Args:
        item_keyword: 품목 키워드 (예: "에어컨", "냉장고")

    Returns:
        내용연수 정보 리스트
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT
            unit_id,
            unit_text,
            path_hint,
            doc
        FROM criteria_units
        WHERE source_id = 'table4'
          AND unit_text ILIKE %s
        ORDER BY unit_id
    """

    cursor.execute(query, [f"%{item_keyword}%"])
    results = cursor.fetchall()

    conn.close()
    return results


def hierarchical_search(user_item: str, limit: int = 10) -> Dict[str, Any]:
    """
    2단계 계층 검색
    Stage 1: 품목 분류 (table1) 검색
    Stage 2: 관련 해결기준 (table2) 검색

    Args:
        user_item: 사용자 입력 품목 (예: "계란", "에어컨")
        limit: 반환할 최대 결과 수

    Returns:
        {
            'stage1': List[품목 분류 결과],
            'stage2': List[해결기준 결과],
            'matched_items': List[매칭된 품목 정보]
        }
    """
    result = {
        'stage1': [],
        'stage2': [],
        'matched_items': []
    }

    # Stage 1: 품목 검색
    stage1_results = search_items_by_keyword(user_item)
    result['stage1'] = stage1_results

    # 품목 그룹 추출
    item_groups = set()
    for item in stage1_results:
        if item.get('item_group'):
            item_groups.add(item['item_group'])
            result['matched_items'].append({
                'category': item.get('category'),
                'industry': item.get('industry'),
                'item_group': item.get('item_group'),
                'path': item.get('path_hint')
            })

    # Stage 2: 품목 그룹별 해결기준 검색
    for item_group in item_groups:
        criteria = get_resolution_criteria(item_group=item_group)
        result['stage2'].extend(criteria[:limit])

    return result


def get_criteria_statistics() -> Dict[str, Any]:
    """
    분쟁조정기준 데이터 통계 조회

    Returns:
        소스별 데이터 통계
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # criteria_units 통계
    cursor.execute("""
        SELECT
            source_id,
            COUNT(*) as unit_count,
            COUNT(embedding) as embedded_count,
            COUNT(DISTINCT category) as category_count,
            COUNT(DISTINCT industry) as industry_count,
            COUNT(DISTINCT item_group) as item_group_count
        FROM criteria_units
        GROUP BY source_id
        ORDER BY source_id
    """)

    units_stats = cursor.fetchall()

    # chunks 통계 (documents 테이블 조인)
    cursor.execute("""
        SELECT
            d.doc_type,
            COUNT(c.chunk_id) as chunk_count,
            COUNT(c.embedding) as embedded_count
        FROM chunks c
        JOIN documents d ON c.doc_id = d.doc_id
        WHERE d.doc_type LIKE 'criteria_%'
        GROUP BY d.doc_type
        ORDER BY d.doc_type
    """)

    chunks_stats = cursor.fetchall()

    conn.close()

    return {
        'criteria_units': units_stats,
        'chunks': chunks_stats
    }


# CLI 테스트용
if __name__ == '__main__':
    import sys

    print("=" * 60)
    print("S1-D3: 분쟁조정기준 기본 쿼리 테스트")
    print("=" * 60)

    # 통계 출력
    print("\n📊 Data Statistics:")
    stats = get_criteria_statistics()

    print("\n[criteria_units table]")
    for row in stats['criteria_units']:
        print(f"  {row['source_id']}: {row['unit_count']} units "
              f"({row['embedded_count']} embedded)")

    print("\n[chunks table]")
    for row in stats['chunks']:
        print(f"  {row['doc_type']}: {row['chunk_count']} chunks "
              f"({row['embedded_count']} embedded)")

    # 테스트 쿼리
    test_item = sys.argv[1] if len(sys.argv) > 1 else "계란"

    print(f"\n🔍 Testing hierarchical search for: '{test_item}'")
    result = hierarchical_search(test_item, limit=5)

    print(f"\n[Stage 1: 품목 분류] {len(result['stage1'])} results")
    for item in result['stage1'][:3]:
        print(f"  - {item.get('path_hint')}: {item.get('item_group')}")

    print(f"\n[Stage 2: 해결기준] {len(result['stage2'])} results")
    for criteria in result['stage2'][:3]:
        print(f"  - {criteria.get('unit_text')[:80]}...")

    print(f"\n[Matched Items] {len(result['matched_items'])} items")
    for match in result['matched_items']:
        print(f"  - {match}")

    print("\n" + "=" * 60)
    print("✅ Query test completed")
    print("=" * 60)
