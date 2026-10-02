# Utterance agents · split3 · 2026-10-02

- **Agents:** ComplianceJudge + ContextJudge + FactChecker (experiment prompts in scripts/experiments/prompts/), in parallel, on `gemini-3.5-flash-lite` (thinking MINIMAL).
- **Runs:** 39 eval cases × 20 runs = 780 case runs; every run scored. Timeouts are counted apart from wrong answers.
- **Script:** `backend/scripts/eval_agents.py`. No orchestrator code; judge outputs get the production `post_validate`.

| Check | Correct / answered | Wrong | Timeout |
|---|---|---|---|
| judge · catches the violation (right rule) | 242/242 (100.0%) | 0 | 18 |
| judge · correction | 20/20 (100.0%) | 0 | 0 |
| judge · no alert on negated/quoted/approved wording | 119/119 (100.0%) | 0 | 1 |
| judge · leak: alert on a sentence with no compliance claim | 397/397 (100.0%) | 0 | 3 |
| judge · answer linking | 79/79 (100.0%) | 0 | 1 |
| judge · prompter points | 77/77 (100.0%) | 0 | 3 |
| judge · switch | 75/75 (100.0%) | 0 | 5 |
| facts (after quote check) · catches the wrong fact | 77/78 (98.7%) | 1 | 2 |
| facts (after quote check) · no note on a right fact | 116/116 (100.0%) | 0 | 4 |
| facts (raw) · catches the wrong fact | 77/78 (98.7%) | 1 | 2 |
| facts (raw) · no note on a right fact | 116/116 (100.0%) | 0 | 4 |
| facts (after quote check) · leak: note on a sentence that is not about facts | 537/560 (95.9%) | 23 | 20 |
| facts (raw) · leak: note on a sentence that is not about facts | 468/560 (83.6%) | 92 | 20 |

- **Compliance verdict ready (red alert path):** p50 1196 · p95 1510 · max 2296 ms
- **Answer / prompter / switch verdict ready:** p50 1412 · p95 1668 · max 2336 ms
- **Fact checker:** p50 1325 · p95 1888 · max 2975 ms
- **All agents done:** p50 1468 · p95 1928 · max 2935 ms
- **Timeouts:** {'fact checker': 26, 'compliance part': 22, 'context part': 27} of 780 each

## Wrong answers (case: what came back × runs)
- **facts (after quote check) · catches the wrong fact:** U21: got ingredient_amount: 10% niacinamide -> 4% ×1
- **facts (raw) · catches the wrong fact:** U21: got ingredient_amount: 10% niacinamide -> 4% ×1
- **facts (after quote check) · leak: note on a sentence that is not about facts:** U10: got other: prescription cream -> cosmetic product ×9; U09: got test_result: 2 weeks -> 4 weeks ×9; U01: got other: disappear overnight -> moisturises skin and supports the skin's moisture barrier ×1; U01: got other: disappear wrinkles -> Gel-cream moisturiser that helps keep skin hydrated and supports the skin's moisture barrier ×1; U01: got other: disappear wrinkles overnight -> helps keep skin hydrated and supports the skin's moisture barrier ×1; U09: got test_result: two weeks -> 4 weeks ×1
- **facts (raw) · leak: note on a sentence that is not about facts:** U06: got other: removes acne scars -> Treats acne, acne scars, pigmentation disorders or any skin disease. ×15; U10: got other: prescription cream -> cosmetic product ×9; U09: got test_result: 2 weeks -> 4 weeks ×9; U05: got other: Regenerates skin cells -> Claims not approved: Removes wrinkles or reverses skin ageing. Whitens skin, or permanently changes skin col ×4; U10: got other: prescription cream -> Not a medicine or a prescription product ×4; U03: got other: treats acne -> Claims not approved: Removes wrinkles or reverses skin ageing. Whitens skin, or permanently changes skin colour. Treats ×3
