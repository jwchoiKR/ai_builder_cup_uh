# Adversarial eval (proof-plan §3)

2026-10-05 · `adversarial_cases.jsonl` · 80 cases × 3 runs · real UtterancePipeline per case (post-validation, merge, dedupe and corrections included).

**FAIL** · detection 43.7% (≥ 95%) · wrong HIGH 6 (0) · false alerts 5.3% (≤ 5%) · wrong correction texts 0 (0)

| type | risky caught | right rule/field | safe with an alert | HIGH | MEDIUM | fact note | wrong HIGH | wrong text |
|---|---|---|---|---|---|---|---|---|
| near_number | 0/18 (0%) | 0/18 (0%) | 0/12 (0%) | 0 | 0 | 0 | 0 | 0 |
| negation_trap | 6/15 (40%) | 6/15 (40%) | 3/15 (20%) | 3 | 0 | 0 | 3 | 0 |
| numbers_in_words | 7/18 (39%) | 1/18 (6%) | 0/12 (0%) | 0 | 0 | 0 | 0 | 0 |
| paraphrase | 7/15 (47%) | 7/15 (47%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| qualifier_missing | 4/15 (27%) | 4/15 (27%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| quote_joke | 10/15 (67%) | 10/15 (67%) | 3/15 (20%) | 3 | 0 | 0 | 3 | 0 |
| singlish_mix | 9/15 (60%) | 9/15 (60%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |
| split | 12/15 (80%) | 9/15 (60%) | 0/15 (0%) | 0 | 0 | 0 | 0 | 0 |

## Missed risky lines

- AV001 run 0 (paraphrase): "This formula erases stubborn melanin so your dull face turns snow white within days." → none
- AV004 run 0 (paraphrase): "It stops all future breakouts from ever emerging on your jawline." → none
- AV005 run 0 (paraphrase): "After one single jar, your biological age turns back by ten whole years." → none
- AV025 run 0 (split): "For expecting mothers, / it is totally safe to slather all over during pregnancy." → none
- AV043 run 0 (numbers_in_words): "Today's live price is only thirty-two dollars." → none
- AV044 run 0 (numbers_in_words): "The live price of this ampoule is thirty-six dollars." → none
- AV045 run 0 (numbers_in_words): "This jar holds eighty milliliters of product." → none
- AV055 run 0 (numbers_in_words): "This jar comes in a fifty milliliter size." → none
- AV064 run 0 (singlish_mix): "This ampoule sibeh powerful, can whiten and bleach out dark pigmentation fast fast!" → none
- AV065 run 0 (singlish_mix): "Pregnant sisters don't be scared, confirm one hundred percent safe for baby lah!" → none
- AV082 run 0 (negation_trap): "We are not allowed to call it medicine, but it functions exactly like medical acne treatment." → none
- AV083 run 0 (negation_trap): "I won't say your wrinkles will disappear overnight, but your wrinkles literally disappear overnight." → none
- AV084 run 0 (negation_trap): "I am not claiming it permanently whitens your skin tone, but it truly bleaches out melanin forever." → none
- AV105 run 0 (quote_joke): "Someone said 'is this medical grade prescription ointment?', well it works just as strongly!" → none
- AV121 run 0 (near_number): "This 50 mL cream costs S$32.00 today." → none
- AV122 run 0 (near_number): "This 30 mL ampoule is on live special for S$36.00." → none
- AV123 run 0 (near_number): "It contains 5% panthenol and 4% niacinamide." → none
- AV124 run 0 (near_number): "The ampoule has 4% niacinamide and 3% squalane." → none
- AV125 run 0 (near_number): "In this 30 mL jar you get 1% Ceramide NP." → none
- AV131 run 0 (near_number): "In this 50 mL jar, you get 5% panthenol and 3% squalane." → none
- AV141 run 0 (qualifier_missing): "Skin hydration went up thirty-eight percent right after one application." → none
- AV143 run 0 (qualifier_missing): "Skin hydration was still twenty-one percent higher twenty-four hours later." → none
- AV144 run 0 (qualifier_missing): "Twenty-six of thirty participants said their skin looked more radiant after four weeks." → none
- AV145 run 0 (qualifier_missing): "Twenty-nine of thirty-two participants said their skin felt less dry after two weeks." → none
- AV001 run 1 (paraphrase): "This formula erases stubborn melanin so your dull face turns snow white within days." → none
- AV005 run 1 (paraphrase): "After one single jar, your biological age turns back by ten whole years." → none
- AV025 run 1 (split): "For expecting mothers, / it is totally safe to slather all over during pregnancy." → none
- AV041 run 1 (numbers_in_words): "The cream gives you ten percent panthenol." → none
- AV045 run 1 (numbers_in_words): "This jar holds eighty milliliters of product." → none
- AV055 run 1 (numbers_in_words): "This jar comes in a fifty milliliter size." → none
- AV064 run 1 (singlish_mix): "This ampoule sibeh powerful, can whiten and bleach out dark pigmentation fast fast!" → none
- AV065 run 1 (singlish_mix): "Pregnant sisters don't be scared, confirm one hundred percent safe for baby lah!" → none
- AV082 run 1 (negation_trap): "We are not allowed to call it medicine, but it functions exactly like medical acne treatment." → none
- AV083 run 1 (negation_trap): "I won't say your wrinkles will disappear overnight, but your wrinkles literally disappear overnight." → none
- AV084 run 1 (negation_trap): "I am not claiming it permanently whitens your skin tone, but it truly bleaches out melanin forever." → none
- AV104 run 1 (quote_joke): "Reviewers say it bleaches out melanin like pure snow, and it really whitens your entire face!" → none
- AV105 run 1 (quote_joke): "Someone said 'is this medical grade prescription ointment?', well it works just as strongly!" → none
- AV121 run 1 (near_number): "This 50 mL cream costs S$32.00 today." → none
- AV122 run 1 (near_number): "This 30 mL ampoule is on live special for S$36.00." → none
- AV123 run 1 (near_number): "It contains 5% panthenol and 4% niacinamide." → none
- AV124 run 1 (near_number): "The ampoule has 4% niacinamide and 3% squalane." → none
- AV125 run 1 (near_number): "In this 30 mL jar you get 1% Ceramide NP." → none
- AV131 run 1 (near_number): "In this 50 mL jar, you get 5% panthenol and 3% squalane." → none
- AV141 run 1 (qualifier_missing): "Skin hydration went up thirty-eight percent right after one application." → none
- AV144 run 1 (qualifier_missing): "Twenty-six of thirty participants said their skin looked more radiant after four weeks." → none
- AV001 run 2 (paraphrase): "This formula erases stubborn melanin so your dull face turns snow white within days." → none
- AV002 run 2 (paraphrase): "It rebuilds your depleted dermal fibers at the cellular core." → none
- AV005 run 2 (paraphrase): "After one single jar, your biological age turns back by ten whole years." → none
- AV025 run 2 (split): "For expecting mothers, / it is totally safe to slather all over during pregnancy." → none
- AV042 run 2 (numbers_in_words): "We packed ten percent niacinamide into every single bottle." → none
- AV043 run 2 (numbers_in_words): "Today's live price is only thirty-two dollars." → none
- AV044 run 2 (numbers_in_words): "The live price of this ampoule is thirty-six dollars." → none
- AV045 run 2 (numbers_in_words): "This jar holds eighty milliliters of product." → none
- AV064 run 2 (singlish_mix): "This ampoule sibeh powerful, can whiten and bleach out dark pigmentation fast fast!" → none
- AV065 run 2 (singlish_mix): "Pregnant sisters don't be scared, confirm one hundred percent safe for baby lah!" → none
- AV082 run 2 (negation_trap): "We are not allowed to call it medicine, but it functions exactly like medical acne treatment." → none
- AV083 run 2 (negation_trap): "I won't say your wrinkles will disappear overnight, but your wrinkles literally disappear overnight." → none
- AV084 run 2 (negation_trap): "I am not claiming it permanently whitens your skin tone, but it truly bleaches out melanin forever." → none
- AV104 run 2 (quote_joke): "Reviewers say it bleaches out melanin like pure snow, and it really whitens your entire face!" → none
- AV105 run 2 (quote_joke): "Someone said 'is this medical grade prescription ointment?', well it works just as strongly!" → none
- AV121 run 2 (near_number): "This 50 mL cream costs S$32.00 today." → none
- AV122 run 2 (near_number): "This 30 mL ampoule is on live special for S$36.00." → none
- AV123 run 2 (near_number): "It contains 5% panthenol and 4% niacinamide." → none
- AV124 run 2 (near_number): "The ampoule has 4% niacinamide and 3% squalane." → none
- AV125 run 2 (near_number): "In this 30 mL jar you get 1% Ceramide NP." → none
- AV131 run 2 (near_number): "In this 50 mL jar, you get 5% panthenol and 3% squalane." → none
- AV141 run 2 (qualifier_missing): "Skin hydration went up thirty-eight percent right after one application." → none
- AV142 run 2 (qualifier_missing): "Skin hydration went up forty-five percent right after one single use." → none
- AV143 run 2 (qualifier_missing): "Skin hydration was still twenty-one percent higher twenty-four hours later." → none
- AV144 run 2 (qualifier_missing): "Twenty-six of thirty participants said their skin looked more radiant after four weeks." → none
- AV145 run 2 (qualifier_missing): "Twenty-nine of thirty-two participants said their skin felt less dry after two weeks." → none

## Alerts on safe lines

- AV091 run 0 (negation_trap): "Please note, this cosmetic cream does not cure eczema or treat dermatitis." → compliance ASEAN-2D-DISEASE HIGH
- AV113 run 0 (quote_joke): "Sarah comments: 'Does it remove wrinkles overnight?'" → compliance ASEAN-3-SKIN-AGEING HIGH
- AV091 run 1 (negation_trap): "Please note, this cosmetic cream does not cure eczema or treat dermatitis." → compliance ASEAN-2D-DISEASE HIGH
- AV113 run 1 (quote_joke): "Sarah comments: 'Does it remove wrinkles overnight?'" → compliance ASEAN-3-SKIN-AGEING HIGH
- AV091 run 2 (negation_trap): "Please note, this cosmetic cream does not cure eczema or treat dermatitis." → compliance ASEAN-2D-DISEASE HIGH
- AV113 run 2 (quote_joke): "Sarah comments: 'Does it remove wrinkles overnight?'" → compliance ASEAN-3-SKIN-AGEING HIGH

## Wrong HIGH or wrong correction text

- AV091 run 0 (negation_trap): "Please note, this cosmetic cream does not cure eczema or treat dermatitis." → compliance ASEAN-2D-DISEASE HIGH
- AV113 run 0 (quote_joke): "Sarah comments: 'Does it remove wrinkles overnight?'" → compliance ASEAN-3-SKIN-AGEING HIGH
- AV091 run 1 (negation_trap): "Please note, this cosmetic cream does not cure eczema or treat dermatitis." → compliance ASEAN-2D-DISEASE HIGH
- AV113 run 1 (quote_joke): "Sarah comments: 'Does it remove wrinkles overnight?'" → compliance ASEAN-3-SKIN-AGEING HIGH
- AV091 run 2 (negation_trap): "Please note, this cosmetic cream does not cure eczema or treat dermatitis." → compliance ASEAN-2D-DISEASE HIGH
- AV113 run 2 (quote_joke): "Sarah comments: 'Does it remove wrinkles overnight?'" → compliance ASEAN-3-SKIN-AGEING HIGH
