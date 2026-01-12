#!/usr/bin/env python3
"""
Interactive RAG Test Tool (Lite Version for S1-D3)
- Supports interactive search for criteria (S1-D3)
- Placeholder for full RAG system test
"""

import sys
import os
import argparse

# Add examples directory to sys.path to import query_criteria
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../examples'))

try:
    from query_criteria import hierarchical_search, get_criteria_statistics
except ImportError:
    print("❌ Error: Could not import query_criteria. Make sure backend/scripts/examples/query_criteria.py exists.")
    sys.exit(1)

def print_separator():
    print("=" * 60)

def search_loop():
    print_separator()
    print("🤖 Interactive RAG Test (S1-D3 Logic)")
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
            result = hierarchical_search(query, limit=3)
            
            print(f"\n[Stage 1: Classification] Found {len(result['stage1'])} candidates")
            for item in result['stage1']:
                print(f"  - {item.get('path_hint')}: {item.get('item_group')}")
                
            print(f"\n[Stage 2: Criteria] Found {len(result['stage2'])} related rules")
            for criteria in result['stage2']:
                 text = criteria.get('unit_text', '')
                 print(f"  - {text[:80]}..." if len(text) > 80 else f"  - {text}")

            if not result['stage1'] and not result['stage2']:
                print("  (No results found)")
                
        except Exception as e:
            print(f"❌ Error during search: {e}")

def show_stats():
    print("\n📊 Current DB Statistics:")
    try:
        stats = get_criteria_statistics()
        for row in stats['criteria_units']:
            print(f"  - {row['source_id']}: {row['unit_count']} units")
    except Exception as e:
        print(f"❌ Error fetching stats: {e}")

def main():
    parser = argparse.ArgumentParser(description="Interactive RAG Test Tool")
    parser.add_argument("--stats", action="store_true", help="Show database statistics on startup")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        
    search_loop()
    print("\nBye! 👋")

if __name__ == "__main__":
    main()
