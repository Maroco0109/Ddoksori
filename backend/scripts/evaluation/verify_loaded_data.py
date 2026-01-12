"""
로드된 데이터 검증 스크립트 (S1-D2 Enhanced)

documents/chunks/law_node 테이블에 로드된 데이터를 검증합니다.
argparse 지원: --law, --criteria, --dispute, --counsel, --all
"""
import os
import argparse
from dotenv import load_dotenv

load_dotenv()

import psycopg


def conninfo_from_env() -> str:
    """환경 변수에서 PostgreSQL 연결 정보 생성"""
    return (
        f"host={os.environ.get('PGHOST','localhost')} "
        f"port={os.environ.get('PGPORT','5432')} "
        f"dbname={os.environ.get('PGDATABASE','ddoksori')} "
        f"user={os.environ.get('PGUSER','postgres')} "
        f"password={os.environ.get('PGPASSWORD','postgres')}"
    )


def verify_documents(conn: psycopg.Connection):
    """documents 테이블 검증"""
    print("\n=== Documents 테이블 검증 ===")
    
    with conn.cursor() as cur:
        # 전체 문서 수
        cur.execute("SELECT COUNT(*) FROM documents")
        total = cur.fetchone()[0]
        print(f"전체 문서 수: {total}")
        
        # doc_type별 통계
        cur.execute("""
            SELECT doc_type, COUNT(*) as count
            FROM documents
            GROUP BY doc_type
            ORDER BY count DESC
        """)
        print("\ndoc_type별 통계:")
        for row in cur.fetchall():
            print(f"  - {row[0]}: {row[1]}개")
        
        # source_org별 통계
        cur.execute("""
            SELECT source_org, COUNT(*) as count
            FROM documents
            GROUP BY source_org
            ORDER BY count DESC
        """)
        print("\nsource_org별 통계:")
        for row in cur.fetchall():
            print(f"  - {row[0]}: {row[1]}개")
        
        # 샘플 문서
        cur.execute("""
            SELECT doc_id, doc_type, title, source_org, category_path
            FROM documents
            ORDER BY created_at DESC
            LIMIT 5
        """)
        print("\n샘플 문서 (최근 5개):")
        for row in cur.fetchall():
            category = row[4] if row[4] else []
            print(f"  - {row[0]} ({row[1]}): {row[2][:50]}... [{row[3]}] {category}")


def verify_chunks(conn: psycopg.Connection):
    """chunks 테이블 검증"""
    print("\n=== Chunks 테이블 검증 ===")
    
    with conn.cursor() as cur:
        # 전체 청크 수
        cur.execute("SELECT COUNT(*) FROM chunks")
        total = cur.fetchone()[0]
        print(f"전체 청크 수: {total}")
        
        # doc_type별 청크 수
        cur.execute("""
            SELECT d.doc_type, COUNT(*) as count
            FROM chunks c
            JOIN documents d ON c.doc_id = d.doc_id
            GROUP BY d.doc_type
            ORDER BY count DESC
        """)
        print("\ndoc_type별 청크 수:")
        for row in cur.fetchall():
            print(f"  - {row[0]}: {row[1]}개")
        
        # chunk_type별 통계
        cur.execute("""
            SELECT chunk_type, COUNT(*) as count
            FROM chunks
            WHERE chunk_type IS NOT NULL
            GROUP BY chunk_type
            ORDER BY count DESC
            LIMIT 10
        """)
        print("\nchunk_type별 통계 (상위 10개):")
        for row in cur.fetchall():
            print(f"  - {row[0]}: {row[1]}개")
        
        # 샘플 청크
        cur.execute("""
            SELECT c.chunk_id, c.doc_id, c.chunk_type, c.chunk_index, c.chunk_total,
                   LENGTH(c.content) as content_length, d.title
            FROM chunks c
            JOIN documents d ON c.doc_id = d.doc_id
            ORDER BY c.created_at DESC
            LIMIT 5
        """)
        print("\n샘플 청크 (최근 5개):")
        for row in cur.fetchall():
            print(f"  - {row[0]}: {row[2]} (index={row[3]}/{row[4]-1}, len={row[5]}) - {row[6][:30]}...")


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
            print(f"⚠️  chunk_total 불일치 문서 {len(inconsistent)}개 발견")
            for row in inconsistent[:5]:
                print(f"    - {row[0]}: chunk_total={row[1]}, 실제={row[2]}")
        else:
            print("✓ chunk_total 일관성 확인")
        
        # 2. 외래키 관계 검증
        cur.execute("""
            SELECT COUNT(*) 
            FROM chunks c
            LEFT JOIN documents d ON c.doc_id = d.doc_id
            WHERE d.doc_id IS NULL
        """)
        orphan_chunks = cur.fetchone()[0]
        if orphan_chunks > 0:
            print(f"⚠️  고아 청크 {orphan_chunks}개 발견")
        else:
            print("✓ 외래키 관계 확인")
        
        # 3. chunk_index 범위 검증
        cur.execute("""
            SELECT COUNT(*) 
            FROM chunks c
            WHERE c.chunk_index >= c.chunk_total OR c.chunk_index < 0
        """)
        invalid_index = cur.fetchone()[0]
        if invalid_index > 0:
            print(f"⚠️  잘못된 chunk_index {invalid_index}개 발견")
        else:
            print("✓ chunk_index 범위 확인")
        
        # 4. 중복 chunk_id 검증
        cur.execute("""
            SELECT chunk_id, COUNT(*) as count
            FROM chunks
            GROUP BY chunk_id
            HAVING COUNT(*) > 1
        """)
        duplicates = cur.fetchall()
        if duplicates:
            print(f"⚠️  중복 chunk_id {len(duplicates)}개 발견")
            for row in duplicates[:5]:
                print(f"    - {row[0]}: {row[1]}개")
        else:
            print("✓ chunk_id 중복 없음")


