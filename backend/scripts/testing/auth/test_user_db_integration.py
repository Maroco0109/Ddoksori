"""
Integration tests for UserDB

작성일: 2026-01-28
설명: UserDB 통합 테스트 (실제 DB 필요)

⚠️ 주의: DB가 READ_ONLY이거나 테이블이 없으면 SKIP됩니다.
"""

import pytest
from datetime import datetime

from app.auth.user_db import UserDB
from app.auth.models import User


@pytest.fixture
async def user_db():
    """UserDB 인스턴스 생성"""
    return UserDB()


@pytest.fixture
async def check_db_available(user_db):
    """DB 테이블 존재 여부 확인"""
    import psycopg2
    try:
        conn = user_db._get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users LIMIT 1")
        conn.close()
        return True
    except (psycopg2.Error, Exception):
        pytest.skip("DB 테이블이 없거나 READ_ONLY입니다. 수동으로 마이그레이션을 실행하세요.")


@pytest.mark.integration
@pytest.mark.needs_db
@pytest.mark.asyncio
async def test_upsert_user_integration(user_db, check_db_available):
    """사용자 생성/갱신 통합 테스트"""
    provider_user_id = f"test_{int(datetime.now().timestamp())}"

    # 사용자 생성
    user = await user_db.upsert_user(
        provider="google",
        provider_user_id=provider_user_id,
        email=f"{provider_user_id}@test.com",
        name="Test User",
        avatar_url="https://example.com/avatar.jpg"
    )

    assert isinstance(user, User)
    assert user.provider == "google"
    assert user.provider_user_id == provider_user_id

    # 같은 사용자 갱신 (이름 변경)
    user_updated = await user_db.upsert_user(
        provider="google",
        provider_user_id=provider_user_id,
        email=f"{provider_user_id}@test.com",
        name="Updated Name",
        avatar_url="https://example.com/avatar2.jpg"
    )

    assert user_updated.user_id == user.user_id
    assert user_updated.name == "Updated Name"


@pytest.mark.integration
@pytest.mark.needs_db
@pytest.mark.asyncio
async def test_get_user_by_id_integration(user_db, check_db_available):
    """사용자 ID로 조회 통합 테스트"""
    provider_user_id = f"test_{int(datetime.now().timestamp())}"

    # 사용자 생성
    user = await user_db.upsert_user(
        provider="naver",
        provider_user_id=provider_user_id,
        email=f"{provider_user_id}@test.com",
        name="Naver User"
    )

    # ID로 조회
    found_user = await user_db.get_user_by_id(user.user_id)
    assert found_user is not None
    assert found_user.user_id == user.user_id
    assert found_user.email == user.email


@pytest.mark.integration
@pytest.mark.needs_db
@pytest.mark.asyncio
async def test_get_user_by_email_integration(user_db, check_db_available):
    """이메일로 조회 통합 테스트"""
    provider_user_id = f"test_{int(datetime.now().timestamp())}"
    email = f"{provider_user_id}@test.com"

    # 사용자 생성
    user = await user_db.upsert_user(
        provider="naver",
        provider_user_id=provider_user_id,
        email=email,
        name="Naver User"
    )

    # 이메일로 조회
    found_user = await user_db.get_user_by_email(email)
    assert found_user is not None
    assert found_user.email == email
    assert found_user.provider == "naver"


@pytest.mark.integration
@pytest.mark.needs_db
@pytest.mark.asyncio
async def test_update_last_login_integration(user_db, check_db_available):
    """마지막 로그인 갱신 통합 테스트"""
    provider_user_id = f"test_{int(datetime.now().timestamp())}"

    # 사용자 생성
    user = await user_db.upsert_user(
        provider="google",
        provider_user_id=provider_user_id,
        email=f"{provider_user_id}@test.com",
        name="Test User"
    )

    initial_login = user.last_login_at

    # 로그인 시각 갱신
    await user_db.update_last_login(user.user_id)

    # 다시 조회
    updated_user = await user_db.get_user_by_id(user.user_id)
    assert updated_user.last_login_at is not None
    if initial_login:
        assert updated_user.last_login_at >= initial_login
