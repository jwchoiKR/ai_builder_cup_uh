# Utterance agents · split3 · 2026-10-05

- **Agents:** ComplianceJudge + ContextJudge + FactChecker in parallel (production, D-099), on `gemini-3.5-flash-lite` (thinking MINIMAL).
- **Runs:** 39 eval cases × 3 runs = 117 case runs; every run scored. Timeouts are counted apart from wrong answers.
- **Script:** `backend/scripts/eval_agents.py`; production prompts in `prompts/`, the router prompt in `backend/scripts/experiments/prompts/`. Judge outputs get the production `post_validate`.

| Check | Correct / answered | Wrong | Timeout |
|---|---|---|---|
| judge · catches the violation (right rule) | 39/39 (100.0%) | 0 | 0 |
| judge · correction | 3/3 (100.0%) | 0 | 0 |
| judge · no alert on negated/quoted/approved wording | 18/18 (100.0%) | 0 | 0 |
| judge · leak: alert on a sentence with no compliance claim | 60/60 (100.0%) | 0 | 0 |
| judge · answer linking | 24/27 (88.9%) | 3 | 0 |
| judge · prompter points | 12/12 (100.0%) | 0 | 0 |
| judge · switch | 12/12 (100.0%) | 0 | 0 |
| facts (after quote check) · catches the wrong fact | 12/12 (100.0%) | 0 | 0 |
| facts (after quote check) · no note on a right fact | 18/18 (100.0%) | 0 | 0 |
| facts (raw) · catches the wrong fact | 12/12 (100.0%) | 0 | 0 |
| facts (raw) · no note on a right fact | 18/18 (100.0%) | 0 | 0 |
| facts (after quote check) · leak: note on a sentence that is not about facts | 87/87 (100.0%) | 0 | 0 |
| facts (raw) · leak: note on a sentence that is not about facts | 69/87 (79.3%) | 18 | 0 |

- **Compliance verdict ready (red alert path):** p50 1058 · p95 1326 · max 2309 ms
- **Answer / prompter / switch verdict ready:** p50 1258 · p95 1429 · max 1521 ms
- **Fact verdict ready:** p50 1187 · p95 1544 · max 1833 ms
- **All done:** p50 1287 · p95 1581 · max 2309 ms
- **Timeouts:** none of 117 each

## Wrong answers (case: what came back × runs)
- **judge · answer linking:** U29: matched_group_id=None ×3
- **facts (raw) · leak: note on a sentence that is not about facts:** U04: [{'span': 'the results are permanent', 'field': 'other', 'product_id': 'cream_hydra_barrier', 'stated_value': 'permanent results', 'verdict': 'co ×2; U06: [{'span': 'removes your old acne scars', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'removes acne scars', 'verdict ×2; U09: [{'span': 'It whitens your skin in two weeks', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'whitens skin in two wee ×2; U01: [{'span': 'your wrinkles will disappear overnight', 'field': 'test_result', 'product_id': 'cream_hydra_barrier', 'stated_value': 'removes wrinkle ×1; U05: [{'span': 'It regenerates your skin cells from the inside', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'regenerate ×1; U07: [{'span': 'totally safe for pregnant women', 'field': 'other', 'product_id': 'cream_hydra_barrier', 'stated_value': 'safe during pregnancy', 'ver ×1
