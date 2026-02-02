"""
OpenAI Embedding API 테스트
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

# Load .env
backend_path = Path(__file__).parent.parent.parent.parent
env_path = backend_path / ".env"
load_dotenv(dotenv_path=env_path)

api_key = os.getenv("OPENAI_API_KEY")
print("=" * 80)
print("OPENAI EMBEDDING API TEST")
print("=" * 80)
print(f"API Key: {api_key[:20]}..." if api_key else "API Key: NOT SET")
print()

if not api_key:
    print("ERROR: OPENAI_API_KEY not set!")
    exit(1)

client = OpenAI(api_key=api_key)

# Test embedding
test_query = "노트북을 구매했는데 화면이 깨져서 도착했어요"
print(f"Test query: {test_query}")
print()

try:
    response = client.embeddings.create(
        model="text-embedding-3-large",
        input=test_query,
        dimensions=1024,  # Matryoshka embedding
    )

    embedding = response.data[0].embedding
    print(f"✅ Success!")
    print(f"   Embedding dimension: {len(embedding)}")
    print(f"   First 5 values: {embedding[:5]}")
    print()

except Exception as e:
    print(f"❌ Failed: {e}")
    print()

print("=" * 80)
print("TEST COMPLETE")
print("=" * 80)
