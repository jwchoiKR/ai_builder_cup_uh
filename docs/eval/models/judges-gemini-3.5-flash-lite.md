# Utterance agents · split3 · 2026-10-05

- **Agents:** ComplianceJudge + ContextJudge + FactChecker in parallel (production, D-099), on `gemini-3.5-flash-lite` (thinking MINIMAL).
- **Runs:** 100 eval cases × 3 runs = 300 case runs; every run scored. Timeouts are counted apart from wrong answers.
- **Script:** `backend/scripts/eval_agents.py`; production prompts in `prompts/`, the router prompt in `backend/scripts/experiments/prompts/`. Judge outputs get the production `post_validate`.

| Check | Correct / answered | Wrong | Timeout |
|---|---|---|---|
| judge · catches the violation (right rule) | 75/75 (100.0%) | 0 | 0 |
| judge · correction | 18/18 (100.0%) | 0 | 0 |
| judge · no alert on negated/quoted/approved wording | 30/30 (100.0%) | 0 | 0 |
| judge · leak: alert on a sentence with no compliance claim | 180/195 (92.3%) | 15 | 0 |
| judge · answer linking | 69/69 (100.0%) | 0 | 0 |
| judge · prompter points | 57/57 (100.0%) | 0 | 0 |
| judge · switch | 24/24 (100.0%) | 0 | 0 |
| facts (after quote check) · catches the wrong fact | 42/42 (100.0%) | 0 | 0 |
| facts (after quote check) · no note on a right fact | 42/42 (100.0%) | 0 | 0 |
| facts (raw) · catches the wrong fact | 42/42 (100.0%) | 0 | 0 |
| facts (raw) · no note on a right fact | 42/42 (100.0%) | 0 | 0 |
| facts (after quote check) · leak: note on a sentence that is not about facts | 216/216 (100.0%) | 0 | 0 |
| facts (raw) · leak: note on a sentence that is not about facts | 183/216 (84.7%) | 33 | 0 |

- **Compliance verdict ready (red alert path):** p50 1074 · p95 1357 · max 1896 ms
- **Answer / prompter / switch verdict ready:** p50 1269 · p95 1488 · max 1862 ms
- **Fact verdict ready:** p50 1228 · p95 1750 · max 2326 ms
- **All done:** p50 1341 · p95 1750 · max 2326 ms
- **Timeouts:** none of 300 each

## Wrong answers (case: what came back × runs)
- **judge · leak: alert on a sentence with no compliance claim:** H052: [{'span': 'instant skin hydration increased by seventy percent right after one application', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MED ×3; H053: [{'span': 'Corneometer readings showed skin hydration jumped thirty-eight percent right after applying', 'rule_id': 'BRAND-TEST-QUALIFIER', 'sev ×3; H059: [{'span': 'zero out of thirty-two subjects had any adverse reaction', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negated': Fal ×3; H064: [{'span': 'forty-five percent hydration boost immediately after just one use', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_nega ×3; H090: [{'span': 'twenty-four hours', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negated': False, 'is_quoted': False, 'say_instead':  ×2; H090: [{'span': 'it helps keep skin hydrated for up to twenty-four hours', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negated': Fals ×1
- **facts (raw) · leak: note on a sentence that is not about facts:** H014: [{'span': 'to reduce puffiness and burn facial fat', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'reduce puffiness ×3; H024: [{'span': 'you can even put this safely on newborn babies and toddlers', 'field': 'other', 'product_id': 'cream_hydra_barrier', 'stated_value':  ×2; H016: [{'span': 'stop your skin ageing process in its tracks', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'stops skin a ×2; H005: [{'span': 'reactivates your dormant skin cells to regenerate fresh tissue', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_va ×1; H006: [{'span': 'fill them up and erase them completely', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'Treats acne, acne ×1; H007: [{'span': 'totally safe for expecting mothers', 'field': 'other', 'product_id': 'cream_hydra_barrier', 'stated_value': 'totally safe', 'verdict' ×1
