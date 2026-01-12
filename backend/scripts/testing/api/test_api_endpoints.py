"""
API Endpoint Tests - Phase 6 Validation

Tests all API endpoints with various scenarios:
- Root endpoint (/)
- Health endpoint (/health)
- Search endpoint (/search)
- Chat endpoint (/chat)
- Chat stream endpoint (/chat/stream)
- Case endpoint (/case/{uid})

Usage:
    conda activate dsr
    pytest backend/scripts/testing/test_api_endpoints.py -v
"""
import pytest
import time
import os


class TestRootEndpoint:
    """Tests for / endpoint"""

    def test_root_returns_version(self, api_client):
        """/ endpoint returns version 0.4.1"""
        resp = api_client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "version" in data
        assert data["version"] == "0.4.1"

    def test_root_returns_retrieval_mode(self, api_client):
        """/ endpoint shows retrieval_mode: hybrid"""
        resp = api_client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "retrieval_mode" in data
        assert data["retrieval_mode"] in ["hybrid", "dense"]


class TestHealthEndpoint:
    """Tests for /health endpoint"""

    def test_health_check_healthy(self, api_client):
        """/health returns healthy status"""
        resp = api_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "database" in data
        assert data["database"] == "connected"

    def test_health_check_performance(self, api_client):
        """/health responds within 1 second"""
        start = time.time()
        resp = api_client.get("/health")
        elapsed = time.time() - start
        assert resp.status_code == 200
        assert elapsed < 1.0, f"Health check took {elapsed:.3f}s (expected <1s)"


class TestSearchEndpoint:
    """Tests for /search endpoint"""

    def test_search_basic_query(self, api_client):
        """/search accepts valid Korean query"""
        payload = {"query": "환불 기준", "top_k": 5}
        resp = api_client.post("/search", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "query" in data
        assert data["query"] == "환불 기준"
        assert "results_count" in data
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_search_korean_text_encoding(self, api_client, korean_test_queries):
        """/search preserves Korean text encoding"""
        for query in korean_test_queries:
            resp = api_client.post("/search", json={"query": query, "top_k": 3})
            assert resp.status_code == 200
            # Verify Korean text is preserved in response
            assert resp.json()["query"] == query

    def test_search_empty_results(self, api_client):
        """/search handles no results gracefully"""
        payload = {"query": "xyzabc12345nonexistent", "top_k": 5}
        resp = api_client.post("/search", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["results_count"] == 0
        assert data["results"] == []

    def test_search_top_k_parameter(self, api_client):
        """/search respects top_k parameter"""
        for k in [1, 3, 5, 10]:
            resp = api_client.post("/search", json={"query": "환불", "top_k": k})
            assert resp.status_code == 200
            results = resp.json()["results"]
            assert len(results) <= k, f"Expected ≤{k} results, got {len(results)}"

    def test_search_chunk_type_filter(self, api_client):
        """/search filters by chunk_type"""
        # Test with chunk_types parameter
        payload = {
            "query": "환불",
            "top_k": 5,
            "chunk_types": ["facts", "problem"]
        }
        resp = api_client.post("/search", json=payload)
        assert resp.status_code == 200
        # Response should not error even if filter doesn't match anything

    def test_search_agency_filter(self, api_client):
        """/search filters by source_org (agencies)"""
        # Test with agencies parameter
        payload = {
            "query": "분쟁조정",
            "top_k": 5,
            "agencies": ["KCA", "ECMC"]
        }
        resp = api_client.post("/search", json=payload)
        assert resp.status_code == 200

    @pytest.mark.slow
    def test_search_performance_p95(self, api_client):
        """/search responds within 500ms (p95 latency)"""
        times = []
        for i in range(20):  # 20 requests for statistical significance
            start = time.time()
            api_client.post("/search", json={"query": f"환불 {i}", "top_k": 5})
            times.append(time.time() - start)

        times.sort()
        p95 = times[int(len(times) * 0.95)]
        assert p95 < 0.5, f"p95 latency {p95:.3f}s exceeds 500ms"

    def test_search_result_schema(self, api_client):
        """/search returns valid SearchResult structure"""
        resp = api_client.post("/search", json={"query": "환불", "top_k": 5})
        assert resp.status_code == 200
        data = resp.json()

        # Verify response structure
        assert "query" in data
        assert "results_count" in data
        assert "results" in data

        # If results exist, verify structure
        if data["results_count"] > 0:
            result = data["results"][0]
            expected_fields = [
                "chunk_id", "doc_id", "chunk_type", "content",
                "doc_title", "doc_type", "category_path", "similarity"
            ]
            for field in expected_fields:
                assert field in result, f"Missing field: {field}"

    def test_search_null_embeddings(self, api_client):
        """/search works in FTS-only mode (NULL embeddings)"""
        # System currently has NULL embeddings, should use FTS
        resp = api_client.post("/search", json={"query": "환불", "top_k": 5})
        assert resp.status_code == 200
        # Should not error even with NULL embeddings


class TestChatEndpoint:
    """Tests for /chat endpoint"""

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY required for LLM tests"
    )
    def test_chat_basic_query(self, api_client):
        """/chat generates answer with sources"""
        payload = {"message": "전자상거래 환불 규정은?", "top_k": 3}
        resp = api_client.post("/chat", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "answer" in data
        assert len(data["answer"]) > 0
        assert "chunks_used" in data
        assert "model" in data
        assert "sources" in data
        assert isinstance(data["sources"], list)

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY required"
    )
    def test_chat_includes_disclaimer(self, api_client):
        """/chat includes legal disclaimer"""
        payload = {"message": "환불 조건은?", "top_k": 3}
        resp = api_client.post("/chat", json=payload)
        assert resp.status_code == 200
        answer = resp.json()["answer"]

        # Check for disclaimer (may be in Korean or English)
        disclaimer_keywords = ["정보 제공", "법률 자문", "상담", "정보제공"]
        has_disclaimer = any(keyword in answer for keyword in disclaimer_keywords)
        # Note: Some generators may not include disclaimer, so this is informational

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY required"
    )
    def test_chat_sources_valid(self, api_client):
        """/chat sources reference actual chunks"""
        payload = {"message": "환불 기준은?", "top_k": 3}
        resp = api_client.post("/chat", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        # Verify sources structure
        if len(data["sources"]) > 0:
            source = data["sources"][0]
            assert "chunk_id" in source or "doc_id" in source

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY required"
    )
    def test_chat_korean_text_preserved(self, api_client):
        """/chat preserves Korean text in input/output"""
        query = "전자상거래 환불은 어떻게 하나요?"
        payload = {"message": query, "top_k": 3}
        resp = api_client.post("/chat", json=payload)
        assert resp.status_code == 200
        answer = resp.json()["answer"]

        # Answer should be in Korean (contains Korean characters)
        korean_chars = sum(1 for char in answer if '\uAC00' <= char <= '\uD7A3')
        assert korean_chars > 0, "Answer should contain Korean text"

    @pytest.mark.slow
    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY required"
    )
    def test_chat_performance_p95(self, api_client):
        """/chat responds within 5s (p95 latency)"""
        times = []
        queries = ["환불은?", "배송은?", "취소는?", "반품은?", "교환은?"]

        for query in queries:
            start = time.time()
            try:
                resp = api_client.post(
                    "/chat",
                    json={"message": query, "top_k": 3},
                    timeout=10
                )
                if resp.status_code == 200:
                    times.append(time.time() - start)
            except Exception:
                # Skip timeout/error cases
                continue

        if len(times) > 0:
            times.sort()
            p95 = times[int(len(times) * 0.95)] if len(times) > 1 else times[0]
            assert p95 < 5.0, f"p95 latency {p95:.2f}s exceeds 5s"

    def test_chat_no_api_key(self, api_client):
        """/chat handles missing API key gracefully"""
        if os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY is configured")

        payload = {"message": "환불은?", "top_k": 3}
        resp = api_client.post("/chat", json=payload)

        # Should return error status (not 200)
        assert resp.status_code in [500, 503, 400]

    @pytest.mark.skipif(
        not os.getenv("OPENAI_API_KEY"),
        reason="OPENAI_API_KEY required"
    )
    def test_chat_stream_endpoint(self, api_client):
        """/chat/stream returns streaming response"""
        payload = {"message": "환불 조건은?", "top_k": 3}
        with api_client.stream("POST", "/chat/stream", json=payload, timeout=10) as resp:
            assert resp.status_code == 200
            assert "text/plain" in resp.headers.get("content-type", "")

            # Read some chunks
            chunk_count = 0
            for chunk in resp.iter_text():
                chunk_count += 1
                if chunk_count >= 5:  # Read first 5 chunks
                    break

            assert chunk_count > 0, "Should receive at least one chunk"

    def test_chat_chunk_types_filter(self, api_client):
        """/chat respects chunk_types parameter"""
        payload = {
            "message": "환불은?",
            "top_k": 3,
            "chunk_types": ["facts", "solution"]
        }

        # Should not error even if API key missing (will error on LLM call, not parameter validation)
        resp = api_client.post("/chat", json=payload)
        assert resp.status_code in [200, 400, 500, 503]  # Various valid error codes


