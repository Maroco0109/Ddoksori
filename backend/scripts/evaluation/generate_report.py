#!/usr/bin/env python3
"""
평가 결과 리포트 생성기

Usage:
    python -m scripts.evaluation.generate_report \
      --results-dir ./results \
      --output ./reports/eval_report.csv
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


TARGETS = {
    'query_type_accuracy': {'target': 0.90, 'op': '>='},
    'keyword_precision_mean': {'target': 0.80, 'op': '>='},
    'keyword_recall_mean': {'target': 0.70, 'op': '>='},
    'agency_hint_accuracy': {'target': 0.85, 'op': '>='},
    'missing_field_f1_mean': {'target': 0.85, 'op': '>='},
    'violation_detection_precision': {'target': 0.85, 'op': '>='},
    'violation_detection_recall': {'target': 0.90, 'op': '>='},
    'false_positive_rate': {'target': 0.10, 'op': '<='},
    'overall_ndcg_mean': {'target': 0.65, 'op': '>='},
    'overall_mrr_mean': {'target': 0.60, 'op': '>='},
    'overall_hit_rate_mean': {'target': 0.85, 'op': '>='},
    'domain_accuracy_mean': {'target': 0.85, 'op': '>='},
}


def load_result_files(results_dir: str) -> Dict[str, Dict]:
    results = {}
    results_path = Path(results_dir)

    if not results_path.exists():
        return results

    for json_file in results_path.glob('*.json'):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                results[json_file.stem] = data
        except Exception as e:
            print(f"Warning: Failed to load {json_file}: {e}")

    return results


def check_target(metric: str, score: float) -> str:
    if metric not in TARGETS:
        return "N/A"

    target_info = TARGETS[metric]
    target = target_info['target']
    op = target_info['op']

    if op == '>=':
        return "PASS" if score >= target else "FAIL"
    else:
        return "PASS" if score <= target else "FAIL"


def generate_summary_rows(results: Dict[str, Dict]) -> List[Dict[str, Any]]:
    rows = []

    for eval_name, data in results.items():
        summary = data.get('summary', {})

        if 'query_type_accuracy' in summary:
            eval_type = 'Query Analysis'
        elif 'violation_detection_precision' in summary:
            eval_type = 'Review'
        elif 'overall_ndcg_mean' in summary:
            eval_type = 'Retrieval'
        else:
            eval_type = 'Unknown'

        for metric, value in summary.items():
            if isinstance(value, (int, float)) and not metric.endswith('_count') and metric != 'total_time_seconds':
                status = check_target(metric, value)
                target_info = TARGETS.get(metric, {})

                rows.append({
                    'evaluation': eval_name,
                    'type': eval_type,
                    'metric': metric,
                    'score': round(value, 4) if isinstance(value, float) else value,
                    'target': target_info.get('target', ''),
                    'operator': target_info.get('op', ''),
                    'status': status,
                    'timestamp': summary.get('timestamp', ''),
                })

    return rows


def print_summary_table(rows: List[Dict[str, Any]]):
    print("\n" + "=" * 80)
    print("=== Evaluation Summary Report ===")
    print("=" * 80)

    current_type = None
    for row in sorted(rows, key=lambda x: (x['type'], x['metric'])):
        if row['type'] != current_type:
            current_type = row['type']
            print(f"\n--- {current_type} ---")
            print(f"{'Metric':<40} {'Score':>10} {'Target':>10} {'Status':>8}")
            print("-" * 70)

        target_str = f"{row['operator']}{row['target']}" if row['target'] else ''
        print(f"{row['metric']:<40} {row['score']:>10} {target_str:>10} {row['status']:>8}")

    print("=" * 80)

    pass_count = sum(1 for r in rows if r['status'] == 'PASS')
    fail_count = sum(1 for r in rows if r['status'] == 'FAIL')
    total = pass_count + fail_count

    print(f"\nOverall: {pass_count}/{total} metrics passed ({100*pass_count/total:.1f}%)" if total > 0 else "\nNo metrics evaluated")


def save_csv(output_path: str, rows: List[Dict[str, Any]]):
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    fieldnames = ['evaluation', 'type', 'metric', 'score', 'target', 'operator', 'status', 'timestamp']

    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nCSV report saved to: {output_path}")


def save_json(output_path: str, rows: List[Dict[str, Any]], raw_results: Dict[str, Dict]):
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    report = {
        'generated_at': datetime.now().isoformat(),
        'summary': rows,
        'raw_results': raw_results,
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\nJSON report saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='평가 결과 리포트 생성')
    parser.add_argument('--results-dir', default='results', help='결과 파일 디렉토리')
    parser.add_argument('--output', default='reports/eval_report.csv', help='출력 파일 경로')
    parser.add_argument('--format', choices=['csv', 'json', 'both'], default='csv', help='출력 형식')

    args = parser.parse_args()

    print(f"Loading results from: {args.results_dir}")
    results = load_result_files(args.results_dir)

    if not results:
        print("No result files found!")
        sys.exit(1)

    print(f"Found {len(results)} result file(s): {', '.join(results.keys())}")

    rows = generate_summary_rows(results)
    print_summary_table(rows)

    if args.format in ('csv', 'both'):
        csv_path = args.output if args.output.endswith('.csv') else args.output + '.csv'
        save_csv(csv_path, rows)

    if args.format in ('json', 'both'):
        json_path = args.output.replace('.csv', '.json') if args.output.endswith('.csv') else args.output + '.json'
        save_json(json_path, rows, results)


if __name__ == "__main__":
    main()
