import sys

import psycopg2
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

from app.common.config import get_config


def verify_raw_sql():
    print("=== Raw SQL Verification ===")
    config = get_config()
    db_config = config.database.get_connection_dict()

    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()

    target_title_part = "개인 PT"
    print(f"Searching for '%{target_title_part}%' in DB...")

    # Check 'documents' table
    try:
        cur.execute(
            "SELECT doc_id, title, content FROM documents WHERE title ILIKE %s LIMIT 5",
            (f"%{target_title_part}%",),
        )
        docs = cur.fetchall()
        print(f"\n[documents table search]: Found {len(docs)} matches")
        for d in docs:
            print(f" - Found Title: {d[1]}")
            if "정상 요금 규정을 적용하여 환급해주겠다고 하는 경우" in d[1]:
                print("   >>> EXACT MATCH CONFIRMED in 'documents' table! <<<")
    except Exception as e:
        print(f"[documents table search] Error: {e}")
        conn.rollback()

    # Check 'vector_chunks' table (metadata)
    try:
        # Assuming metadata is JSONB
        cur.execute(
            "SELECT chunk_id, text, metadata FROM vector_chunks WHERE metadata->>'title' ILIKE %s LIMIT 50",
            (f"%{target_title_part}%",),
        )
        chunks = cur.fetchall()
        print(f"\n[vector_chunks table search (metadata)]: Found {len(chunks)} matches")
        for c in chunks:
            meta = c[2]
            title = meta.get("title", "No Title")
            print(f" - Found Title in Metadata: {title}")
            if "정상 요금 규정" in title:
                print("   >>> MATCH CONFIRMED in 'vector_chunks' metadata! <<<")

    except Exception as e:
        print(f"[vector_chunks table search] Error: {e}")
        conn.rollback()

    cur.close()
    conn.close()


if __name__ == "__main__":
    verify_raw_sql()
