# Data Collection Guide - Training Data for Fine-Tuning

This guide explains how to collect and prepare training data from RAG logs for fine-tuning a small LLM (EXAONE 2.4B) to replace the current Rule/LLM-based Query Analysis agent.

## Overview

The data collection pipeline extracts query analysis examples from production RAG logs and generates JSONL datasets suitable for supervised fine-tuning. This is part of PR#3 implementation for the long-term fine-tuning strategy.

## Purpose

- **Goal**: Build a dataset to fine-tune EXAONE 2.4B for query analysis tasks
- **Tasks**: Query type classification, keyword extraction, query rewriting
- **Source**: `backend/logs/rag/` JSON logs containing `node_timings` snapshots

## Prerequisites

- Conda environment `dsr` activated
- RAG logs available in `backend/logs/rag/`
- Python 3.10+

## Quick Start

### Basic Usage

```bash
# Activate conda environment
conda activate dsr

# Run data collection script (using default paths)
python backend/scripts/data/collect_training_data.py

# Output will be saved to: backend/data/training/training_data.jsonl
```

### Custom Paths

```bash
# Specify custom log directory and output directory
python backend/scripts/data/collect_training_data.py \
  --log-dir /path/to/logs \
  --output-dir /path/to/output
```

### Help

```bash
python backend/scripts/data/collect_training_data.py --help
```

## Dataset Format

The script generates a JSONL (JSON Lines) file where each line represents one training example:

```json
{
  "instruction": "Classify the user query into 'dispute', 'general', 'law', 'system'.",
  "input": "환불이 안 된다는데 법적으로 어떻게 되나요?",
  "output": "law"
}
```

### Training Tasks

The dataset includes three types of examples:

#### 1. Query Type Classification

```json
{
  "instruction": "Classify the user query into 'dispute', 'general', 'law', 'system'.",
  "input": "환불 요청 어떻게 하나요?",
  "output": "general"
}
```

#### 2. Keyword Extraction

```json
{
  "instruction": "Extract relevant keywords from the user query.",
  "input": "전자상거래 환불 규정이 궁금합니다",
  "output": "[\"전자상거래\", \"환불\", \"규정\"]"
}
```

#### 3. Query Rewriting

```json
{
  "instruction": "Rewrite the user query for better search.",
  "input": "환불 안 해줘요",
  "output": "환불 거부 분쟁 해결 방법"
}
```

## PII Handling

The script automatically masks personally identifiable information (PII) to protect user privacy:

### Masked Patterns

| Type | Pattern | Replacement |
|------|---------|-------------|
| Korean Phone | `01[0-9]-[0-9]{3,4}-[0-9]{4}` | `[PHONE]` |
| Email | `name@domain.com` | `[EMAIL]` |
| Korean Address (동) | `서울시 강남구 역삼동` | `[ADDRESS]` |
| Korean Address (로) | `서울시 강남구 테헤란로 123` | `[ADDRESS]` |
| Korean Address (길) | `서울시 강남구 논현길 456` | `[ADDRESS]` |

### Example

**Before masking**:
```
010-1234-5678로 연락 주세요. test@example.com으로 이메일 보내거나 서울시 강남구 역삼동으로 방문하세요.
```

**After masking**:
```
[PHONE]로 연락 주세요. [EMAIL]으로 이메일 보내거나 [ADDRESS]으로 방문하세요.
```

## Quality Filtering

The script applies multiple quality filters to ensure high-quality training data:

### Filters Applied

1. **Snapshot Validity**
   - Rejects truncated snapshots (string instead of dict)
   - Rejects oversized snapshots (> 2KB)

2. **Query Validity**
   - Minimum query length: 3 characters
   - Rejects empty or whitespace-only queries

3. **Query Type Validity**
   - Only accepts: `dispute`, `general`, `law`, `system`
   - Rejects invalid or missing query types

4. **Data Completeness**
   - Requires valid `query_analysis_v2` structure
   - Requires valid `input_snapshot` and `output_snapshot`

