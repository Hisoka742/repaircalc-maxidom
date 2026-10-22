## Work types on a PILOT set (single labeller = LLM, NOT human; development use only)

- Test split n=78 (never used for tuning); dev n=132; ambiguous rows n=100

| system | micro-F1 | macro-F1 | samples-F1 | Hamming loss | exact match | dev micro-F1 |
|---|---|---|---|---|---|---|
| категория (baseline) | 0.512 | 0.587 | 0.774 | 0.0322 | 0.603 | 0.570 |
| правила | 0.907 | 0.959 | 0.966 | 0.0047 | 0.897 | 0.854 |
| модель | 0.864 | 0.921 | 0.948 | 0.0072 | 0.846 | 0.848 |
| правила + модель | 0.907 | 0.959 | 0.966 | 0.0047 | 0.897 | 0.850 |

- Target micro-F1 >= 0.8 (aim 0.9): **reached** (0.907)

- Ambiguous subset (n=100): micro-F1 0.873, macro-F1 0.862, exact match 0.800
- Same ambiguous rows, CATEGORY BASELINE: micro-F1 0.543, macro-F1 0.553, exact match 0.230; product-level matcher gains +0.331 micro-F1 ("semantic, not literal" proof)
- Non-repair negatives that wrongly received a work type: категория (baseline) 1.8%, правила 1.8%, модель 2.7%, правила + модель 2.7%
- Semantic, not literal (name has no keyword of the work; 56 pairs): P 0.847, R 0.893, F1 0.870
- Ranking per work type (k=10, 12 works with >=3 positives): MAP@10 0.933, nDCG@10 0.962

### Per work type, rules + model, test split (n=78)

- micro-F1 **0.907** (P 0.890, R 0.924); macro-F1 0.959; sample-based F1 0.966; Hamming loss 0.0047; exact match 0.897

| work type | P | R | F1 | support |
|---|---|---|---|---|
| general_assembly | 0.87 | 0.93 | 0.90 | 14 |
| tile_laying | 1.00 | 0.86 | 0.92 | 7 |
| wall_panels | 1.00 | 0.60 | 0.75 | 5 |
| sealing | 1.00 | 1.00 | 1.00 | 5 |
| priming | 1.00 | 1.00 | 1.00 | 4 |
| drywall_install | 1.00 | 1.00 | 1.00 | 4 |
| wall_painting | 1.00 | 0.75 | 0.86 | 4 |
| plastering | 1.00 | 1.00 | 1.00 | 3 |
| insulation | 1.00 | 1.00 | 1.00 | 3 |
| puttying | 1.00 | 1.00 | 1.00 | 3 |
| wallpapering | 1.00 | 1.00 | 1.00 | 3 |
| ceiling_painting | 1.00 | 1.00 | 1.00 | 3 |
| demolition | 0.67 | 1.00 | 0.80 | 2 |
| laminate_laying | 1.00 | 1.00 | 1.00 | 2 |
| linoleum_laying | 1.00 | 1.00 | 1.00 | 2 |
| skirting_install | 1.00 | 1.00 | 1.00 | 2 |
| wood_metal_coating | 1.00 | 0.50 | 0.67 | 2 |
| plumbing_fixtures | 1.00 | 1.00 | 1.00 | 2 |
| antiseptic | 1.00 | 1.00 | 1.00 | 1 |
| masonry | 1.00 | 1.00 | 1.00 | 1 |
| decorative_coating | 1.00 | 1.00 | 1.00 | 1 |
| ceiling_install | 1.00 | 1.00 | 1.00 | 1 |
| sockets_switches | 1.00 | 1.00 | 1.00 | 1 |
| pipe_laying | 1.00 | 1.00 | 1.00 | 1 |
| faucet_install | 1.00 | 1.00 | 1.00 | 1 |
| door_install | 1.00 | 1.00 | 1.00 | 1 |
| window_install | 1.00 | 1.00 | 1.00 | 1 |
| screed | 0.00 | 0.00 | 0.00 | 0 |
| self_leveling | 0.00 | 0.00 | 0.00 | 0 |
| waterproofing | 0.00 | 0.00 | 0.00 | 0 |
