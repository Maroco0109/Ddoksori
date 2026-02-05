import asyncio
import json
import os
import sys

# Force UTF-8
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.agents.query_analysis.agent import query_analysis_node
from app.agents.query_analysis.classifier import classify_intent
from app.supervisor.state import ChatState


async def debug_multiturn():
    print("=== Debugging Multi-turn Greeting ===")

    # Turn 1: "안녕"
    print("\n[Turn 1] User: 안녕")
    state_t1: ChatState = {
        "user_query": "안녕",
        "chat_type": "general",
        "messages": [],
        "onboarding": {},
        "_last_turn_context": {},
    }

    result_t1 = query_analysis_node(state_t1)
    qa_t1 = result_t1["query_analysis"]
    mode_t1 = result_t1["mode"]
    print(f"Turn 1 Result: QueryType={qa_t1['query_type']}, Mode={mode_t1}")

    # Simulate saving context for next turn
    # In a real graph, state is preserved. We need to see what `query_analysis_node` keeps or expects.
    # The node doesn't strictly update state object in-place but returns updates.
    # However, let's construct State T2 assuming T1 worked.

    # Mimic what the supervisor would pass to T2
    # We will pass the T1 query type in _last_turn_context if relevant,
    # but the key hypothesis is that 'chat_type' might stick or context might interfere.

    print("\n[Turn 2] User: 고마워")
    state_t2: ChatState = {
        "user_query": "고마워",
        "chat_type": qa_t1[
            "query_type"
        ],  # The system might preserve chat_type from previous turn?
        "messages": [
            {"role": "user", "content": "안녕"},
            {"role": "assistant", "content": "안녕하세요! (Template Response)"},
        ],
        "onboarding": {},
        "_last_turn_context": {
            "query_type": qa_t1["query_type"],
            "intent": qa_t1.get("intent", "general"),
        },
    }

    result_t2 = query_analysis_node(state_t2)
    qa_t2 = result_t2["query_analysis"]
    mode_t2 = result_t2["mode"]
    print(f"Turn 2 Result: QueryType={qa_t2['query_type']}, Mode={mode_t2}")

    # Additional Check: Direct Classifier on T2
    print(f"\n[Classifier Check] '고마워': {classify_intent('고마워').query_type}")

    results = {
        "turn1": {"query": "안녕", "query_type": qa_t1["query_type"], "mode": mode_t1},
        "turn2": {
            "query": "고마워",
            "query_type": qa_t2["query_type"],
            "mode": mode_t2,
            "input_chat_type": state_t2["chat_type"],
        },
    }

    with open("debug_multiturn_result.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    asyncio.run(debug_multiturn())
