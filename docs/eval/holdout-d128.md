# Utterance agents · split3 · 2026-10-05

- **Agents:** ComplianceJudge + ContextJudge + FactChecker in parallel (production, D-099), on `gemini-3.5-flash-lite` (thinking MINIMAL).
- **Runs:** 100 eval cases × 3 runs = 300 case runs; every run scored. Timeouts are counted apart from wrong answers.
- **Script:** `backend/scripts/eval_agents.py`; production prompts in `prompts/`, the router prompt in `backend/scripts/experiments/prompts/`. Judge outputs get the production `post_validate`.

| Check | Correct / answered | Wrong | Timeout |
|---|---|---|---|
| judge · catches the violation (right rule) | 87/87 (100.0%) | 0 | 0 |
| judge · correction | 18/18 (100.0%) | 0 | 0 |
| judge · no alert on negated/quoted/approved wording | 30/30 (100.0%) | 0 | 0 |
| judge · leak: alert on a sentence with no compliance claim | 181/183 (98.9%) | 2 | 0 |
| judge · answer linking | 69/69 (100.0%) | 0 | 0 |
| judge · prompter points | 57/57 (100.0%) | 0 | 0 |
| judge · switch | 24/24 (100.0%) | 0 | 0 |
| facts (after quote check) · catches the wrong fact | 41/42 (97.6%) | 1 | 0 |
| facts (after quote check) · no note on a right fact | 42/42 (100.0%) | 0 | 0 |
| facts (raw) · catches the wrong fact | 41/42 (97.6%) | 1 | 0 |
| facts (raw) · no note on a right fact | 42/42 (100.0%) | 0 | 0 |
| facts (after quote check) · leak: note on a sentence that is not about facts | 216/216 (100.0%) | 0 | 0 |
| facts (raw) · leak: note on a sentence that is not about facts | 184/216 (85.2%) | 32 | 0 |

- **Compliance verdict ready (red alert path):** p50 1096 · p95 1410 · max 2083 ms
- **Answer / prompter / switch verdict ready:** p50 1307 · p95 1483 · max 1891 ms
- **Fact verdict ready:** p50 1221 · p95 1783 · max 2402 ms
- **All done:** p50 1365 · p95 1783 · max 2402 ms
- **Timeouts:** none of 300 each

## Wrong answers (case: what came back × runs)
- **judge · leak: alert on a sentence with no compliance claim:** H090: [{'span': 'it helps keep skin hydrated for up to twenty-four hours', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negated': Fals ×1; H090: [{'span': 'twenty-four hours', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negated': False, 'is_quoted': False, 'say_instead':  ×1
- **facts (after quote check) · catches the wrong fact:** H052: [{'span': 'seventy percent', 'field': 'test_result', 'product_id': 'ampoule_deep_hydration', 'stated_value': '70%', 'verdict': 'contradicted', ' ×1
- **facts (raw) · catches the wrong fact:** H052: [{'span': 'seventy percent', 'field': 'test_result', 'product_id': 'ampoule_deep_hydration', 'stated_value': '70%', 'verdict': 'contradicted', ' ×1
- **facts (raw) · leak: note on a sentence that is not about facts:** H020: [{'span': 'whiten your dull skin tone and turn your complexion snow white', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_va ×2; H014: [{'span': 'to reduce puffiness and burn facial fat', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'reduce puffiness ×2; H005: [{'span': 'physically reactivates your dormant skin cells to regenerate fresh tissue', 'field': 'test_result', 'product_id': 'ampoule_deep_hydra ×1; H006: [{'span': 'fill them up and erase them completely', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'removes acne scar ×1; H007: [{'span': 'totally safe for expecting mothers', 'field': 'other', 'product_id': 'cream_hydra_barrier', 'stated_value': 'totally safe for expecti ×1; H009: [{'span': 'bleaches out stubborn melanin so your face turns fairer within days', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stat ×1
