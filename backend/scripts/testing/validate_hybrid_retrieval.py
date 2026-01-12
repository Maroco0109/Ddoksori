import os
import sys
import requests
import json
from dotenv import load_dotenv

# Add backend to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from rag import HybridRetriever
from utils.embedding_connection import get_embedding_api_url

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME', 'ddoksori'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres')
}

def test_retrieval():
    # Use adaptive URL
    embed_api_url = get_embedding_api_url()
    print(f"Using Embedding API: {embed_api_url}")
    
    print("Initializing HybridRetriever...")
    retriever = HybridRetriever(DB_CONFIG, embed_api_url)
    retriever.connect()

    queries = [
        "전자상거래 환불",
        "소비자 보호법", 
        "계약 해지 위약금"
    ]

    for q in queries:
        print(f"\n========================================")
        print(f"Testing Query: '{q}'")
        print(f"========================================")
        
        # 1. Lexical Only
        print("\n[Lexical Search (FTS)]")
        try:
            lex_results = retriever._lexical_search(q, top_k=3)
            if not lex_results:
                print("  - No results found.")
            for r in lex_results:
                print(f"  - [{r.doc_type}] {r.doc_title} (Rank: {r.similarity:.4f})")
                print(f"    Content snippet: {r.content[:50]}...")
        except Exception as e:
            print(f"  - Error: {e}")

        # 2. Dense Only
        print("\n[Dense Search (Vector)]")
        try:
            dense_results = retriever._dense_search(q, top_k=3)
            if not dense_results:
                print("  - No results found (Embeddings might be missing).")
            for r in dense_results:
                print(f"  - [{r.doc_type}] {r.doc_title} (Score: {r.similarity:.4f})")
                print(f"    Content snippet: {r.content[:50]}...")
        except Exception as e:
            print(f"  - Error: {e}")

        # 3. Hybrid
        print("\n[Hybrid Search (RRF Fusion)]")
        try:
            hybrid_results = retriever.search(q, top_k=3)
            if not hybrid_results:
                print("  - No results found.")
            for r in hybrid_results:
                # Similarity here is RRF score
                print(f"  - [{r.doc_type}] {r.doc_title} (RRF Score: {r.similarity:.4f})")
                print(f"    Content snippet: {r.content[:50]}...")
        except Exception as e:
            print(f"  - Error: {e}")

    retriever.close()
    print("\nValidation Complete.")

if __name__ == "__main__":
    test_retrieval()
