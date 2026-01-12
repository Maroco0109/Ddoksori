#!/usr/bin/env python3
"""
분쟁조정기준 데이터 로딩 스크립트 (S1-D3)
- 별표1~4, 지침 데이터를 JSONL에서 PostgreSQL로 로드
- Dual storage: criteria_units (구조화) + documents/chunks (RAG 검색)
"""

import os
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime
import psycopg  # Switched to psycopg (v3)

# 환경 변수 또는 기본값
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'dbname': os.getenv('DB_NAME', 'ddoksori'),  # Changed 'database' to 'dbname'
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres')
}

# JSONL 파일 매핑
CRITERIA_FILES = {
    'table1': 'consumer_dispute_resolution_criteria_table1_items.jsonl',
    'table2': 'consumer_dispute_resolution_criteria_table2_resolutions.jsonl',
    'table3': 'consumer_dispute_resolution_criteria_table3_warranty.jsonl',
    'table4': 'consumer_dispute_resolution_criteria_table4_lifespan.jsonl',
    'ecommerce_guideline': 'ecommerce_guideline.jsonl',
    'content_guideline': 'content_guideline.jsonl',
}


def compute_md5(text: str) -> str:
    """텍스트의 MD5 해시 계산"""
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def parse_jsonl_line(line: str, source_id: str, line_no: int) -> Optional[Dict[str, Any]]:
    """JSONL 라인 파싱"""
    try:
        data = json.loads(line.strip())

        # unit_id 생성: source_id:record_type:line_no
        record_type = data.get('record_type', 'unknown')
        unit_id = f"{source_id}:{record_type}:{line_no:06d}"

        # unit_text 생성 (대표 텍스트)
        text_data = data.get('text', {})
        unit_text = text_data.get('normalized') or text_data.get('raw', '')

        if not unit_text:
            print(f"  ⚠️ Warning: Empty unit_text for {unit_id}, skipping")
            return None

        # 계층 정보 추출 (payload에서)
        payload = data.get('payload', {})
        category = payload.get('category')
        industry = payload.get('industry')
        item_group = payload.get('item_group')
        item = payload.get('item')
        dispute_type = payload.get('dispute_type')

        # search_stage 결정 (table1은 stage1, 나머지는 stage2)
        search_stage = 'stage1' if source_id == 'table1' else 'stage2'

        # path_hint 생성
        path_parts = []
        if category:
            path_parts.append(category)
        if industry:
            path_parts.append(industry)
        if item_group:
            path_parts.append(item_group)
        path_hint = ' > '.join(path_parts) if path_parts else None

        return {
            'unit_id': unit_id,
            'source_id': source_id,
            'record_type': record_type,
            'unit_type': data.get('unit_type'),
            'path_hint': path_hint,
            'unit_text': unit_text,
            'content_md5': compute_md5(unit_text),
            'doc': json.dumps(data, ensure_ascii=False),  # 원본 JSON 전체 저장
            'category': category,
            'industry': industry,
            'item_group': item_group,
            'item': item,
            'dispute_type': dispute_type,
            'search_stage': search_stage,
        }
    except json.JSONDecodeError as e:
        print(f"  ❌ JSON parsing error at line {line_no}: {e}")
        return None
    except Exception as e:
        print(f"  ❌ Unexpected error at line {line_no}: {e}")
        return None


