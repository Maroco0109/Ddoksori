"""
데이터 로드 테스트 스크립트

소량 데이터로 로드 스크립트를 테스트하고 검증합니다.
"""
import os
import json
import tempfile
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

import psycopg
from load_cases_to_db import (
    load_counsel_jsonl,
    load_dispute_jsonl,
    conninfo_from_env
)


def create_test_counsel_jsonl(output_path: str, num_cases: int = 3):
    """테스트용 counsel jsonl 파일 생성"""
    test_data = [
        {
            "doc_id": "TEST001",
            "chunk_id": "TEST001:problem:0000",
            "chunk_type": "problem",
            "chunk_index": 0,
            "dataset": "cnslt",
            "doc_type": "consumer_counsel_case",
            "title": "테스트 상담사례 1",
            "url": "https://www.consumer.go.kr/test/001",
            "source": "1372 소비자 상담센터",
            "category": "금융 > 신용카드",
            "collected_at": "2025-01-01T10:00:00+00:00",
            "text": "제목: 테스트 상담사례 1\n\n분류: 금융 > 신용카드\n\n질문:\n- 신용카드 수수료에 대해 문의합니다.",
            "metadata": {
                "site": "consumer.go.kr",
                "doc_type": "consumer_counsel_case",
                "case_sn": "TEST001",
                "field": "금융",
                "item": "신용카드",
                "views": "100"
            }
        },
        {
            "doc_id": "TEST001",
            "chunk_id": "TEST001:solution:0001",
            "chunk_type": "solution",
            "chunk_index": 1,
            "dataset": "cnslt",
            "doc_type": "consumer_counsel_case",
            "title": "테스트 상담사례 1",
            "url": "https://www.consumer.go.kr/test/001",
            "source": "1372 소비자 상담센터",
            "category": "금융 > 신용카드",
            "collected_at": "2025-01-01T10:00:00+00:00",
            "text": "제목: 테스트 상담사례 1\n\n답변:\n- 신용카드 수수료는 관련 법령에 따라 정해집니다.",
            "metadata": {
                "site": "consumer.go.kr",
                "doc_type": "consumer_counsel_case",
                "case_sn": "TEST001",
                "field": "금융",
                "item": "신용카드",
                "views": "100"
            }
        },
        {
            "doc_id": "TEST001",
            "chunk_id": "TEST001:full:0002",
            "chunk_type": "full",
            "chunk_index": 2,
            "dataset": "cnslt",
            "doc_type": "consumer_counsel_case",
            "title": "테스트 상담사례 1",
            "url": "https://www.consumer.go.kr/test/001",
            "source": "1372 소비자 상담센터",
            "category": "금융 > 신용카드",
            "collected_at": "2025-01-01T10:00:00+00:00",
            "text": "제목: 테스트 상담사례 1\n\n분류: 금융 > 신용카드\n\n질문:\n- 신용카드 수수료에 대해 문의합니다.\n\n답변:\n- 신용카드 수수료는 관련 법령에 따라 정해집니다.",
            "metadata": {
                "site": "consumer.go.kr",
                "doc_type": "consumer_counsel_case",
                "case_sn": "TEST001",
                "field": "금융",
                "item": "신용카드",
                "views": "100"
            }
        }
    ]
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for item in test_data[:num_cases * 3]:  # 각 케이스당 3개 청크
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    
    print(f"테스트 counsel jsonl 파일 생성: {output_path} ({len(test_data)}개 청크)")


def create_test_dispute_jsonl(output_path: str, agency: str = "kca", num_cases: int = 2):
    """테스트용 dispute jsonl 파일 생성"""
    test_data = [
        {
            "agency": agency,
            "source_pdf": f"{agency}_test_001",
            "case_index": 1,
            "case_no": "TEST001",
            "decision_date": "2025.1.1",
            "section_type": "facts",
            "page_start": 1,
            "page_end": 5,
            "chunk_index": 1,
            "text": "사건개요: 테스트 분쟁조정사례 1의 사실관계입니다."
        },
        {
            "agency": agency,
            "source_pdf": f"{agency}_test_001",
            "case_index": 1,
            "case_no": "TEST001",
            "decision_date": "2025.1.1",
            "section_type": "claims",
            "page_start": 5,
            "page_end": 10,
            "chunk_index": 2,
            "text": "당사자 주장: 신청인과 피신청인의 주장 내용입니다."
        },
        {
            "agency": agency,
            "source_pdf": f"{agency}_test_001",
            "case_index": 1,
            "case_no": "TEST001",
            "decision_date": "2025.1.1",
            "section_type": "mediation_outcome",
            "page_start": 10,
            "page_end": 15,
            "chunk_index": 3,
            "text": "조정결과: 양 당사자가 합의하여 조정이 성립되었습니다."
        }
    ]
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for item in test_data[:num_cases * 3]:  # 각 케이스당 3개 청크
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    
    print(f"테스트 dispute jsonl 파일 생성: {output_path} ({len(test_data)}개 청크)")


def verify_documents(conn: psycopg.Connection, doc_type: str, expected_count: int):
    """documents 테이블 검증"""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM documents WHERE doc_type = %s",
            (doc_type,)
        )
        count = cur.fetchone()[0]
        print(f"  documents 테이블 ({doc_type}): {count}개 (예상: {expected_count}개)")
        
        if count > 0:
            cur.execute(
                """
                SELECT doc_id, title, source_org, category_path, url
                FROM documents 
                WHERE doc_type = %s 
                LIMIT 5
                """,
                (doc_type,)
            )
            rows = cur.fetchall()
            print("  샘플 문서:")
            for row in rows:
                print(f"    - {row[0]}: {row[1]} ({row[2]})")
        
        return count == expected_count


