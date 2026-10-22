# Reproduction report (`make reproduce`)

- Catalog: 61346 products; total wall time 135 s
- Machine: Intel64 Family 6 Model 158 Stepping 10, GenuineIntel, 4 cores / 8 threads, 15.8 GB RAM, GPU: none (CPU only)
- Model size: 58.1 MB

## Held-out categories (SILVER: labels are the rules)

- 292 categories never seen in training, 6278 products: micro-F1 **0.852**, macro-F1 0.828, sample-F1 0.897, Hamming loss 0.0083
- Name has no keyword of the work (3970 pairs): F1 0.870

## Timings and resources

| step | seconds | items | s per 1k items | peak RAM, MB |
|---|---|---|---|---|
| load | 14.5 | 61346 | 0.24 | 486 |
| rules | 2.5 | 61346 | 0.04 | 489 |
| train_holdout | 44.1 | 32425 | 1.36 | 695 |
| predict_holdout | 1.1 | 6278 | 0.17 | 563 |
| train_full | 46.7 | 38703 | 1.21 | 723 |
| match_5000 | 1.1 | 5000 | 0.22 | 663 |

## Human gold set

- `eval/gold/worktype_gold.csv` not found: the REAL micro-F1 is **not measured**. Label the sheets (docs/EVAL_METHODOLOGY.md), run scripts/merge_worktype_gold.py.
