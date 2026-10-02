# Utterance agents · split2 · 2026-10-02

- **Agents:** UtteranceJudge + FactChecker, in parallel, on `gemini-3.5-flash-lite` (thinking MINIMAL).
- **Runs:** 39 eval cases × 20 runs = 780 case runs; every run scored. Timeouts are counted apart from wrong answers.
- **Script:** `backend/scripts/eval_agents.py`. No orchestrator code; judge outputs get the production `post_validate`.

| Check | Correct / answered | Wrong | Timeout |
|---|---|---|---|
| judge · catches the violation (right rule) | 241/241 (100.0%) | 0 | 19 |
| judge · correction | 19/19 (100.0%) | 0 | 1 |
| judge · no alert on negated/quoted/approved wording | 110/110 (100.0%) | 0 | 10 |
| judge · leak: alert on a sentence with no compliance claim | 376/378 (99.5%) | 2 | 22 |
| judge · answer linking | 73/73 (100.0%) | 0 | 7 |
| judge · prompter points | 74/74 (100.0%) | 0 | 6 |
| judge · switch | 73/73 (100.0%) | 0 | 7 |
| facts (after quote check) · catches the wrong fact | 76/78 (97.4%) | 2 | 2 |
| facts (after quote check) · no note on a right fact | 111/111 (100.0%) | 0 | 9 |
| facts (raw) · catches the wrong fact | 76/78 (97.4%) | 2 | 2 |
| facts (raw) · no note on a right fact | 111/111 (100.0%) | 0 | 9 |
| facts (after quote check) · leak: note on a sentence that is not about facts | 532/551 (96.6%) | 19 | 29 |
| facts (raw) · leak: note on a sentence that is not about facts | 461/551 (83.7%) | 90 | 29 |

- **Compliance verdict ready (red alert path):** p50 1542 · p95 1932 · max 2473 ms
- **Answer / prompter / switch verdict ready:** p50 1542 · p95 1932 · max 2473 ms
- **Fact checker:** p50 1336 · p95 1834 · max 2983 ms
- **All agents done:** p50 1581 · p95 1994 · max 2983 ms
- **Timeouts:** {'compliance part': 51, 'context part': 51, 'fact checker': 40} of 780 each

## Wrong answers (case: what came back × runs)
- **judge · leak: alert on a sentence with no compliance claim:** U21: got BRAND-SUPERLATIVE ×1; U21: got BRAND-ABSOLUTE-SAFETY ×1
- **facts (after quote check) · catches the wrong fact:** U21: got ingredient_amount: 10% niacinamide -> 4% ×2
- **facts (raw) · catches the wrong fact:** U21: got ingredient_amount: 10% niacinamide -> 4% ×2
- **facts (after quote check) · leak: note on a sentence that is not about facts:** U09: got test_result: 2 weeks -> 4 weeks ×6; U10: got other: prescription cream -> cosmetic product ×6; U01: got other: disappear wrinkles overnight -> helps keep skin hydrated and supports the skin's moisture barrier ×2; U09: got other: whitens in two weeks -> Participants who said skin looked more radiant after 4 weeks: 26 of 30 (87%) ×2; U07: got other: safe for pregnant women -> not specifically tested on pregnant or breastfeeding women; consult doctor ×1; U01: got other: disappear wrinkles overnight -> Keep skin hydrated and supports the skin's moisture barrier ×1
- **facts (raw) · leak: note on a sentence that is not about facts:** U06: got other: removes acne scars -> Treats acne, acne scars, pigmentation disorders or any skin disease. ×17; U10: got other: prescription cream -> cosmetic product ×7; U09: got test_result: 2 weeks -> 4 weeks ×6; U10: got other: prescription cream -> not a medicine or prescription product ×5; U03: got other: treats acne -> Claims not approved: Treats acne, acne scars, pigmentation disorders or any skin disease.; test_result: never break out ×3; U03: got other: treats acne -> Claims not approved: Treats acne, acne scars, pigmentation disorders or any skin disease.; other: never break out again ×3
