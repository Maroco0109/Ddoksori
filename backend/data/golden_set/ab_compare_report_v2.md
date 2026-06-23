# M2-7R A/B Comparison (retrieval)

- eval set: `ab_retrieval_eval_v2.jsonl` | columns: A (MAS core retriever), B-frontier

| metric | A (MAS core retriever) | B-frontier |
| --- | --- | --- |
| ndcg@5 | 0.8101 | 0.7063 |
| hit_rate@5 | 1.0000 | 0.9167 |
| ndcg@10 | 0.8796 | 0.7063 |
| hit_rate@10 | 1.0000 | 0.9167 |
| mrr | 0.9583 | 0.6528 |
| clarification_rate | - | 0.0000 |
| block_rate | - | 0.0000 |
| mean_latency_ms | - | 7547.7941 |

> nDCG is the headline. clarified/blocked queries are excluded from retrieval metrics (see clarification_rate/block_rate).
