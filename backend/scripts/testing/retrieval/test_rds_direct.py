"""
RDS 직접 연결 테스트 - 검색 기능 확인
"""

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


def main():
    # Load .env
    backend_path = Path(__file__).parent.parent.parent.parent
    env_path = backend_path / ".env"
    load_dotenv(dotenv_path=env_path)

    # DB Config
    db_config = {
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT", "5432"),
        "dbname": os.getenv("DB_NAME", "ddoksori"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
    }

    print("=" * 80)
    print("RDS DIRECT CONNECTION TEST")
    print("=" * 80)
    print(f"Host: {db_config['host']}")
    print(f"Database: {db_config['dbname']}")
    print(f"User: {db_config['user']}")
    print()

    # Connect
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()

    # Test 1: Count records
    print("[Test 1] Count records by dataset_type")
    cur.execute("""
        SELECT dataset_type, COUNT(*)
        FROM vector_chunks
        GROUP BY dataset_type
    """)
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,}")
    print()

    # Test 2: FTS search test
    print("[Test 2] FTS search for '노트북 화면 깨짐'")
    query = "노트북 화면 깨짐"
    cur.execute(
        """
        SELECT chunk_id, dataset_type, category, chunk_type,
               LEFT(text, 100) as text_preview,
               ts_rank(text_tsv, plainto_tsquery('simple', %s)) AS rank_score
        FROM vector_chunks
        WHERE text_tsv @@ plainto_tsquery('simple', %s)
        ORDER BY rank_score DESC
        LIMIT 5
    """,
        (query, query),
    )

    results = cur.fetchall()
    print(f"  Found {len(results)} results:")
    for i, row in enumerate(results, 1):
        print(
            f"  [{i}] {row[1]}/{row[2] or 'N/A'}/{row[3] or 'N/A'}: {row[4]}... (score: {row[5]:.4f})"
        )
    print()

    # Test 3: FTS search with dataset_type filter
    print("[Test 3] FTS search for '노트북 화면 깨짐' filtered by dataset_type='law_guide'")
    cur.execute(
        """
        SELECT chunk_id, dataset_type, category, chunk_type,
               LEFT(text, 100) as text_preview,
               ts_rank(text_tsv, plainto_tsquery('simple', %s)) AS rank_score
        FROM vector_chunks
        WHERE text_tsv @@ plainto_tsquery('simple', %s)
          AND dataset_type = 'law_guide'
        ORDER BY rank_score DESC
        LIMIT 5
    """,
        (query, query),
    )

    results = cur.fetchall()
    print(f"  Found {len(results)} results:")
    for i, row in enumerate(results, 1):
        print(
            f"  [{i}] {row[1]}/{row[2] or 'N/A'}/{row[3] or 'N/A'}: {row[4]}... (score: {row[5]:.4f})"
        )
    print()

    # Test 4: FTS search with dataset_type='case' and category='상담'
    print("[Test 4] FTS search for '노트북 화면 깨짐' filtered by case/상담")
    cur.execute(
        """
        SELECT chunk_id, dataset_type, category, chunk_type,
               LEFT(text, 100) as text_preview,
               ts_rank(text_tsv, plainto_tsquery('simple', %s)) AS rank_score
        FROM vector_chunks
        WHERE text_tsv @@ plainto_tsquery('simple', %s)
          AND dataset_type = 'case'
          AND category = '상담'
        ORDER BY rank_score DESC
        LIMIT 5
    """,
        (query, query),
    )

    results = cur.fetchall()
    print(f"  Found {len(results)} results:")
    for i, row in enumerate(results, 1):
        print(
            f"  [{i}] {row[1]}/{row[2] or 'N/A'}/{row[3] or 'N/A'}: {row[4]}... (score: {row[5]:.4f})"
        )
    print()

    # Test 5: ILIKE fallback test
    print("[Test 5] ILIKE fallback search for '%노트북%화면%'")
    cur.execute(
        """
        SELECT chunk_id, dataset_type, category, chunk_type,
               LEFT(text, 100) as text_preview
        FROM vector_chunks
        WHERE text ILIKE %s AND text ILIKE %s
          AND dataset_type = 'case'
        LIMIT 5
    """,
        ("%노트북%", "%화면%"),
    )

    results = cur.fetchall()
    print(f"  Found {len(results)} results:")
    for i, row in enumerate(results, 1):
        print(f"  [{i}] {row[1]}/{row[2] or 'N/A'}/{row[3] or 'N/A'}: {row[4]}...")
    print()

    cur.close()
    conn.close()

    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
