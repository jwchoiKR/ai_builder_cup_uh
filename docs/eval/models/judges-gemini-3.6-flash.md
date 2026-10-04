# Utterance agents · split3 · 2026-10-05

- **Agents:** ComplianceJudge + ContextJudge + FactChecker in parallel (production, D-099), on `gemini-3.6-flash` (thinking MINIMAL).
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
| facts (after quote check) · catches the wrong fact | 39/42 (92.9%) | 3 | 0 |
| facts (after quote check) · no note on a right fact | 41/41 (100.0%) | 0 | 1 |
| facts (raw) · catches the wrong fact | 39/42 (92.9%) | 3 | 0 |
| facts (raw) · no note on a right fact | 41/41 (100.0%) | 0 | 1 |
| facts (after quote check) · leak: note on a sentence that is not about facts | 211/214 (98.6%) | 3 | 2 |
| facts (raw) · leak: note on a sentence that is not about facts | 211/214 (98.6%) | 3 | 2 |

- **Compliance verdict ready (red alert path):** p50 1568 · p95 1884 · max 2181 ms
- **Answer / prompter / switch verdict ready:** p50 1780 · p95 2049 · max 2405 ms
- **Fact verdict ready:** p50 1719 · p95 2637 · max 2975 ms
- **All done:** p50 1888 · p95 2637 · max 2975 ms
- **Timeouts:** {'context part': 1, 'fact checker': 3} of 300 each

## Wrong answers (case: what came back × runs)
- **judge · leak: alert on a sentence with no compliance claim:** H052: [{'span': 'instant skin hydration increased by seventy percent right after one application', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MED ×3; H053: [{'span': 'skin hydration jumped thirty-eight percent right after applying', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negate ×3; H059: [{'span': 'zero out of thirty-two subjects had any adverse reaction', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negated': Fal ×3; H064: [{'span': 'forty-five percent hydration boost immediately after just one use', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_nega ×3; H090: [{'span': 'twenty-four hours', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negated': False, 'is_quoted': False, 'say_instead':  ×2; H090: [{'span': 'helps keep skin hydrated for up to twenty-four hours', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negated': False,  ×1
- **facts (after quote check) · catches the wrong fact:** H078: [{'span': 'shelf life, you can safely store and use this opened jar for five whole years', 'field': 'shelf_life', 'product_id': 'cream_hydra_bar ×1; H078: [{'span': 'opened jar for five whole years', 'field': 'shelf_life', 'product_id': 'cream_hydra_barrier', 'stated_value': '5 years after opening' ×1; H078: [{'span': 'opened jar', 'field': 'packaging', 'product_id': 'cream_hydra_barrier', 'stated_value': 'jar', 'verdict': 'contradicted', 'correct_va ×1
- **facts (raw) · catches the wrong fact:** H078: [{'span': 'shelf life, you can safely store and use this opened jar for five whole years', 'field': 'shelf_life', 'product_id': 'cream_hydra_bar ×1; H078: [{'span': 'opened jar for five whole years', 'field': 'shelf_life', 'product_id': 'cream_hydra_barrier', 'stated_value': '5 years after opening' ×1; H078: [{'span': 'opened jar', 'field': 'packaging', 'product_id': 'cream_hydra_barrier', 'stated_value': 'jar', 'verdict': 'contradicted', 'correct_va ×1
- **facts (after quote check) · leak: note on a sentence that is not about facts:** H034: [{'span': 'rich texture', 'field': 'texture', 'product_id': 'cream_hydra_barrier', 'stated_value': 'rich texture', 'verdict': 'contradicted', 'c ×1; H034: [{'span': 'rich texture', 'field': 'texture', 'product_id': 'cream_hydra_barrier', 'stated_value': 'rich texture', 'verdict': 'contradicted', 'c ×1; H034: [{'span': 'rich texture', 'field': 'texture', 'product_id': 'cream_hydra_barrier', 'stated_value': 'rich texture', 'verdict': 'contradicted', 'c ×1
- **facts (raw) · leak: note on a sentence that is not about facts:** H034: [{'span': 'rich texture', 'field': 'texture', 'product_id': 'cream_hydra_barrier', 'stated_value': 'rich texture', 'verdict': 'contradicted', 'c ×1; H034: [{'span': 'rich texture', 'field': 'texture', 'product_id': 'cream_hydra_barrier', 'stated_value': 'rich texture', 'verdict': 'contradicted', 'c ×1; H034: [{'span': 'rich texture', 'field': 'texture', 'product_id': 'cream_hydra_barrier', 'stated_value': 'rich texture', 'verdict': 'contradicted', 'c ×1
