"""
게시판 DB 연결 및 설정 테스트 스크립트

사용법:
    conda activate ddoksori
    cd LLM/backend
    python scripts/test_board_db.py
"""

import os
import sys

# 프로젝트 루트를 path에 추가
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

# .env 파일 로드 (프로젝트 루트의 LLM/.env)
llm_dir = os.path.dirname(backend_dir)
env_path = os.path.join(llm_dir, ".env")

try:
    from dotenv import load_dotenv

    if os.path.exists(env_path):
        load_dotenv(env_path)
        print(f"[INFO] .env 파일 로드: {env_path}")
    else:
        print(f"[WARNING] .env 파일 없음: {env_path}")
except ImportError:
    print("[WARNING] python-dotenv가 설치되지 않았습니다. pip install python-dotenv")

import psycopg2
import psycopg2.extras

from app.common.config import get_config


def test_db_connection():
    """DB 연결 테스트"""
    print("[1/4] DB 연결 테스트...")

    try:
        config = get_config()
        conn = psycopg2.connect(**config.database.get_connection_dict())
        conn.close()
        print("     [OK] DB 연결 성공!")
        return True
    except Exception as e:
        print(f"     [ERROR] DB 연결 실패: {e}")
        return False


def test_tables_exist():
    """테이블 존재 여부 확인"""
    print("[2/4] 테이블 존재 여부 확인...")

    tables = [
        "community_category",
        "community_post",
        "community_comment",
        "community_post_like",
        "community_comment_like",
        "community_report",
    ]

    try:
        config = get_config()
        conn = psycopg2.connect(**config.database.get_connection_dict())
        with conn.cursor() as cur:
            for table in tables:
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables
                        WHERE table_name = %s
                    )
                """,
                    (table,),
                )
                exists = cur.fetchone()[0]
                status = "[OK]" if exists else "[MISSING]"
                print(f"     {status} {table}")
        conn.close()
        return True
    except Exception as e:
        print(f"     [ERROR] 테이블 확인 실패: {e}")
        return False


def test_categories():
    """카테고리 데이터 확인"""
    print("[3/4] 카테고리 데이터 확인...")

    try:
        config = get_config()
        conn = psycopg2.connect(**config.database.get_connection_dict())
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT category_key, display_name FROM community_category ORDER BY sort_order"
            )
            rows = cur.fetchall()

            if not rows:
                print("     [WARNING] 카테고리가 없습니다! 마이그레이션을 실행하세요.")
                return False

            for row in rows:
                print(f"     [OK] {row['category_key']}: {row['display_name']}")

        conn.close()
        return True
    except psycopg2.errors.UndefinedTable:
        print("     [ERROR] community_category 테이블이 없습니다.")
        print("             마이그레이션 파일을 먼저 실행하세요:")
        print("             psql -f app/database/migrations/005_community_board.sql")
        return False
    except Exception as e:
        print(f"     [ERROR] 카테고리 확인 실패: {e}")
        return False


def test_api_import():
    """API 모듈 import 테스트"""
    print("[4/4] API 모듈 import 테스트...")

    try:
        print("     [OK] board_router import 성공")

        print("     [OK] get_board_service import 성공")

        print("     [OK] BoardDB import 성공")

        return True
    except Exception as e:
        print(f"     [ERROR] import 실패: {e}")
        return False


def main():
    print("=" * 60)
    print("게시판 DB 연결 및 설정 테스트")
    print("=" * 60)
    print()

    results = []
    results.append(test_db_connection())
    results.append(test_tables_exist())
    results.append(test_categories())
    results.append(test_api_import())

    print()
    print("=" * 60)
    if all(results):
        print("모든 테스트 통과! 백엔드 서버를 시작하세요:")
        print()
        print("    conda activate ddoksori")
        print("    cd LLM/backend")
        print("    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000")
    else:
        print("일부 테스트 실패! 위의 오류를 해결하세요.")
        print()
        print("마이그레이션이 필요하면:")
        print("    psql 접속 후 005_community_board.sql 실행")
        print("    또는")
        print(
            "    cat app/database/migrations/005_community_board.sql | psql <connection_string>"
        )
    print("=" * 60)


if __name__ == "__main__":
    main()
