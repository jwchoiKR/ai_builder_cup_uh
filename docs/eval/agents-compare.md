# Utterance agent structures compared · 2026-10-02

**Structures:**
- **2 agents (run 1):** UtteranceJudge + FactChecker in parallel (production)
- **2 agents (run 2):** UtteranceJudge + FactChecker in parallel (production)
- **3 agents parallel:** ComplianceJudge + ContextJudge + FactChecker in parallel (experiment)
- **LLM router + 3:** LLM router first, then only the chosen of ComplianceJudge / ContextJudge / FactChecker in parallel (experiment)

**Same conditions:**
- 39 eval cases × 20 runs on `gemini-3.5-flash-lite` (thinking MINIMAL).
- The same specialist prompts (the experiment judges are cut from the production prompt with the same wording).
- At most 12 specialist calls in flight. Timeouts are counted apart from wrong answers.

## Accuracy (correct / answered in time)
| Check | 2 agents (run 1) | 2 agents (run 2) | 3 agents parallel | LLM router + 3 |
|---|---|---|---|---|
| judge · catches the violation (right rule) | 251/251 (100.0%) | 241/241 (100.0%) | 242/242 (100.0%) | 247/247 (100.0%) |
| judge · correction | 20/20 (100.0%) | 19/19 (100.0%) | 20/20 (100.0%) | 20/20 (100.0%) |
| judge · no alert on negated/quoted/approved wording | 115/115 (100.0%) | 110/110 (100.0%) | 119/119 (100.0%) | 120/120 (100.0%) |
| judge · leak: alert on a sentence with no compliance claim | 386/387 (99.7%) | 376/378 (99.5%) | 397/397 (100.0%) | 400/400 (100.0%) |
| judge · answer linking | 78/78 (100.0%) | 73/73 (100.0%) | 79/79 (100.0%) | 80/80 (100.0%) |
| judge · prompter points | 76/76 (100.0%) | 74/74 (100.0%) | 77/77 (100.0%) | 80/80 (100.0%) |
| judge · switch | 79/79 (100.0%) | 73/73 (100.0%) | 75/75 (100.0%) | 80/80 (100.0%) |
| facts (after quote check) · catches the wrong fact | 80/80 (100.0%) | 76/78 (97.4%) | 77/78 (98.7%) | 80/80 (100.0%) |
| facts (after quote check) · no note on a right fact | 119/119 (100.0%) | 111/111 (100.0%) | 116/116 (100.0%) | 120/120 (100.0%) |
| facts (raw) · catches the wrong fact | 80/80 (100.0%) | 76/78 (97.4%) | 77/78 (98.7%) | 80/80 (100.0%) |
| facts (raw) · no note on a right fact | 119/119 (100.0%) | 111/111 (100.0%) | 116/116 (100.0%) | 120/120 (100.0%) |
| facts (after quote check) · leak: note on a sentence that is not about facts | 544/570 (95.4%) | 532/551 (96.6%) | 537/560 (95.9%) | 551/571 (96.5%) |
| facts (raw) · leak: note on a sentence that is not about facts | 474/570 (83.2%) | 461/551 (83.7%) | 468/560 (83.6%) | 538/571 (94.2%) |

## Speed and cost
| | 2 agents (run 1) | 2 agents (run 2) | 3 agents parallel | LLM router + 3 |
|---|---|---|---|---|
| Compliance verdict ready (red alert path) | p50 1506 · p95 1826 · max 2498 ms | p50 1542 · p95 1932 · max 2473 ms | p50 1196 · p95 1510 · max 2296 ms | p50 1990 · p95 2384 · max 2765 ms |
| Answer / prompter / switch verdict ready | p50 1506 · p95 1826 · max 2498 ms | p50 1542 · p95 1932 · max 2473 ms | p50 1412 · p95 1668 · max 2336 ms | p50 2325 · p95 2593 · max 3394 ms |
| Fact verdict ready | p50 1301 · p95 1782 · max 2595 ms | p50 1336 · p95 1834 · max 2983 ms | p50 1325 · p95 1888 · max 2975 ms | p50 2085 · p95 2721 · max 4415 ms |
| All done | p50 1536 · p95 1931 · max 2595 ms | p50 1581 · p95 1994 · max 2983 ms | p50 1468 · p95 1928 · max 2935 ms | p50 2369 · p95 2755 · max 3690 ms |
| Compliance part timed out | 27/780 (3.5%) | 51/780 (6.5%) | 22/780 (2.8%) | 13/780 (1.7%) |
| Answer/prompter/switch part timed out | 27/780 (3.5%) | 51/780 (6.5%) | 27/780 (3.5%) | 12/780 (1.5%) |
| Fact checker timed out | 11/780 (1.4%) | 40/780 (5.1%) | 26/780 (3.3%) | 9/780 (1.2%) |
| Model calls per sentence | 2 | 2 | 3 | 3.13 |

## Routing (LLM router + 3)
- **Router:** p50 985 · p95 1161 · max 1326 ms; timed out 12/780 (then every specialist runs)
- **Model calls per sentence:** 3.13 (router included)
- **Specialist chosen:** compliance 444/780, context 780/780, facts 439/780
- **Needed specialist not chosen (case × runs):** none

