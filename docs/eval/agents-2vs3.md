# 2 agents vs 3 agents (utterance path) · 2026-10-02

**What is compared:**
- **2 agents (production):** one UtteranceJudge (compliance, correction, answer, prompter, switch) and the FactChecker.
- **3 agents (experiment):** a ComplianceJudge (compliance and correction), a ContextJudge (answer, prompter, switch) and the same FactChecker.
- **Same conditions:** the two judges' prompts are cut from the production judge prompt with the same wording. All agents run in parallel on `gemini-3.5-flash-lite`. Same 39 cases × 20 runs, 12 model calls in flight in both runs. Timeouts are counted apart from wrong answers.
- **Script:** `backend/scripts/eval_agents.py`.

## Accuracy (correct / answered in time)
| Check | 2 agents | 3 agents |
|---|---|---|
| judge · catches the violation (right rule) | 241/241 (100.0%) | 242/242 (100.0%) |
| judge · correction | 19/19 (100.0%) | 20/20 (100.0%) |
| judge · no alert on negated/quoted/approved wording | 110/110 (100.0%) | 119/119 (100.0%) |
| judge · leak: alert on a sentence with no compliance claim | 376/378 (99.5%) | 397/397 (100.0%) |
| judge · answer linking | 73/73 (100.0%) | 79/79 (100.0%) |
| judge · prompter points | 74/74 (100.0%) | 77/77 (100.0%) |
| judge · switch | 73/73 (100.0%) | 75/75 (100.0%) |
| facts (after quote check) · catches the wrong fact | 76/78 (97.4%) | 77/78 (98.7%) |
| facts (after quote check) · no note on a right fact | 111/111 (100.0%) | 116/116 (100.0%) |
| facts (raw) · catches the wrong fact | 76/78 (97.4%) | 77/78 (98.7%) |
| facts (raw) · no note on a right fact | 111/111 (100.0%) | 116/116 (100.0%) |
| facts (after quote check) · leak: note on a sentence that is not about facts | 532/551 (96.6%) | 537/560 (95.9%) |
| facts (raw) · leak: note on a sentence that is not about facts | 461/551 (83.7%) | 468/560 (83.6%) |

## Speed
| | 2 agents | 3 agents |
|---|---|---|
| Compliance verdict ready (red alert path) | p50 1542 · p95 1932 · max 2473 ms | p50 1196 · p95 1510 · max 2296 ms |
| Answer / prompter / switch verdict ready | p50 1542 · p95 1932 · max 2473 ms | p50 1412 · p95 1668 · max 2336 ms |
| Fact checker | p50 1336 · p95 1834 · max 2983 ms | p50 1325 · p95 1888 · max 2975 ms |
| All agents done | p50 1581 · p95 1994 · max 2983 ms | p50 1468 · p95 1928 · max 2935 ms |
| Compliance part timed out | 51/780 (6.5%) | 22/780 (2.8%) |
| Answer/prompter/switch part timed out | 51/780 (6.5%) | 27/780 (3.5%) |
| Fact checker timed out | 40/780 (5.1%) | 26/780 (3.3%) |
| Model calls per sentence | 2 | 3 |

## Wrong answers
- **2 agents · judge · leak: alert on a sentence with no compliance claim:** U21: got BRAND-SUPERLATIVE ×1; U21: got BRAND-ABSOLUTE-SAFETY ×1
- **2 agents · facts (after quote check) · catches the wrong fact:** U21: got ingredient_amount: 10% niacinamide -> 4% ×2
- **2 agents · facts (raw) · catches the wrong fact:** U21: got ingredient_amount: 10% niacinamide -> 4% ×2
- **2 agents · facts (after quote check) · leak: note on a sentence that is not about facts:** U09: got test_result: 2 weeks -> 4 weeks ×6; U10: got other: prescription cream -> cosmetic product ×6; U01: got other: disappear wrinkles overnight -> helps keep skin hydrated and supports the skin's moisture barrier ×2; U09: got other: whitens in two weeks -> Participants who said skin looked more radiant after 4 weeks: 26 of 30 (87%) ×2; U07: got other: safe for pregnant women -> not specifically tested on pregnant or breastfeeding women; consult doctor ×1
- **2 agents · facts (raw) · leak: note on a sentence that is not about facts:** U06: got other: removes acne scars -> Treats acne, acne scars, pigmentation disorders or any skin disease. ×17; U10: got other: prescription cream -> cosmetic product ×7; U09: got test_result: 2 weeks -> 4 weeks ×6; U10: got other: prescription cream -> not a medicine or prescription product ×5; U03: got other: treats acne -> Claims not approved: Treats acne, acne scars, pigmentation disorders or any skin disease. ×3
- **3 agents · facts (after quote check) · catches the wrong fact:** U21: got ingredient_amount: 10% niacinamide -> 4% ×1
- **3 agents · facts (raw) · catches the wrong fact:** U21: got ingredient_amount: 10% niacinamide -> 4% ×1
- **3 agents · facts (after quote check) · leak: note on a sentence that is not about facts:** U10: got other: prescription cream -> cosmetic product ×9; U09: got test_result: 2 weeks -> 4 weeks ×9; U01: got other: disappear overnight -> moisturises skin and supports the skin's moisture barrier ×1; U01: got other: disappear wrinkles -> Gel-cream moisturiser that helps keep skin hydrated and supports the skin's moistu ×1; U01: got other: disappear wrinkles overnight -> helps keep skin hydrated and supports the skin's moisture barrier ×1
- **3 agents · facts (raw) · leak: note on a sentence that is not about facts:** U06: got other: removes acne scars -> Treats acne, acne scars, pigmentation disorders or any skin disease. ×15; U10: got other: prescription cream -> cosmetic product ×9; U09: got test_result: 2 weeks -> 4 weeks ×9; U05: got other: Regenerates skin cells -> Claims not approved: Removes wrinkles or reverses skin ageing. Whitens skin, o ×4; U10: got other: prescription cream -> Not a medicine or a prescription product ×4

## Run order and load
- **Order:** the 3-agent run went first; the 2-agent run above went right after it.
- **Load:** Vertex AI was slower during the 2-agent run. Its warm-up timed out, and its timeouts are higher than in an earlier 2-agent run the same day.
- **Earlier 2-agent run:** saved as `agents-baseline-run1.json`. Against it, the 3-agent compliance path is still faster:

| | 2 agents (earlier run) | 3 agents |
|---|---|---|
| Compliance verdict ready | p50 1506 · p95 1826 ms | p50 1196 · p95 1510 ms |
| Compliance part timed out | 27/780 (3.5%) | 22/780 (2.8%) |
| Alert on a sentence with no compliance claim | 1/387 | 0/397 |

- **Not measured:** tokens per sentence. Three calls repeat the shared context (product, recent transcript, utterance and the instruction preamble), so the cost is higher than with two calls.
