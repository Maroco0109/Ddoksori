# M5-5 Answer Generation Quality (A/B)

- columns: A, Bexaone, Bfrontier

| metric | A | Bexaone | Bfrontier |
| --- | --- | --- | --- |
| n | 12 | 12 | 12 |
| n_scored | 10 | 9 | 12 |
| faithfulness_mean | 2.0000 | 1.8889 | 1.9167 |
| coverage_ratio_mean | 0.5750 | 0.7574 | 0.5514 |
| safety_pass_rate | 1.0000 | 0.7778 | 0.8333 |
| error_rate | 0.1667 | 0.2500 | 0.0000 |
| clarification_rate | 0.0000 | 0.0000 | 0.0000 |
| block_rate | 0.0000 | 0.0000 | 0.0000 |

> faithfulness/coverage: substantive answers only (clarified/blocked excluded). faithfulness is graded against retrieved contexts, so read it together with the M5-4 retrieval nDCG. Small set (12) — see per-query rows; judge reliability is validated in M5-6.
