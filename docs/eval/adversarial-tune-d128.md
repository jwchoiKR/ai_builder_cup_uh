# Adversarial eval (proof-plan §3)

2026-10-05 · `adversarial_cases.jsonl` · 80 cases × 3 runs · real UtterancePipeline per case (post-validation, merge, dedupe and corrections included).

**PASS** · detection 100.0% (≥ 95%) · wrong HIGH 0 (0) · false alerts 0.0% (≤ 5%) · wrong correction texts 0 (0)

| type | risky caught | right rule/field | safe with an alert | HIGH | MEDIUM | fact note | wrong HIGH | wrong text |
|---|---|---|---|---|---|---|---|---|
| near_number | 18/18 (100%) | 12/18 (67%) | 0/12 (0%) | 0 | 0 | 0 | 0 | 0 |
| negation_trap | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| numbers_in_words | 18/18 (100%) | 6/18 (33%) | 0/12 (0%) | 0 | 0 | 0 | 0 | 0 |
| paraphrase | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| qualifier_missing | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| quote_joke | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| singlish_mix | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| split | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |

## Missed risky lines

- none

## Alerts on safe lines

- none

## Wrong HIGH or wrong correction text

- none
