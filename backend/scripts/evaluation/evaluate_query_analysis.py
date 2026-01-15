#!/usr/bin/env python3
"""
Query Analysis Agent 평가 CLI

Usage:
    python -m scripts.evaluation.evaluate_query_analysis \
      --golden-set ./data/golden_set/query_analysis.jsonl \
      --output ./results/qa_eval.json
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.orchestrator.nodes.query_analysis import (
    _classify_query_type,
    _extract_keywords,
    _determine_agency_hint,
)
from rag.evaluation import (
    QueryAnalysisMetrics,
    aggregate_query_analysis_results,
)


def load_golden_set(path: str) -> List[Dict]:
    dataset = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                dataset.append(json.loads(line))
    return dataset


def run_query_analysis(query: str) -> Dict:
    query_type = _classify_query_type(query)
    keywords = _extract_keywords(query)
    agency_hint = _determine_agency_hint(query)

    return {
        'query_type': query_type,
        'keywords': keywords,
        'agency_hint': agency_hint,
        'missing_fields': [],
    }


def print_progress(current: int, total: int, verbose: bool = False):
    pct = (current / total) * 100
    if not verbose:
        bar_len = 30
        filled = int(bar_len * current / total)
        bar = '=' * filled + '-' * (bar_len - filled)
        print(f"\r[{bar}] {pct:.1f}%", end='', flush=True)


def print_summary(summary: Dict, elapsed_sec: float):
    print("\n" + "=" * 55)
    print("=== Query Analysis Evaluation Results ===")
    print("=" * 55)

    print(f"\nDataset: {summary.get('sample_count', 0)} samples")
    print(f"Time: {elapsed_sec:.1f}s")

    print(f"\n{'Metric':<30} {'Score':>10} {'Target':>10}")
    print("-" * 55)

    targets = {
        'query_type_accuracy': 0.90,
        'keyword_precision_mean': 0.80,
        'keyword_recall_mean': 0.70,
        'agency_hint_accuracy': 0.85,
        'missing_field_f1_mean': 0.85,
    }

    for metric, target in targets.items():
        if metric in summary:
            score = summary[metric]
            status = "OK" if score >= target else "FAIL"
            print(f"{metric:<30} {score:>10.4f} {target:>10.2f}  [{status}]")

    print("=" * 55)


def save_results(output_path: str, summary: Dict, detailed_results: List[Dict]):
    output_data = {
        'summary': summary,
        'detailed_results': detailed_results
    }

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\nResults saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='Query Analysis Agent 평가')
    parser.add_argument('--golden-set', required=True, help='Golden Set 파일 경로 (JSONL)')
    parser.add_argument('--output', default='results/qa_eval.json', help='결과 저장 경로')
    parser.add_argument('--verbose', action='store_true', help='상세 로그 출력')

    args = parser.parse_args()

    print(f"Loading golden set: {args.golden_set}")
    try:
        golden_set = load_golden_set(args.golden_set)
    except FileNotFoundError:
        print(f"Error: Golden set not found: {args.golden_set}")
        sys.exit(1)

    print(f"Loaded {len(golden_set)} evaluation items")

    metrics = QueryAnalysisMetrics()
    start_time = time.time()
    results = []

    for i, item in enumerate(golden_set):
        print_progress(i + 1, len(golden_set), args.verbose)

        try:
            prediction = run_query_analysis(item['query'])

            result = metrics.evaluate_item(
                item_id=item['id'],
                query=item['query'],
                category=item.get('category', 'unknown'),
                predicted_query_type=prediction['query_type'],
                expected_query_type=item['expected_query_type'],
                predicted_keywords=prediction['keywords'],
                expected_keywords=item.get('expected_keywords', []),
                predicted_agency_hint=prediction['agency_hint'],
                expected_agency_hint=item.get('expected_agency_hint'),
                predicted_missing_fields=prediction['missing_fields'],
                expected_missing_fields=item.get('expected_missing_fields', []),
            )

            results.append(result)

            if args.verbose:
                status = "OK" if result.query_type_correct else "FAIL"
                print(f"\n  [{item['id']}] Query Type: {status}, "
                      f"Keyword F1: {result.keyword_f1:.3f}")

        except Exception as e:
            print(f"\n  Error evaluating {item['id']}: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()

    print()

    total_time = time.time() - start_time
    summary = aggregate_query_analysis_results(results)
    summary.update({
        'run_id': f"qa_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        'timestamp': datetime.now().isoformat(),
        'golden_set': args.golden_set,
        'total_time_seconds': round(total_time, 2),
    })

    print_summary(summary, total_time)

    detailed_results = [r.to_dict() for r in results]
    save_results(args.output, summary, detailed_results)


if __name__ == "__main__":
    main()
