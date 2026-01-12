"""
Load All Test Data - Phase 6 Data Loading Orchestrator

Loads all test data sources (counsel + dispute + criteria) to PostgreSQL in one command.

Data Sources:
    - counsel.jsonl: ~18,000 records → ~62,851 chunks
    - kca.jsonl: ~909 records → ~2,727 chunks
    - ecmc.jsonl: ~811 records → ~2,433 chunks
    - kcdrc.jsonl: ~295 records → ~885 chunks
    - criteria/*.jsonl: 7 files → ~507 chunks

Usage:
    conda activate dsr

    # Load all data
    python load_all_test_data.py --all

    # Load specific datasets
    python load_all_test_data.py --counsel --dispute

    # Skip already loaded data
    python load_all_test_data.py --all --skip-existing

    # Custom batch size
    python load_all_test_data.py --all --batch-size 500
"""
import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
import psycopg

# Add backend directory to path for imports
BACKEND_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# Import existing data loaders
from scripts.data_loading.load_cases_to_db import (
    load_counsel_jsonl,
    load_dispute_jsonl,
    conninfo_from_env,
    ensure_schema
)
from scripts.data_loading.load_criteria_to_db import (
    load_criteria_units,
    load_to_documents_chunks
)


class DataLoadOrchestrator:
    """Orchestrates loading of all test data sources"""

    def __init__(
        self,
        batch_size: int = 1000,
        skip_existing: bool = False,
        verbose: bool = True
    ):
        """
        Initialize orchestrator

        Args:
            batch_size: Batch size for insert operations
            skip_existing: Skip documents that already exist
            verbose: Print progress messages
        """
        self.batch_size = batch_size
        self.skip_existing = skip_existing
        self.verbose = verbose
        self.start_time = None
        self.results = {
            'counsel': {'docs': 0, 'chunks': 0, 'errors': 0},
            'dispute': {'docs': 0, 'chunks': 0, 'errors': 0},
            'criteria': {'docs': 0, 'chunks': 0, 'errors': 0}
        }

    def log(self, message: str) -> None:
        """Print log message if verbose enabled"""
        if self.verbose:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def load_counsel_data(self, conn: psycopg.Connection) -> Dict[str, int]:
        """
        Load counsel data from counsel.jsonl

        Args:
            conn: PostgreSQL connection

        Returns:
            {docs: count, chunks: count, errors: count}
        """
        counsel_file = BACKEND_DIR / "data" / "counsel" / "counsel.jsonl"

        if not counsel_file.exists():
            self.log(f"⚠️  Counsel file not found: {counsel_file}")
            return {'docs': 0, 'chunks': 0, 'errors': 0}

        self.log(f"📥 Loading counsel data from {counsel_file.name}...")

        try:
            doc_count, chunk_count = load_counsel_jsonl(
                conn=conn,
                jsonl_path=counsel_file,
                batch_size=self.batch_size,
                skip_existing=self.skip_existing
            )

            self.log(f"✅ Counsel: {doc_count} documents, {chunk_count} chunks")

            return {
                'docs': doc_count,
                'chunks': chunk_count,
                'errors': 0
            }

        except Exception as e:
            self.log(f"❌ Error loading counsel data: {e}")
            return {'docs': 0, 'chunks': 0, 'errors': 1}

    def load_dispute_data(self, conn: psycopg.Connection) -> Dict[str, Dict[str, int]]:
        """
        Load dispute data from kca.jsonl, ecmc.jsonl, kcdrc.jsonl

        Args:
            conn: PostgreSQL connection

        Returns:
            {
                'kca': {docs: count, chunks: count, errors: count},
                'ecmc': {docs: count, chunks: count, errors: count},
                'kcdrc': {docs: count, chunks: count, errors: count},
                'total': {docs: count, chunks: count, errors: count}
            }
        """
        dispute_dir = BACKEND_DIR / "data" / "dispute"
        agencies = {
            'kca': dispute_dir / "kca.jsonl",
            'ecmc': dispute_dir / "ecmc.jsonl",
            'kcdrc': dispute_dir / "kcdrc.jsonl"
        }

        results = {}
        total_docs = 0
        total_chunks = 0
        total_errors = 0

        for agency_code, jsonl_file in agencies.items():
            if not jsonl_file.exists():
                self.log(f"⚠️  Dispute file not found: {jsonl_file}")
                results[agency_code] = {'docs': 0, 'chunks': 0, 'errors': 0}
                continue

            self.log(f"📥 Loading {agency_code.upper()} dispute data from {jsonl_file.name}...")

            try:
                doc_count, chunk_count = load_dispute_jsonl(
                    conn=conn,
                    jsonl_path=jsonl_file,
                    agency=agency_code.upper(),
                    batch_size=self.batch_size,
                    skip_existing=self.skip_existing
                )

                self.log(f"✅ {agency_code.upper()}: {doc_count} documents, {chunk_count} chunks")

                results[agency_code] = {
                    'docs': doc_count,
                    'chunks': chunk_count,
                    'errors': 0
                }

                total_docs += doc_count
                total_chunks += chunk_count

            except Exception as e:
                self.log(f"❌ Error loading {agency_code.upper()} data: {e}")
                results[agency_code] = {'docs': 0, 'chunks': 0, 'errors': 1}
                total_errors += 1

        results['total'] = {
            'docs': total_docs,
            'chunks': total_chunks,
            'errors': total_errors
        }

        return results

    def load_criteria_data(self, conn: psycopg.Connection) -> Dict[str, int]:
        """
        Load criteria data from criteria/*.jsonl files

        Args:
            conn: PostgreSQL connection

        Returns:
            {docs: count, chunks: count, errors: count}
        """
        criteria_dir = BACKEND_DIR / "data" / "criteria" / "jsonl"

        if not criteria_dir.exists():
            self.log(f"⚠️  Criteria directory not found: {criteria_dir}")
            return {'docs': 0, 'chunks': 0, 'errors': 0}

        # Find all criteria JSONL files
        criteria_files = list(criteria_dir.glob("*.jsonl"))

        if not criteria_files:
            self.log(f"⚠️  No criteria JSONL files found in {criteria_dir}")
            return {'docs': 0, 'chunks': 0, 'errors': 0}

        self.log(f"📥 Loading {len(criteria_files)} criteria files...")

        total_docs = 0
        total_chunks = 0
        errors = 0

        for criteria_file in criteria_files:
            try:
                # Determine source_id from filename
                # e.g., "consumer_dispute_resolution_criteria_table1_items.jsonl" → "table1"
                filename = criteria_file.stem
                if "table1" in filename:
                    source_id = "table1"
                    source_label = "소비자분쟁해결기준 별표1 (품목분류)"
                elif "table2" in filename:
                    source_id = "table2"
                    source_label = "소비자분쟁해결기준 별표2 (해결기준)"
                elif "table3" in filename:
                    source_id = "table3"
                    source_label = "소비자분쟁해결기준 별표3 (보증기간)"
                elif "table4" in filename:
                    source_id = "table4"
                    source_label = "소비자분쟁해결기준 별표4 (내용연수)"
                elif "ecommerce" in filename:
                    source_id = "ecommerce_guideline"
                    source_label = "전자상거래 가이드라인"
                elif "content" in filename:
                    source_id = "content_guideline"
                    source_label = "콘텐츠 가이드라인"
                else:
                    self.log(f"⚠️  Unknown criteria file: {criteria_file.name}")
                    continue

                self.log(f"  → Loading {source_id} ({criteria_file.name})")

                # Load to documents/chunks tables (for RAG integration)
                chunk_count = load_to_documents_chunks(
                    conn=conn,
                    source_id=source_id,
                    source_label=source_label,
                    jsonl_path=criteria_file
                )

                total_docs += 1  # One document per criteria file
                total_chunks += chunk_count

            except Exception as e:
                self.log(f"❌ Error loading {criteria_file.name}: {e}")
                errors += 1

        self.log(f"✅ Criteria: {total_docs} documents, {total_chunks} chunks")

        return {
            'docs': total_docs,
            'chunks': total_chunks,
            'errors': errors
        }

    def load_all(
        self,
        load_counsel: bool = True,
        load_dispute: bool = True,
        load_criteria: bool = True
    ) -> Dict[str, Any]:
        """
        Load all specified data sources

        Args:
            load_counsel: Load counsel data
            load_dispute: Load dispute data
            load_criteria: Load criteria data

        Returns:
            Summary report dictionary
        """
        self.start_time = datetime.now()
        self.log("=" * 60)
        self.log("📊 Phase 6 Data Loading - Starting...")
        self.log("=" * 60)

        # Connect to database
        conninfo = conninfo_from_env()
        self.log(f"🔌 Connecting to PostgreSQL...")

        try:
            conn = psycopg.connect(conninfo)
            self.log("✅ Connected to database")

            # Verify schema exists
            ensure_schema(conn)
            self.log("✅ Schema verified (documents, chunks tables exist)")

        except Exception as e:
            self.log(f"❌ Database connection failed: {e}")
            return self._generate_report(error=str(e))

        try:
            # Load counsel data
            if load_counsel:
                self.results['counsel'] = self.load_counsel_data(conn)

            # Load dispute data
            if load_dispute:
                dispute_results = self.load_dispute_data(conn)
                self.results['dispute'] = dispute_results.get('total', {'docs': 0, 'chunks': 0, 'errors': 0})
                self.results['dispute_breakdown'] = {
                    k: v for k, v in dispute_results.items() if k != 'total'
                }

            # Load criteria data
            if load_criteria:
                self.results['criteria'] = self.load_criteria_data(conn)

        finally:
            conn.close()
            self.log("🔌 Database connection closed")

        # Generate report
        report = self._generate_report()
        self.log("=" * 60)
        self.log("📊 Data Loading Complete!")
        self.log("=" * 60)

        return report

    def _generate_report(self, error: str = None) -> Dict[str, Any]:
        """
        Generate summary report

        Args:
            error: Optional error message if loading failed

        Returns:
            Report dictionary
        """
        if error:
            return {
                'timestamp': datetime.now().isoformat(),
                'status': 'failed',
                'error': error
            }

        elapsed = (datetime.now() - self.start_time).total_seconds()

        # Calculate totals
        total_docs = (
            self.results['counsel']['docs'] +
            self.results['dispute']['docs'] +
            self.results['criteria']['docs']
        )
        total_chunks = (
            self.results['counsel']['chunks'] +
            self.results['dispute']['chunks'] +
            self.results['criteria']['chunks']
        )
        total_errors = (
            self.results['counsel']['errors'] +
            self.results['dispute']['errors'] +
            self.results['criteria']['errors']
        )

        report = {
            'timestamp': datetime.now().isoformat(),
            'duration_seconds': round(elapsed, 2),
            'data_sources': {
                'counsel': self.results['counsel'],
                'dispute': self.results.get('dispute', {}),
                'criteria': self.results.get('criteria', {})
            },
            'summary': {
                'total_documents': total_docs,
                'total_chunks': total_chunks,
                'total_errors': total_errors
            },
            'performance': {
                'documents_per_second': round(total_docs / elapsed, 2) if elapsed > 0 else 0,
                'chunks_per_second': round(total_chunks / elapsed, 2) if elapsed > 0 else 0
            },
            'status': 'success' if total_errors == 0 else 'partial_success'
        }

        # Add dispute breakdown if available
        if 'dispute_breakdown' in self.results:
            report['data_sources']['dispute']['breakdown'] = self.results['dispute_breakdown']

        return report


