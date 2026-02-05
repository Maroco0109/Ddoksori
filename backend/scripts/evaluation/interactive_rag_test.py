#!/usr/bin/env python3
"""
Interactive RAG Test Tool (Lite Version for S1-D3)
- Supports interactive search for criteria (S1-D3)
- Uses refactored agents/retrieval tools
"""

import sys
import os
import argparse
from dotenv import load_dotenv

# Add backend directory to sys.path to allow importing app
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.abspath(os.path.join(current_dir, '../../'))
sys.path.insert(0, backend_dir)

try:
    from app.agents.retrieval.tools.specialized_retrievers import CriteriaRetriever
except ImportError as e:
    print(f"❌ Error: Could not import CriteriaRetriever: {e}")
    sys.exit(1)

def get_db_config():
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', '5432'),
        'dbname': os.getenv('DB_NAME', 'ddoksori'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'postgres'),
    }

def print_separator():
    print("=" * 60)

def search_loop(retriever: CriteriaRetriever):
    print_separator()
    print("🤖 Interactive RAG Test (Refactored Agents)")
    print("Type 'exit' or 'quit' to stop.")
    print_separator()

    while True:
        try:
            query = input("\n🔍 Enter item keyword (e.g., '계란', '스마트폰'): ").strip()
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        
        if query.lower() in ('exit', 'quit'):
            break
            
        if not query:
            continue
            
        print(f"\nSearching for: '{query}'...")
        
        try:
            # Using search_two_stage from CriteriaRetriever
            results = retriever.search_two_stage(query, top_k=3)
            
            print(f"\n[Criteria Search Results] Found {len(results)} matches")
            for i, result in enumerate(results, 1):
                print(f"\nResult {i}:")
                print(f"  - Source: {result.source_label}")
                path = f"{result.category or ''} > {result.item or ''}"
                print(f"  - Path: {path}")
                text = result.unit_text if result.unit_text else ""
                print(f"  - Content: {text[:80]}..." if len(text) > 80 else f"  - Content: {text}")

            if not results:
                print("  (No results found)")
                
        except Exception as e:
            print(f"❌ Error during search: {e}")

def main():
    parser = argparse.ArgumentParser(description="Interactive RAG Test Tool")
    args = parser.parse_args()
    
    load_dotenv()
    
    db_config = get_db_config()
    embed_api_url = os.getenv('EMBED_API_URL', 'http://localhost:8001/embed')
    
    print(f"Connecting to DB at {db_config['host']}:{db_config['port']}...")
    retriever = CriteriaRetriever(db_config, embed_api_url)
    
    try:
        retriever.connect()
        search_loop(retriever)
    finally:
        retriever.close()
    
    print("\nBye! 👋")

if __name__ == "__main__":
    main()
