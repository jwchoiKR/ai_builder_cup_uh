# Utterance agents · split3 · 2026-10-05

- **Agents:** ComplianceJudge + ContextJudge + FactChecker in parallel (production, D-099), on `gemini-3.1-flash-lite` (thinking MINIMAL).
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
| facts (after quote check) · catches the wrong fact | 35/42 (83.3%) | 7 | 0 |
| facts (after quote check) · no note on a right fact | 42/42 (100.0%) | 0 | 0 |
| facts (raw) · catches the wrong fact | 35/42 (83.3%) | 7 | 0 |
| facts (raw) · no note on a right fact | 42/42 (100.0%) | 0 | 0 |
| facts (after quote check) · leak: note on a sentence that is not about facts | 213/216 (98.6%) | 3 | 0 |
| facts (raw) · leak: note on a sentence that is not about facts | 151/216 (69.9%) | 65 | 0 |

- **Compliance verdict ready (red alert path):** p50 1785 · p95 2208 · max 2431 ms
- **Answer / prompter / switch verdict ready:** p50 1872 · p95 2194 · max 2428 ms
- **Fact verdict ready:** p50 1933 · p95 2571 · max 2940 ms
- **All done:** p50 2076 · p95 2571 · max 2940 ms
- **Timeouts:** {'context part': 2} of 300 each

## Wrong answers (case: what came back × runs)
- **judge · leak: alert on a sentence with no compliance claim:** H059: [{'span': 'zero out of thirty-two subjects had any adverse reaction', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negated': Fal ×3; H064: [{'span': 'forty-five percent hydration boost', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negated': False, 'is_quoted': False ×3; H053: [{'span': 'Corneometer readings showed skin hydration jumped thirty-eight percent right after applying', 'rule_id': 'BRAND-TEST-QUALIFIER', 'sev ×2; H052: [{'span': 'instant skin hydration increased by seventy percent right after one application', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MED ×2; H052: [{'span': 'In clinical corneometer tests, instant skin hydration increased by seventy percent right after one application', 'rule_id': 'BRAND-TE ×1; H078: [{'span': 'safely store and use this opened jar for five whole years', 'rule_id': 'BRAND-ABSOLUTE-SAFETY', 'severity': 'MEDIUM', 'is_negated': F ×1
- **facts (after quote check) · catches the wrong fact:** H052: [{'span': 'seventy percent', 'field': 'test_result', 'product_id': 'ampoule_deep_hydration', 'stated_value': '70%', 'verdict': 'contradicted', ' ×1; H078: [{'span': 'this opened jar', 'field': 'packaging', 'product_id': 'cream_hydra_barrier', 'stated_value': 'jar', 'verdict': 'contradicted', 'corre ×1; H046: [{'span': 'fifty dollars flat', 'field': 'set_price', 'product_id': 'set_cream_ampoule', 'stated_value': 'S$50', 'verdict': 'contradicted', 'cor ×1; H052: [{'span': 'seventy percent', 'field': 'test_result', 'product_id': 'ampoule_deep_hydration', 'stated_value': '70%', 'verdict': 'contradicted', ' ×1; H078: [{'span': 'five whole years', 'field': 'shelf_life', 'product_id': 'cream_hydra_barrier', 'stated_value': '5 years', 'verdict': 'contradicted',  ×1; H052: [{'span': 'instant skin hydration increased by seventy percent right after one application', 'field': 'test_result', 'product_id': 'ampoule_deep ×1
- **facts (raw) · catches the wrong fact:** H052: [{'span': 'seventy percent', 'field': 'test_result', 'product_id': 'ampoule_deep_hydration', 'stated_value': '70%', 'verdict': 'contradicted', ' ×1; H078: [{'span': 'this opened jar', 'field': 'packaging', 'product_id': 'cream_hydra_barrier', 'stated_value': 'jar', 'verdict': 'contradicted', 'corre ×1; H046: [{'span': 'fifty dollars flat', 'field': 'set_price', 'product_id': 'set_cream_ampoule', 'stated_value': 'S$50', 'verdict': 'contradicted', 'cor ×1; H052: [{'span': 'seventy percent', 'field': 'test_result', 'product_id': 'ampoule_deep_hydration', 'stated_value': '70%', 'verdict': 'contradicted', ' ×1; H078: [{'span': 'five whole years', 'field': 'shelf_life', 'product_id': 'cream_hydra_barrier', 'stated_value': '5 years', 'verdict': 'contradicted',  ×1; H052: [{'span': 'instant skin hydration increased by seventy percent right after one application', 'field': 'test_result', 'product_id': 'ampoule_deep ×1
- **facts (after quote check) · leak: note on a sentence that is not about facts:** H034: [{'span': 'rich texture', 'field': 'texture', 'product_id': 'cream_hydra_barrier', 'stated_value': 'rich', 'verdict': 'contradicted', 'correct_v ×3
- **facts (raw) · leak: note on a sentence that is not about facts:** H034: [{'span': 'rich texture', 'field': 'texture', 'product_id': 'cream_hydra_barrier', 'stated_value': 'rich', 'verdict': 'contradicted', 'correct_v ×3; H004: [{'span': 'moisture retention is permanent', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'permanent', 'verdict': ' ×2; H010: [{'span': 'pharmaceutical strength relief', 'field': 'other', 'product_id': 'cream_hydra_barrier', 'stated_value': 'pharmaceutical strength', 'v ×2; H015: [{'span': 'cure the chronic lesion', 'field': 'other', 'product_id': 'cream_hydra_barrier', 'stated_value': 'cure psoriasis', 'verdict': 'contra ×2; H006: [{'span': 'this serum will fill them up and erase them completely', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'e ×2; H001: [{'span': 'completely cures the inflammation', 'field': 'other', 'product_id': 'cream_hydra_barrier', 'stated_value': 'cures inflammation', 'ver ×1
