# A/B Retrieval Baseline — variant A

- timestamp: 20260623_145010
- eval set: `backend/data/golden_set/ab_retrieval_eval.jsonl` (12 queries)
- retriever: search_hybrid_rrf (core, no expansion, no filters), rrf_k=10, embed=text-embedding-3-large

## Summary (mean)

| metric | value |
| --- | --- |
| ndcg@5 | 0.7244 |
| hit_rate@5 | 1.0000 |
| ndcg@10 | 0.8693 |
| hit_rate@10 | 1.0000 |
| mrr | 1.0000 |

## Per-domain (mean nDCG@10 / HitRate@10)

| domain | n | nDCG@10 | HitRate@10 |
| --- | --- | --- | --- |
| case | 4 | 0.8568 | 1.0000 |
| criteria | 4 | 0.8413 | 1.0000 |
| law | 4 | 0.9099 | 1.0000 |
