"""
BGE-M3 Retrieval Tests

Tests for BGE-M3 sparse embedding integration and 3-way RRF fusion.

Usage:
    pytest scripts/testing/orchestrator/test_bge_m3_retrieval.py -v

Requirements:
    - BGE-M3 server running on port 8003 (or BGE_M3_EMBED_URL set)
    - Database with BGE-M3 embeddings (run embed_bge_m3_all_data.py first)
"""

import os
import sys
import json
import time
import pytest
import requests

# Add backend to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from dotenv import load_dotenv
load_dotenv()

# Test configuration
BGE_M3_URL = os.getenv('BGE_M3_EMBED_URL', 'http://localhost:8003/embed')
BGE_M3_HEALTH_URL = BGE_M3_URL.replace('/embed', '/health')

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'ddoksori'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres')
}


class TestBGEM3Server:
    """BGE-M3 Server Tests"""

    def test_server_health(self):
        """Test BGE-M3 server health endpoint"""
        try:
            response = requests.get(BGE_M3_HEALTH_URL, timeout=10)
            assert response.status_code == 200

            health = response.json()
            assert health.get('status') == 'healthy'
            assert health.get('model') == 'BAAI/bge-m3'
            assert health.get('dense_dim') == 1024
            assert 'sparse' in health.get('capabilities', [])

            print(f"BGE-M3 Server Health: {health}")
        except requests.exceptions.ConnectionError:
            pytest.skip("BGE-M3 server not running")

    def test_single_embedding(self):
        """Test single text embedding generation"""
        try:
            response = requests.post(
                BGE_M3_URL,
                json={
                    'text': '헬스장 환불 규정',
                    'return_dense': True,
                    'return_sparse': True
                },
                timeout=30
            )

            assert response.status_code == 200
            result = response.json()

            # Check dense embedding
            assert 'dense_embedding' in result
            assert len(result['dense_embedding']) == 1024

            # Check sparse embedding
            assert 'sparse_embedding' in result
            assert isinstance(result['sparse_embedding'], dict)
            assert len(result['sparse_embedding']) > 0  # Should have some tokens

            print(f"Dense dim: {len(result['dense_embedding'])}")
            print(f"Sparse tokens: {len(result['sparse_embedding'])}")

        except requests.exceptions.ConnectionError:
            pytest.skip("BGE-M3 server not running")

    def test_batch_embedding(self):
        """Test batch embedding generation"""
        try:
            texts = [
                '헬스장 환불 규정',
                '온라인 쇼핑 환불',
                '소비자 피해 구제'
            ]

            response = requests.post(
                BGE_M3_URL,
                json={
                    'texts': texts,
                    'return_dense': True,
                    'return_sparse': True
                },
                timeout=60
            )

            assert response.status_code == 200
            result = response.json()

            # Check batch results
            assert 'dense_embeddings' in result
            assert len(result['dense_embeddings']) == len(texts)

            assert 'sparse_embeddings' in result
            assert len(result['sparse_embeddings']) == len(texts)

            for i, emb in enumerate(result['dense_embeddings']):
                assert len(emb) == 1024

            print(f"Batch size: {len(texts)}")
            print(f"Dense embeddings: {len(result['dense_embeddings'])}")
            print(f"Sparse embeddings: {len(result['sparse_embeddings'])}")

        except requests.exceptions.ConnectionError:
            pytest.skip("BGE-M3 server not running")

    def test_embedding_latency(self):
        """Test embedding generation latency (target: < 100ms per text)"""
        try:
            text = '헬스장 환불 규정'
            iterations = 5
            latencies = []

            for _ in range(iterations):
                start = time.time()
                response = requests.post(
                    BGE_M3_URL,
                    json={'text': text, 'return_dense': True, 'return_sparse': True},
                    timeout=30
                )
                latency = (time.time() - start) * 1000
                latencies.append(latency)

                assert response.status_code == 200

            avg_latency = sum(latencies) / len(latencies)
            print(f"Average latency: {avg_latency:.1f}ms")
            print(f"Min: {min(latencies):.1f}ms, Max: {max(latencies):.1f}ms")

            # Warning if latency is high (but don't fail the test)
            if avg_latency > 100:
                print(f"WARNING: Average latency {avg_latency:.1f}ms exceeds 100ms target")

        except requests.exceptions.ConnectionError:
            pytest.skip("BGE-M3 server not running")


