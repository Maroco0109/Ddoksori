# M2-7R A/B Comparison (retrieval)

- eval set: `ab_retrieval_eval.jsonl` | columns: A (MAS core retriever), B-frontier

| metric | A (MAS core retriever) | B-frontier |
| --- | --- | --- |
| ndcg@5 | 0.7244 | 0.2527 |
| hit_rate@5 | 1.0000 | 0.3333 |
| ndcg@10 | 0.8693 | 0.2527 |
| hit_rate@10 | 1.0000 | 0.3333 |
| mrr | 1.0000 | 0.2083 |
| clarification_rate | - | 0.0000 |
| block_rate | - | 0.0000 |
| mean_latency_ms | - | 8583.7620 |

> A HitRate/MRR are pooling-inflated (labels drawn from A top-15); B columns become discriminative. nDCG is the headline. clarified/blocked queries excluded from retrieval metrics (see clarification_rate/block_rate).