### Statistics Tracking

The script provides detailed statistics after completion:

```
Data collection complete!
Total log files found: 150
Successfully parsed: 145
Skipped (no query_analysis): 5
Generated training examples: 387
Output saved to: backend/data/training/training_data.jsonl
```

## Log Structure Requirements

The script expects RAG logs with the following structure:

```json
{
  "node_timings": {
    "query_analysis": {
      "input_snapshot": {
        "user_query": "사용자 질문"
      },
      "output_snapshot": {
        "query_analysis_v2": {
          "query_type": "dispute|general|law|system",
          "keywords": ["키워드1", "키워드2"],
          "rewritten_query": "재작성된 질문",
          "search_queries": ["검색 쿼리"]
        }
      }
    }
  }
}
```

## Best Practices

### 1. Regular Collection

Run the script weekly to continuously expand the training dataset:

```bash
# Add to cron or schedule
0 0 * * 0 conda run -n dsr python backend/scripts/data/collect_training_data.py
```

### 2. Data Inspection

Always inspect the generated JSONL file before using for training:

```bash
# View first 5 examples
head -n 5 backend/data/training/training_data.jsonl | jq '.'

# Check statistics
wc -l backend/data/training/training_data.jsonl

# Verify no PII leaked
grep -E "01[0-9]-[0-9]{3,4}-[0-9]{4}" backend/data/training/training_data.jsonl
grep -E "[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+" backend/data/training/training_data.jsonl
```

### 3. Version Control

Track dataset versions with timestamps:

```bash
# Add timestamp to output filename
OUTPUT_FILE="training_data_$(date +%Y%m%d_%H%M%S).jsonl"
python backend/scripts/data/collect_training_data.py \
  --output-dir backend/data/training/$OUTPUT_FILE
```

### 4. Quality Validation

Before using the dataset for fine-tuning:

1. Manually review 50-100 random samples
2. Check PII masking effectiveness
3. Verify query type distribution
4. Confirm output format consistency

## Troubleshooting

### No logs found

**Problem**: `Total log files found: 0`

**Solution**:
```bash
# Check if logs directory exists
ls -la backend/logs/rag/

# Verify JSON files exist
find backend/logs/rag/ -name "*.json" | head -5
```

### Low parsing success rate

**Problem**: `Successfully parsed: 10 / Total files: 100`

**Solution**:
1. Check log file format consistency
2. Verify `node_timings.query_analysis` exists in logs
3. Review error messages in stderr

### No examples generated

**Problem**: `Generated training examples: 0`

**Solution**:
1. Check if `query_analysis_v2` structure exists in logs
2. Verify query types are valid
3. Ensure queries are not too short (< 3 chars)

## Security and Privacy

### CRITICAL: Data Handling Policy

1. **Never commit training data to git**
   - Add `backend/data/training/*.jsonl` to `.gitignore`

2. **PII Audit**
   - Always run PII detection before sharing data
   - Use automated PII detection tools for validation

3. **Access Control**
   - Restrict access to training data directory
   - Use encrypted storage for production data

4. **Data Retention**
   - Define clear retention policy (e.g., 90 days)
   - Implement automatic cleanup for old datasets

## Next Steps

After collecting training data:

1. **Phase 2**: Quality Filtering
   - Implement indirect quality metrics
   - Add user feedback integration (when available)

2. **Phase 3**: Fine-Tuning
   - Train EXAONE 2.4B on collected dataset
   - Evaluate performance vs current implementation

3. **Phase 4**: Deployment
   - A/B test fine-tuned model
   - Monitor accuracy and performance

## References

- **Implementation Plan**: `docs/plans/260122/03_LongTerm_FineTuning_Strategy.md`
- **RAG Logger**: `backend/app/common/logger.py`
- **Graph Orchestrator**: `backend/app/orchestrator/graph.py`

## Support

For questions or issues:
1. Check this guide first
2. Review test cases in `backend/scripts/testing/data/test_collect_training_data.py`
3. Contact the AI/MAS team
