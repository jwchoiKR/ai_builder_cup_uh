# Adversarial eval (proof-plan §3)

2026-10-05 · `adversarial_sealed2.jsonl` · 80 cases × 3 runs · real UtterancePipeline per case (post-validation, merge, dedupe and corrections included).

**FAIL** · detection 100.0% (≥ 95%) · wrong HIGH 7 (0) · false alerts 2.5% (≤ 5%) · wrong correction texts 0 (0)

| type | risky caught | right rule/field | safe with an alert | HIGH | MEDIUM | fact note | wrong HIGH | wrong text |
|---|---|---|---|---|---|---|---|---|
| near_number | 15/15 (100%) | 14/15 (93%) | 0/15 (0%) | 0 | 0 | 0 | 6 | 0 |
| negation_trap | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| numbers_in_words | 15/15 (100%) | 6/15 (40%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| paraphrase | 15/15 (100%) | 13/15 (87%) | 3/15 (20%) | 1 | 2 | 0 | 1 | 0 |
| qualifier_missing | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| quote_joke | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| singlish_mix | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| split | 15/15 (100%) | 15/15 (100%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |

## Missed risky lines

- none

## Alerts on safe lines

- AW010 run 0 (paraphrase): "Contains no added fragrance and no essential oils, making it suitable for all skin types." → compliance BRAND-SUPERLATIVE MEDIUM
- AW010 run 1 (paraphrase): "Contains no added fragrance and no essential oils, making it suitable for all skin types." → compliance ASEAN-2D-VULNERABLE HIGH
- AW010 run 2 (paraphrase): "Contains no added fragrance and no essential oils, making it suitable for all skin types." → compliance BRAND-SUPERLATIVE MEDIUM

## Wrong HIGH or wrong correction text

- AW063 run 0 (near_number): "This barrier cream has a skin-balancing pH of 3.5 for deep exfoliating action." → compliance ASEAN-DP5-PHYSIOLOGICAL HIGH; fact ph 
- AW064 run 0 (near_number): "Our ampoule is formulated at an alkaline pH of 7.5 to open your pores." → compliance ASEAN-DP5-PHYSIOLOGICAL HIGH; fact ph 
- AW010 run 1 (paraphrase): "Contains no added fragrance and no essential oils, making it suitable for all skin types." → compliance ASEAN-2D-VULNERABLE HIGH
- AW063 run 1 (near_number): "This barrier cream has a skin-balancing pH of 3.5 for deep exfoliating action." → compliance ASEAN-DP5-PHYSIOLOGICAL HIGH; fact ph 
- AW064 run 1 (near_number): "Our ampoule is formulated at an alkaline pH of 7.5 to open your pores." → compliance ASEAN-DP5-PHYSIOLOGICAL HIGH; fact ph 
- AW063 run 2 (near_number): "This barrier cream has a skin-balancing pH of 3.5 for deep exfoliating action." → compliance ASEAN-DP5-PHYSIOLOGICAL HIGH; fact ph 
- AW064 run 2 (near_number): "Our ampoule is formulated at an alkaline pH of 7.5 to open your pores." → compliance ASEAN-DP5-PHYSIOLOGICAL HIGH; fact ph 
