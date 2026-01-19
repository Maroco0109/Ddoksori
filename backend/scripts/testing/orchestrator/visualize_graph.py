#!/usr/bin/env python
"""
LangGraph Orchestrator Visualization CLI

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

from app.orchestrator import reset_graph
from app.orchestrator.graph import create_chat_graph
from app.orchestrator.state import ChatState


def get_graph():
    reset_graph()
    return create_chat_graph()


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
    __start__([Start]) --> query_analysis
    query_analysis --> |needs_clarification & no_info| ask_clarification
    query_analysis --> |has_info or general| retrieval
    retrieval --> |high_similarity| generation
    retrieval --> |low_similarity or no_results| low_similarity_prompt
    generation --> review
    review --> |passed| __end__([End])
    review --> |failed & retry < 2| generation
    review --> |failed & retry >= 2| __end__
    ask_clarification --> __end__
    low_similarity_prompt --> __end__
    
    style query_analysis fill:#e1f5fe
    style retrieval fill:#e1f5fe
    style generation fill:#e1f5fe
    style review fill:#e1f5fe
    style ask_clarification fill:#fff3e0
    style low_similarity_prompt fill:#fff3e0
```""")


def save_png(output_path: str):
    graph = get_graph()
    compiled = graph.compile()
    
    try:
        png_bytes = compiled.get_graph().draw_mermaid_png()
        with open(output_path, 'wb') as f:
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
    print("LangGraph Orchestrator Nodes")
    print("=" * 60)
    
    nodes = list(graph.nodes.keys())
    
    node_descriptions = {
        'query_analysis': '질의 유형 분류, 키워드 추출, 쿼리 재생성',
        'retrieval': '4섹션 검색 (disputes, counsels, laws, criteria)',
        'generation': 'LLM 답변 생성',
        'review': '가드레일 검토 (금지 표현, 출처 확인)',
        'ask_clarification': '추가 정보 요청 (되묻기)',
        'low_similarity_prompt': '낮은 유사도 경고',
    }
    
    print(f"\nTotal nodes: {len(nodes)}\n")
    
    for i, node in enumerate(nodes, 1):
        desc = node_descriptions.get(node, 'No description')
        print(f"{i}. {node}")
        print(f"   └── {desc}")
    
    print()


def list_edges():
    graph = get_graph()
    compiled = graph.compile()
    
    print("=" * 60)
    print("LangGraph Orchestrator Edges")
    print("=" * 60)
    
    try:
        drawable = compiled.get_graph()
        
        print("\n[Normal Edges]")
        for edge in drawable.edges:
            if hasattr(edge, 'source') and hasattr(edge, 'target'):
                print(f"  {edge.source} → {edge.target}")
        
        print("\n[Conditional Edges]")
        conditional_info = [
            ("query_analysis", "_route_after_query_analysis", 
             ["ask_clarification", "retrieval"]),
            ("retrieval", "_route_after_retrieval", 
             ["generation", "low_similarity_prompt"]),
            ("review", "_route_after_review", 
             ["generation (retry)", "__end__"]),
        ]
        
        for source, func, targets in conditional_info:
            print(f"  {source} --[{func}]--> {', '.join(targets)}")
        
        print("\n[Terminal Edges]")
        terminals = ["ask_clarification", "low_similarity_prompt"]
        for node in terminals:
            print(f"  {node} → __end__")
        
    except Exception as e:
        print(f"Error: {e}")


def print_state_schema():
    print("=" * 60)
    print("ChatState Schema")
    print("=" * 60)
    
    annotations = ChatState.__annotations__
    
    categories = {
        'Session Metadata': ['chat_type', 'onboarding'],
        'Current Turn': ['user_query'],
        'Agent Results': ['query_analysis', 'retrieval', 'draft_answer', 'review'],
        'Final Output': ['final_answer', 'sources', 'has_sufficient_evidence', 'clarifying_questions'],
        'Control Flags': ['retry_count', 'awaiting_user_choice', 'low_similarity_mode'],
        'Internal': ['messages', '_node_timings'],
    }
    
    for category, fields in categories.items():
        print(f"\n[{category}]")
        for field in fields:
            if field in annotations:
                type_hint = str(annotations[field])
                type_hint = type_hint.replace('typing.', '')
                print(f"  {field}: {type_hint}")


def print_routing_thresholds():
    from app.orchestrator.graph import SIMILARITY_THRESHOLD_HIGH
    
    print("=" * 60)
    print("Routing Thresholds")
    print("=" * 60)
    
    print(f"\n[Similarity Threshold]")
    print(f"  SIMILARITY_THRESHOLD_HIGH: {SIMILARITY_THRESHOLD_HIGH}")
    print(f"  - >= {SIMILARITY_THRESHOLD_HIGH}: → generation")
    print(f"  - < {SIMILARITY_THRESHOLD_HIGH}: → low_similarity_prompt")
    
    print(f"\n[Review Retry]")
    print(f"  MAX_RETRIES: 2")
    print(f"  - retry_count < 2: → generation (retry)")
    print(f"  - retry_count >= 2: → __end__")


def main():
    parser = argparse.ArgumentParser(description='LangGraph Orchestrator Visualization')
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--format', choices=['mermaid', 'png'], help='Output format')
    group.add_argument('--list-nodes', action='store_true', help='List all nodes')
    group.add_argument('--list-edges', action='store_true', help='List all edges')
    group.add_argument('--state-schema', action='store_true', help='Print state schema')
    group.add_argument('--thresholds', action='store_true', help='Print routing thresholds')
    group.add_argument('--all', action='store_true', help='Print all information')
    
    parser.add_argument('--output', '-o', help='Output file path (for PNG)')
    
    args = parser.parse_args()
    
    if args.format == 'mermaid':
        print_mermaid()
    elif args.format == 'png':
        output = args.output or 'orchestrator_graph.png'
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


if __name__ == '__main__':
    main()
