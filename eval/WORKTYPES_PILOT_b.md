## Work types on a PILOT set (single labeller = LLM, NOT human; development use only)

- Test split n=58 (never used for tuning); dev n=75; ambiguous rows n=93

| system | micro-F1 | macro-F1 | samples-F1 | Hamming loss | exact match | dev micro-F1 |
|---|---|---|---|---|---|---|
| категория (baseline) | 0.525 | 0.491 | 0.662 | 0.0433 | 0.448 | 0.583 |
| правила | 0.886 | 0.838 | 0.932 | 0.0080 | 0.879 | 0.871 |
| модель | 0.831 | 0.775 | 0.884 | 0.0126 | 0.776 | 0.871 |
| правила + модель | 0.871 | 0.809 | 0.915 | 0.0093 | 0.862 | 0.871 |

- Target micro-F1 >= 0.8 (aim 0.9): **reached** (0.871)

- Ambiguous subset (n=93): micro-F1 0.877, macro-F1 0.846, exact match 0.806
- Same ambiguous rows, CATEGORY BASELINE: micro-F1 0.565, macro-F1 0.532, exact match 0.258; product-level matcher gains +0.312 micro-F1 ("semantic, not literal" proof)
- Non-repair negatives that wrongly received a work type: категория (baseline) 2.5%, правила 2.5%, модель 2.5%, правила + модель 2.5%
- Semantic, not literal (name has no keyword of the work; 51 pairs): P 0.754, R 0.902, F1 0.821
- Ranking per work type (k=10, 10 works with >=3 positives): MAP@10 0.905, nDCG@10 0.942

### Per work type, rules + model, test split (n=58)

- micro-F1 **0.871** (P 0.831, R 0.914); macro-F1 0.809; sample-based F1 0.915; Hamming loss 0.0093; exact match 0.862

| work type | P | R | F1 | support |
|---|---|---|---|---|
| general_assembly | 0.90 | 1.00 | 0.95 | 18 |
| wall_painting | 1.00 | 1.00 | 1.00 | 9 |
| wall_panels | 1.00 | 0.75 | 0.86 | 8 |
| ceiling_painting | 1.00 | 1.00 | 1.00 | 7 |
| skirting_install | 1.00 | 1.00 | 1.00 | 6 |
| tile_laying | 0.60 | 0.60 | 0.60 | 5 |
| wood_metal_coating | 1.00 | 0.80 | 0.89 | 5 |
| drywall_install | 0.80 | 1.00 | 0.89 | 4 |
| puttying | 1.00 | 1.00 | 1.00 | 3 |
| wallpapering | 0.75 | 1.00 | 0.86 | 3 |
| priming | 1.00 | 1.00 | 1.00 | 2 |
| plastering | 0.67 | 1.00 | 0.80 | 2 |
| cable_laying | 1.00 | 1.00 | 1.00 | 2 |
| demolition | 0.50 | 1.00 | 0.67 | 1 |
| antiseptic | 0.00 | 0.00 | 0.00 | 1 |
| masonry | 1.00 | 1.00 | 1.00 | 1 |
| insulation | 0.50 | 1.00 | 0.67 | 1 |
| grouting | 1.00 | 1.00 | 1.00 | 1 |
| lighting_install | 0.00 | 0.00 | 0.00 | 1 |
| heating_install | 1.00 | 1.00 | 1.00 | 1 |
| screed | 0.00 | 0.00 | 0.00 | 0 |
| self_leveling | 0.00 | 0.00 | 0.00 | 0 |
| waterproofing | 0.00 | 0.00 | 0.00 | 0 |
