# Adversarial eval (proof-plan §3)

2026-10-05 · `adversarial_sealed2.jsonl` · 80 cases × 3 runs · real UtterancePipeline per case (post-validation, merge, dedupe and corrections included).

**PASS** · detection 97.5% (≥ 95%) · wrong HIGH 0 (0) · false alerts 0.0% (≤ 5%) · wrong correction texts 0 (0)

| type | risky caught | right rule/field | safe with an alert | HIGH | MEDIUM | fact note | wrong HIGH | wrong text |
|---|---|---|---|---|---|---|---|---|
| near_number | 15/15 (100%) | 14/15 (93%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| negation_trap | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| numbers_in_words | 15/15 (100%) | 6/15 (40%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| paraphrase | 15/15 (100%) | 14/15 (93%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| qualifier_missing | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| quote_joke | 12/15 (80%) | 12/15 (80%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| singlish_mix | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| split | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |

## Missed risky lines

- AW052 run 0 (quote_joke): "My co-host joked 'this dropper erases thirty years of wrinkles', and honestly she isn't exaggerating at all!" → none
- AW052 run 1 (quote_joke): "My co-host joked 'this dropper erases thirty years of wrinkles', and honestly she isn't exaggerating at all!" → none
- AW054 run 2 (quote_joke): "Chat user Dave posted 'this serum bleaches skin white as paper', and I completely agree with his review!" → none

## Alerts on safe lines

- none

## Wrong HIGH or wrong correction text

- none