def verify_search_metadata(conn: psycopg.Connection):
    """검색 결과 메타데이터 검증"""
    print("\n=== 검색 결과 메타데이터 검증 ===")

    with conn.cursor() as cur:
        # 검색 결과에 포함되어야 할 메타데이터 확인
        cur.execute("""
            SELECT
                c.chunk_id,
                c.doc_id,
                c.chunk_type,
                d.title,
                d.source_org,
                d.doc_type,
                d.category_path,
                d.url,
                d.metadata
            FROM chunks c
            JOIN documents d ON c.doc_id = d.doc_id
            WHERE d.doc_type IN ('counsel_case', 'mediation_case')
            LIMIT 5
        """)

        print("검색 결과 샘플 (메타데이터 포함):")
        for row in cur.fetchall():
            print(f"\n  청크: {row[0]}")
            print(f"    - doc_id: {row[1]}")
            print(f"    - chunk_type: {row[2]}")
            print(f"    - title: {row[3]}")
            print(f"    - source_org: {row[4]}")
            print(f"    - doc_type: {row[5]}")
            print(f"    - category_path: {row[6]}")
            print(f"    - url: {row[7]}")
            print(f"    - metadata: {str(row[8])[:100]}...")


def verify_laws(conn: psycopg.Connection):
    """laws 테이블 검증 (S1-D2)"""
    print("\n=== Laws 테이블 검증 (S1-D2) ===")

    with conn.cursor() as cur:
        # 전체 법령 수
        cur.execute("SELECT COUNT(*) FROM laws")
        total = cur.fetchone()[0]
        print(f"전체 법령 수: {total}")

        # 법령별 통계
        cur.execute("""
            SELECT law_name, enforcement_date, revision_type
            FROM laws
            ORDER BY law_name
        """)
        print("\n법령 목록:")
        for row in cur.fetchall():
            print(f"  - {row[0]} (시행: {row[1]}, {row[2]})")


def verify_law_nodes(conn: psycopg.Connection):
    """law_node 테이블 검증 (S1-D2)"""
    print("\n=== Law_Node 테이블 검증 (S1-D2) ===")

    with conn.cursor() as cur:
        # 전체 노드 수
        cur.execute("SELECT COUNT(*) FROM law_node")
        total = cur.fetchone()[0]
        print(f"전체 law_node 수: {total}")

        # level별 통계
        cur.execute("""
            SELECT level, COUNT(*) as count
            FROM law_node
            GROUP BY level
            ORDER BY count DESC
        """)
        print("\nlevel별 통계:")
        for row in cur.fetchall():
            print(f"  - {row[0]}: {row[1]}개")

        # search_stage별 통계
        cur.execute("""
            SELECT search_stage, COUNT(*) as count
            FROM law_node
            WHERE search_stage IS NOT NULL
            GROUP BY search_stage
            ORDER BY count DESC
        """)
        print("\nsearch_stage별 통계:")
        for row in cur.fetchall():
            print(f"  - {row[0]}: {row[1]}개")

        # indexable 통계
        cur.execute("""
            SELECT is_indexable, COUNT(*) as count
            FROM law_node
            GROUP BY is_indexable
        """)
        print("\nis_indexable 통계:")
        for row in cur.fetchall():
            indexable_str = "indexable" if row[0] else "not_indexable"
            print(f"  - {indexable_str}: {row[1]}개")


