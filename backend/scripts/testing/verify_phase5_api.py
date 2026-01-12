
import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_api():
    print("Starting API Test...")
    
    # 1. Health Check
    try:
        resp = requests.get(f"{BASE_URL}/health")
        print(f"Health Check: {resp.status_code} - {resp.json()}")
        if resp.status_code != 200:
            print("Health check failed!")
            return
    except Exception as e:
        print(f"Server not running? {e}")
        return

    # 2. Search Test (FTS)
    print("\nTesting Search Endpoint (Keyword: '환불')...")
    query_payload = {"query": "환불", "top_k": 3}
    try:
        resp = requests.post(f"{BASE_URL}/search", json=query_payload)
        if resp.status_code == 200:
            data = resp.json()
            print(f"Search Results Count: {data.get('results_count')}")
            for res in data.get('results', []):
                print(f" - [{res.get('doc_type')}] {res.get('doc_title')}")
        else:
            print(f"Search Error: {resp.text}")
    except Exception as e:
        print(f"Search request failed: {e}")

    # 3. Chat Test (FTS)
    print("\nTesting Chat Endpoint...")
    chat_payload = {"message": "전자상거래 환불 규정이 어떻게 되나요?", "top_k": 3}
    try:
        resp = requests.post(f"{BASE_URL}/chat", json=chat_payload)
        if resp.status_code == 200:
            data = resp.json()
            print(f"Chat Answer: {data.get('answer')[:100]}...")
            print(f"Sources Used: {len(data.get('sources', []))}")
        else:
            print(f"Chat Error: {resp.text}")
    except Exception as e:
        print(f"Chat request failed: {e}")

if __name__ == "__main__":
    test_api()
