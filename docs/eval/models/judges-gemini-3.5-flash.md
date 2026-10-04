# Utterance agents · split3 · 2026-10-05

- **Agents:** ComplianceJudge + ContextJudge + FactChecker in parallel (production, D-099), on `gemini-3.5-flash` (thinking MINIMAL).
- **Runs:** 100 eval cases × 3 runs = 300 case runs; every run scored. Timeouts are counted apart from wrong answers.
- **Script:** `backend/scripts/eval_agents.py`; production prompts in `prompts/`, the router prompt in `backend/scripts/experiments/prompts/`. Judge outputs get the production `post_validate`.

| Check | Correct / answered | Wrong | Timeout |
|---|---|---|---|
| judge · catches the violation (right rule) | 75/75 (100.0%) | 0 | 0 |
| judge · correction | 18/18 (100.0%) | 0 | 0 |
| judge · no alert on negated/quoted/approved wording | 30/30 (100.0%) | 0 | 0 |
| judge · leak: alert on a sentence with no compliance claim | 179/193 (92.7%) | 14 | 2 |
| judge · answer linking | 69/69 (100.0%) | 0 | 0 |
| judge · prompter points | 57/57 (100.0%) | 0 | 0 |
| judge · switch | 24/24 (100.0%) | 0 | 0 |
| facts (after quote check) · catches the wrong fact | 39/42 (92.9%) | 3 | 0 |
| facts (after quote check) · no note on a right fact | 42/42 (100.0%) | 0 | 0 |
| facts (raw) · catches the wrong fact | 39/42 (92.9%) | 3 | 0 |
| facts (raw) · no note on a right fact | 42/42 (100.0%) | 0 | 0 |
| facts (after quote check) · leak: note on a sentence that is not about facts | 211/215 (98.1%) | 4 | 1 |
| facts (raw) · leak: note on a sentence that is not about facts | 179/215 (83.3%) | 36 | 1 |

- **Compliance verdict ready (red alert path):** p50 1457 · p95 1819 · max 2211 ms
- **Answer / prompter / switch verdict ready:** p50 1579 · p95 1905 · max 2397 ms
- **Fact verdict ready:** p50 1671 · p95 2305 · max 2837 ms
- **All done:** p50 1749 · p95 2346 · max 2837 ms
- **Timeouts:** {'fact checker': 1, 'compliance part': 2} of 300 each

## Wrong answers (case: what came back × runs)
- **judge · leak: alert on a sentence with no compliance claim:** H053: [{'span': 'skin hydration jumped thirty-eight percent right after applying', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negate ×3; H059: [{'span': 'zero out of thirty-two subjects had any adverse reaction', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negated': Fal ×3; H064: [{'span': 'forty-five percent hydration boost immediately after just one use', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_nega ×3; H052: [{'span': 'instant skin hydration increased by seventy percent right after one application', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MED ×2; H090: [{'span': 'twenty-four hours', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negated': False, 'is_quoted': False, 'say_instead':  ×2; H052: [{'span': 'increased by seventy percent right after one application', 'rule_id': 'BRAND-TEST-QUALIFIER', 'severity': 'MEDIUM', 'is_negated': Fal ×1
- **facts (after quote check) · catches the wrong fact:** H078: [{'span': 'this opened jar', 'field': 'packaging', 'product_id': 'cream_hydra_barrier', 'stated_value': 'jar', 'verdict': 'contradicted', 'corre ×2; H078: [{'span': 'opened jar', 'field': 'packaging', 'product_id': 'cream_hydra_barrier', 'stated_value': 'jar', 'verdict': 'contradicted', 'correct_va ×1
- **facts (raw) · catches the wrong fact:** H078: [{'span': 'this opened jar', 'field': 'packaging', 'product_id': 'cream_hydra_barrier', 'stated_value': 'jar', 'verdict': 'contradicted', 'corre ×2; H078: [{'span': 'opened jar', 'field': 'packaging', 'product_id': 'cream_hydra_barrier', 'stated_value': 'jar', 'verdict': 'contradicted', 'correct_va ×1
- **facts (after quote check) · leak: note on a sentence that is not about facts:** H034: [{'span': 'rich texture', 'field': 'texture', 'product_id': 'cream_hydra_barrier', 'stated_value': 'rich texture', 'verdict': 'contradicted', 'c ×2; H024: [{'span': 'put this safely on newborn babies and toddlers', 'field': 'usage', 'product_id': 'cream_hydra_barrier', 'stated_value': 'safely use o ×1; H034: [{'span': 'rich texture', 'field': 'texture', 'product_id': 'cream_hydra_barrier', 'stated_value': 'rich texture', 'verdict': 'contradicted', 'c ×1
- **facts (raw) · leak: note on a sentence that is not about facts:** H034: [{'span': 'rich texture', 'field': 'texture', 'product_id': 'cream_hydra_barrier', 'stated_value': 'rich texture', 'verdict': 'contradicted', 'c ×2; H001: [{'span': 'completely cures the inflammation', 'field': 'other', 'product_id': 'cream_hydra_barrier', 'stated_value': 'cures inflammation / ecze ×1; H004: [{'span': 'the moisture retention is permanent', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'permanent results',  ×1; H005: [{'span': 'reactivates your dormant skin cells to regenerate fresh tissue', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_va ×1; H006: [{'span': 'this serum will fill them up and erase them completely', 'field': 'other', 'product_id': 'ampoule_deep_hydration', 'stated_value': 'e ×1; H007: [{'span': 'totally safe for expecting mothers', 'field': 'other', 'product_id': 'cream_hydra_barrier', 'stated_value': 'safe during pregnancy',  ×1
