import asyncio
import sys

from dotenv import load_dotenv

# Force UTF-8
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

load_dotenv()

import json

from app.agents.answer_generation.agent import _try_early_exit
from app.agents.query_analysis.agent import query_analysis_node
from app.agents.query_analysis.classifier import classify_intent


async def debugers_greeting():
    test_queries = ["안녕", "고마워", "점심 메뉴 추천 해줘"]
    results = []

    print("=== Debugging Greeting Classification & Generation ===\n")

    for query in test_queries:
        print(f"--- Query: '{query}' ---")

        # 1. Test Classifier directly (Mock context if needed)
        intent_result = classify_intent(query)
        print(
            f"[Classifier] Type: {intent_result.query_type}, Confidence: {intent_result.confidence}"
        )

        # 2. Test Query Analysis Node
        state = {"user_query": query, "chat_type": "general"}
        qa_result = query_analysis_node(state)
        final_query_type = qa_result["query_analysis"]["query_type"]
        print(f"[QA Node] Final Query Type: {final_query_type}")

        # 3. Test Early Exit Logic
        gen_state = {
            "user_query": query,
            "query_analysis": {"query_type": final_query_type},
            "retrieval": {},
            "mode": "NO_RETRIEVAL" if final_query_type == "general" else "NEED_RAG",
        }

        early_exit_result = _try_early_exit(gen_state, None, 0)

        has_response = bool(early_exit_result)
        response_text = (
            early_exit_result.get("draft_answer") if early_exit_result else None
        )

        results.append(
            {
                "query": query,
                "classifier_type": intent_result.query_type,
                "qa_node_type": final_query_type,
                "early_exit_triggered": has_response,
                "response_preview": response_text[:50] if response_text else None,
            }
        )

    with open("debug_greeting_result.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("Results saved to debug_greeting_result.json")


if __name__ == "__main__":
    asyncio.run(debugers_greeting())
