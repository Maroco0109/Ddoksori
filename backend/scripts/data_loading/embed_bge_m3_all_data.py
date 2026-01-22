"""
BGE-M3 Batch Embedding Script

Generates BGE-M3 Dense + Sparse embeddings for all chunks in the database.
Supports resumable processing with progress tracking.

Usage:
    python embed_bge_m3_all_data.py [--batch-size 32] [--limit 1000]
"""

import os
import sys
import json
import time
import argparse
import requests
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
from datetime import datetime

# Add backend to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'ddoksori'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres')
}

# Default BGE-M3 API URL
BGE_M3_API_URL = os.getenv('BGE_M3_EMBED_URL', 'http://localhost:8003/embed')

# Batch size (smaller than KURE due to higher memory usage)
DEFAULT_BATCH_SIZE = 32
MAX_RETRIES = 3
RETRY_DELAY = 2


def get_total_chunks(cur) -> int:
    """Get total number of chunks to process."""
    cur.execute("""
        SELECT COUNT(*) FROM chunks
        WHERE bge_m3_encoded = FALSE AND drop = FALSE
    """)
    return cur.fetchone()[0]


def get_unencoded_chunks(cur, batch_size: int):
    """Get chunks that haven't been encoded with BGE-M3 yet."""
    cur.execute("""
        SELECT c.chunk_id, c.content
        FROM chunks c
        JOIN documents d ON c.doc_id = d.doc_id
        WHERE c.bge_m3_encoded = FALSE AND c.drop = FALSE
        ORDER BY
            CASE
                WHEN d.doc_type IN ('counsel_case', 'mediation_case') THEN 0
                ELSE 1
            END,
            c.chunk_id ASC
        LIMIT %s;
    """, (batch_size,))
    return cur.fetchall()


def embed_batch(texts: list, api_url: str) -> dict:
    """
    Call BGE-M3 API to generate embeddings for a batch of texts.
    Returns dict with dense_embeddings and sparse_embeddings.
    """
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(
                api_url,
                json={
                    'texts': texts,
                    'return_dense': True,
                    'return_sparse': True
                },
                timeout=120  # Longer timeout for batch processing
            )

            if response.status_code == 200:
                return response.json()
            else:
                print(f"  API Error {response.status_code}: {response.text[:200]}")
                time.sleep(RETRY_DELAY)

        except requests.exceptions.Timeout:
            print(f"  Timeout on attempt {attempt + 1}/{MAX_RETRIES}")
            time.sleep(RETRY_DELAY * 2)
        except requests.exceptions.ConnectionError as e:
            print(f"  Connection error on attempt {attempt + 1}/{MAX_RETRIES}: {e}")
            time.sleep(RETRY_DELAY * 2)
        except Exception as e:
            print(f"  Unexpected error: {e}")
            time.sleep(RETRY_DELAY)

    return None


def update_chunks_bge_m3(cur, updates: list):
    """
    Batch update chunks with BGE-M3 embeddings.
    updates: list of (dense_embedding_str, sparse_embedding_json, chunk_id)
    """
    execute_values(cur, """
        UPDATE chunks SET
            bge_dense_vector = data.dense::vector,
            bge_sparse_vector = data.sparse::jsonb,
            bge_m3_encoded = TRUE
        FROM (VALUES %s) AS data (dense, sparse, chunk_id)
        WHERE chunks.chunk_id = data.chunk_id
    """, updates)


def check_api_health(api_url: str) -> bool:
    """Check if BGE-M3 API is healthy."""
    try:
        health_url = api_url.replace('/embed', '/health')
        response = requests.get(health_url, timeout=10)
        if response.status_code == 200:
            info = response.json()
            print(f"BGE-M3 Server Status: {info.get('status', 'unknown')}")
            print(f"  Model: {info.get('model', 'unknown')}")
            print(f"  Device: {info.get('device', 'unknown')}")
            print(f"  Dense dim: {info.get('dense_dim', 'unknown')}")
            return True
    except Exception as e:
        print(f"Failed to connect to BGE-M3 API: {e}")
    return False


