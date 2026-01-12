"""
Pytest Configuration and Shared Fixtures

Provides shared fixtures for API testing, database connections, and test data.

Usage:
    pytest backend/scripts/testing/ -v
"""
import pytest
import httpx
import os
import psycopg
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@pytest.fixture(scope="session")
def api_client():
    """
    HTTP client for API testing

    Yields:
        httpx.Client: HTTP client configured for backend API
    """
    base_url = os.getenv("TEST_API_URL", "http://localhost:8000")

    with httpx.Client(base_url=base_url, timeout=30) as client:
        yield client


@pytest.fixture(scope="session")
def db_connection():
    """
    Database connection for validation queries

    Yields:
        psycopg.Connection: PostgreSQL connection
    """
    conninfo = (
        f"host={os.getenv('DB_HOST', 'localhost')} "
        f"port={os.getenv('DB_PORT', '5432')} "
        f"dbname={os.getenv('DB_NAME', 'ddoksori')} "
        f"user={os.getenv('DB_USER', 'postgres')} "
        f"password={os.getenv('DB_PASSWORD', 'postgres')}"
    )

    conn = psycopg.connect(conninfo)
    yield conn
    conn.close()


@pytest.fixture(scope="function")
def korean_test_queries():
    """
    Real Korean consumer dispute queries for testing

    Returns:
        List[str]: List of Korean test queries
    """
    return [
        "전자상거래 환불 규정이 어떻게 되나요?",
        "배송지연으로 인한 손해배상은?",
        "신용카드 결제 취소 후 가맹점 수수료는?",
        "가전제품 정액감가상각 계산법은?",
        "소비자분쟁조정위원회는 어디인가요?"
    ]


@pytest.fixture(scope="function")
def sample_search_request():
    """
    Sample search request payload

    Returns:
        dict: Search request payload
    """
    return {
        "query": "환불 기준",
        "top_k": 5
    }


@pytest.fixture(scope="function")
def sample_chat_request():
    """
    Sample chat request payload

    Returns:
        dict: Chat request payload
    """
    return {
        "message": "전자상거래에서 환불을 받을 수 있나요?",
        "top_k": 5
    }


@pytest.fixture(scope="function")
def api_key_available():
    """
    Check if OpenAI API key is configured

    Returns:
        bool: True if API key is available
    """
    return bool(os.getenv("OPENAI_API_KEY"))


def pytest_configure(config):
    """
    Pytest configuration hook

    Registers custom markers.
    """
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers",
        "docker: requires docker environment"
    )
    config.addinivalue_line(
        "markers",
        "integration: end-to-end integration tests"
    )
    config.addinivalue_line(
        "markers",
        "skip_ci: skip in CI environment"
    )


def pytest_collection_modifyitems(config, items):
    """
    Pytest hook to modify test collection

    Automatically skips tests requiring OpenAI API key if not configured.
    """
    skip_no_api_key = pytest.mark.skip(reason="OPENAI_API_KEY not configured")

    for item in items:
        # Skip tests that need API key if not available
        if "chat" in item.nodeid and not os.getenv("OPENAI_API_KEY"):
            # Check if test explicitly requires API key
            if "test_chat" in item.name and "no_api_key" not in item.name:
                item.add_marker(skip_no_api_key)