def load_criteria_units(conn, source_id: str, jsonl_path: Path) -> int:
    """criteria_units 테이블에 데이터 로드"""
    # conn passed from outside is likely a psycopg v3 connection
    # Use context manager for cursor
    with conn.cursor() as cursor:

        # JSONL 파일 읽기
        units = []
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line_no, line in enumerate(f, start=1):
                if not line.strip():
                    continue

                unit_data = parse_jsonl_line(line, source_id, line_no)
                if unit_data:
                    units.append(unit_data)

        if not units:
            print(f"  ⚠️ No valid units found in {jsonl_path.name}")
            return 0

        # 데이터베이스에 삽입
        insert_sql = """
        INSERT INTO criteria_units (
            unit_id, source_id, record_type, unit_type, path_hint,
            unit_text, content_md5, doc, embedding,
            category, industry, item_group, item, dispute_type, search_stage
        ) VALUES (
            %(unit_id)s, %(source_id)s, %(record_type)s, %(unit_type)s, %(path_hint)s,
            %(unit_text)s, %(content_md5)s, %(doc)s::jsonb, NULL,
            %(category)s, %(industry)s, %(item_group)s, %(item)s, %(dispute_type)s, %(search_stage)s
        )
        ON CONFLICT (unit_id) DO UPDATE SET
            unit_text = EXCLUDED.unit_text,
            content_md5 = EXCLUDED.content_md5,
            doc = EXCLUDED.doc,
            category = EXCLUDED.category,
            industry = EXCLUDED.industry,
            item_group = EXCLUDED.item_group,
            item = EXCLUDED.item,
            dispute_type = EXCLUDED.dispute_type,
            updated_at = NOW()
        """

        # Replace execute_batch with executemany
        # Note: psycopg 3 executemany automatically handles batching effectively
        cursor.executemany(insert_sql, units)
        conn.commit()

        print(f"  ✅ Loaded {len(units)} units from {jsonl_path.name}")
        return len(units)


def load_to_documents_chunks(conn, source_id: str, source_label: str, jsonl_path: Path) -> int:
    """
    documents + chunks 테이블에도 데이터 로드 (RAG 통합 검색용)
    - doc_type: 'criteria_{source_id}'
    - chunk_type: record_type 값 사용
    """
    with conn.cursor() as cursor:

        # 1. documents 테이블에 문서 메타데이터 삽입
        doc_id = f"criteria_{source_id}"
        cursor.execute("""
            INSERT INTO documents (
                doc_id, doc_type, title, source_org, category_path, url, metadata
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s::jsonb
            )
            ON CONFLICT (doc_id) DO UPDATE SET
                title = EXCLUDED.title,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
        """, (
            doc_id,
            f'criteria_{source_id}',
            source_label,
            'consumer.go.kr',
            ['분쟁조정기준', source_label],
            None,
            json.dumps({'source_id': source_id, 'source_label': source_label})
        ))

        # 2. chunks 테이블에 청크 삽입
        chunks = []
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line_no, line in enumerate(f, start=1):
                if not line.strip():
                    continue

                try:
                    data = json.loads(line.strip())
                    text_data = data.get('text', {})
                    unit_text = text_data.get('normalized') or text_data.get('raw', '')

                    if not unit_text:
                        continue

                    record_type = data.get('record_type', 'unknown')
                    chunk_id = f"{doc_id}:{record_type}:{line_no:06d}"

                    chunks.append({
                        'chunk_id': chunk_id,
                        'doc_id': doc_id,
                        'chunk_index': line_no - 1,  # 0-based
                        'chunk_type': record_type,
                        'content': unit_text,
                        'content_length': len(unit_text),
                    })
                except Exception as e:
                    print(f"  ⚠️ Error parsing line {line_no} for chunks: {e}")
                    continue

        if not chunks:
            print(f"  ⚠️ No chunks created from {jsonl_path.name}")
            return 0

        # chunk_total 설정
        chunk_total = len(chunks)
        for chunk in chunks:
            chunk['chunk_total'] = chunk_total

        # 삽입
        insert_sql = """
        INSERT INTO chunks (
            chunk_id, doc_id, chunk_index, chunk_total, chunk_type,
            content, content_length, embedding, drop
        ) VALUES (
            %(chunk_id)s, %(doc_id)s, %(chunk_index)s, %(chunk_total)s, %(chunk_type)s,
            %(content)s, %(content_length)s, NULL, FALSE
        )
        ON CONFLICT (chunk_id) DO UPDATE SET
            content = EXCLUDED.content,
            content_length = EXCLUDED.content_length,
            updated_at = NOW()
        """

        # Replace execute_batch with executemany
        cursor.executemany(insert_sql, chunks)
        conn.commit()

        print(f"  ✅ Loaded {len(chunks)} chunks to documents/chunks tables")
        return len(chunks)


