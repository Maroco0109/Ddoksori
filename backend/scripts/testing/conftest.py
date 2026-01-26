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
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Clean up problematic environment variables that conflict with Pydantic Settings
if 'AGENT' in os.environ:
    del os.environ['AGENT']


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
        psycopg.Connection: PostgreSQL connection (or None if unavailable)

    Note:
        PR-T6: Unit 테스트 지원을 위해 연결 실패 시 skip 대신 None 반환.
        통합 테스트는 db_connection이 None이면 개별적으로 skip 처리.
    """
    conninfo = (
        f"host={os.getenv('DB_HOST', 'localhost')} "
        f"port={os.getenv('DB_PORT', '5432')} "
        f"dbname={os.getenv('DB_NAME', 'ddoksori')} "
        f"user={os.getenv('DB_USER', 'postgres')} "
        f"password={os.getenv('DB_PASSWORD', 'postgres')}"
    )

    try:
        conn = psycopg.connect(conninfo, autocommit=True)
        yield conn
        conn.close()
    except psycopg.OperationalError as e:
        # PR-T6: Unit 테스트를 위해 skip 대신 None 반환
        print(f"\n⚠️  PostgreSQL 연결 실패 (Unit 테스트는 계속 실행됨): {e}")
        yield None


@pytest.fixture(scope="session", autouse=True)
def ensure_test_data(db_connection, request):
    """
    PR-T1: 테스트 실행 전 DB 준비 상태 점검 + 최소 시드 데이터 주입

    동작 흐름:
    1. DB 연결 확인
    2. 필수 오브젝트 존재 확인 (documents, chunks, mv_searchable_chunks)
    3. 스키마 부재 시 즉시 Skip
    4. 데이터 부재 시 최소 시드 데이터 삽입
    5. MV 갱신 및 검증

    Note:
        PR-Phase5: Unit 테스트(-m unit)는 DB 체크 스킵
    """
    # PR-Phase5: Unit 테스트만 실행 시 DB 체크 스킵
    # -m unit 옵션이 있으면 DB 불필요
    markexpr = request.config.getoption("-m", default="")
    if markexpr == "unit":
        return

    if db_connection is None:
        return

    with db_connection.cursor() as cur:
        # 1. 필수 테이블/뷰 존재 확인
        required_objects = ['documents', 'chunks', 'mv_searchable_chunks']
        for obj in required_objects:
            cur.execute(
                "SELECT to_regclass(%s)",
                (f"public.{obj}",)
            )
            if cur.fetchone()[0] is None:
                pytest.skip(
                    f"DB schema not initialized. Required object '{obj}' is missing. "
                    f"Run migrations first: backend/database/migrations/"
                )

        # 2. 데이터 존재 여부 확인
        cur.execute("SELECT COUNT(*) FROM documents")
        doc_count = cur.fetchone()[0]

        if doc_count == 0:
            print("\n⚠️  DB is empty. Creating minimal seed data for tests...")
            
            # 3. 최소 시드 데이터 생성 (PR-T1 spec: 3+ docs, 6-12 chunks)
            # Documents: counsel_case, mediation_case, law 각 2개씩
            docs = [
                ('test_doc_counsel_01', 'counsel_case', '전자상거래 환불 문의', 'KCA', ['상품(재화)', '전자상거래', '환불']),
                ('test_doc_counsel_02', 'counsel_case', '배송 지연 및 취소 요청', 'KCA', ['상품(재화)', '전자상거래', '배송']),
                ('test_doc_mediation_01', 'mediation_case', '배송지연 손해배상 분쟁', 'ECMC', ['상품(재화)', '전자상거래', '손해배상']),
                ('test_doc_mediation_02', 'mediation_case', '불량제품 교환 거부 분쟁', 'ECMC', ['상품(재화)', '가전제품', '교환']),
                ('test_doc_law_01', 'law', '전자상거래 등에서의 소비자보호에 관한 법률', 'statute', ['법률', '소비자보호']),
                ('test_doc_law_02', 'law', '소비자분쟁해결기준', 'statute', ['기준', '분쟁조정'])
            ]
            
            for doc_id, doc_type, title, source, category_path in docs:
                cur.execute("""
                    INSERT INTO documents (doc_id, doc_type, title, source_org, category_path, metadata, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                """, (doc_id, doc_type, title, source, category_path, json.dumps({"test_seeded": True})))

            # Chunks: 각 문서당 2개씩 = 12 chunks (PR-T1 spec 준수)
            # Dummy 1024-dim zero vector (NOT NULL 조건 충족 → MV 포함됨)
            dummy_vector = [0.0] * 1024
            chunks = [
                # counsel_case chunks (문제 + 해결)
                ('test_chunk_c01_01', 'test_doc_counsel_01', 0, 2, 'problem', 
                 '전자상거래로 구매한 제품을 환불하고 싶은데 판매자가 거부합니다. 환불 규정이 어떻게 되나요?'),
                ('test_chunk_c01_02', 'test_doc_counsel_01', 1, 2, 'solution', 
                 '전자상거래법 제17조에 따라 7일 이내 청약철회가 가능합니다. 단, 포장 훼손 시 제외될 수 있습니다.'),
                ('test_chunk_c02_01', 'test_doc_counsel_02', 0, 2, 'problem', 
                 '배송이 2주째 지연되고 있습니다. 취소하고 싶은데 가능한가요?'),
                ('test_chunk_c02_02', 'test_doc_counsel_02', 1, 2, 'solution', 
                 '배송 지연이 7일을 초과하면 계약 해제 사유가 될 수 있습니다.'),
                # mediation_case chunks (사실관계 + 조정결과)
                ('test_chunk_m01_01', 'test_doc_mediation_01', 0, 2, 'facts', 
                 '주문한 상품이 2주째 배송되지 않아 분쟁조정을 신청했습니다. 판매자는 배송사 책임이라고 주장합니다.'),
                ('test_chunk_m01_02', 'test_doc_mediation_01', 1, 2, 'mediation_outcome', 
                 '소비자에게 전액 환불 및 위자료 5만원 지급으로 조정 성립. 배송 지연은 판매자 책임으로 판단.'),
                ('test_chunk_m02_01', 'test_doc_mediation_02', 0, 2, 'facts', 
                 '냉장고 구매 후 1주일 만에 고장났으나 판매자가 수리만 제안하고 교환을 거부합니다.'),
                ('test_chunk_m02_02', 'test_doc_mediation_02', 1, 2, 'mediation_outcome', 
                 '동일 제품 교환 또는 전액 환불 중 소비자 선택으로 조정. 초기 불량은 교환 사유 해당.'),
                # law chunks (조문)
                ('test_chunk_l01_01', 'test_doc_law_01', 0, 2, 'article', 
                 '제17조(청약철회등) 통신판매업자와 재화등의 구매에 관한 계약을 체결한 소비자는 수신한 날부터 7일 이내 청약철회 가능.'),
                ('test_chunk_l01_02', 'test_doc_law_01', 1, 2, 'article', 
                 '제18조(청약철회등의 효과) 통신판매업자는 소비자로부터 재화를 반환받은 날부터 3영업일 이내 환급.'),
                ('test_chunk_l02_01', 'test_doc_law_02', 0, 2, 'article', 
                 '별표1: 품목별 분쟁해결기준. 상품(재화) - 전자상거래 - 환불기준 7일 이내 청약철회.'),
                ('test_chunk_l02_02', 'test_doc_law_02', 1, 2, 'article', 
                 '별표2: 배송지연 시 소비자 귀책사유 없으면 계약해제 및 손해배상 청구 가능.')
            ]

            for chunk_id, doc_id, idx, total, c_type, content in chunks:
                # psycopg3: Python list → PostgreSQL array → cast to vector
                cur.execute("""
                    INSERT INTO chunks (chunk_id, doc_id, chunk_index, chunk_total, chunk_type, content, embedding, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::vector, NOW())
                """, (chunk_id, doc_id, idx, total, c_type, content, dummy_vector))
            
            print(f"✅  Seed data created: {len(docs)} docs, {len(chunks)} chunks")
            
            # 4. MV 갱신 (FTS 검색 활성화)
            print("🔄  Refreshing materialized view mv_searchable_chunks...")
            try:
                cur.execute("REFRESH MATERIALIZED VIEW mv_searchable_chunks")
                
                # 5. MV 갱신 검증 (시드 데이터가 MV에 포함되었는지 확인)
                cur.execute("SELECT COUNT(*) FROM mv_searchable_chunks WHERE doc_id LIKE 'test_doc_%'")
                mv_count = cur.fetchone()[0]
                
                if mv_count != len(chunks):
                    print(f"⚠️  Warning: Expected {len(chunks)} chunks in MV, but found {mv_count}")
                    print("    Check mv_searchable_chunks definition (WHERE c.drop = FALSE AND c.embedding IS NOT NULL)")
                else:
                    print(f"✅  MV refresh successful: {mv_count} test chunks indexed")
                    
            except Exception as e:
                print(f"❌  MV refresh failed: {e}")
                pytest.skip(f"Failed to refresh materialized view: {e}")


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
    Also skips Docker tests if Docker is not available.
    
    PR-T5: Docker tests require RUN_DOCKER_TESTS=1 (opt-in) and are auto-skipped in CI.
    """
    skip_no_api_key = pytest.mark.skip(reason="OPENAI_API_KEY not configured")
    skip_docker_opt_in = pytest.mark.skip(
        reason="Docker tests require RUN_DOCKER_TESTS=1 environment variable"
    )
    skip_docker_ci = pytest.mark.skip(
        reason="Docker tests are skipped in CI environment"
    )
    skip_docker_unavail = pytest.mark.skip(reason="Docker daemon not available")

    run_docker_tests = os.getenv("RUN_DOCKER_TESTS") == "1"
    is_ci = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"

    docker_available = False
    if run_docker_tests and not is_ci:
        try:
            import docker
            client = docker.from_env()
            client.ping()
            docker_available = True
        except Exception:
            pass

    for item in items:
        if "chat" in item.nodeid and not os.getenv("OPENAI_API_KEY"):
            if "test_chat" in item.name and "no_api_key" not in item.name:
                item.add_marker(skip_no_api_key)

        if "docker" in item.keywords:
            if is_ci:
                item.add_marker(skip_docker_ci)
            elif not run_docker_tests:
                item.add_marker(skip_docker_opt_in)
            elif not docker_available:
                item.add_marker(skip_docker_unavail)
