#!/usr/bin/env python
"""
Retrieval Evaluation Script
Sprint 3 - s3-6: nDCG@K, Hit Rate@K measurement

Measures retrieval quality using golden set with doc_type-based relevance.

Usage:
    conda run -n dsr python scripts/evaluation/evaluate_retrieval.py --top-k 5 10
"""

import os
import json
import argparse
import math
from typing import List, Dict, Any, Optional
from pathlib import Path
from dataclasses import dataclass

GOLDEN_SET_PATH = Path(__file__).parent.parent.parent / 'data' / 'golden_set' / 'retrieval.jsonl'


@dataclass
class EvalSample:
    id: str
    query: str
    expected_doc_types: List[str]
    expected_agency: str
    category: str


def load_golden_set(path: Path = GOLDEN_SET_PATH) -> List[EvalSample]:
    samples = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            data = json.loads(line.strip())
            doc_types = [ctx['doc_type'] for ctx in data.get('expected_contexts', [])]
            samples.append(EvalSample(
                id=data['id'],
                query=data['query'],
                expected_doc_types=doc_types,
                expected_agency=data.get('expected_agency', 'KCA'),
                category=data.get('category', '')
            ))
    return samples


def dcg_at_k(relevances: List[float], k: int) -> float:
    relevances = relevances[:k]
    dcg = 0.0
    for i, rel in enumerate(relevances):
        dcg += rel / math.log2(i + 2)
    return dcg


def ndcg_at_k(relevances: List[float], k: int) -> float:
    dcg = dcg_at_k(relevances, k)
    ideal = sorted(relevances, reverse=True)
    idcg = dcg_at_k(ideal, k)
    return dcg / idcg if idcg > 0 else 0.0


def hit_rate_at_k(results: List[Dict], expected_doc_types: List[str], k: int) -> float:
    for r in results[:k]:
        doc_type = r.get('doc_type', '')
        doc_type_mapped = map_doc_type(doc_type)
        if doc_type_mapped in expected_doc_types:
            return 1.0
    return 0.0


def map_doc_type(doc_type: str) -> str:
    if doc_type == 'mediation_case':
        return 'dispute'
    elif doc_type == 'counsel_case':
        return 'counsel'
    elif doc_type.startswith('criteria'):
        return 'criteria'
    elif doc_type == 'law':
        return 'law'
    return doc_type


def compute_relevances(results: List[Dict], expected_doc_types: List[str]) -> List[float]:
    relevances = []
    for r in results:
        doc_type = map_doc_type(r.get('doc_type', ''))
        if doc_type in expected_doc_types:
            relevances.append(1.0)
        else:
            relevances.append(0.0)
    return relevances


def run_evaluation(retriever, samples: List[EvalSample], k_values: List[int]) -> Dict[str, Any]:
    results = {f'ndcg@{k}': [] for k in k_values}
    results.update({f'hit_rate@{k}': [] for k in k_values})
    
    max_k = max(k_values)
    
    for sample in samples:
        try:
            search_results = retriever.search_all_sections(
                query=sample.query,
                dispute_k=max_k,
                counsel_k=max_k,
                law_k=max_k,
                criteria_k=max_k
            )
            
            all_results = []
            for section in ['disputes', 'counsels', 'laws', 'criteria']:
                items = search_results.get(section, [])
                for item in items:
                    if isinstance(item, dict):
                        if section == 'disputes':
                            item['doc_type'] = 'mediation_case'
                        elif section == 'counsels':
                            item['doc_type'] = 'counsel_case'
                        elif section == 'laws':
                            item['doc_type'] = 'law'
                        elif section == 'criteria':
                            item['doc_type'] = 'criteria'
                        all_results.append(item)
            
            all_results.sort(key=lambda x: x.get('similarity', 0), reverse=True)
            
            relevances = compute_relevances(all_results, sample.expected_doc_types)
            
            for k in k_values:
                results[f'ndcg@{k}'].append(ndcg_at_k(relevances, k))
                results[f'hit_rate@{k}'].append(hit_rate_at_k(all_results, sample.expected_doc_types, k))
                
        except Exception as e:
            print(f"Error processing {sample.id}: {e}")
            for k in k_values:
                results[f'ndcg@{k}'].append(0.0)
                results[f'hit_rate@{k}'].append(0.0)
    
    summary = {}
    for metric, values in results.items():
        if values:
            summary[metric] = sum(values) / len(values)
    
    return {
        'summary': summary,
        'sample_count': len(samples),
        'k_values': k_values
    }


def print_report(eval_results: Dict[str, Any]):
    print("\n" + "=" * 60)
    print("Retrieval Evaluation Report")
    print("=" * 60)
    print(f"Samples evaluated: {eval_results['sample_count']}")
    print(f"K values: {eval_results['k_values']}")
    print("-" * 60)
    
    summary = eval_results['summary']
    for metric, value in sorted(summary.items()):
        status = "✓" if value >= 0.65 else "✗"
        print(f"  {metric}: {value:.4f} {status}")
    
    print("-" * 60)
    ndcg5 = summary.get('ndcg@5', 0)
    hit10 = summary.get('hit_rate@10', 0)
    print(f"Sprint 3 DoD: nDCG@5 >= 0.65: {'PASS' if ndcg5 >= 0.65 else 'FAIL'}")
    print(f"             Hit Rate@10 >= 0.85: {'PASS' if hit10 >= 0.85 else 'FAIL'}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='Evaluate retrieval quality')
    parser.add_argument('--top-k', nargs='+', type=int, default=[5, 10], help='K values for metrics')
    parser.add_argument('--golden-set', type=str, default=str(GOLDEN_SET_PATH), help='Path to golden set')
    parser.add_argument('--dry-run', action='store_true', help='Load data only, no DB connection')
    args = parser.parse_args()
    
    print(f"Loading golden set from {args.golden_set}")
    samples = load_golden_set(Path(args.golden_set))
    print(f"Loaded {len(samples)} samples")
    
    if args.dry_run:
        print("\n[Dry run] Sample queries:")
        for s in samples[:5]:
            print(f"  - {s.id}: {s.query[:50]}... -> {s.expected_doc_types}")
        return
    
    from dotenv import load_dotenv
    load_dotenv()
    
    db_config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': os.getenv('DB_PORT', '5432'),
        'database': os.getenv('DB_NAME', 'ddoksori'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', 'postgres')
    }
    embed_api_url = os.getenv('EMBED_API_URL', 'http://localhost:8001/embed')
    
    from app.agents.retrieval.tools.specialized_retrievers import StructuredRetriever
    
    print("Connecting to database...")
    retriever = StructuredRetriever(db_config, embed_api_url)
    retriever.connect()
    
    try:
        print(f"Running evaluation with k={args.top_k}")
        results = run_evaluation(retriever, samples, args.top_k)
        print_report(results)
        
        output_path = Path(args.golden_set).parent / 'retrieval_eval_results.json'
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to {output_path}")
        
    finally:
        retriever.close()


if __name__ == '__main__':
    main()
