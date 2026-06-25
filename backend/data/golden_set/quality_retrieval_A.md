# A/B Retrieval Baseline — variant A

- timestamp: 20260625_143930
- eval set: `backend/data/golden_set/quality_eval_v1.jsonl` (12 queries)
- retriever: search_hybrid_rrf (core, no expansion, no filters), rrf_k=10, embed=text-embedding-3-large

## Summary (mean)

| metric | value |
| --- | --- |
| ndcg@5 | 0.8101 |
| hit_rate@5 | 1.0000 |
| ndcg@10 | 0.8796 |
| hit_rate@10 | 1.0000 |
| mrr | 0.9583 |

## Per-domain (mean nDCG@10 / HitRate@10)

| domain | n | nDCG@10 | HitRate@10 |
| --- | --- | --- | --- |
| case | 4 | 0.9265 | 1.0000 |
| criteria | 4 | 0.8507 | 1.0000 |
| law | 4 | 0.8614 | 1.0000 |
