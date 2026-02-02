"""
Test script to verify routing bug fixes.

Tests:
1. "ㅎㅇ" (greeting) → should be classified as "general" → NO_RETRIEVAL
2. "노트북 관련 기준 있어?" → should be classified as "criteria" → NEED_RAG
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from app.agents.query_analysis.classifiers import (
    classify_mode,
    classify_query_type_with_confidence,
)


def test_routing():
    """Test routing bug fixes"""

    # Test case 1: Greeting "ㅎㅇ"
    print("\n=== Test Case 1: 인사말 'ㅎㅇ' ===")
    query1 = "ㅎㅇ"
    query_type1, confidence1 = classify_query_type_with_confidence(query1)
    mode1 = classify_mode(query_type1, False, query1)

    print(f"Query: '{query1}'")
    print(f"Classified as: {query_type1} (confidence: {confidence1:.2f})")
    print(f"Routing mode: {mode1}")
    print(f"Expected: query_type='general', mode='NO_RETRIEVAL'")
    print(f"PASS" if query_type1 == "general" and mode1 == "NO_RETRIEVAL" else "FAIL")

    # Test case 2: Criteria query "노트북 관련 기준 있어?"
    print("\n=== Test Case 2: 기준 질문 '노트북 관련 기준 있어?' ===")
    query2 = "노트북 관련 기준 있어?"
    query_type2, confidence2 = classify_query_type_with_confidence(query2)
    mode2 = classify_mode(query_type2, False, query2)

    print(f"Query: '{query2}'")
    print(f"Classified as: {query_type2} (confidence: {confidence2:.2f})")
    print(f"Routing mode: {mode2}")
    print(f"Expected: query_type='criteria', mode='NEED_RAG'")
    print(f"PASS" if query_type2 == "criteria" and mode2 == "NEED_RAG" else "FAIL")

    # Test case 3: General greeting variations
    print("\n=== Test Case 3: 다양한 인사말 ===")
    greetings = ["안녕", "안녕하세요", "하이", "hi", "hello"]
    for greeting in greetings:
        query_type, confidence = classify_query_type_with_confidence(greeting)
        mode = classify_mode(query_type, False, greeting)
        status = "✓" if query_type == "general" and mode == "NO_RETRIEVAL" else "✗"
        print(f"{status} '{greeting}' → {query_type} ({confidence:.2f}) → {mode}")

    # Test case 4: More criteria queries
    print("\n=== Test Case 4: 다양한 기준 질문 ===")
    criteria_queries = [
        "냉장고 환불 기준 알려줘",
        "스마트폰 교환 기준이 궁금해요",
        "분쟁조정기준 보여줘",
    ]
    for query in criteria_queries:
        query_type, confidence = classify_query_type_with_confidence(query)
        mode = classify_mode(query_type, False, query)
        status = "✓" if query_type == "criteria" and mode == "NEED_RAG" else "✗"
        print(f"{status} '{query}' → {query_type} ({confidence:.2f}) → {mode}")


if __name__ == "__main__":
    test_routing()
