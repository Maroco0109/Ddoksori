import os
import sys
import requests
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
import time

# Add backend to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from utils.embedding_connection import get_embedding_api_url

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'ddoksori'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres')
}

BATCH_SIZE = 50

def generate_embeddings():
    embed_api_url = get_embedding_api_url()
    print(f"Using Embedding API: {embed_api_url}")

    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    while True:
        # Get chunks without embeddings
        # Prioritize law chunks first
        cur.execute("""
            SELECT c.chunk_id, c.content 
            FROM chunks c
            JOIN documents d ON c.doc_id = d.doc_id
            WHERE c.embedding IS NULL AND d.doc_type='law' 
            LIMIT %s;
        """, (BATCH_SIZE,))
        chunks = cur.fetchall()
        
        if not chunks:
            print("No more chunks to embed.")
            break
            
        print(f"Processing batch of {len(chunks)} chunks...")

        updates = []
        for chunk_id, content in chunks:
            try:
                # Use retry logic
                for attempt in range(3):
                    try:
                        resp = requests.post(embed_api_url, json={'text': content}, timeout=30)
                        if resp.status_code == 200:
                            embedding = resp.json()['embedding']
                            updates.append((embedding, chunk_id))
                            break
                        else:
                            print(f"Error {resp.status_code}: {resp.text}")
                            time.sleep(1)
                    except Exception as e:
                        print(f"Connection error: {e}")
                        time.sleep(2)
            except Exception as e:
                print(f"Failed to embed chunk {chunk_id}: {e}")
        
        # Batch update
        if updates:
            print(f"Updating {len(updates)} chunks in DB...")
            # Cast list to string format compatible with pgvector if needed, 
            # but psycopg2 list usually works if registered? 
            # execute_values handles list adaptation automatically if configured?
            # PGVector stores as '[0.1, 0.2, ...]' string or array.
            # Using execute_values with `embedding::vector` cast usually handles python list [float].
            
            execute_values(cur, """
                UPDATE chunks SET embedding = data.embedding::vector
                FROM (VALUES %s) AS data (embedding, chunk_id)
                WHERE chunks.chunk_id = data.chunk_id
            """, updates)
            conn.commit()
        else:
            print("No updates in this batch (all failed?). stopping to avoid inf loop.")
            break
    
    # Refresh materialized view
    print("Refreshing materialized view...")
    cur.execute("REFRESH MATERIALIZED VIEW mv_searchable_chunks;")
    conn.commit()
    
    cur.close()
    conn.close()
    print("Done.")

if __name__ == "__main__":
    generate_embeddings()