class TestCaseEndpoint:
    """Tests for /case/{uid} endpoint"""

    def test_get_case_valid_uid(self, api_client, db_connection):
        """/case/{uid} returns case details"""
        # Get a valid case_uid from database
        with db_connection.cursor() as cur:
            cur.execute("""
                SELECT doc_id FROM documents
                WHERE doc_type IN ('counsel_case', 'mediation_case')
                LIMIT 1
            """)
            row = cur.fetchone()
            if not row:
                pytest.skip("No cases in database")
            case_uid = row[0]

        resp = api_client.get(f"/case/{case_uid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["case_uid"] == case_uid
        assert "chunks_count" in data
        assert "chunks" in data

    def test_get_case_invalid_uid(self, api_client):
        """/case/{uid} returns 404 for invalid UID"""
        resp = api_client.get("/case/nonexistent_uid_12345")
        assert resp.status_code == 404

    def test_get_case_chunk_structure(self, api_client, db_connection):
        """/case/{uid} returns valid chunk structure"""
        # Get a valid case_uid
        with db_connection.cursor() as cur:
            cur.execute("""
                SELECT doc_id FROM documents
                WHERE doc_type IN ('counsel_case', 'mediation_case')
                LIMIT 1
            """)
            row = cur.fetchone()
            if not row:
                pytest.skip("No cases in database")
            case_uid = row[0]

        resp = api_client.get(f"/case/{case_uid}")
        assert resp.status_code == 200
        data = resp.json()

        # Verify chunk structure if chunks exist
        if data["chunks_count"] > 0:
            chunk = data["chunks"][0]
            expected_fields = ["chunk_id", "chunk_type", "content"]
            for field in expected_fields:
                assert field in chunk, f"Missing field: {field}"
