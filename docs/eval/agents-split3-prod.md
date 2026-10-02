# Utterance agents · split3 · 2026-10-03

- **Agents:** ComplianceJudge + ContextJudge + FactChecker in parallel (production, D-099), on `gemini-3.5-flash-lite` (thinking MINIMAL).
- **Runs:** 39 eval cases × 20 runs = 780 case runs; every run scored. Timeouts are counted apart from wrong answers.
- **Script:** `backend/scripts/eval_agents.py`; production prompts in `prompts/`, the router prompt in `backend/scripts/experiments/prompts/`. Judge outputs get the production `post_validate`.

| Check | Correct / answered | Wrong | Timeout |
|---|---|---|---|
| judge · catches the violation (right rule) | 259/259 (100.0%) | 0 | 1 |
| judge · correction | 20/20 (100.0%) | 0 | 0 |
| judge · no alert on negated/quoted/approved wording | 120/120 (100.0%) | 0 | 0 |
| judge · leak: alert on a sentence with no compliance claim | 400/400 (100.0%) | 0 | 0 |
| judge · answer linking | 80/80 (100.0%) | 0 | 0 |
| judge · prompter points | 80/80 (100.0%) | 0 | 0 |
| judge · switch | 80/80 (100.0%) | 0 | 0 |
| facts (after quote check) · catches the wrong fact | 78/80 (97.5%) | 2 | 0 |
| facts (after quote check) · no note on a right fact | 120/120 (100.0%) | 0 | 0 |
| facts (raw) · catches the wrong fact | 78/80 (97.5%) | 2 | 0 |
| facts (raw) · no note on a right fact | 120/120 (100.0%) | 0 | 0 |
| facts (after quote check) · leak: note on a sentence that is not about facts | 559/579 (96.5%) | 20 | 1 |
| facts (raw) · leak: note on a sentence that is not about facts | 478/579 (82.6%) | 101 | 1 |

- **Compliance verdict ready (red alert path):** p50 1143 · p95 1390 · max 2472 ms
- **Answer / prompter / switch verdict ready:** p50 1329 · p95 1542 · max 2024 ms
- **Fact verdict ready:** p50 1241 · p95 1721 · max 2919 ms
- **All done:** p50 1389 · p95 1772 · max 2919 ms
- **Timeouts:** {'fact checker': 1, 'context part': 3, 'compliance part': 1} of 780 each

## Wrong answers (case: what came back × runs)
- **facts (after quote check) · catches the wrong fact:** U21: got ingredient_amount: 10% -> 4% ×1; U21: got ingredient_amount: 10% niacinamide -> 4% ×1
- **facts (raw) · catches the wrong fact:** U21: got ingredient_amount: 10% -> 4% ×1; U21: got ingredient_amount: 10% niacinamide -> 4% ×1
- **facts (after quote check) · leak: note on a sentence that is not about facts:** U10: got other: prescription cream -> cosmetic product ×5; U09: got test_result: 2 weeks -> 4 weeks ×4; U09: got test_result: two weeks -> 4 weeks ×4; U09: got other: 2 weeks -> 4 weeks ×2; U07: got other: safe for pregnant women -> has not been specifically tested on pregnant or breastfeeding women. Please consult your doctor before use ×1; U07: got other: safe for pregnant women -> The product has not been specifically tested on pregnant or breastfeeding women. Please consult your doctor ×1
- **facts (raw) · leak: note on a sentence that is not about facts:** U06: got other: removes acne scars -> Treats acne, acne scars, pigmentation disorders or any skin disease. ×14; U05: got other: Regenerates skin cells -> Claims not approved: Removes wrinkles or reverses skin ageing. Whitens skin, or permanently changes skin col ×7; U10: got other: prescription cream -> not a medicine or prescription product ×7; U10: got other: prescription cream -> cosmetic product ×6; U10: got other: prescription cream -> Not a medicine or a prescription product ×4; U09: got test_result: 2 weeks -> 4 weeks ×4
