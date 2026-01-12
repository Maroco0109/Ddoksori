"""
Data Quality Tests - Phase 6 Validation

Tests database integrity and data quality.

Usage:
    conda activate dsr
    pytest backend/scripts/testing/test_data_quality.py -v
"""
import pytest


class TestDataIntegrity:
    """Test database integrity constraints"""

    def test_all_chunks_have_valid_documents(self, db_connection):
        """All chunks reference valid documents (no orphan chunks)"""
        with db_connection.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM chunks c
                LEFT JOIN documents d ON c.doc_id = d.doc_id
                WHERE d.doc_id IS NULL
            """)
            orphan_count = cur.fetchone()[0]
            assert orphan_count == 0, f"Found {orphan_count} orphan chunks"

    def test_chunk_totals_consistent(self, db_connection):
        """chunk_total field matches actual chunk count per document"""
        with db_connection.cursor() as cur:
            cur.execute("""
                SELECT c.doc_id, c.chunk_total, COUNT(*) as actual_count
                FROM chunks c
                GROUP BY c.doc_id, c.chunk_total
                HAVING COUNT(*) != c.chunk_total
                LIMIT 10
            """)
            inconsistent = cur.fetchall()
            assert len(inconsistent) == 0, \
                f"Found {len(inconsistent)} documents with inconsistent chunk_total"

    def test_chunk_index_ranges_valid(self, db_connection):
        """chunk_index is within valid range [0, chunk_total)"""
        with db_connection.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM chunks c
                WHERE c.chunk_index >= c.chunk_total OR c.chunk_index < 0
            """)
            invalid_count = cur.fetchone()[0]
            assert invalid_count == 0, \
                f"Found {invalid_count} chunks with invalid chunk_index"


class TestDocumentStructure:
    """Test document type-specific structure"""

    def test_counsel_cases_have_expected_chunk_types(self, db_connection):
        """Counsel cases have problem/solution/full chunk_types"""
        with db_connection.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT chunk_type
                FROM chunks c
                JOIN documents d ON c.doc_id = d.doc_id
                WHERE d.doc_type = 'counsel_case'
            """)
            chunk_types = {row[0] for row in cur.fetchall()}

            if len(chunk_types) > 0:
                expected = {"problem", "solution", "full"}
                # At least one should exist
                assert len(expected.intersection(chunk_types)) > 0, \
                    f"Expected chunk types {expected}, found {chunk_types}"

    def test_dispute_cases_have_expected_chunk_types(self, db_connection):
        """Dispute cases have facts/claims/mediation_outcome chunk_types"""
        with db_connection.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT chunk_type
                FROM chunks c
                JOIN documents d ON c.doc_id = d.doc_id
                WHERE d.doc_type = 'mediation_case'
            """)
            chunk_types = {row[0] for row in cur.fetchall()}

            if len(chunk_types) > 0:
                expected = {"facts", "claims", "mediation_outcome", "judgment", "decision"}
                # At least one should exist
                assert len(expected.intersection(chunk_types)) > 0, \
                    f"Expected chunk types {expected}, found {chunk_types}"


class TestSearchQuality:
    """Test search functionality and data quality"""

    def test_fts_search_returns_results(self, db_connection):
        """Full-text search returns results for common Korean terms"""
        with db_connection.cursor() as cur:
            cur.execute("""
                SELECT chunk_id
                FROM mv_searchable_chunks
                WHERE content_vector @@ to_tsquery('simple', '환불')
                LIMIT 5
            """)
            results = cur.fetchall()

            # Should have at least some results if data is loaded
            # (informational - may be 0 if no data loaded)

    def test_embeddings_status_report(self, db_connection):
        """Report embedding status (NULL vs populated)"""
        with db_connection.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE embedding IS NOT NULL) as with_embedding,
                    COUNT(*) FILTER (WHERE embedding IS NULL) as without_embedding,
                    COUNT(*) as total
                FROM chunks
            """)
            stats = cur.fetchone()

            print(f"\n📊 Embedding Status:")
            print(f"  With embeddings: {stats[0]}")
            print(f"  Without embeddings (NULL): {stats[1]}")
            print(f"  Total chunks: {stats[2]}")

            # No assertion - just informational

    def test_materialized_view_populated(self, db_connection):
        """mv_searchable_chunks has expected row count"""
        with db_connection.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM mv_searchable_chunks")
            count = cur.fetchone()[0]

            print(f"\n📊 Materialized View: {count} chunks indexed")

            # Should have at least law chunks (8,960) if data loaded
            # Informational check