class TestHybridRetriever3Way:
    """3-way RRF Retrieval Tests"""

    @pytest.fixture
    def retriever(self):
        """Create HybridRetriever instance with sparse enabled"""
        try:
            from rag.hybrid_retriever import HybridRetriever

            retriever = HybridRetriever(
                db_config=DB_CONFIG,
                enable_sparse=True
            )
            retriever.connect()
            yield retriever
            retriever.close()
        except Exception as e:
            pytest.skip(f"Failed to create retriever: {e}")

    def test_hybrid_search_with_sparse(self, retriever):
        """Test hybrid search with sparse enabled"""
        query = "헬스장 환불 규정"

        results = retriever.search(query, top_k=5)

        assert len(results) > 0
        print(f"Query: {query}")
        print(f"Results: {len(results)}")
        for i, r in enumerate(results):
            print(f"  {i+1}. [{r.doc_type}] {r.chunk_id}: score={r.similarity:.4f}")

    def test_3way_rrf_fusion(self, retriever):
        """Test 3-way RRF fusion produces valid results"""
        query = "온라인 쇼핑몰 환불"

        # Get results with sparse enabled
        retriever.enable_sparse = True
        results_3way = retriever.search(query, top_k=10)

        # Get results without sparse
        retriever.enable_sparse = False
        results_2way = retriever.search(query, top_k=10)

        print(f"Query: {query}")
        print(f"3-way RRF results: {len(results_3way)}")
        print(f"2-way RRF results: {len(results_2way)}")

        # Both should return results
        assert len(results_3way) > 0
        assert len(results_2way) > 0

        # Compare result overlap
        ids_3way = {r.chunk_id for r in results_3way}
        ids_2way = {r.chunk_id for r in results_2way}
        overlap = ids_3way.intersection(ids_2way)

        print(f"Overlap: {len(overlap)} / {len(ids_3way.union(ids_2way))}")

    def test_retrieval_latency(self, retriever):
        """Test retrieval latency (target: < 100ms)"""
        query = "소비자 피해 구제"

        start = time.time()
        results = retriever.search(query, top_k=10)
        latency = (time.time() - start) * 1000

        print(f"Query: {query}")
        print(f"Results: {len(results)}")
        print(f"Total latency: {latency:.1f}ms")

        # Warning if latency exceeds target
        if latency > 100:
            print(f"WARNING: Latency {latency:.1f}ms exceeds 100ms target")


class TestEmbeddingModelSwitch:
    """Embedding model switching tests"""

    def test_kure_to_bge_switch(self):
        """Test switching between KURE and BGE-M3"""
        try:
            from utils.embedding_connection import (
                get_embedding_api_url,
                get_bge_m3_api_url,
                EMBEDDING_MODEL
            )

            kure_url = get_embedding_api_url()
            bge_url = get_bge_m3_api_url()

            print(f"Current model: {EMBEDDING_MODEL}")
            print(f"KURE URL: {kure_url}")
            print(f"BGE-M3 URL: {bge_url}")

            # At least one should be available
            assert kure_url is not None or bge_url is not None

        except Exception as e:
            pytest.skip(f"Configuration error: {e}")

    def test_rrf_weights_configuration(self):
        """Test RRF weight configuration"""
        from utils.embedding_connection import (
            RRF_WEIGHT_DENSE,
            RRF_WEIGHT_LEXICAL,
            RRF_WEIGHT_SPARSE
        )

        print(f"RRF Weights:")
        print(f"  Dense: {RRF_WEIGHT_DENSE}")
        print(f"  Lexical: {RRF_WEIGHT_LEXICAL}")
        print(f"  Sparse: {RRF_WEIGHT_SPARSE}")

        # Weights should be positive
        assert RRF_WEIGHT_DENSE >= 0
        assert RRF_WEIGHT_LEXICAL >= 0
        assert RRF_WEIGHT_SPARSE >= 0


class TestDatabaseBGEM3:
    """Database BGE-M3 column tests"""

    @pytest.fixture
    def local_db_connection(self):
        """Create database connection (local fixture to avoid scope mismatch)"""
        import psycopg2
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            yield conn
            conn.close()
        except Exception as e:
            pytest.skip(f"Database connection failed: {e}")

    def test_bge_m3_columns_exist(self, local_db_connection):
        """Test BGE-M3 columns exist in chunks table"""
        with local_db_connection.cursor() as cur:
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'chunks'
                AND column_name IN ('bge_dense_vector', 'bge_sparse_vector', 'bge_m3_encoded')
            """)
            columns = {row[0]: row[1] for row in cur.fetchall()}

        print(f"BGE-M3 columns: {columns}")

        # Check if columns exist (migration may not have run yet)
        if not columns:
            pytest.skip("BGE-M3 columns not yet created. Run migration first.")

        assert 'bge_dense_vector' in columns or 'bge_m3_encoded' in columns

    def test_bge_m3_encoding_status(self, local_db_connection):
        """Check BGE-M3 encoding status"""
        with local_db_connection.cursor() as cur:
            # Check if bge_m3_encoded column exists
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'chunks' AND column_name = 'bge_m3_encoded'
            """)
            if not cur.fetchone():
                pytest.skip("bge_m3_encoded column not found")

            # Count encoded vs not encoded
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE bge_m3_encoded = TRUE) AS encoded,
                    COUNT(*) FILTER (WHERE bge_m3_encoded = FALSE OR bge_m3_encoded IS NULL) AS not_encoded,
                    COUNT(*) AS total
                FROM chunks
                WHERE drop = FALSE
            """)
            result = cur.fetchone()

        encoded, not_encoded, total = result
        print(f"BGE-M3 Encoding Status:")
        print(f"  Encoded: {encoded:,}")
        print(f"  Not encoded: {not_encoded:,}")
        print(f"  Total: {total:,}")
        print(f"  Progress: {encoded/total*100:.1f}%" if total > 0 else "  Progress: 0%")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