def generate_bge_m3_embeddings(batch_size: int = DEFAULT_BATCH_SIZE, limit: int = None):
    """Main function to generate BGE-M3 embeddings for all chunks."""

    print("=" * 60)
    print("BGE-M3 Batch Embedding Script")
    print("=" * 60)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"API URL: {BGE_M3_API_URL}")
    print(f"Batch size: {batch_size}")
    if limit:
        print(f"Limit: {limit} chunks")
    print("=" * 60)

    # Check API health
    if not check_api_health(BGE_M3_API_URL):
        print("\nERROR: BGE-M3 API is not available.")
        print("Please start the BGE-M3 server first:")
        print("  docker-compose up -d bge_m3_embedding")
        print("  or")
        print("  python bge_m3_server.py")
        sys.exit(1)

    # Connect to database
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Get total count
    total_remaining = get_total_chunks(cur)
    if limit:
        total_remaining = min(total_remaining, limit)

    print(f"\nTotal chunks to process: {total_remaining:,}")

    if total_remaining == 0:
        print("All chunks already have BGE-M3 embeddings!")
        cur.close()
        conn.close()
        return

    # Estimate time
    estimated_time_gpu = total_remaining * 0.05 / 60  # ~50ms per chunk on GPU
    estimated_time_cpu = total_remaining * 0.5 / 60   # ~500ms per chunk on CPU
    print(f"Estimated time: {estimated_time_gpu:.1f} - {estimated_time_cpu:.1f} minutes")
    print()

    processed = 0
    failed = 0
    start_time = time.time()

    try:
        while True:
            # Check limit
            if limit and processed >= limit:
                print(f"\nReached limit of {limit} chunks.")
                break

            # Get batch
            remaining_in_limit = (limit - processed) if limit else batch_size
            current_batch_size = min(batch_size, remaining_in_limit)

            chunks = get_unencoded_chunks(cur, current_batch_size)

            if not chunks:
                print("\nNo more chunks to process.")
                break

            batch_start = time.time()
            chunk_ids = [c[0] for c in chunks]
            texts = [c[1] for c in chunks]

            # Generate embeddings
            result = embed_batch(texts, BGE_M3_API_URL)

            if result is None:
                print(f"  FAILED: Could not embed batch (chunk_ids: {chunk_ids[:3]}...)")
                failed += len(chunks)
                # Skip this batch to avoid infinite loop
                continue

            # Prepare updates
            dense_embeddings = result.get('dense_embeddings', [])
            sparse_embeddings = result.get('sparse_embeddings', [])

            if len(dense_embeddings) != len(chunks) or len(sparse_embeddings) != len(chunks):
                print(f"  WARNING: Embedding count mismatch. Expected {len(chunks)}, got {len(dense_embeddings)}/{len(sparse_embeddings)}")
                failed += len(chunks)
                continue

            updates = []
            for i, chunk_id in enumerate(chunk_ids):
                dense_str = str(dense_embeddings[i])
                sparse_json = json.dumps(sparse_embeddings[i])
                updates.append((dense_str, sparse_json, chunk_id))

            # Update database
            update_chunks_bge_m3(cur, updates)
            conn.commit()

            processed += len(chunks)
            batch_time = time.time() - batch_start
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = total_remaining - processed
            eta = remaining / rate if rate > 0 else 0

            # Progress output
            print(f"[{processed:,}/{total_remaining:,}] "
                  f"Batch: {len(chunks)} in {batch_time:.1f}s "
                  f"({batch_time/len(chunks)*1000:.0f}ms/chunk) | "
                  f"Rate: {rate:.1f}/s | "
                  f"ETA: {eta/60:.1f}min")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user. Progress saved.")
    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Final stats
        elapsed = time.time() - start_time
        print("\n" + "=" * 60)
        print("Summary")
        print("=" * 60)
        print(f"Total processed: {processed:,}")
        print(f"Failed: {failed:,}")
        print(f"Total time: {elapsed/60:.1f} minutes")
        if processed > 0:
            print(f"Average rate: {processed/elapsed:.1f} chunks/second")
            print(f"Average time per chunk: {elapsed/processed*1000:.1f}ms")
        print("=" * 60)

        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='Generate BGE-M3 embeddings for all chunks')
    parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE,
                        help=f'Batch size (default: {DEFAULT_BATCH_SIZE})')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit number of chunks to process')
    parser.add_argument('--api-url', type=str, default=None,
                        help='BGE-M3 API URL (default: from env or localhost:8003)')

    args = parser.parse_args()

    if args.api_url:
        global BGE_M3_API_URL
        BGE_M3_API_URL = args.api_url

    generate_bge_m3_embeddings(
        batch_size=args.batch_size,
        limit=args.limit
    )


if __name__ == "__main__":
    main()
