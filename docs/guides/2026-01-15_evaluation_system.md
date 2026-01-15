# S2-5: Agent Evaluation System

**Date**: 2026-01-15  
**Status**: Completed  
**Sprint**: S2 (MAS Extension)

## Overview

This document describes the evaluation system implemented for the 똑소리 Multi-Agent System (MAS). The system provides CLI-based evaluation tools for measuring agent performance against predefined golden sets.

## Quick Start

```bash
# Activate conda environment
conda activate dsr
cd backend

# Run Query Analysis evaluation
python -m scripts.evaluation.evaluate_query_analysis \
  --golden-set ./data/golden_set/query_analysis.jsonl \
  --output ./results/qa_eval.json

# Run Review evaluation
python -m scripts.evaluation.evaluate_review \
  --golden-set ./data/golden_set/review.jsonl \
  --output ./results/review_eval.json

# Run Retrieval evaluation (requires DB connection)
python -m scripts.evaluation.run_evaluation \
  --dataset ./data/golden_set/retrieval.jsonl \
  --output ./results/retrieval_eval.json

# Generate combined report
python -m scripts.evaluation.generate_report \
  --results-dir ./results \
  --output ./reports/eval_report.csv \
  --format both
```

## Golden Sets

Golden sets are stored in `backend/data/golden_set/`:

| File | Samples | Description |
|------|---------|-------------|
| `query_analysis.jsonl` | 110 | Query type classification, keyword extraction, agency hints |
| `retrieval.jsonl` | 60 | Expected document contexts, agency classification |
| `review.jsonl` | 110 | Violation patterns (absolute expressions, legal assertions) |

### Golden Set Formats

#### Query Analysis (`query_analysis.jsonl`)
```json
{
  "id": "qa_001",
  "query": "소비자보호법 제17조 환불 규정",
  "expected_query_type": "law",
  "expected_keywords": ["소비자보호법", "17조", "환불"],
  "expected_agency_hint": "KCA",
  "expected_missing_fields": [],
  "category": "법령조회"
}
```

#### Retrieval (`retrieval.jsonl`)
```json
{
  "id": "ret_001",
  "query": "에어컨 환불 요청",
  "expected_contexts": [
    {"doc_type": "dispute", "doc_id": "KCA-001", "relevance": "essential"},
    {"doc_type": "law", "doc_id": "consumer-law-7", "relevance": "supporting"}
  ],
  "expected_agency": "KCA",
  "category": "가전제품_하자"
}
```

#### Review (`review.jsonl`)
```json
{
  "id": "rev_001",
  "answer_text": "반드시 환불받으실 수 있습니다.",
  "expected_violations": [
    {"pattern": "반드시", "type": "absolute_expression"}
  ],
  "is_violation": true
}
```

## Evaluation Metrics

### Query Analysis Agent

| Metric | Description | Target |
|--------|-------------|--------|
| Query Type Accuracy | Classification accuracy (dispute/general/law/criteria) | ≥0.90 |
| Keyword Precision | Extracted keywords precision | ≥0.80 |
| Keyword Recall | Extracted keywords recall | ≥0.70 |
| Agency Hint Accuracy | Recommended agency accuracy | ≥0.85 |
| Missing Field Detection F1 | Required field detection F1 | ≥0.85 |

### Information Retrieval Agent

| Metric | Description | Target |
|--------|-------------|--------|
| nDCG@K | Normalized Discounted Cumulative Gain | ≥0.65 |
| MRR | Mean Reciprocal Rank | ≥0.60 |
| Hit Rate@K | Relevant document found in top-K | ≥0.85 |
| Domain Accuracy | Agency classification accuracy | ≥0.85 |

### Legal Review Agent

| Metric | Description | Target |
|--------|-------------|--------|
| Violation Detection Precision | Prohibition pattern detection precision | ≥0.85 |
| Violation Detection Recall | Prohibition pattern detection recall | ≥0.90 |
| False Positive Rate | Clean text incorrectly flagged | ≤0.10 |
| Binary Accuracy | Overall violation/clean classification | ≥0.85 |

## Evaluation Results (2026-01-15)

### Query Analysis
- Query Type Accuracy: **95.45%** (Target: 90%) ✅
- Keyword Precision: 40.86% (Target: 80%) ❌
- Keyword Recall: 59.82% (Target: 70%) ❌
- Agency Hint Accuracy: 70.00% (Target: 85%) ❌

### Retrieval
- nDCG@5: **67.9%** (Target: 65%) ✅
- MRR: **75.0%** (Target: 60%) ✅
- Hit Rate: **100%** (Target: 85%) ✅
- Domain Accuracy: **100%** (Target: 85%) ✅

### Review
- Precision: **96.67%** (Target: 85%) ✅
- Recall: **98.31%** (Target: 90%) ✅
- False Positive Rate: **3.33%** (Target: ≤10%) ✅
- Binary Accuracy: **100%** ✅

## File Structure

```
backend/
├── data/
│   └── golden_set/
│       ├── query_analysis.jsonl   # 110 samples
│       ├── retrieval.jsonl        # 60 samples
│       └── review.jsonl           # 110 samples
│
├── rag/
│   └── evaluation/
│       ├── __init__.py
│       ├── retrieval_metrics.py
│       ├── query_analysis_metrics.py
│       └── review_metrics.py
│
├── scripts/
│   └── evaluation/
│       ├── run_evaluation.py           # Retrieval evaluation
│       ├── evaluate_query_analysis.py  # Query analysis evaluation
│       ├── evaluate_review.py          # Review agent evaluation
│       └── generate_report.py          # Report generator
│
├── results/                             # Evaluation results (JSON)
└── reports/                             # Generated reports (CSV/JSON)
```

## Adding New Golden Set Samples

1. Edit the corresponding `.jsonl` file in `backend/data/golden_set/`
2. Follow the format specified above
3. Run evaluation to verify samples are valid

## Notes

- Retrieval evaluation requires database connection and embedding service
- Query Analysis and Review evaluations run locally without external dependencies
- Generation evaluation is deferred (requires LLM API calls, cost considerations)
