# Eval report

## Golden calculation suite

- Cases: 288 (verified against external source: 72)
- Pack-count exact match: 144/144
- MAE of pack counts: 0.000 packs (max error 0)
- MAPE on continuous quantities: 0.101%
- Split (quote only the first on stage):
  - manufacturer_verified: 72 cases; pack exact 26/26; MAE 0.000 packs; MAPE 0.316%
  - rederived: 216 cases; pack exact 118/118; MAE 0.000 packs; MAPE 0.000%

| calc | passed | total |
|---|---|---|
| adhesive_kg | 28 | 28 |
| grout_kg | 23 | 23 |
| grout_table_kg | 8 | 8 |
| laminate_packs | 21 | 21 |
| layer_kg | 23 | 23 |
| pack_cost | 14 | 14 |
| paint_liters | 30 | 30 |
| paint_packs | 8 | 8 |
| primer_packs | 8 | 8 |
| putty_bags | 35 | 35 |
| skirting_pieces | 15 | 15 |
| tile_packs | 26 | 26 |
| wallpaper_rolls | 29 | 29 |
| waterproofing_kg | 20 | 20 |

## Attribute extraction (regex layer)

- Gold cases: 28 (SYNTHETIC, team-written; not real catalog rows)
- Micro precision: 1.000, micro recall: 1.000

| field | precision | recall | tp | wrong | fp | fn |
|---|---|---|---|---|---|---|
| consumption_kg_per_m2_per_mm | 1.00 | 1.00 | 2 | 0 | 0 | 0 |
| ip_rating | 1.00 | 1.00 | 1 | 0 | 0 | 0 |
| length_mm | 1.00 | 1.00 | 4 | 0 | 0 | 0 |
| m2_per_pack | 1.00 | 1.00 | 4 | 0 | 0 | 0 |
| pack_mass_kg | 1.00 | 1.00 | 6 | 0 | 0 | 0 |
| pack_volume_l | 1.00 | 1.00 | 4 | 0 | 0 | 0 |
| pcs_per_pack | 1.00 | 1.00 | 2 | 0 | 0 | 0 |
| rapport_cm | 1.00 | 1.00 | 1 | 0 | 0 | 0 |
| roll_length_m | 1.00 | 1.00 | 5 | 0 | 0 | 0 |
| roll_width_m | 1.00 | 1.00 | 5 | 0 | 0 | 0 |
| spread_m2_per_l | 1.00 | 1.00 | 1 | 0 | 0 | 0 |
| thickness_mm | 1.00 | 1.00 | 4 | 0 | 0 | 0 |
| tile_h_mm | 1.00 | 1.00 | 3 | 0 | 0 | 0 |
| tile_w_mm | 1.00 | 1.00 | 3 | 0 | 0 | 0 |
| wear_class | 1.00 | 1.00 | 3 | 0 | 0 | 0 |
| width_mm | 1.00 | 1.00 | 4 | 0 | 0 | 0 |

## Catalog matching (SYNTHETIC catalog; machinery check, not a quality claim)

- Items: 3000 (train 1786 / dev 589 / test 625, split by product group, test models unseen)
- Train labels: weak (rules). Calibration + thresholds (target precision 0.95): dev gold.

| scenario | work F1 (macro/micro) | room F1 | prop F1 | calc P@1 | auto coverage | auto precision |
|---|---|---|---|---|---|---|
| rules only, category present | 0.87/0.94 | 0.99/1.00 | 0.99/0.98 | 0.974 | 0.960 | 0.935 |
| rules + model, category present | 0.87/0.95 | 0.99/1.00 | 0.99/0.98 | 0.974 | 0.936 | 0.959 |
| rules only, category missing | 0.81/0.80 | 1.00/1.00 | 1.00/1.00 | 0.682 | 0.682 | 1.000 |
| rules + model, category missing | 0.95/0.96 | 1.00/1.00 | 1.00/1.00 | 1.000 | 0.989 | 0.917 |

## Recommendation (SYNTHETIC catalog)

- Truth = gold labels; relevance = independent rubric over the same room-rule KB (measures label-error propagation, not rule correctness)

| catalog labels | queries | nDCG@5 | recommended | hard-rule violations | empty results |
|---|---|---|---|---|---|
| gold | 61 | 1.000 | 297 | 0 | 0 |
| pipeline (rules+model) | 61 | 0.995 | 295 | 0 | 0 |

## Recommendation: embedding-relevance ablation (SYNTHETIC catalog)

- Weight of the query-product embedding similarity in the ranking score; 0 = off. Embedder: hashing (offline). nDCG@5 against the rubric; delta vs weight 0.

| weight | nDCG@5 gold | Δ | nDCG@5 pipeline | Δ | violations (pipeline) |
|---|---|---|---|---|---|
| 0.0 | 1.000 | +0.000 | 0.995 | +0.000 | 0 |
| 0.02 | 1.000 | +0.000 | 0.978 | -0.017 | 0 |
| 0.05 | 1.000 | +0.000 | 0.978 | -0.017 | 0 |
| 0.1 | 1.000 | +0.000 | 0.978 | -0.017 | 0 |
| 0.2 | 1.000 | +0.000 | 0.978 | -0.017 | 0 |
| 0.3 | 1.000 | +0.000 | 0.978 | -0.017 | 0 |
| 0.5 | 1.000 | +0.000 | 0.978 | -0.017 | 0 |

## Work types (multi-label matching of products to repair processes)

- Human gold set: **not measured** (eval/gold/worktype_gold.csv absent; label the sheets, run scripts/merge_worktype_gold.py and scripts/eval_worktypes.py).

### PILOT: an LLM as the only labeller (NOT human), fresh set C, category baseline vs product-level matcher (docs/CATEGORY_MAP.md)

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

- SILVER held-out categories (297 categories never seen in training; labels = rules): micro-F1 0.857, macro-F1 0.726, sample-F1 0.917, Hamming loss 0.0092; name without the work keyword: F1 0.752 (5203 pairs)

## Recommendation (HUMAN grades)

- No graded file at eval/gold/rec_grades.csv: human nDCG not measured
