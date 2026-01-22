"""
분쟁조정사례 청크 관계 마이그레이션 스크립트
작성일: 2026-01-20
Phase 3: chunk_relations에 분쟁조정사례의 prev/next 관계 추가

분쟁조정사례는 하나의 사례가 여러 청크로 분할되어 있음.
이 스크립트는 같은 doc_id 내 청크들을 chunk_index로 연결하여
사례 수준 유사도 검색을 가능하게 함.
"""

import os
import sys
import logging
import psycopg2
from psycopg2.extras import execute_values

# 프로젝트 루트 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_db_connection():
    """데이터베이스 연결"""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        dbname=os.getenv('DB_NAME', 'ddoksori'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD', 'postgres')
    )


def migrate_dispute_chunk_relations(conn, dry_run: bool = False):
    """
    분쟁조정사례 청크에 prev_chunk, next_chunk 관계 추가

    Args:
        conn: 데이터베이스 연결
        dry_run: True면 실제 삽입 없이 미리보기만
    """
    with conn.cursor() as cur:
        # 1. 기존 분쟁조정사례 관계 삭제 (재실행 대비)
        if not dry_run:
            logger.info("기존 분쟁조정사례 관계 삭제 중...")
            cur.execute("""
                DELETE FROM chunk_relations
                WHERE (source_chunk_id LIKE 'ECMC%%' OR source_chunk_id LIKE 'KCA%%' OR source_chunk_id LIKE 'KCDRC%%')
                  AND relation_type IN ('prev_chunk', 'next_chunk', 'same_document')
            """)
            deleted = cur.rowcount
            logger.info(f"삭제된 관계: {deleted}개")

        # 2. next_chunk 관계 생성 (같은 doc_id, 같은 chunk_type, 연속 chunk_index)
        logger.info("next_chunk 관계 생성 중...")
        cur.execute("""
            SELECT
                c1.chunk_id as source,
                c2.chunk_id as target,
                'next_chunk' as relation_type
            FROM chunks c1
            JOIN chunks c2 ON c1.doc_id = c2.doc_id
                AND c1.chunk_type = c2.chunk_type
                AND c2.chunk_index = c1.chunk_index + 1
            WHERE (c1.doc_id LIKE 'ECMC%%' OR c1.doc_id LIKE 'KCA%%' OR c1.doc_id LIKE 'KCDRC%%')
              AND c1.drop = FALSE
              AND c2.drop = FALSE
        """)
        next_relations = cur.fetchall()
        logger.info(f"next_chunk 관계: {len(next_relations)}개")

        # 3. prev_chunk 관계 생성 (역방향)
        logger.info("prev_chunk 관계 생성 중...")
        cur.execute("""
            SELECT
                c2.chunk_id as source,
                c1.chunk_id as target,
                'prev_chunk' as relation_type
            FROM chunks c1
            JOIN chunks c2 ON c1.doc_id = c2.doc_id
                AND c1.chunk_type = c2.chunk_type
                AND c2.chunk_index = c1.chunk_index + 1
            WHERE (c1.doc_id LIKE 'ECMC%%' OR c1.doc_id LIKE 'KCA%%' OR c1.doc_id LIKE 'KCDRC%%')
              AND c1.drop = FALSE
              AND c2.drop = FALSE
        """)
        prev_relations = cur.fetchall()
        logger.info(f"prev_chunk 관계: {len(prev_relations)}개")

        if dry_run:
            logger.info("[DRY RUN] 실제 삽입 없음")
            return

        # 4. 관계 삽입
        all_relations = [(r[0], r[1], r[2], 1.0) for r in next_relations + prev_relations]

        if all_relations:
            logger.info(f"총 {len(all_relations)}개 관계 삽입 중...")
            execute_values(
                cur,
                """
                INSERT INTO chunk_relations (source_chunk_id, target_chunk_id, relation_type, confidence)
                VALUES %s
                ON CONFLICT (source_chunk_id, target_chunk_id, relation_type) DO NOTHING
                """,
                all_relations
            )
            logger.info("삽입 완료")

        conn.commit()


def verify_migration(conn):
    """마이그레이션 결과 검증"""
    with conn.cursor() as cur:
        # 관계 유형별 통계
        cur.execute("""
            SELECT relation_type, COUNT(*)
            FROM chunk_relations
            WHERE source_chunk_id LIKE 'ECMC%%'
               OR source_chunk_id LIKE 'KCA%%'
               OR source_chunk_id LIKE 'KCDRC%%'
            GROUP BY relation_type
        """)
        stats = cur.fetchall()

        logger.info("=== 마이그레이션 결과 ===")
        for relation_type, count in stats:
            logger.info(f"  {relation_type}: {count}개")

        # 샘플 데이터 확인
        cur.execute("""
            SELECT cr.source_chunk_id, cr.target_chunk_id, cr.relation_type
            FROM chunk_relations cr
            WHERE cr.source_chunk_id LIKE 'ECMC%%'
            LIMIT 5
        """)
        samples = cur.fetchall()

        if samples:
            logger.info("\n=== 샘플 관계 ===")
            for source, target, rel_type in samples:
                logger.info(f"  {source} --[{rel_type}]--> {target}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='분쟁조정사례 청크 관계 마이그레이션')
    parser.add_argument('--dry-run', action='store_true', help='실제 삽입 없이 미리보기')
    parser.add_argument('--verify', action='store_true', help='마이그레이션 결과 검증만')
    args = parser.parse_args()

    try:
        conn = get_db_connection()
        logger.info("데이터베이스 연결 성공")

        if args.verify:
            verify_migration(conn)
        else:
            migrate_dispute_chunk_relations(conn, dry_run=args.dry_run)
            verify_migration(conn)

        conn.close()
        logger.info("완료")

    except Exception as e:
        logger.error(f"오류 발생: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