## Wrong answers
- **2 agents (run 1) · judge · leak: alert on a sentence with no compliance claim:** U21: got ASEAN-DP5-PHYSIOLOGICAL ×1
- **2 agents (run 1) · facts (after quote check) · leak: note on a sentence that is not about facts:** U09: got test_result: 2 weeks -> 4 weeks ×11; U10: got other: prescription cream -> cosmetic product ×11; U09: got other: 2 weeks -> 4 weeks ×1; U11: got other: ten years younger -> Cosmetic effects only ×1; U07: got other: safe for pregnant women -> not specifically tested on pregnant or breastfeeding women; consult doctor be ×1
- **2 agents (run 1) · facts (raw) · leak: note on a sentence that is not about facts:** U06: got other: removes acne scars -> Treats acne, acne scars, pigmentation disorders or any skin disease. ×15; U09: got test_result: 2 weeks -> 4 weeks ×11; U10: got other: prescription cream -> cosmetic product ×11; U05: got other: Regenerates skin cells -> Claims not approved: Removes wrinkles or reverses skin ageing. Whitens skin, o ×5; U05: got other: Regenerates skin cells -> Claims not approved: Repairs, heals or regenerates skin cells. ×4
- **2 agents (run 2) · judge · leak: alert on a sentence with no compliance claim:** U21: got BRAND-SUPERLATIVE ×1; U21: got BRAND-ABSOLUTE-SAFETY ×1
- **2 agents (run 2) · facts (after quote check) · catches the wrong fact:** U21: got ingredient_amount: 10% niacinamide -> 4% ×2
- **2 agents (run 2) · facts (raw) · catches the wrong fact:** U21: got ingredient_amount: 10% niacinamide -> 4% ×2
- **2 agents (run 2) · facts (after quote check) · leak: note on a sentence that is not about facts:** U09: got test_result: 2 weeks -> 4 weeks ×6; U10: got other: prescription cream -> cosmetic product ×6; U01: got other: disappear wrinkles overnight -> helps keep skin hydrated and supports the skin's moisture barrier ×2; U09: got other: whitens in two weeks -> Participants who said skin looked more radiant after 4 weeks: 26 of 30 (87%) ×2; U07: got other: safe for pregnant women -> not specifically tested on pregnant or breastfeeding women; consult doctor ×1
- **2 agents (run 2) · facts (raw) · leak: note on a sentence that is not about facts:** U06: got other: removes acne scars -> Treats acne, acne scars, pigmentation disorders or any skin disease. ×17; U10: got other: prescription cream -> cosmetic product ×7; U09: got test_result: 2 weeks -> 4 weeks ×6; U10: got other: prescription cream -> not a medicine or prescription product ×5; U03: got other: treats acne -> Claims not approved: Treats acne, acne scars, pigmentation disorders or any skin disease. ×3
- **3 agents parallel · facts (after quote check) · catches the wrong fact:** U21: got ingredient_amount: 10% niacinamide -> 4% ×1
- **3 agents parallel · facts (raw) · catches the wrong fact:** U21: got ingredient_amount: 10% niacinamide -> 4% ×1
- **3 agents parallel · facts (after quote check) · leak: note on a sentence that is not about facts:** U10: got other: prescription cream -> cosmetic product ×9; U09: got test_result: 2 weeks -> 4 weeks ×9; U01: got other: disappear overnight -> moisturises skin and supports the skin's moisture barrier ×1; U01: got other: disappear wrinkles -> Gel-cream moisturiser that helps keep skin hydrated and supports the skin's moistu ×1; U01: got other: disappear wrinkles overnight -> helps keep skin hydrated and supports the skin's moisture barrier ×1
- **3 agents parallel · facts (raw) · leak: note on a sentence that is not about facts:** U06: got other: removes acne scars -> Treats acne, acne scars, pigmentation disorders or any skin disease. ×15; U10: got other: prescription cream -> cosmetic product ×9; U09: got test_result: 2 weeks -> 4 weeks ×9; U05: got other: Regenerates skin cells -> Claims not approved: Removes wrinkles or reverses skin ageing. Whitens skin, o ×4; U10: got other: prescription cream -> Not a medicine or a prescription product ×4
- **LLM router + 3 · facts (after quote check) · leak: note on a sentence that is not about facts:** U10: got other: prescription cream -> cosmetic product ×5; U09: got test_result: 2 weeks -> 4 weeks ×5; U09: got test_result: two weeks -> 4 weeks ×4; U09: got other: 2 weeks -> 4 weeks ×3; U01: got other: disappear wrinkles overnight -> helps keep skin hydrated and supports the skin's moisture barrier ×1
- **LLM router + 3 · facts (raw) · leak: note on a sentence that is not about facts:** U10: got other: prescription cream -> cosmetic product ×5; U10: got other: prescription cream -> Not a medicine or a prescription product ×5; U09: got test_result: 2 weeks -> 4 weeks ×5; U09: got test_result: two weeks -> 4 weeks ×4; U09: got other: 2 weeks -> 4 weeks ×3