def verify_chunks(conn: psycopg.Connection, doc_type: str, expected_count: int):
    """chunks 테이블 검증"""
    with conn.cursor() as cur:
        # documents와 조인하여 doc_type으로 필터링
        cur.execute(
            """
            SELECT COUNT(*) 
            FROM chunks c
            JOIN documents d ON c.doc_id = d.doc_id
            WHERE d.doc_type = %s
            """,
            (doc_type,)
        )
        count = cur.fetchone()[0]
        print(f"  chunks 테이블 ({doc_type}): {count}개 (예상: {expected_count}개)")
        
        if count > 0:
            cur.execute(
                """
                SELECT c.chunk_id, c.doc_id, c.chunk_type, c.chunk_index, c.chunk_total, 
                       LENGTH(c.content) as content_length
                FROM chunks c
                JOIN documents d ON c.doc_id = d.doc_id
                WHERE d.doc_type = %s
                ORDER BY c.doc_id, c.chunk_index
                LIMIT 5
                """,
                (doc_type,)
            )
            rows = cur.fetchall()
            print("  샘플 청크:")
            for row in rows:
                print(f"    - {row[0]}: {row[2]} (index={row[3]}, total={row[4]}, len={row[5]})")
        
        return count == expected_count


def verify_data_integrity(conn: psycopg.Connection):
    """데이터 무결성 검증"""
    print("\n=== 데이터 무결성 검증 ===")
    
    with conn.cursor() as cur:
        # 1. chunk_total 일관성 검증
        cur.execute("""
            SELECT c.doc_id, c.chunk_total, COUNT(*) as actual_count
            FROM chunks c
            GROUP BY c.doc_id, c.chunk_total
            HAVING COUNT(*) != c.chunk_total
        """)
        inconsistent = cur.fetchall()
        if inconsistent:
            print(f"  경고: chunk_total 불일치 문서 {len(inconsistent)}개 발견")
            for row in inconsistent[:5]:
                print(f"    - {row[0]}: chunk_total={row[1]}, 실제={row[2]}")
        else:
            print("  ✓ chunk_total 일관성 확인")
        
        # 2. 외래키 관계 검증
        cur.execute("""
            SELECT COUNT(*) 
            FROM chunks c
            LEFT JOIN documents d ON c.doc_id = d.doc_id
            WHERE d.doc_id IS NULL
        """)
        orphan_chunks = cur.fetchone()[0]
        if orphan_chunks > 0:
            print(f"  경고: 고아 청크 {orphan_chunks}개 발견")
        else:
            print("  ✓ 외래키 관계 확인")
        
        # 3. chunk_index 범위 검증
        cur.execute("""
            SELECT COUNT(*) 
            FROM chunks c
            WHERE c.chunk_index >= c.chunk_total OR c.chunk_index < 0
        """)
        invalid_index = cur.fetchone()[0]
        if invalid_index > 0:
            print(f"  경고: 잘못된 chunk_index {invalid_index}개 발견")
        else:
            print("  ✓ chunk_index 범위 확인")


def test_counsel_loading():
    """Counsel 데이터 로드 테스트"""
    print("\n=== Counsel 데이터 로드 테스트 ===")
    
    # 테스트 파일 생성
    test_file = tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False, encoding='utf-8')
    test_file.close()
    
    try:
        create_test_counsel_jsonl(test_file.name, num_cases=1)
        
        # 데이터 로드
        conninfo = conninfo_from_env()
        conn = psycopg.connect(conninfo)
        
        try:
            doc_count, chunk_count = load_counsel_jsonl(test_file.name, batch_size=100, conn=conn)
            
            print(f"\n로드 완료: {doc_count}개 문서, {chunk_count}개 청크")
            
            # 검증
            print("\n=== 검증 ===")
            verify_documents(conn, 'counsel_case', 1)
            verify_chunks(conn, 'counsel_case', 3)
            verify_data_integrity(conn)
            
        finally:
            conn.close()
    
    finally:
        # 테스트 파일 삭제
        os.unlink(test_file.name)


def test_dispute_loading():
    """Dispute 데이터 로드 테스트"""
    print("\n=== Dispute 데이터 로드 테스트 ===")
    
    # 테스트 파일 생성
    test_file = tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False, encoding='utf-8')
    test_file.close()
    
    try:
        create_test_dispute_jsonl(test_file.name, agency='kca', num_cases=1)
        
        # 데이터 로드
        conninfo = conninfo_from_env()
        conn = psycopg.connect(conninfo)
        
        try:
            doc_count, chunk_count = load_dispute_jsonl(test_file.name, 'kca', batch_size=100, conn=conn)
            
            print(f"\n로드 완료: {doc_count}개 문서, {chunk_count}개 청크")
            
            # 검증
            print("\n=== 검증 ===")
            verify_documents(conn, 'mediation_case', 1)
            verify_chunks(conn, 'mediation_case', 3)
            verify_data_integrity(conn)
            
        finally:
            conn.close()
    
    finally:
        # 테스트 파일 삭제
        os.unlink(test_file.name)


def main():
    """메인 함수"""
    print("=" * 60)
    print("데이터 로드 테스트 시작")
    print("=" * 60)
    
    try:
        test_counsel_loading()
        test_dispute_loading()
        
        print("\n" + "=" * 60)
        print("모든 테스트 완료")
        print("=" * 60)
    
    except Exception as e:
        print(f"\n오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
