"""
Batch Loading Utilities for JSONL Files

Provides reusable batch processing utilities for loading JSONL files to PostgreSQL.

Usage:
    conda activate dsr
    from batch_loader import BatchProcessor
"""
import json
import time
from pathlib import Path
from typing import Callable, Tuple, Dict, Any, Optional
from tqdm import tqdm
import psycopg


class BatchProcessor:
    """Generic batch processor for JSONL files"""

    def __init__(self, conn: psycopg.Connection, batch_size: int = 1000):
        """
        Initialize batch processor

        Args:
            conn: PostgreSQL connection
            batch_size: Number of records per batch
        """
        self.conn = conn
        self.batch_size = batch_size
        self.stats = {
            'success': 0,
            'errors': 0,
            'skipped': 0,
            'total': 0
        }
        self.start_time = None

    def process_jsonl_file(
        self,
        file_path: Path,
        transform_fn: Callable[[Dict[str, Any]], Optional[Tuple]],
        insert_sql: str,
        progress_bar: bool = True,
        skip_existing: bool = False
    ) -> Tuple[int, int]:
        """
        Generic JSONL batch processor

        Args:
            file_path: Path to JSONL file
            transform_fn: Function to transform JSONL line → DB row tuple
                         Should return None to skip record
            insert_sql: SQL INSERT/UPSERT statement
            progress_bar: Show tqdm progress bar
            skip_existing: Skip records that would trigger unique constraint

        Returns:
            (success_count, error_count)
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        self.start_time = time.time()
        batch = []
        line_number = 0

        # Count total lines for progress bar
        if progress_bar:
            with open(file_path, 'r', encoding='utf-8') as f:
                total_lines = sum(1 for _ in f)
            pbar = tqdm(total=total_lines, desc=f"Loading {file_path.name}")
        else:
            pbar = None

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line_number += 1
                    self.stats['total'] += 1

                    try:
                        # Parse JSON
                        record = json.loads(line)

                        # Transform to DB row
                        row = transform_fn(record)

                        if row is None:
                            self.stats['skipped'] += 1
                            if pbar:
                                pbar.update(1)
                            continue

                        batch.append(row)

                        # Insert batch when full
                        if len(batch) >= self.batch_size:
                            self._insert_batch(batch, insert_sql, skip_existing)
                            batch = []

                    except json.JSONDecodeError as e:
                        print(f"\nWarning: Malformed JSON at line {line_number}: {e}")
                        self.stats['errors'] += 1
                    except Exception as e:
                        print(f"\nWarning: Error processing line {line_number}: {e}")
                        self.stats['errors'] += 1

                    if pbar:
                        pbar.update(1)

                # Insert remaining batch
                if batch:
                    self._insert_batch(batch, insert_sql, skip_existing)

        finally:
            if pbar:
                pbar.close()

        return self.stats['success'], self.stats['errors']

    def _insert_batch(
        self,
        batch: list,
        insert_sql: str,
        skip_existing: bool = False
    ) -> None:
        """
        Insert batch of records to database

        Args:
            batch: List of record tuples/dicts
            insert_sql: SQL INSERT statement
            skip_existing: Skip duplicate key errors (useful for idempotent loads)
        """
        try:
            with self.conn.cursor() as cur:
                # Execute batch insert
                if isinstance(batch[0], dict):
                    # Named parameters
                    cur.executemany(insert_sql, batch)
                else:
                    # Positional parameters
                    cur.executemany(insert_sql, batch)

                self.conn.commit()
                self.stats['success'] += len(batch)

        except psycopg.errors.UniqueViolation as e:
            if skip_existing:
                # Rollback and skip batch
                self.conn.rollback()
                self.stats['skipped'] += len(batch)
                print(f"\nWarning: Skipped batch due to unique constraint: {e}")
            else:
                # Re-raise error
                self.conn.rollback()
                raise

        except Exception as e:
            # Rollback on any error
            self.conn.rollback()
            self.stats['errors'] += len(batch)
            print(f"\nError: Batch insert failed: {e}")

    def estimate_load_time(self, total_records: int) -> str:
        """
        Estimate time remaining based on current progress

        Args:
            total_records: Total number of records to process

        Returns:
            Human-readable time estimate (e.g., "2m 34s")
        """
        if self.start_time is None or self.stats['total'] == 0:
            return "Estimating..."

        elapsed = time.time() - self.start_time
        rate = self.stats['total'] / elapsed  # records per second

        if rate == 0:
            return "Unknown"

        remaining_records = total_records - self.stats['total']
        remaining_seconds = remaining_records / rate

        # Format time
        minutes = int(remaining_seconds // 60)
        seconds = int(remaining_seconds % 60)

        if minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"

    def get_throughput(self) -> float:
        """
        Get current throughput (records/second)

        Returns:
            Records processed per second
        """
        if self.start_time is None or self.stats['total'] == 0:
            return 0.0

        elapsed = time.time() - self.start_time
        return self.stats['total'] / elapsed

    def get_summary(self) -> Dict[str, Any]:
        """
        Get processing summary statistics

        Returns:
            Dictionary with success, error, skip counts and throughput
        """
        elapsed = time.time() - self.start_time if self.start_time else 0

        return {
            'total_processed': self.stats['total'],
            'successful': self.stats['success'],
            'errors': self.stats['errors'],
            'skipped': self.stats['skipped'],
            'elapsed_seconds': round(elapsed, 2),
            'throughput': round(self.get_throughput(), 2)
        }


class ProgressEstimator:
    """Utility for estimating progress and ETA"""

    def __init__(self, total_items: int):
        """
        Initialize progress estimator

        Args:
            total_items: Total number of items to process
        """
        self.total_items = total_items
        self.start_time = time.time()
        self.current_count = 0

    def update(self, count: int) -> None:
        """Update current progress count"""
        self.current_count = count

    def get_eta(self) -> str:
        """
        Get estimated time to completion

        Returns:
            Human-readable ETA (e.g., "Estimated time remaining: 2m 34s")
        """
        if self.current_count == 0:
            return "Estimating..."

        elapsed = time.time() - self.start_time
        rate = self.current_count / elapsed

        if rate == 0:
            return "Unknown"

        remaining = self.total_items - self.current_count
        remaining_seconds = remaining / rate

        minutes = int(remaining_seconds // 60)
        seconds = int(remaining_seconds % 60)

        if minutes > 0:
            return f"Estimated time remaining: {minutes}m {seconds}s"
        else:
            return f"Estimated time remaining: {seconds}s"

    def get_progress_percent(self) -> float:
        """Get progress percentage (0-100)"""
        if self.total_items == 0:
            return 0.0
        return (self.current_count / self.total_items) * 100


def retry_connection(
    conninfo: str,
    max_retries: int = 3,
    backoff_base: int = 2
) -> psycopg.Connection:
    """
    Connect to PostgreSQL with exponential backoff retry

    Args:
        conninfo: PostgreSQL connection string
        max_retries: Maximum number of retry attempts
        backoff_base: Base for exponential backoff (seconds)

    Returns:
        PostgreSQL connection

    Raises:
        psycopg.OperationalError: If connection fails after all retries
    """
    for attempt in range(max_retries):
        try:
            conn = psycopg.connect(conninfo)
            return conn
        except psycopg.OperationalError as e:
            if attempt < max_retries - 1:
                wait_time = backoff_base ** attempt
                print(f"Connection failed (attempt {attempt + 1}/{max_retries}). "
                      f"Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise  # Re-raise on final attempt


def count_jsonl_lines(file_path: Path) -> int:
    """
    Count lines in JSONL file

    Args:
        file_path: Path to JSONL file

    Returns:
        Number of lines
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        return sum(1 for _ in f)