def verify_law_hierarchy(conn: psycopg.Connection):
    """law_node 계층 구조 무결성 검증 (S1-D2)"""
    print("\n=== Law_Node 계층 구조 무결성 검증 ===")

    with conn.cursor() as cur:
        # 1. parent_id 참조 무결성
        cur.execute("""
            SELECT COUNT(*)
            FROM law_node ln1
            WHERE ln1.parent_id IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM law_node ln2 WHERE ln2.doc_id = ln1.parent_id
            )
        """)
        orphan_nodes = cur.fetchone()[0]
        if orphan_nodes > 0:
            print(f"⚠️  parent_id가 유효하지 않은 노드 {orphan_nodes}개 발견")
        else:
            print("✓ parent_id 참조 무결성 확인")

        # 2. article-paragraph-item-subitem 계층 검증
        cur.execute("""
            SELECT
                parent.level as parent_level,
                child.level as child_level,
                COUNT(*) as count
            FROM law_node child
            JOIN law_node parent ON child.parent_id = parent.doc_id
            GROUP BY parent.level, child.level
            ORDER BY count DESC
        """)
        print("\n계층 관계 통계 (parent_level → child_level):")
        for row in cur.fetchall():
            print(f"  - {row[0]} → {row[1]}: {row[2]}개")


def verify_law_2stage_search(conn: psycopg.Connection):
    """2단계 검색 설정 검증 (S1-D2)"""
    print("\n=== 2단계 검색 설정 검증 ===")

    with conn.cursor() as cur:
        # stage1 (article-level) 검증
        cur.execute("""
            SELECT COUNT(*)
            FROM law_node
            WHERE level = 'article' AND search_stage != 'stage1'
        """)
        wrong_stage1 = cur.fetchone()[0]
        if wrong_stage1 > 0:
            print(f"⚠️  article인데 stage1이 아닌 노드 {wrong_stage1}개")
        else:
            print("✓ stage1 (article-level) 설정 확인")

        # stage2 (paragraph/item/subitem) 검증
        cur.execute("""
            SELECT COUNT(*)
            FROM law_node
            WHERE level IN ('paragraph', 'item', 'subitem')
            AND is_indexable = TRUE
            AND search_stage != 'stage2'
        """)
        wrong_stage2 = cur.fetchone()[0]
        if wrong_stage2 > 0:
            print(f"⚠️  paragraph/item/subitem인데 stage2가 아닌 indexable 노드 {wrong_stage2}개")
        else:
            print("✓ stage2 (paragraph/item/subitem-level) 설정 확인")


def verify_law_rag_integration(conn: psycopg.Connection):
    """law_node와 RAG 테이블 통합 검증 (S1-D2)"""
    print("\n=== Law_Node ↔ RAG 통합 검증 ===")

    with conn.cursor() as cur:
        # 1. documents 테이블에 law 타입 문서 존재 확인
        cur.execute("""
            SELECT COUNT(*)
            FROM documents
            WHERE doc_type = 'law'
        """)
        law_docs = cur.fetchone()[0]
        print(f"documents 테이블의 law 타입 문서: {law_docs}개")

        # 2. chunks 테이블에 law 청크 존재 확인
        cur.execute("""
            SELECT COUNT(*)
            FROM chunks c
            JOIN documents d ON c.doc_id = d.doc_id
            WHERE d.doc_type = 'law'
        """)
        law_chunks = cur.fetchone()[0]
        print(f"chunks 테이블의 law 청크: {law_chunks}개")

        # 3. law_node의 indexable 노드와 chunks 개수 비교
        cur.execute("""
            SELECT COUNT(*)
            FROM law_node
            WHERE is_indexable = TRUE
        """)
        indexable_nodes = cur.fetchone()[0]
        print(f"law_node의 indexable 노드: {indexable_nodes}개")

        if law_chunks == indexable_nodes:
            print("✓ law_node (indexable) 개수와 chunks 개수 일치")
        else:
            print(f"⚠️  law_node (indexable) {indexable_nodes}개 vs chunks {law_chunks}개 불일치")

        # 4. chunk_relations에 법령 계층 관계 존재 확인
        cur.execute("""
            SELECT relation_type, COUNT(*) as count
            FROM chunk_relations
            WHERE relation_type IN ('child_paragraph', 'child_item', 'child_subitem')
            GROUP BY relation_type
            ORDER BY count DESC
        """)
        print("\nchunk_relations 법령 계층 타입:")
        has_relations = False
        for row in cur.fetchall():
            print(f"  - {row[0]}: {row[1]}개")
            has_relations = True

        if not has_relations:
            print("  (없음)")


