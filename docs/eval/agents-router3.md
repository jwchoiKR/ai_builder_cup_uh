# Utterance agents · router3 · 2026-10-02

- **Agents:** LLM router first, then only the chosen of ComplianceJudge / ContextJudge / FactChecker in parallel (experiment), on `gemini-3.5-flash-lite` (thinking MINIMAL).
- **Runs:** 39 eval cases × 20 runs = 780 case runs; every run scored. Timeouts are counted apart from wrong answers.
- **Script:** `backend/scripts/eval_agents.py`; experiment prompts in `backend/scripts/experiments/prompts/`. Judge outputs get the production `post_validate`.

| Check | Correct / answered | Wrong | Timeout |
|---|---|---|---|
| judge · catches the violation (right rule) | 247/247 (100.0%) | 0 | 13 |
| judge · correction | 20/20 (100.0%) | 0 | 0 |
| judge · no alert on negated/quoted/approved wording | 120/120 (100.0%) | 0 | 0 |
| judge · leak: alert on a sentence with no compliance claim | 400/400 (100.0%) | 0 | 0 |
| judge · answer linking | 80/80 (100.0%) | 0 | 0 |
| judge · prompter points | 80/80 (100.0%) | 0 | 0 |
| judge · switch | 80/80 (100.0%) | 0 | 0 |
| facts (after quote check) · catches the wrong fact | 80/80 (100.0%) | 0 | 0 |
| facts (after quote check) · no note on a right fact | 120/120 (100.0%) | 0 | 0 |
| facts (raw) · catches the wrong fact | 80/80 (100.0%) | 0 | 0 |
| facts (raw) · no note on a right fact | 120/120 (100.0%) | 0 | 0 |
| facts (after quote check) · leak: note on a sentence that is not about facts | 551/571 (96.5%) | 20 | 9 |
| facts (raw) · leak: note on a sentence that is not about facts | 538/571 (94.2%) | 33 | 9 |

- **Compliance verdict ready (red alert path):** p50 1990 · p95 2384 · max 2765 ms
- **Answer / prompter / switch verdict ready:** p50 2325 · p95 2593 · max 3394 ms
- **Fact verdict ready:** p50 2085 · p95 2721 · max 4415 ms
- **All done:** p50 2369 · p95 2755 · max 3690 ms
- **Timeouts:** {'compliance part': 13, 'context part': 12, 'fact checker': 9} of 780 each
- **Router:** p50 985 · p95 1161 · max 1326 ms; timed out 12/780 (then every specialist runs)
- **Model calls per sentence:** 3.13 (router included)
- **Specialist chosen:** compliance 444/780, context 780/780, facts 439/780
- **Needed specialist not chosen (case × runs):** none

## Wrong answers (case: what came back × runs)
- **facts (after quote check) · leak: note on a sentence that is not about facts:** U10: got other: prescription cream -> cosmetic product ×5; U09: got test_result: 2 weeks -> 4 weeks ×5; U09: got test_result: two weeks -> 4 weeks ×4; U09: got other: 2 weeks -> 4 weeks ×3; U01: got other: disappear wrinkles overnight -> helps keep skin hydrated and supports the skin's moisture barrier ×1; U09: got other: whitens in two weeks -> Participants who said skin looked more radiant after 4 weeks: 26 of 30 (87%) ×1
- **facts (raw) · leak: note on a sentence that is not about facts:** U10: got other: prescription cream -> cosmetic product ×5; U10: got other: prescription cream -> Not a medicine or a prescription product ×5; U09: got test_result: 2 weeks -> 4 weeks ×5; U09: got test_result: two weeks -> 4 weeks ×4; U09: got other: 2 weeks -> 4 weeks ×3; U10: got other: prescription cream -> not a medicine or prescription product ×2