def save_report(report: Dict[str, Any], output_dir: Path = None) -> Path:
    """
    Save report to JSON file

    Args:
        report: Report dictionary
        output_dir: Output directory (default: /tmp)

    Returns:
        Path to saved report file
    """
    if output_dir is None:
        output_dir = Path("/tmp")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = output_dir / f"data_load_report_{timestamp}.json"

    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return report_file


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Load all test data (counsel + dispute + criteria) to PostgreSQL"
    )

    # Data source selection
    parser.add_argument("--all", action="store_true", help="Load all data sources")
    parser.add_argument("--counsel", action="store_true", help="Load counsel data only")
    parser.add_argument("--dispute", action="store_true", help="Load dispute data only")
    parser.add_argument("--criteria", action="store_true", help="Load criteria data only")

    # Options
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for inserts")
    parser.add_argument("--skip-existing", action="store_true", help="Skip existing documents")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress messages")
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp"), help="Report output directory")

    args = parser.parse_args()

    # Determine what to load
    load_counsel = args.all or args.counsel
    load_dispute = args.all or args.dispute
    load_criteria = args.all or args.criteria

    if not (load_counsel or load_dispute or load_criteria):
        parser.error("Specify --all or at least one of --counsel/--dispute/--criteria")

    # Create orchestrator
    orchestrator = DataLoadOrchestrator(
        batch_size=args.batch_size,
        skip_existing=args.skip_existing,
        verbose=not args.quiet
    )

    # Load data
    report = orchestrator.load_all(
        load_counsel=load_counsel,
        load_dispute=load_dispute,
        load_criteria=load_criteria
    )

    # Save report
    report_file = save_report(report, output_dir=args.output_dir)
    print(f"\n📄 Report saved to: {report_file}")

    # Print summary
    print("\n📊 Summary:")
    print(f"  Total documents: {report['summary']['total_documents']}")
    print(f"  Total chunks: {report['summary']['total_chunks']}")
    print(f"  Total errors: {report['summary']['total_errors']}")
    print(f"  Status: {report['status']}")
    print(f"  Duration: {report['duration_seconds']}s")
    print(f"  Throughput: {report['performance']['chunks_per_second']:.1f} chunks/s")

    # Exit with error code if there were errors
    sys.exit(1 if report['summary']['total_errors'] > 0 else 0)


if __name__ == "__main__":
    main()
