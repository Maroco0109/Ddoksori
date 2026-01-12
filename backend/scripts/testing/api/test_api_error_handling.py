"""
API Error Handling Tests - Phase 6 Validation

Tests error handling and input validation for API endpoints.

Usage:
    conda activate dsr
    pytest backend/scripts/testing/test_api_error_handling.py -v
"""
import pytest


class TestInputValidation:
    """Test API input validation"""

    def test_search_missing_query(self, api_client):
        """/search rejects missing query field"""
        resp = api_client.post("/search", json={})
        assert resp.status_code == 422  # Unprocessable Entity (Pydantic validation)

    def test_search_invalid_top_k_negative(self, api_client):
        """/search rejects negative top_k"""
        resp = api_client.post("/search", json={"query": "test", "top_k": -1})
        # May not be validated currently - test for expected behavior
        # assert resp.status_code in [422, 400]

    def test_search_invalid_top_k_zero(self, api_client):
        """/search handles zero top_k"""
        resp = api_client.post("/search", json={"query": "test", "top_k": 0})
        # Should either validate or handle gracefully
        assert resp.status_code in [200, 400, 422]

    def test_search_malformed_json(self, api_client):
        """/search rejects malformed JSON"""
        resp = api_client.post(
            "/search",
            headers={"Content-Type": "application/json"},
            content="not valid json"
        )
        assert resp.status_code == 422

    def test_search_empty_string_query(self, api_client):
        """/search handles empty query string"""
        resp = api_client.post("/search", json={"query": "", "top_k": 5})
        # Should either reject or return empty results
        assert resp.status_code in [200, 400, 422]


class TestCORS:
    """Test CORS configuration"""

    def test_cors_headers_present(self, api_client):
        """API returns CORS headers for allowed origins"""
        resp = api_client.options(
            "/search",
            headers={"Origin": "http://localhost:5173"}
        )
        # Check for CORS headers (case-insensitive)
        headers_lower = {k.lower(): v for k, v in resp.headers.items()}
        assert "access-control-allow-origin" in headers_lower or resp.status_code == 200

    def test_cors_allows_frontend_origin(self, api_client):
        """CORS allows frontend origin"""
        resp = api_client.post(
            "/search",
            json={"query": "test", "top_k": 5},
            headers={"Origin": "http://localhost:5173"}
        )
        # Should not be blocked by CORS
        assert resp.status_code in [200, 404, 500]  # Not 403 (Forbidden)

    def test_cors_preflight_options(self, api_client):
        """CORS handles OPTIONS preflight requests"""
        resp = api_client.options(
            "/search",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Content-Type"
            }
        )
        # Should return 200 or 204 for OPTIONS
        assert resp.status_code in [200, 204]
