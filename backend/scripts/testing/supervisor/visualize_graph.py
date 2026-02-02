#!/usr/bin/env python
"""
LangGraph MAS Supervisor Visualization CLI

Usage:
    python visualize_graph.py --format mermaid
    python visualize_graph.py --format png --output graph.png
    python visualize_graph.py --list-nodes
    python visualize_graph.py --list-edges
    python visualize_graph.py --state-schema
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.supervisor import reset_graph
from app.supervisor.graph_mas import create_mas_supervisor_graph
from app.supervisor.state import ChatState


def get_graph():
    reset_graph()
    return create_mas_supervisor_graph()


def print_mermaid():
    graph = get_graph()
    compiled = graph.compile()

    try:
        mermaid_code = compiled.get_graph().draw_mermaid()
        print("```mermaid")
        print(mermaid_code)
        print("```")
    except Exception as e:
        print(f"Error generating Mermaid: {e}")
        print("\nManual Mermaid diagram:")
        print_manual_mermaid()


def print_manual_mermaid():
    print("""```mermaid
graph TD
    __start__([Start]) --> input_guardrail
    input_guardrail --> |passed| supervisor
    input_guardrail --> |blocked| __end__([End])
    supervisor --> |analyze| query_analysis
    supervisor --> |generate| generation
    supervisor --> |review| review
    supervisor --> |finalize| output_guardrail
    query_analysis --> supervisor
    generation --> supervisor
    review --> |passed| supervisor
    review --> |failed & retry < 2| generation
    output_guardrail --> |complete| __end__

    style input_guardrail fill:#ffcdd2
    style supervisor fill:#c8e6c9
    style query_analysis fill:#e1f5fe
    style generation fill:#e1f5fe
    style review fill:#e1f5fe
    style output_guardrail fill:#ffcdd2
```""")


def save_png(output_path: str):
    graph = get_graph()
    compiled = graph.compile()

    try:
        png_bytes = compiled.get_graph().draw_mermaid_png()
        with open(output_path, "wb") as f:
            f.write(png_bytes)
        print(f"Graph saved to: {output_path}")
    except ImportError:
        print("Error: PNG generation requires additional dependencies.")
        print("Install with: pip install grandalf")
    except Exception as e:
        print(f"Error generating PNG: {e}")
        print("Try: pip install grandalf pyppeteer")


def list_nodes():
    graph = get_graph()

    print("=" * 60)
    print("LangGraph MAS Supervisor Nodes")
    print("=" * 60)

    nodes = list(graph.nodes.keys())

    node_descriptions = {
        "input_guardrail": "입력 가드레일 (유해 콘텐츠 필터링)",
        "supervisor": "MAS Supervisor (에이전트 조율)",
        "query_analysis": "질의 유형 분류, 키워드 추출, 쿼리 재생성",
        "retrieval": "4섹션 검색 (disputes, counsels, laws, criteria)",
        "generation": "LLM 답변 생성 + Fallback 체인",
        "review": "법적 검토 (사실 검증, 금지 표현, 인용 검증)",
        "output_guardrail": "출력 가드레일 (최종 검증)",
        "ask_clarification": "추가 정보 요청 (되묻기)",
        "low_similarity_prompt": "낮은 유사도 경고",
    }

    print(f"\nTotal nodes: {len(nodes)}\n")

    for i, node in enumerate(nodes, 1):
        desc = node_descriptions.get(node, "No description")
        print(f"{i}. {node}")
        print(f"   └── {desc}")

    print()


def list_edges():
    graph = get_graph()
    compiled = graph.compile()

    print("=" * 60)
    print("LangGraph MAS Supervisor Edges")
    print("=" * 60)

    try:
        drawable = compiled.get_graph()

        print("\n[Normal Edges]")
        for edge in drawable.edges:
            if hasattr(edge, "source") and hasattr(edge, "target"):
                print(f"  {edge.source} → {edge.target}")

        print("\n[Conditional Edges - MAS Supervisor]")
        conditional_info = [
            (
                "input_guardrail",
                "route_after_input_guardrail",
                ["supervisor", "__end__ (blocked)"],
            ),
            (
                "supervisor",
                "supervisor_router",
                ["query_analysis", "generation", "review", "output_guardrail"],
            ),
            (
                "review",
                "route_after_review",
                ["generation (retry)", "output_guardrail"],
            ),
            (
                "output_guardrail",
                "route_after_output_guardrail",
                ["supervisor", "__end__"],
            ),
        ]

        for source, func, targets in conditional_info:
            print(f"  {source} --[{func}]--> {', '.join(targets)}")

        print("\n[Terminal Edges]")
        terminals = ["output_guardrail"]
        for node in terminals:
            print(f"  {node} → __end__ (when complete)")

    except Exception as e:
        print(f"Error: {e}")


def print_state_schema():
    print("=" * 60)
    print("ChatState Schema")
    print("=" * 60)

    annotations = ChatState.__annotations__

    categories = {
        "Session Metadata": ["chat_type", "onboarding"],
        "Current Turn": ["user_query"],
        "Agent Results": ["query_analysis", "retrieval", "draft_answer", "review"],
        "Final Output": [
            "final_answer",
            "sources",
            "has_sufficient_evidence",
            "clarifying_questions",
        ],
        "Control Flags": ["retry_count", "awaiting_user_choice", "low_similarity_mode"],
        "Internal": ["messages", "_node_timings"],
    }

    for category, fields in categories.items():
        print(f"\n[{category}]")
        for field in fields:
            if field in annotations:
                type_hint = str(annotations[field])
                type_hint = type_hint.replace("typing.", "")
                print(f"  {field}: {type_hint}")


def print_routing_thresholds():
    from app.common.config import get_config

    config = get_config()

    print("=" * 60)
    print("MAS Supervisor Routing Thresholds")
    print("=" * 60)

    print(f"\n[Similarity Threshold]")
    threshold = config.agent.similarity_threshold
    print(f"  SIMILARITY_THRESHOLD: {threshold}")
    print(f"  - >= {threshold}: → generation (has evidence)")
    print(f"  - < {threshold}: → low_similarity_mode")

    print(f"\n[Review Retry]")
    print(f"  MAX_RETRIES: 2")
    print(f"  - retry_count < 2: → generation (retry)")
    print(f"  - retry_count >= 2: → output_guardrail")

    print(f"\n[Supervisor Routing]")
    print(f"  - query_analysis → analyze intent, extract keywords")
    print(f"  - generation → draft answer with Fallback chain")
    print(f"  - review → legal review (skip for general/system_meta)")
    print(f"  - output_guardrail → final validation, END")


def main():
    parser = argparse.ArgumentParser(
        description="LangGraph MAS Supervisor Visualization"
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--format", choices=["mermaid", "png"], help="Output format")
    group.add_argument("--list-nodes", action="store_true", help="List all nodes")
    group.add_argument("--list-edges", action="store_true", help="List all edges")
    group.add_argument("--state-schema", action="store_true", help="Print state schema")
    group.add_argument(
        "--thresholds", action="store_true", help="Print routing thresholds"
    )
    group.add_argument("--all", action="store_true", help="Print all information")

    parser.add_argument("--output", "-o", help="Output file path (for PNG)")

    args = parser.parse_args()

    if args.format == "mermaid":
        print_mermaid()
    elif args.format == "png":
        output = args.output or "mas_supervisor_graph.png"
        save_png(output)
    elif args.list_nodes:
        list_nodes()
    elif args.list_edges:
        list_edges()
    elif args.state_schema:
        print_state_schema()
    elif args.thresholds:
        print_routing_thresholds()
    elif args.all:
        list_nodes()
        print()
        list_edges()
        print()
        print_state_schema()
        print()
        print_routing_thresholds()
        print()
        print("\n" + "=" * 60)
        print("Mermaid Diagram")
        print("=" * 60)
        print_mermaid()


if __name__ == "__main__":
    main()
