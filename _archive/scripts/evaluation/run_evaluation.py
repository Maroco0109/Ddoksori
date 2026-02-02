#!/usr/bin/env python3
"""
RAG 정량 평가 실행 CLI

검색(Retrieval) 품질을 평가하고 결과를 JSON/CSV로 저장합니다.
LLM 호출 없이 빠르고 저렴하게 실행됩니다.

Usage:
    # 전체 평가 실행
    python scripts/evaluation/run_evaluation.py \
      --dataset data/evaluation/eval_dataset.jsonl \
      --output results/eval_$(date +%Y%m%d).json

    # CSV 출력
    python scripts/evaluation/run_evaluation.py \
      --dataset data/evaluation/eval_dataset.jsonl \
      --output results/eval.csv \
      --format csv

    # 특정 섹션만 평가
    python scripts/evaluation/run_evaluation.py \
      --dataset data/evaluation/eval_dataset.jsonl \
      --sections domain,laws

    # 상세 로그 출력
    python scripts/evaluation/run_evaluation.py \
      --dataset data/evaluation/eval_dataset.jsonl \
      --verbose
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from typing import List, Dict, Optional

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from dotenv import load_dotenv
load_dotenv()

from rag import StructuredRetriever
from rag.evaluation import RetrievalMetrics, aggregate_results
from utils.embedding_connection import get_embedding_api_url


def get_db_config() -> Dict:
    """DB 설정 로드"""
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME', 'ddoksori'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'postgres')
    }


def load_dataset(path: str) -> List[Dict]:
    """JSONL 데이터셋 로드"""
    dataset = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                dataset.append(json.loads(line))
    return dataset


def run_retrieval(
    query: str,
    retriever: StructuredRetriever,
    top_k: int = 3
) -> Dict:
    """RAG 검색 실행"""
    start_time = time.time()

    results = retriever.search_all_sections(
        query=query,
        dispute_k=top_k,
        counsel_k=top_k,
        law_k=top_k,
        criteria_k=top_k
    )

    elapsed_ms = (time.time() - start_time) * 1000

    return {
        'results': results,
        'elapsed_ms': elapsed_ms
    }


def convert_search_results(results: Dict) -> Dict[str, List[Dict]]:
    """검색 결과를 평가기 형식으로 변환"""
    converted = {
        'disputes': [],
        'counsels': [],
        'laws': [],
        'criteria': []
    }

    # Disputes
    for d in results.get('disputes', []):
        converted['disputes'].append({
            'doc_id': d.get('doc_id', ''),
            'doc_title': d.get('doc_title', ''),
            'similarity': d.get('similarity', 0.0)
        })

    # Counsels
    for c in results.get('counsels', []):
        converted['counsels'].append({
            'doc_id': c.get('doc_id', ''),
            'doc_title': c.get('doc_title', ''),
            'similarity': c.get('similarity', 0.0)
        })

    # Laws
    for l in results.get('laws', []):
        converted['laws'].append({
            'doc_id': l.get('chunk_id', l.get('doc_id', '')),
            'law_name': l.get('law_name', ''),
            'article_path': l.get('article_path', ''),
            'similarity': l.get('similarity', 0.0)
        })

    # Criteria
    for cr in results.get('criteria', []):
        converted['criteria'].append({
            'doc_id': cr.get('unit_id', cr.get('chunk_id', '')),
            'source_label': cr.get('source_label', ''),
            'item': cr.get('item', ''),
            'similarity': cr.get('similarity', 0.0)
        })

    return converted


def print_progress(current: int, total: int, item_id: str, verbose: bool = False):
    """진행 상황 출력"""
    pct = (current / total) * 100
    if verbose:
        print(f"  [{current}/{total}] ({pct:.1f}%) Evaluating: {item_id}")
    else:
        # Simple progress bar
        bar_len = 30
        filled = int(bar_len * current / total)
        bar = '=' * filled + '-' * (bar_len - filled)
        print(f"\r[{bar}] {pct:.1f}%", end='', flush=True)


def print_summary(summary: Dict, elapsed_sec: float):
    """결과 요약 출력"""
    print("\n" + "=" * 50)
    print("=== RAG Evaluation Results ===")
    print("=" * 50)

    print(f"\nDataset: {summary.get('sample_count', 0)} samples")
    print(f"Time: {elapsed_sec:.1f}s")

    print(f"\n{'Section':<15} {'Metric':<18} {'Score':>8}")
    print("-" * 45)

    # Domain
    if 'domain_accuracy_mean' in summary:
        print(f"{'Domain':<15} {'Accuracy':<18} {summary['domain_accuracy_mean']:>8.3f}")

    # Cases
    for metric in ['ndcg', 'mrr', 'precision@k', 'recall']:
        key = f'cases_{metric}_mean'
        if key in summary:
            print(f"{'Cases':<15} {metric:<18} {summary[key]:>8.3f}")

    # Laws
    for metric in ['ndcg', 'mrr', 'precision@k', 'recall']:
        key = f'laws_{metric}_mean'
        if key in summary:
            print(f"{'Laws':<15} {metric:<18} {summary[key]:>8.3f}")

    # Criteria
    for metric in ['ndcg', 'mrr', 'precision@k', 'recall']:
        key = f'criteria_{metric}_mean'
        if key in summary:
            print(f"{'Criteria':<15} {metric:<18} {summary[key]:>8.3f}")

    print("-" * 45)

    # Overall
    if 'overall_ndcg_mean' in summary:
        print(f"{'Overall':<15} {'nDCG':<18} {summary['overall_ndcg_mean']:>8.3f}")
    if 'overall_mrr_mean' in summary:
        print(f"{'Overall':<15} {'MRR':<18} {summary['overall_mrr_mean']:>8.3f}")
    if 'overall_hit_rate_mean' in summary:
        print(f"{'Overall':<15} {'Hit Rate':<18} {summary['overall_hit_rate_mean']:>8.3f}")

    print("=" * 50)


def save_json(output_path: str, summary: Dict, detailed_results: List[Dict]):
    """JSON 형식으로 저장"""
    output_data = {
        'summary': summary,
        'detailed_results': detailed_results
    }

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\nResults saved to: {output_path}")


def save_csv(output_path: str, detailed_results: List[Dict]):
    """CSV 형식으로 저장"""
    if not detailed_results:
        print("No results to save")
        return

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)

    # 모든 키 수집
    all_keys = set()
    for r in detailed_results:
        all_keys.update(r.keys())

    # 정렬된 키 리스트
    sorted_keys = ['id', 'question', 'category', 'domain_accuracy',
                   'predicted_agency', 'expected_agency']
    for key in sorted(all_keys):
        if key not in sorted_keys:
            sorted_keys.append(key)

    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=sorted_keys, extrasaction='ignore')
        writer.writeheader()
        for r in detailed_results:
            writer.writerow(r)

    print(f"\nResults saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description='RAG 정량 평가 실행')
    parser.add_argument('--dataset', required=True, help='평가 데이터셋 경로 (JSONL)')
    parser.add_argument('--output', default='results/evaluation_result.json',
                        help='결과 저장 경로')
    parser.add_argument('--format', choices=['json', 'csv'], default='json',
                        help='출력 형식')
    parser.add_argument('--sections', default='all',
                        help='평가할 섹션 (comma-separated: domain,cases,laws,criteria)')
    parser.add_argument('--top-k', type=int, default=3, help='검색 결과 수 (K)')
    parser.add_argument('--verbose', action='store_true', help='상세 로그 출력')
    parser.add_argument('--dry-run', action='store_true',
                        help='검색 없이 데이터셋만 검증')

    args = parser.parse_args()

    # 1. 데이터셋 로드
    print(f"Loading dataset: {args.dataset}")
    try:
        dataset = load_dataset(args.dataset)
    except FileNotFoundError:
        print(f"Error: Dataset not found: {args.dataset}")
        sys.exit(1)

    print(f"Loaded {len(dataset)} evaluation items")

    if args.dry_run:
        print("\n[Dry run] Dataset validation:")
        for item in dataset[:5]:
            print(f"  - {item['id']}: {item['question'][:50]}...")
        print(f"  ... and {len(dataset) - 5} more")
        return

    # 2. Retriever 초기화
    print("\nInitializing StructuredRetriever...")
    db_config = get_db_config()
    embed_api_url = get_embedding_api_url()

    retriever = StructuredRetriever(db_config, embed_api_url)
    retriever.connect()

    # 3. 평가기 초기화
    metrics = RetrievalMetrics(k=args.top_k)

    # 4. 평가 실행
    print(f"\nRunning evaluation (top_k={args.top_k})...")
    start_time = time.time()

    evaluation_results = []
    detailed_results = []

    for i, item in enumerate(dataset):
        print_progress(i + 1, len(dataset), item['id'], args.verbose)

        try:
            # 검색 실행
            search_output = run_retrieval(item['question'], retriever, args.top_k)
            results = search_output['results']
            elapsed_ms = search_output['elapsed_ms']

            # 검색 결과 변환
            converted = convert_search_results(results)

            # 예측 기관
            predicted_agency = results.get('agency', {}).get('agency', 'KCA')

            # 평가 실행
            eval_result = metrics.evaluate_item(
                item_id=item['id'],
                question=item['question'],
                category=item.get('category', 'unknown'),
                retrieved_results=converted,
                expected_contexts=item.get('expected_contexts', []),
                expected_agency=item.get('expected_agency', 'KCA'),
                predicted_agency=predicted_agency,
                retrieval_time_ms=elapsed_ms
            )

            evaluation_results.append(eval_result)
            detailed_results.append(eval_result.to_dict())

            if args.verbose:
                print(f"    -> Domain: {eval_result.domain_accuracy}, "
                      f"Overall MRR: {eval_result.overall_mrr:.3f}")

        except Exception as e:
            print(f"\n  Error evaluating {item['id']}: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()

    if not args.verbose:
        print()  # newline after progress bar

    # 5. 정리
    retriever.close()
    total_time = time.time() - start_time

    # 6. 결과 집계
    summary = aggregate_results(evaluation_results)
    summary.update({
        'run_id': f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        'timestamp': datetime.now().isoformat(),
        'dataset': args.dataset,
        'sample_count': len(dataset),
        'total_time_seconds': round(total_time, 2),
        'top_k': args.top_k
    })

    # 7. 결과 출력
    print_summary(summary, total_time)

    # 8. 결과 저장
    if args.format == 'json':
        save_json(args.output, summary, detailed_results)
    else:
        save_csv(args.output, detailed_results)


if __name__ == "__main__":
    main()