def main():
    """메인 함수"""
    print("=" * 60)
    print("S1-D3: 분쟁조정기준 데이터 로딩")
    print("=" * 60)

    # 데이터 디렉토리
    script_dir = Path(__file__).parent
    # backend/scripts/data_loading -> backend/data/criteria/jsonl
    data_dir = script_dir.parent.parent / 'data' / 'criteria' / 'jsonl'

    if not data_dir.exists():
        print(f"❌ Error: Data directory not found: {data_dir}")
        return

    print(f"\nData directory: {data_dir}")
    print(f"DB: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")

    # 데이터베이스 연결
    try:
        # Use psycopg.connect with dictionary unpacking
        conn = psycopg.connect(**DB_CONFIG)
        print("✅ Database connected")
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return

    try:
        with conn.cursor() as cursor:
            # criteria 테이블 데이터 확인
            cursor.execute("SELECT source_id, source_label FROM criteria ORDER BY source_id")
            criteria_sources = cursor.fetchall()
            print(f"\n📊 Available criteria sources ({len(criteria_sources)}):")
            for source_id, source_label in criteria_sources:
                print(f"  - {source_id}: {source_label}")

            # 각 소스별 JSONL 파일 로드
            total_units = 0
            total_chunks = 0

            for source_id, filename in CRITERIA_FILES.items():
                jsonl_path = data_dir / filename

                print(f"\n📂 Processing: {source_id} ({filename})")

                if not jsonl_path.exists():
                    print(f"  ⚠️ File not found: {jsonl_path}, skipping")
                    continue

                # criteria 테이블에서 source_label 가져오기
                cursor.execute("SELECT source_label FROM criteria WHERE source_id = %s", (source_id,))
                result = cursor.fetchone()
                source_label = result[0] if result else source_id

                # 1. criteria_units 테이블에 로드
                # (load_criteria_units now uses cursor internally, so check if we need to pass cursor or conn)
                # It takes 'conn'.
                units_count = load_criteria_units(conn, source_id, jsonl_path)
                total_units += units_count

                # 2. documents + chunks 테이블에도 로드 (RAG 통합 검색)
                chunks_count = load_to_documents_chunks(conn, source_id, source_label, jsonl_path)
                total_chunks += chunks_count

            # 결과 요약
            print("\n" + "=" * 60)
            print("📊 Loading Summary")
            print("=" * 60)

            cursor.execute("SELECT source_id, COUNT(*) FROM criteria_units GROUP BY source_id ORDER BY source_id")
            print("\n[criteria_units table]")
            for source_id, count in cursor.fetchall():
                print(f"  {source_id}: {count} units")

            cursor.execute("""
                SELECT d.doc_type, COUNT(c.*)
                FROM chunks c
                JOIN documents d ON c.doc_id = d.doc_id
                WHERE d.doc_type LIKE 'criteria_%'
                GROUP BY d.doc_type
                ORDER BY d.doc_type
            """)
            print("\n[chunks table]")
            for doc_type, count in cursor.fetchall():
                print(f"  {doc_type}: {count} chunks")

            print(f"\n✅ Total loaded: {total_units} units, {total_chunks} chunks")
            print("=" * 60)

    except Exception as e:
        print(f"\n❌ Error during processing: {e}")
        # connection rollback is usually automatic on error context exit in some drivers, 
        # but explicit rollback is good if we are reusing conn.
        # Here we are in main, so it's fine.
        conn.rollback()
    finally:
        conn.close()
        print("\n🔌 Database connection closed")


if __name__ == '__main__':
    main()
