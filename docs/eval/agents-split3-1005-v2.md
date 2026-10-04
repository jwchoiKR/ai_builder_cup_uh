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
| judge · answer linking | 27/27 (100.0%) | 0 | 0 |
| judge · prompter points | 12/12 (100.0%) | 0 | 0 |
| judge · switch | 12/12 (100.0%) | 0 | 0 |
| facts (after quote check) · catches the wrong fact | 12/12 (100.0%) | 0 | 0 |
| facts (after quote check) · no note on a right fact | 18/18 (100.0%) | 0 | 0 |
| facts (raw) · catches the wrong fact | 12/12 (100.0%) | 0 | 0 |
| facts (raw) · no note on a right fact | 18/18 (100.0%) | 0 | 0 |
| facts (after quote check) · leak: note on a sentence that is not about facts | 86/86 (100.0%) | 0 | 1 |
| facts (raw) · leak: note on a sentence that is not about facts | 79/86 (91.9%) | 7 | 1 |

- **Compliance verdict ready (red alert path):** p50 1141 · p95 1465 · max 1610 ms
- **Answer / prompter / switch verdict ready:** p50 1345 · p95 1657 · max 1929 ms
- **Fact verdict ready:** p50 1259 · p95 1794 · max 2403 ms
- **All done:** p50 1379 · p95 1807 · max 2403 ms
- **Timeouts:** {'fact checker': 1} of 117 each

## Wrong answers (case: what came back × runs)
- **facts (raw) · leak: note on a sentence that is not about facts:** U09: [{'span': 'It whitens your skin in two weeks', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'Whitens skin in two wee ×1; U06: [{'span': 'removes your old acne scars', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'removes your old acne scars', ×1; U09: [{'span': 'whitens your skin', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'whitens skin', 'verdict': 'contradicted ×1; U11: [{'span': "You'll look ten years younger after one bottle", 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'ten years  ×1; U06: [{'span': 'removes your old acne scars', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'removes old acne scars', 'ver ×1; U09: [{'span': 'whitens your skin in two weeks', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'whitens your skin in two w ×1
