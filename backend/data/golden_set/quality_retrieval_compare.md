# M5-4 Quality Retrieval A/B (canonical eval set: quality_eval_v1.jsonl)

- eval set: `backend/data/golden_set/quality_eval_v1.jsonl` (12 queries, human-graded `relevant[]`)
- A: variant A CORE retriever (`search_hybrid_rrf`), reproduced on the canonical file (matches M2-4R v2).
- B: M2-7R committed numbers (identical `relevant[]`); exaone needs pod, frontier = OpenAI.

| metric | A (MAS core) | B-exaone | B-frontier |
| --- | --- | --- | --- |
| ndcg@5 | 0.8101 | 0.4953 | 0.7063 |
| hit_rate@5 | 1.0000 | 0.8333 | 0.9167 |
| ndcg@10 | 0.8796 | 0.5507 | 0.7063 |
| hit_rate@10 | 1.0000 | 0.9167 | 0.9167 |
| mrr | 0.9583 | 0.5625 | 0.6528 |
| mean_latency_ms | - | 30776.1 | 7547.8 |

> Headline = nDCG (graded). hit_rate saturates (A=1.0) on the 12-query seed → sanity only.
