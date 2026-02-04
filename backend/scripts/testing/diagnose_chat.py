#!/usr/bin/env python3
"""
DDOKSORI Chat Diagnostic Script

Validates API keys, database connectivity, embeddings, and LLM functionality.
Run from backend directory with: PYTHONPATH=. python scripts/testing/diagnose_chat.py
"""

import os
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

load_dotenv()


def check_openai_key():
    """Check if OpenAI API key is valid"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[FAIL] OPENAI_API_KEY not set")
        return False

    if api_key.startswith("sk-") and len(api_key) > 20:
        print("[OK] OPENAI_API_KEY format looks valid")
    else:
        print("[WARN] OPENAI_API_KEY may be invalid (unexpected format)")

    # Test actual API call
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Say 'OK'"}],
            max_tokens=10,
        )
        print(f"[OK] OpenAI API call successful: {response.choices[0].message.content}")
        return True
    except Exception as e:
        print(f"[FAIL] OpenAI API call failed: {e}")
        return False


def check_embedding():
    """Check if embedding model works"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[SKIP] Embedding check - no API key")
        return False

    try:
        from openai import OpenAI

        from app.common.config import get_config

        config = get_config()
        print(f"[INFO] Embedding model: {config.embedding.model}")

        client = OpenAI(api_key=api_key)
        response = client.embeddings.create(
            model=config.embedding.model, input="테스트 쿼리"
        )
        print(f"[OK] Embedding generated: {len(response.data[0].embedding)} dimensions")
        return True
    except Exception as e:
        print(f"[FAIL] Embedding failed: {e}")
        return False


def check_database():
    """Check database connectivity and vector_chunks table"""
    try:
        import psycopg2

        from app.api.dependencies import get_db_config

        config = get_db_config()
        # Mask sensitive host information
        host = config["host"]
        masked_host = host[:8] + "***" if len(host) > 8 else "***"
        print(f"[INFO] DB Host: {masked_host}:{config['port']}/{config['database']}")

        conn = None
        try:
            conn = psycopg2.connect(**config)
            cursor = conn.cursor()

            # Check vector_chunks table exists and has data
            cursor.execute("SELECT COUNT(*) FROM vector_chunks")
            total_chunks = cursor.fetchone()[0]

            # Check how many have embeddings
            cursor.execute(
                "SELECT COUNT(*) FROM vector_chunks WHERE embedding IS NOT NULL"
            )
            with_embeddings = cursor.fetchone()[0]

            print(
                f"[OK] Database connected: {total_chunks} vector_chunks total, {with_embeddings} with embeddings"
            )

            if with_embeddings == 0:
                print(
                    "[WARN] No embeddings found! Retrieval will return empty results."
                )
                return False

            return True
        finally:
            if conn:
                conn.close()
    except Exception as e:
        print(f"[FAIL] Database connection failed: {e}")
        return False


def check_retrieval():
    """Test retrieval pipeline using HybridRetriever directly"""
    try:
        from app.api.dependencies import get_db_config
        from app.common.config import get_config

        config = get_config()
        print(f"[INFO] Similarity threshold: {config.agent.similarity_threshold}")

        # Use the retriever directly instead of the agent
        from app.agents.retrieval.tools.hybrid_retriever import HybridRetriever

        db_config = get_db_config()
        retriever = HybridRetriever(db_config)
        retriever.connect()

        try:
            results = retriever.search("환불 청약철회", top_k=3)
        finally:
            retriever.close()

        print(f"[OK] Hybrid retrieval returned {len(results)} results")
        if results:
            for i, r in enumerate(results[:2], 1):
                # SearchResult is a dataclass, access attributes directly
                score = getattr(r, "score", getattr(r, "similarity", "N/A"))
                text_preview = getattr(r, "text", getattr(r, "page_content", ""))[:50]
                if isinstance(score, float):
                    print(f"     {i}. score={score:.4f} | {text_preview}...")
                else:
                    print(f"     {i}. score={score} | {text_preview}...")

        return len(results) > 0
    except Exception as e:
        print(f"[FAIL] Retrieval failed: {e}")
        import traceback

        traceback.print_exc()
        return False


def check_llm_fallback():
    """Test LLM fallback chain"""
    try:
        from app.agents.answer_generation.fallback import AnswerGenerationFallback

        # Minimal retrieval context
        retrieval = {"disputes": [], "counsels": [], "laws": [], "criteria": []}
        agency_info = {
            "agency_info": {"name": "한국소비자원", "url": "https://www.kca.go.kr"}
        }

        answer, model_used, _ = AnswerGenerationFallback.generate_with_fallback(
            query="테스트 질문입니다",
            retrieval=retrieval,
            agency_info=agency_info,
            include_disclaimer=True,
        )

        print(f"[OK] Fallback chain succeeded with model: {model_used}")
        print(f"     Answer preview: {answer[:100]}...")

        if model_used in ["rule_based", "safe_fallback"]:
            print("[WARN] Fell back to rule_based/safe_fallback - LLM may have issues")
            return False
        return True
    except Exception as e:
        print(f"[FAIL] Fallback chain failed: {e}")
        return False


if __name__ == "__main__":
    print("=" * 70)
    print("DDOKSORI Chat Diagnostic")
    print("=" * 70)

    results = {}

    print("\n[1/5] Checking OpenAI API Key...")
    results["OpenAI API Key"] = check_openai_key()

    print("\n[2/5] Checking Embedding Model...")
    results["Embedding"] = check_embedding()

    print("\n[3/5] Checking Database Connection...")
    results["Database"] = check_database()

    print("\n[4/5] Testing Retrieval Pipeline...")
    results["Retrieval"] = check_retrieval()

    print("\n[5/5] Testing LLM Fallback Chain...")
    results["LLM Fallback"] = check_llm_fallback()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {name}: {status}")

    all_passed = all(results.values())
    print(
        "\n"
        + (
            "All checks passed! Chat should work correctly."
            if all_passed
            else "Some checks failed. Review errors above."
        )
    )

    # Provide guidance based on failures
    if not results.get("OpenAI API Key"):
        print("\n[RECOMMENDATION] Check OPENAI_API_KEY in .env:")
        print("  - Verify key is valid at https://platform.openai.com/api-keys")
        print("  - Check billing status and rate limits")

    if not results.get("Database"):
        print("\n[RECOMMENDATION] Check database configuration:")
        print("  - Verify DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD in .env")
        print("  - Run: SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL;")

    if not results.get("Retrieval"):
        print("\n[RECOMMENDATION] Check retrieval configuration:")
        print("  - Lower SIMILARITY_THRESHOLD in .env (try 0.45)")
        print("  - Verify embeddings exist in chunks table")

    sys.exit(0 if all_passed else 1)