def verify_law_sample_queries(conn: psycopg.Connection):
    """법령 샘플 쿼리 실행 (S1-D2)"""
    print("\n=== 법령 샘플 쿼리 ===")

    with conn.cursor() as cur:
        # 샘플 1: 특정 법령의 조문 조회
        cur.execute("""
            SELECT doc_id, level, article_no, paragraph_no, path, LEFT(text, 60) as text_preview
            FROM law_node
            WHERE law_id = (SELECT law_id FROM laws LIMIT 1)
            AND level = 'article'
            AND is_indexable = TRUE
            LIMIT 3
        """)
        print("\n샘플 1: 조문 조회 (stage1):")
        for row in cur.fetchall():
            print(f"  - {row[4]}: {row[5]}...")

        # 샘플 2: 특정 조문의 하위 항/호 조회
        cur.execute("""
            SELECT child.doc_id, child.level, child.path, LEFT(child.text, 60) as text_preview
            FROM law_node child
            JOIN law_node parent ON child.parent_id = parent.doc_id
            WHERE parent.level = 'article'
            AND child.level IN ('paragraph', 'item')
            AND child.is_indexable = TRUE
            LIMIT 5
        """)
        print("\n샘플 2: 항/호 조회 (stage2):")
        for row in cur.fetchall():
            print(f"  - {row[2]}: {row[3]}...")


def main():
    """메인 함수 (S1-D2: argparse 지원)"""
    parser = argparse.ArgumentParser(
        description="로드된 데이터 검증 스크립트 (S1-D2)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python verify_loaded_data.py --law          # 법령 데이터만 검증
  python verify_loaded_data.py --dispute --counsel  # 분쟁/상담 사례 검증
  python verify_loaded_data.py --all          # 모든 데이터 검증
        """
    )

    parser.add_argument('--law', action='store_true', help='법령 데이터 검증')
    parser.add_argument('--criteria', action='store_true', help='분쟁조정기준 검증')
    parser.add_argument('--dispute', action='store_true', help='분쟁조정사례 검증')
    parser.add_argument('--counsel', action='store_true', help='상담사례 검증')
    parser.add_argument('--all', action='store_true', help='모든 데이터 검증')

    args = parser.parse_args()

    # 아무 옵션도 지정하지 않으면 --all과 동일
    if not (args.law or args.criteria or args.dispute or args.counsel or args.all):
        args.all = True

    print("=" * 60)
    print("로드된 데이터 검증 시작 (S1-D2 Enhanced)")
    print("=" * 60)

    try:
        conninfo = conninfo_from_env()
        conn = psycopg.connect(conninfo)

        try:
            # 공통 검증 (항상 실행)
            if args.all or args.dispute or args.counsel:
                verify_documents(conn)
                verify_chunks(conn)
                verify_data_integrity(conn)

            # 법령 데이터 검증
            if args.law or args.all:
                print("\n" + "=" * 60)
                print("법령 데이터 검증 (S1-D2)")
                print("=" * 60)
                verify_laws(conn)
                verify_law_nodes(conn)
                verify_law_hierarchy(conn)
                verify_law_2stage_search(conn)
                verify_law_rag_integration(conn)
                verify_law_sample_queries(conn)

            # 검색 메타데이터 검증 (모든 타입 공통)
            if args.all or args.dispute or args.counsel:
                verify_search_metadata(conn)

            print("\n" + "=" * 60)
            print("검증 완료")
            print("=" * 60)

        finally:
            conn.close()

    except psycopg.OperationalError as e:
        print(f"\n❌ 데이터베이스 연결 실패: {e}")
        print("데이터베이스가 실행 중인지 확인하세요.")
        return 1
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
