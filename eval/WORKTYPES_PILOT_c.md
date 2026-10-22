## Work types on a PILOT set (single labeller = LLM, NOT human; development use only)

- Test split n=50 (never used for tuning); dev n=69; ambiguous rows n=89

| system | micro-F1 | macro-F1 | samples-F1 | Hamming loss | exact match | dev micro-F1 |
|---|---|---|---|---|---|---|
| категория (baseline) | 0.628 | 0.715 | 0.711 | 0.0341 | 0.500 | 0.492 |
| правила | 0.778 | 0.857 | 0.832 | 0.0176 | 0.740 | 0.759 |
| модель | 0.768 | 0.845 | 0.822 | 0.0185 | 0.720 | 0.755 |
| правила + модель | 0.778 | 0.857 | 0.832 | 0.0176 | 0.740 | 0.759 |

- Target micro-F1 >= 0.8 (aim 0.9): **NOT reached** (0.778)

- Ambiguous subset (n=89): micro-F1 0.768, macro-F1 0.834, exact match 0.685
- Same ambiguous rows, CATEGORY BASELINE: micro-F1 0.550, macro-F1 0.538, exact match 0.360; product-level matcher gains +0.217 micro-F1 ("semantic, not literal" proof)
- Semantic, not literal (name has no keyword of the work; 48 pairs): P 0.594, R 0.854, F1 0.701
- Ranking per work type (k=10, 13 works with >=3 positives): MAP@10 0.860, nDCG@10 0.923

### Per work type, rules + model, test split (n=50)

- micro-F1 **0.778** (P 0.692, R 0.887); macro-F1 0.857; sample-based F1 0.832; Hamming loss 0.0176; exact match 0.740

| work type | P | R | F1 | support |
|---|---|---|---|---|
| wall_panels | 0.88 | 0.64 | 0.74 | 11 |
| general_assembly | 0.62 | 1.00 | 0.76 | 8 |
| tile_laying | 0.75 | 0.50 | 0.60 | 6 |
| insulation | 1.00 | 1.00 | 1.00 | 5 |
| puttying | 0.83 | 1.00 | 0.91 | 5 |
| plastering | 0.67 | 1.00 | 0.80 | 4 |
| sealing | 1.00 | 1.00 | 1.00 | 4 |
| priming | 1.00 | 1.00 | 1.00 | 3 |
| wall_painting | 0.75 | 1.00 | 0.86 | 3 |
| wood_metal_coating | 1.00 | 0.67 | 0.80 | 3 |
| ceiling_painting | 0.75 | 1.00 | 0.86 | 3 |
| door_install | 1.00 | 1.00 | 1.00 | 3 |
| window_install | 1.00 | 1.00 | 1.00 | 3 |
| wallpapering | 0.50 | 1.00 | 0.67 | 2 |
| faucet_install | 1.00 | 1.00 | 1.00 | 2 |
| surface_cleaning | 1.00 | 1.00 | 1.00 | 1 |
| waterproofing | 0.33 | 1.00 | 0.50 | 1 |
| skirting_install | 1.00 | 1.00 | 1.00 | 1 |
| ceiling_install | 0.33 | 1.00 | 0.50 | 1 |
| cornice_install | 1.00 | 1.00 | 1.00 | 1 |
| sockets_switches | 1.00 | 1.00 | 1.00 | 1 |
| demolition | 0.00 | 0.00 | 0.00 | 0 |
| crack_repair | 0.00 | 0.00 | 0.00 | 0 |
| screed | 0.00 | 0.00 | 0.00 | 0 |
| self_leveling | 0.00 | 0.00 | 0.00 | 0 |
| decorative_coating | 0.00 | 0.00 | 0.00 | 0 |
| slopes | 0.00 | 0.00 | 0.00 | 0 |
