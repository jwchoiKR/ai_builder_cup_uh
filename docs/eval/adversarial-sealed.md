# Adversarial eval (proof-plan §3)

2026-10-05 · `adversarial_sealed.jsonl` · 80 cases × 3 runs · real UtterancePipeline per case (post-validation, merge, dedupe and corrections included).

**FAIL** · detection 100.0% (≥ 95%) · wrong HIGH 1 (0) · false alerts 2.5% (≤ 5%) · wrong correction texts 0 (0)

| type | risky caught | right rule/field | safe with an alert | HIGH | MEDIUM | fact note | wrong HIGH | wrong text |
|---|---|---|---|---|---|---|---|---|
| near_number | 15/15 (100%) | 12/15 (80%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| negation_trap | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| numbers_in_words | 15/15 (100%) | 6/15 (40%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| paraphrase | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| qualifier_missing | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| quote_joke | 15/15 (100%) | 15/15 (100%) | 2/15 (13%) | 0 | 0 | 2 | 0 | 0 |
| singlish_mix | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| split | 15/15 (100%) | 15/15 (100%) | 1/15 (7%) | 1 | 0 | 0 | 1 | 0 |

## Missed risky lines

- none

## Alerts on safe lines

- AV037 run 0 (split): "In our in-house study, / 29 of 32 participants said their skin felt less dry after 2 weeks." → compliance ASEAN-3-SKIN-ACNE HIGH
- AV117 run 0 (quote_joke): "Haha, Marcus jokes that he wants to bathe in a 50 mL tube because it feels so nice!" → fact packaging 
- AV117 run 2 (quote_joke): "Haha, Marcus jokes that he wants to bathe in a 50 mL tube because it feels so nice!" → fact packaging 

## Wrong HIGH or wrong correction text

- AV037 run 0 (split): "In our in-house study, / 29 of 32 participants said their skin felt less dry after 2 weeks." → compliance ASEAN-3-SKIN-ACNE HIGH
