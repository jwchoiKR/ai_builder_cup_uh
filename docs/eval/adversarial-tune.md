# Adversarial eval (proof-plan §3)

2026-10-05 · `adversarial_cases.jsonl` · 80 cases × 3 runs · real UtterancePipeline per case (post-validation, merge, dedupe and corrections included).

**FAIL** · detection 99.2% (≥ 95%) · wrong HIGH 0 (0) · false alerts 0.0% (≤ 5%) · wrong correction texts 12 (0)

| type | risky caught | right rule/field | safe with an alert | HIGH | MEDIUM | fact note | wrong HIGH | wrong text |
|---|---|---|---|---|---|---|---|---|
| near_number | 18/18 (100%) | 6/18 (33%) | 0/12 (0%) | 0 | 0 | 0 | 0 | 9 |
| negation_trap | 14/15 (93%) | 14/15 (93%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| numbers_in_words | 18/18 (100%) | 6/18 (33%) | 0/12 (0%) | 0 | 0 | 0 | 0 | 3 |
| paraphrase | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| qualifier_missing | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| quote_joke | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| singlish_mix | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| split | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |

## Missed risky lines

- AV083 run 1 (negation_trap): "I won't say your wrinkles will disappear overnight, but your wrinkles literally disappear overnight." → none

## Alerts on safe lines

- none

## Wrong HIGH or wrong correction text

- AV045 run 0 (numbers_in_words): "This jar holds eighty milliliters of product." → fact volume ; fact packaging 
- AV123 run 0 (near_number): "It contains 5% panthenol and 4% niacinamide." → fact ingredient_amount 
- AV124 run 0 (near_number): "The ampoule has 4% niacinamide and 3% squalane." → fact ingredient 
- AV125 run 0 (near_number): "In this 30 mL jar you get 1% Ceramide NP." → fact volume ; fact packaging 
- AV045 run 1 (numbers_in_words): "This jar holds eighty milliliters of product." → fact packaging ; fact volume 
- AV123 run 1 (near_number): "It contains 5% panthenol and 4% niacinamide." → fact ingredient 
- AV124 run 1 (near_number): "The ampoule has 4% niacinamide and 3% squalane." → fact ingredient 
- AV125 run 1 (near_number): "In this 30 mL jar you get 1% Ceramide NP." → fact volume ; fact packaging 
- AV045 run 2 (numbers_in_words): "This jar holds eighty milliliters of product." → fact volume ; fact packaging 
- AV123 run 2 (near_number): "It contains 5% panthenol and 4% niacinamide." → fact ingredient 
- AV124 run 2 (near_number): "The ampoule has 4% niacinamide and 3% squalane." → fact ingredient 
- AV125 run 2 (near_number): "In this 30 mL jar you get 1% Ceramide NP." → fact volume ; fact packaging 
