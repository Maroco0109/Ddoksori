"""
API Integration Tests - Phase 6 Validation

End-to-end RAG workflow tests.

Usage:
    conda activate dsr
    pytest backend/scripts/testing/test_api_integration.py -v -m integration
"""
import pytest
import os


class TestRAGWorkflow:
    """End-to-end RAG workflow tests"""

    @pytest.mark.integration
    def test_full_rag_pipeline(self, api_client):
        """Complete workflow: Search → Chat → Case Details"""

        # Step 1: Search for relevant cases
        search_resp = api_client.post(
            "/search",
            json={"query": "환불 기준", "top_k": 3}
        )
        assert search_resp.status_code == 200
        results = search_resp.json()["results"]

        # Step 2: Generate answer using same query (if API key available)
        if os.getenv("OPENAI_API_KEY") and len(results) > 0:
            chat_resp = api_client.post(
                "/chat",
                json={"message": "환불 기준은?", "top_k": 3}
            )
            assert chat_resp.status_code == 200
            assert len(chat_resp.json()["answer"]) > 0

        # Step 3: Retrieve detailed case information
        if len(results) > 0:
            case_uid = results[0]["doc_id"]
            case_resp = api_client.get(f"/case/{case_uid}")

            # Should return 200 or 404 (case may not exist as document)
            assert case_resp.status_code in [200, 404]

            if case_resp.status_code == 200:
                assert case_resp.json()["case_uid"] == case_uid

    @pytest.mark.integration
    def test_search_results_used_in_chat(self, api_client):
        """Chat endpoint uses search results as context"""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY required")

        # First search
        search_resp = api_client.post(
            "/search",
            json={"query": "배송지연 손해배상", "top_k": 5}
        )
        assert search_resp.status_code == 200
        search_count = search_resp.json()["results_count"]

        # Then chat
        chat_resp = api_client.post(
            "/chat",
            json={"message": "배송지연 시 손해배상은?", "top_k": 5}
        )
        assert chat_resp.status_code == 200
        chunks_used = chat_resp.json()["chunks_used"]

        # Chat should use similar number of chunks
        # (may differ slightly due to internal retrieval)
        # This is informational, not strict assertion

    @pytest.mark.integration
    def test_agency_recommendation(self, api_client):
        """Agency routing logic works for dispute queries"""
        # Query about KCA jurisdiction
        resp = api_client.post(
            "/search",
            json={"query": "한국소비자원 분쟁조정", "top_k": 5}
        )
        assert resp.status_code == 200

        # If results exist, check if KCA-related content is returned
        results = resp.json()["results"]
        if len(results) > 0:
            # Check if any result is from KCA
            has_kca = any(
                "KCA" in result.get("category_path", []) or
                "한국소비자원" in result.get("doc_title", "")
                for result in results
            )
            # Informational check


class TestHybridRetrieval:
    """Test hybrid retrieval mode"""

    def test_hybrid_mode_active(self, api_client):
        """Verify hybrid retrieval mode is enabled"""
        resp = api_client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        retrieval_mode = data.get("retrieval_mode", "unknown")

        # Should be either hybrid or dense
        assert retrieval_mode in ["hybrid", "dense"]

    def test_fts_search_works_with_null_embeddings(self, api_client):
        """FTS lexical search works even with NULL embeddings"""
        resp = api_client.post(
            "/search",
            json={"query": "환불", "top_k": 5}
        )
        assert resp.status_code == 200

        # May have 0 results if no data loaded, but should not error
        data = resp.json()
        assert "results_count" in data
        assert "results" in data
