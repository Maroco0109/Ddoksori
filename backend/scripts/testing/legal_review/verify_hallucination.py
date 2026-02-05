
import os
import sys
import io

# Force UTF-8
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

from app.common.config import get_config
from app.agents.retrieval.tools.specialized_retrievers import CaseRetriever

def verify_1372_case():
    print("=== 1372 Case Verification ===")
    
    config = get_config()
    db_config = config.database.get_connection_dict()
    
    print(f"Connecting to DB: {db_config['host']}:{db_config['port']}")
    
    try:
        retriever = CaseRetriever(db_config)
        retriever.connect()
    except Exception as e:
        print(f"Failed to connect to DB: {e}")
        return

    target_title = "개인 PT(퍼스널트레이닝) 계약 해지시 실제 결제한 요금이 아닌 정상 요금 규정을 적용하여 환급해주겠다고 하는 경우"
    print(f"\nTarget Title: {target_title}")
    
    # 1. Search by exact title query
    print("\n[Search 1] Using full title as query...")
    results = retriever.search_counsels(target_title, top_k=5)
    
    found = False
    for i, res in enumerate(results):
        title = res.get('doc_title', '').strip()
        print(f"Result {i+1}: {title}")
        print(f"Similarity: {res.get('similarity')}")
        
        # Check for title match (ignoring whitespace differences)
        if target_title.replace(" ", "") in title.replace(" ", ""):
            print(">>> EXACT TITLE MATCH FOUND! <<<")
            print("Content Snippet:", res.get('content')[:200] + "...")
            found = True
            break
            
    if not found:
        print("\n[Search 2] Trying broader query '개인 PT 환불 정상요금'...")
        results = retriever.search_counsels("개인 PT 환불 정상요금", top_k=5)
        for i, res in enumerate(results):
            title = res.get('doc_title', '').strip()
            print(f"Result {i+1}: {title}")
            
            if target_title.replace(" ", "") in title.replace(" ", ""):
                print(">>> TITLE MATCH FOUND IN BROADER SEARCH! <<<")
                found = True
                break

    retriever.close()
    
    if found:
        print("\nVERDICT: The case exists in the database. NOT A HALLUCINATION.")
    else:
        print("\nVERDICT: Case NOT found in top results. Potential hallucination or data gap.")

if __name__ == "__main__":
    verify_1372_case()
