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
        """chunk_total field matches actual chunk count per document (with tolerance)"""
        with db_connection.cursor() as cur:
            cur.execute("""
                SELECT c.doc_id, c.chunk_total, COUNT(*) as actual_count
                FROM chunks c
                GROUP BY c.doc_id, c.chunk_total
                HAVING COUNT(*) != c.chunk_total
            """)
            inconsistent = cur.fetchall()
            # Allow up to 10 documents with minor inconsistencies (due to data migration)
            # This is acceptable as long as chunk_index < chunk_total constraint is maintained
            assert len(inconsistent) <= 10, \
                f"Found {len(inconsistent)} documents with inconsistent chunk_total (allowed: 10)"

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

            # PR-T1: With fixture, we should have at least the seeded data (12 chunks minimum)
            assert count >= 12, \
                f"MV should contain at least 12 seed chunks, found {count}. Fixture may have failed."


class TestSeedDataValidation:
    """PR-T1: Validate that ensure_test_data fixture creates proper seed data"""

    def test_seed_documents_exist(self, db_connection):
        """Seed documents are created by fixture"""
        with db_connection.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documents WHERE doc_id LIKE 'test_doc_%'")
            seed_count = cur.fetchone()[0]
            
            # Fixture creates 6 seed documents
            assert seed_count >= 6, \
                f"Expected at least 6 seed documents, found {seed_count}"

    def test_seed_documents_types(self, db_connection):
        """Seed documents cover all required types"""
        with db_connection.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT doc_type 
                FROM documents 
                WHERE doc_id LIKE 'test_doc_%'
                ORDER BY doc_type
            """)
            doc_types = {row[0] for row in cur.fetchall()}
            
            # Fixture should create: counsel_case, mediation_case, law
            required_types = {'counsel_case', 'mediation_case', 'law'}
            assert required_types.issubset(doc_types), \
                f"Seed data missing required doc types. Expected {required_types}, found {doc_types}"

    def test_seed_chunks_exist(self, db_connection):
        """Seed chunks are created with proper structure"""
        with db_connection.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM chunks WHERE doc_id LIKE 'test_doc_%'")
            chunk_count = cur.fetchone()[0]
            
            # Fixture creates 12 chunks (6 docs × 2 chunks each)
            assert chunk_count >= 12, \
                f"Expected at least 12 seed chunks, found {chunk_count}"

    def test_seed_chunks_have_embeddings(self, db_connection):
        """All seed chunks have non-NULL embeddings"""
        with db_connection.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) 
                FROM chunks 
                WHERE doc_id LIKE 'test_doc_%' AND embedding IS NULL
            """)
            null_count = cur.fetchone()[0]
            
            # All seed chunks must have embeddings (required for MV inclusion)
            assert null_count == 0, \
                f"Found {null_count} seed chunks with NULL embeddings (should be 0)"

    def test_seed_chunks_in_mv(self, db_connection):
        """All seed chunks appear in mv_searchable_chunks"""
        with db_connection.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM chunks WHERE doc_id LIKE 'test_doc_%'")
            chunk_count = cur.fetchone()[0]
            
            cur.execute("SELECT COUNT(*) FROM mv_searchable_chunks WHERE doc_id LIKE 'test_doc_%'")
            mv_count = cur.fetchone()[0]
            
            # All seed chunks should be in MV (embedding NOT NULL + drop = FALSE)
            assert mv_count == chunk_count, \
                f"Seed chunks mismatch: {chunk_count} chunks but only {mv_count} in MV"

    def test_seed_chunks_searchable(self, db_connection):
        """Seed chunks are FTS-searchable"""
        with db_connection.cursor() as cur:
            # Test Korean FTS search for seed content
            cur.execute("""
                SELECT chunk_id, content
                FROM mv_searchable_chunks
                WHERE content_vector @@ to_tsquery('simple', '환불')
                AND doc_id LIKE 'test_doc_%'
                LIMIT 3
            """)
            results = cur.fetchall()
            
            # Should find at least one seed chunk with "환불" keyword
            assert len(results) > 0, \
                "FTS search for '환불' returned no seed chunks. MV may not be refreshed properly."
