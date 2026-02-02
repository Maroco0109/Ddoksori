"""
API Concurrency Tests - Phase 6 Validation

Tests concurrent request handling and connection pooling.

Usage:
    conda activate dsr
    pytest backend/scripts/testing/test_api_concurrent.py -v -m slow

마커:
    @pytest.mark.integration - API 서버 연결 필요
    @pytest.mark.api - API 엔드포인트 테스트
    @pytest.mark.slow - 느린 테스트
"""

import concurrent.futures

import pytest

# 전체 모듈에 마커 적용
pytestmark = [
    pytest.mark.integration,
    pytest.mark.api,
    pytest.mark.slow,
    pytest.mark.skip_ci,
]


class TestConcurrency:
    """Test concurrent request handling"""

    @pytest.mark.slow
    def test_concurrent_search_requests(self, api_client):
        """API handles 10 concurrent /search requests without errors"""

        def make_request(query_id):
            resp = api_client.post(
                "/search", json={"query": f"환불 테스트 {query_id}", "top_k": 5}
            )
            return resp.status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request, i) for i in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # All requests should succeed
        assert all(status == 200 for status in results), (
            f"Some requests failed: {results}"
        )

    @pytest.mark.slow
    def test_no_connection_pool_exhaustion(self, api_client):
        """API maintains connection pool under sustained load"""
        # Send 50 rapid sequential requests
        for i in range(50):
            resp = api_client.post("/search", json={"query": f"테스트 {i}", "top_k": 3})
            assert resp.status_code == 200, (
                f"Request {i} failed with status {resp.status_code}"
            )

        # No connection errors should occur
